"""Opt-in, uncalibrated input-error propagation through the shared NumPy fit.

Not a posterior sampler or an anatomical confidence estimator. Each draw refits
similarity pose, identity, Huber weights and optionally lambda. Marker-only
statistical fitting; no dense constraints, craniometry loss or local TPS.
"""
import argparse
import copy
import json
import math
from pathlib import Path

import numpy as np

from .fit_contract import DEFAULT_MAX_ITER, DEFAULT_TOL, HUBER_K_MM
from .identity import active_components
from .optimize import LossConfig, fit_identity
from .validation import finite_array, has_documented_tissue_source, validate_points


def placement_config(document: dict, labels: list[str]) -> dict:
    """Validate per-coordinate isotropic placement SDs, without filling unknowns.

    SD is NOT a 3-D repeat-placement distance or its standard deviation. Conversion
    from repeat-session data needs a separately justified statistical model.
    """
    if not isinstance(document, dict) or set(document) != {'schema_version', 'placement'}:
        raise ValueError('Placement config requires only schema_version and placement')
    if type(document['schema_version']) is not int or document['schema_version'] != 1:
        raise ValueError('Unsupported placement config schema_version')
    rows = document['placement']
    if not isinstance(rows, dict) or set(rows) - set(labels):
        raise ValueError('Placement contains unknown or excluded marker labels')
    result = {}
    for label in labels:
        row = rows.get(label, {'sigma_mm': None, 'source': None})
        if not isinstance(row, dict) or set(row) != {'sigma_mm', 'source'}:
            raise ValueError(f'{label}: placement requires sigma_mm and source')
        sigma, source = row['sigma_mm'], row['source']
        if sigma is not None:
            try:
                valid = type(sigma) in (int, float) and math.isfinite(sigma) and sigma >= 0
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError(f'{label}: sigma_mm must be finite and nonnegative, or null')
            if not has_documented_tissue_source(source):
                raise ValueError(f'{label}: configured placement SD requires a source/assumption statement')
        if source is not None and not isinstance(source, str):
            raise ValueError(f'{label}: placement source must be text or null')
        result[label] = copy.deepcopy(row)
    return result


def _truncated_depths(rng, location, sd, samples):
    """Sample N(location, sd) conditional on depth >= 0 by rejection, not clipping.

    location >= 0 guarantees acceptance probability >= 1/2. The finite iteration
    guard protects execution; it is not an anatomical threshold. Supplied values
    describe the UNTRUNCATED parent, not the resulting distribution's moments.
    """
    values = np.broadcast_to(location, (samples, len(location))).copy()
    active = sd > 0
    if active.any():
        draw = rng.normal(location[active], sd[active], size=(samples, int(active.sum())))
        for _ in range(1000):
            reject = draw < 0
            if not reject.any():
                break
            _, columns = np.nonzero(reject)
            draw[reject] = rng.normal(location[active][columns], sd[active][columns])
        else:
            raise RuntimeError('Truncated-normal rejection sampler failed to finish')
        values[:, active] = draw
    return finite_array(values, 'sampled depths')


def _fit_record(result):
    """Replayable numeric output and convergence/clipping diagnostics."""
    d = result.info.diagnostics
    return dict(coefficients=result.coefficients.tolist(), scale=result.scale,
                rotation=result.rotation.tolist(), translation_mm=result.translation.tolist(),
                regularization=result.regularization, residuals_mm=result.residuals_mm.tolist(),
                converged=d['converged'], stop_reason=d['stop_reason'], iterations=d['iterations'],
                last_iteration_change=d['iteration_records'][-1],
                clipped_active_count=d['identity_fit']['clipped_active_count'],
                condition_number=d['least_squares']['condition_number'],
                final_irls_weights=d['final_irls_weights'], identity_fit=d['identity_fit'])


def monte_carlo_identity(model, targets, metadata, *, placement=None, samples=200, seed=0,
                         allow_partial=False, table=None, depth_labels=(), axis_policy='unconfigured',
                         directions=None, regularization=30.0, identity_subspace='all',
                         prior=None, prior_variants=('off',), max_iter=DEFAULT_MAX_ITER) -> dict:
    """Refit paired, seeded perturbations without modifying caller inputs.

    Coordinates/errors are world mm. Placement independently translates bone/skin
    endpoint pairs while keeping axes fixed. Depth sampling explicitly selects
    table labels. Missing requested SDs fail unless allow_partial; null terms are
    then held fixed, listed as omitted and never relabelled zero/calibrated.
    At least one SD must be supplied. Prior scenarios share draws, never pooled.

    Returns JSON-compatible replay records, not meshes (A2.2) or coverage (A2.4).
    """
    if type(samples) is not int or samples < 2 or type(seed) is not int or seed < 0:
        raise ValueError('samples must be an integer >= 2; seed a nonnegative integer')
    if type(max_iter) is not int or max_iter < 1:
        raise ValueError('max_iter must be a positive integer')
    if type(allow_partial) is not bool:
        raise ValueError('allow_partial must be boolean')
    if not isinstance(metadata, dict):
        raise ValueError('Marker metadata must be an object')
    if not isinstance(prior_variants, (list, tuple)):
        raise ValueError('prior_variants must be a list/tuple')
    variants = tuple(prior_variants)
    if not variants or any(v not in ('off', 'on') for v in variants) or len(set(variants)) != len(variants):
        raise ValueError('prior_variants must contain distinct off/on choices')
    if ('on' in variants) != (prior is not None):
        raise ValueError('Supply a prior exactly when an on variant is requested')
    if prior is not None and (not isinstance(prior, dict) or not {'mean', 'scale'} <= set(prior)):
        raise ValueError('Prior requires mean and scale')
    labels = [t.label for t in targets]
    indices = np.asarray([t.vertex for t in targets])
    if (any(not isinstance(s, str) or not s.strip() for s in labels) or len(set(labels)) != len(labels)
            or len(np.unique(indices)) != len(indices)):
        raise ValueError('Distinct nonempty labels and distinct vertices are required')
    original = validate_points([t.xyz for t in targets], 'original targets')
    weights = finite_array([t.weight for t in targets], 'weights', (len(targets),))
    config = placement_config(placement if placement is not None else
                              dict(schema_version=1, placement={}), labels)
    if (not isinstance(depth_labels, (list, tuple)) or any(not isinstance(x, str) for x in depth_labels)
            or len(set(depth_labels)) != len(depth_labels)):
        raise ValueError('depth_labels must be a distinct list/tuple of labels')
    if depth_labels and table is None:
        raise ValueError('Depth sampling requires an explicit tissue table')
    if directions is not None and axis_policy != 'source':
        raise ValueError('Direction manifest requires source-axis mode')
    if not depth_labels and (table is not None or directions is not None or axis_policy != 'unconfigured'):
        raise ValueError('Table/direction options require explicit depth_labels')
    active = active_components(model, identity_subspace)
    planned, application = targets, None
    if depth_labels:
        from .tissue_application import apply_table
        planned, _, application = apply_table(targets, metadata, table, depth_labels, axis_policy, directions)
    central = finite_array([t.xyz for t in planned], 'central targets', original.shape)
    missing = [f'placement:{label}' for label in labels if config[label]['sigma_mm'] is None]
    warnings = ['Uncalibrated input-error propagation; not posterior or facial-accuracy confidence.',
                'Independent isotropic placement and independent depth errors are modelling assumptions; '
                'axes, correspondences, skull geometry and model basis are held fixed.',
                'Marker-only statistical fit: no dense rows, craniometry constraints or local TPS correction.']
    if not depth_labels:
        warnings.append('Depth variation not requested: all recorded skin depths/targets held fixed.')
    rows = {} if table is None else table.document['landmarks']
    depth_rows = []
    for label in depth_labels:
        row = rows[label]
        if row['sd_mm'] is None:
            missing.append(f'depth:{label}')
        elif row['estimator'] != 'mean':
            raise ValueError(f'{label}: Gaussian depth sampling requires a supplied mean; '
                             'median/shorth/75-shormax/unknown are not converted to means')
        depth_rows.append(dict(label=label, parent_location_mm=row['central_mm'],
                               parent_sd_mm=row['sd_mm'], estimator=row['estimator'],
                               status='omitted_missing_sd' if row['sd_mm'] is None else 'configured'))
    if missing and not allow_partial:
        raise ValueError('Uncalibrated/missing error inputs: '+', '.join(missing)+
                         '. Supply SDs or explicitly allow_partial for conditional sensitivity only.')
    known = [r['sigma_mm'] for r in config.values()] + [r['parent_sd_mm'] for r in depth_rows]
    if all(value is None for value in known):
        raise ValueError('No error SD is configured; no ensemble can be labelled uncertainty')
    if missing:
        warnings.append('Conditional sensitivity only; omitted errors held fixed: '+', '.join(missing))
    if not any(value is not None and value > 0 for value in known):
        warnings.append('All configured SDs are zero: deterministic replay, not evidence of certainty.')
    if application is not None:
        warnings.extend(table.warnings)
        warnings.extend(application['context']['warnings'])
        warnings.append(application['interpretation'])
    if metadata.get('version') != 3:
        warnings.append('Legacy CSV: bone positions and provenance unavailable; placement-only analysis.')
    warnings.extend(metadata.get('landmark_audit', {}).get('warnings', []))
    records = metadata.get('marker_records', {})
    unreviewed = [label for label in labels if records.get(label, {}).get('mapping_reviewed') is not True]
    if unreviewed:
        warnings.append('Mapping review absent/not confirmed: '+', '.join(unreviewed))
    # Generate once with a local, explicit generator so prior scenarios are paired.
    rng = np.random.Generator(np.random.PCG64(seed))
    sigmas = np.array([config[label]['sigma_mm'] or 0.0 for label in labels])
    placement_draws = rng.normal(size=(samples, len(labels), 3)) * sigmas[None, :, None]
    depths = _truncated_depths(rng, np.array([r['parent_location_mm'] for r in depth_rows]),
                              np.array([r['parent_sd_mm'] or 0.0 for r in depth_rows]), samples)
    sample_targets = np.broadcast_to(central, (samples, *central.shape)).copy() + placement_draws
    if application is not None:
        for column, item in enumerate(application['replacements']):
            index = labels.index(item['label'])
            sample_targets[:, index] += (depths[:, column]-item['after_mm'])[:, None]*np.array(item['axis_world'])
    finite_array(sample_targets, 'sample targets')
    output = {}
    for variant in variants:
        options = {} if variant == 'off' else dict(prior_mean=prior['mean'], prior_scale=prior['scale'])
        def fit(points):
            return fit_identity(model.mu, model.basis, indices, points, weights,
                                lam=regularization, active_components=active, max_iter=max_iter, **options)
        baseline = _fit_record(fit(central))
        results = []
        for index, points in enumerate(sample_targets):
            try:
                results.append(_fit_record(fit(points)))
            except (ValueError, np.linalg.LinAlgError) as exc:
                # Never drop failures or retry until a convenient draw fits.
                raise ValueError(f'{variant} sample {index}: fit failed; ensemble aborted: {exc}') from exc
        nonconverged = [i for i, r in enumerate(results) if not r['converged']]
        clipped = [i for i, r in enumerate(results) if r['clipped_active_count']]
        output[variant] = dict(baseline=baseline, samples=results,
            numerical_status='nonconverged' if nonconverged or not baseline['converged'] else 'converged',
            nonconverged_indices=nonconverged, clipped_indices=clipped)
        if nonconverged or not baseline['converged']:
            warnings.append(f'Prior {variant}: baseline converged={baseline["converged"]}; '
                            f'{len(nonconverged)}/{samples} draws did not converge; retained and flagged.')
        if clipped or baseline['clipped_active_count']:
            warnings.append(f'Prior {variant}: coefficient clipping active; nonlinear/truncated fit response.')
    from . import __version__
    return dict(schema_version=1, method='marker_error_propagation', calibration_status='uncalibrated',
                analysis_status='partial_conditional_sensitivity' if missing else 'configured_input_propagation',
                units='world_mm', samples=samples, seed=seed, rng='PCG64',
                software=dict(cranio=__version__, numpy=np.__version__),
                labels=labels, vertex_indices=indices.tolist(), weights=weights.tolist(),
                settings=dict(regularization=regularization, identity_subspace=identity_subspace,
                    allow_partial=allow_partial, prior_variants=list(variants), max_iter=max_iter,
                    tol=DEFAULT_TOL, huber_k_mm=HUBER_K_MM, clip_sigma=LossConfig().clip_sigma, prior_weight=1.0),
                prior_parameters=None if prior is None else dict(mean=np.asarray(prior['mean']).tolist(),
                                                                 scale=np.asarray(prior['scale']).tolist()),
                placement=config, depth_distribution='parent normal truncated at zero by rejection',
                depth_parameters=depth_rows, omitted_error_inputs=missing, tissue_application=application,
                original_targets_mm=original.tolist(), central_targets_mm=central.tolist(),
                placement_draws_mm=placement_draws.tolist(), depth_draws_mm=depths.tolist(),
                target_draws_mm=sample_targets.tolist(), variants=output, warnings=warnings)


def main(argv=None) -> int:
    """Standalone opt-in CLI; existing pipeline/add-on defaults are untouched."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('input', 'npz', 'output'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--placement', help='Placement error JSON; missing values remain unconfigured')
    parser.add_argument('--samples', type=int, default=200)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--max-iter', type=int, default=DEFAULT_MAX_ITER)
    parser.add_argument('--allow-partial', action='store_true')
    parser.add_argument('--tissue-table')
    parser.add_argument('--depth-labels', nargs='+', default=[])
    parser.add_argument('--tissue-axis', choices=('existing', 'source'), default='unconfigured')
    parser.add_argument('--tissue-directions')
    parser.add_argument('--regularization', default='30')
    parser.add_argument('--identity-subspace', choices=('all', 'head'), default='all')
    parser.add_argument('--prior')
    parser.add_argument('--prior-variants', nargs='+', choices=('off', 'on'), default=['off'])
    args = parser.parse_args(argv)
    try:
        from .backend import GNMBackend
        from .export import atomic_text
        from .io_csv import read_marker_csv
        from .prior import load_prior
        from .tissue import _json, load_table, table_path
        from .tissue_directions import load_directions
        from .validation import sha256_file, validate_outputs
        paths = [p for p in (args.input, args.npz, args.placement, args.prior, args.tissue_directions,
                            table_path(args.tissue_table) if args.tissue_table else None) if p]
        validate_outputs(paths, [args.output])
        hashes = {str(p): sha256_file(p) for p in paths}
        backend = GNMBackend(args.npz)
        targets, skipped, metadata = read_marker_csv(args.input, backend.index_to_label, backend.landmark_vertex_map)
        if metadata.get('model_sha256') and metadata['model_sha256'] != hashes[args.npz]:
            raise ValueError('Marker/model SHA-256 mismatch')
        prior = load_prior(args.prior, backend.load().identity_dim) if args.prior else None
        result = monte_carlo_identity(backend.load(), targets, metadata,
            placement=_json(Path(args.placement).read_text(encoding='utf-8-sig')) if args.placement else None,
            samples=args.samples, seed=args.seed, max_iter=args.max_iter, allow_partial=args.allow_partial,
            table=load_table(args.tissue_table) if args.tissue_table else None, depth_labels=args.depth_labels,
            axis_policy=args.tissue_axis,
            directions=load_directions(args.tissue_directions) if args.tissue_directions else None,
            regularization='auto' if args.regularization == 'auto' else float(args.regularization),
            identity_subspace=args.identity_subspace, prior=prior, prior_variants=args.prior_variants)
        result.update(input_hashes=hashes, marker_metadata=metadata, skipped=skipped,
                      prior_record=None if prior is None else dict(sha256=prior['sha256'],
                          mean=prior['mean'].tolist(), scale=prior['scale'].tolist()))
        import platform
        from . import optimize
        result['implementation'] = dict(python=platform.python_version(), platform=platform.platform(),
            uncertainty_sha256=sha256_file(__file__), optimize_sha256=sha256_file(optimize.__file__))
        if not metadata.get('model_sha256'):
            result['warnings'].append('CSV model hash missing; correspondence compatibility not verified.')
        if any(sha256_file(p) != digest for p, digest in hashes.items()):
            raise ValueError('An input changed during sampling; refusing to publish')
        validate_outputs(paths, [args.output])
        with atomic_text(args.output) as stream:
            json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write('\n')
        print(args.output)
        for warning in result['warnings']:
            print('WARNING: '+warning)
        return 0
    except (ValueError, OSError, np.linalg.LinAlgError, RuntimeError) as exc:
        print(f'Uncertainty analysis unavailable: {exc}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

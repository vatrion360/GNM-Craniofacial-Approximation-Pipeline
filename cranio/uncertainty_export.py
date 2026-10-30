"""Export uncalibrated A2.1 ensembles without re-alignment or posterior claims.

NumPy-only statistics; optional CLI reads an existing ensemble rather than
rerunning the fit. Mean/SD describe posed statistical surfaces, not dense/TPS
final fits, anatomical accuracy, or confidence/coverage intervals.
"""
import argparse
import copy
import json
from pathlib import Path
import tempfile

import numpy as np

from .export import atomic_text, export_obj
from .validation import finite_array, sha256_file


def _sample(model, row):
    """Validate a replay transform; matrix tolerance is numerical, not anatomical."""
    if not isinstance(row, dict) or row.get('converged') is not True:
        raise ValueError('All samples and the baseline must have converged; rerun A2.1 with a larger budget')
    c = finite_array(row.get('coefficients'), 'coefficients', (model.identity_dim,))
    r = finite_array(row.get('rotation'), 'rotation', (3, 3))
    t = finite_array(row.get('translation_mm'), 'translation', (3,))
    s = row.get('scale')
    if type(s) not in (float, int) or not np.isfinite(s) or s <= 0:
        raise ValueError('Scale must be finite and positive')
    if not np.allclose(r @ r.T, np.eye(3), rtol=0, atol=1e-10) or abs(np.linalg.det(r)-1) > 1e-10:
        raise ValueError('Rotation must be proper orthogonal (no reflection/shear)')
    clipped = row.get('clipped_active_count')
    if type(clipped) is not int or not 0 <= clipped <= model.identity_dim:
        raise ValueError('Invalid clipped component count')
    return c, float(s), r, t


def replay_vertices(model, sample):
    """Reconstruct a sample in its original world-mm frame; no ICP/Procrustes."""
    c, scale, rotation, translation = _sample(model, sample)
    return finite_array(scale*(model.generate(c) @ rotation.T)+translation,
                        'replayed vertices', (model.vertex_count, 3))


def region_indices(document, vertex_count, model_hash=None):
    """Explicit, source-labelled vertex sets; no anatomical thresholds inferred.

    All vertices is always included and contains internal geometry. Regions may
    overlap and are vertex-weighted, not area-weighted. CLI binds them to NPZ hash.
    """
    result = {'all_vertices': np.arange(vertex_count)}
    if document is None:
        return result
    if (not isinstance(document, dict) or set(document) != {'schema_version', 'model_sha256', 'regions'}
            or type(document['schema_version']) is not int or document['schema_version'] != 1):
        raise ValueError('Regions require schema_version=1, model_sha256 and regions')
    digest = document['model_sha256']
    if (not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)
            or model_hash is not None and digest != model_hash):
        raise ValueError('Region/model SHA-256 mismatch or invalid hash')
    if not isinstance(document['regions'], dict):
        raise ValueError('regions must be an object')
    for name, row in document['regions'].items():
        if not isinstance(name, str) or not name.strip() or name == 'all_vertices':
            raise ValueError('Invalid/reserved region name')
        if (not isinstance(row, dict) or set(row) != {'vertex_indices', 'source'}
                or not isinstance(row['source'], str) or not row['source'].strip()):
            raise ValueError(f'{name}: vertex_indices and source are required')
        raw = row['vertex_indices']
        if (not isinstance(raw, list) or not raw or any(type(i) is not int for i in raw)
                or min(raw) < 0 or max(raw) >= vertex_count or len(set(raw)) != len(raw)):
            raise ValueError(f'{name}: vertex indices must be distinct in-range integers')
        result[name] = np.array(sorted(raw), dtype=np.int64)
    return result


def representative_indices(samples, count):
    """Real samples: nearest beta-centroid then farthest-point in beta space.

    Exact duplicate replay parameters are removed. Ties use input index; poses
    are not part of the distance metric. No attempt to confine samples to 1 SD.
    """
    if type(count) is not int or not 3 <= count <= 5:
        raise ValueError('variant count must be 3, 4 or 5')
    beta = np.asarray([s['coefficients'] for s in samples], dtype=float)
    parameters = np.array([np.concatenate((s['coefficients'], [s['scale']],
                            np.ravel(s['rotation']), s['translation_mm'])) for s in samples])
    _, ids = np.unique(parameters, axis=0, return_index=True)
    ids = np.sort(ids)
    # Rescale before squared distances to avoid overflow, without changing order.
    b = beta / max(float(np.abs(beta).max()), 1.)
    first = int(ids[np.argmin(np.sum((b[ids]-b.mean(axis=0))**2, axis=1))])
    chosen = [first]
    nearest = np.sum((b-b[first])**2, axis=1)
    for _ in range(min(count, len(ids))-1):
        available = ids[~np.isin(ids, chosen)]
        next_id = int(available[np.argmax(nearest[available])])
        chosen.append(next_id)
        nearest = np.minimum(nearest, np.sum((b-b[next_id])**2, axis=1))
    return chosen


def summarize_ensemble(model, record, *, variants=3, regions=None, model_hash=None):
    """Validate complete converged scenarios and return arrays plus JSON summaries.

    Streaming Welford statistics use ddof=1. sqrt(trace(sample covariance)) is
    named spread_rms_mm; it is NOT the SD of radial distances. Regional percentiles
    summarize this field across vertices, never a 95% confidence interval.
    """
    if type(variants) is not int or not 3 <= variants <= 5:
        raise ValueError('variant count must be 3, 4 or 5')
    if (not isinstance(record, dict) or type(record.get('schema_version')) is not int
            or record['schema_version'] != 1 or record.get('method') != 'marker_error_propagation'
            or record.get('units') != 'world_mm' or record.get('calibration_status') != 'uncalibrated'
            or record.get('analysis_status') not in ('configured_input_propagation', 'partial_conditional_sensitivity')):
        raise ValueError('Expected an uncalibrated A2.1 world-mm ensemble record')
    if not isinstance(record.get('warnings'), list) or any(not isinstance(w, str) for w in record['warnings']):
        raise ValueError('Ensemble warnings must be a list of strings')
    count = record.get('samples')
    cases = record.get('variants')
    if (type(count) is not int or count < 2 or not isinstance(cases, dict) or not cases
            or set(cases)-{'off', 'on'}):
        raise ValueError('Invalid sample count or prior scenarios')
    selected_regions = region_indices(regions, model.vertex_count, model_hash)
    triangles = np.asarray(model.triangles)
    if (triangles.ndim != 2 or triangles.shape[1] != 3 or triangles.dtype.kind not in 'iu'
            or np.any(triangles < 0) or np.any(triangles >= model.vertex_count)):
        raise ValueError('Invalid model topology')
    # Preflight all scenarios before calculating any exportable statistics.
    for name, scenario in cases.items():
        if (not isinstance(scenario, dict) or not isinstance(scenario.get('samples'), list)
                or len(scenario['samples']) != count or scenario.get('numerical_status') != 'converged'
                or scenario.get('nonconverged_indices') != []):
            raise ValueError(f'{name}: inconsistent or nonconverged ensemble; no samples will be discarded')
        _sample(model, scenario.get('baseline'))
        for row in scenario['samples']:
            _sample(model, row)
        if scenario.get('clipped_indices') != [i for i,s in enumerate(scenario['samples']) if s['clipped_active_count']]:
            raise ValueError(f'{name}: inconsistent clipping diagnostics')
    outputs = {}
    for name, scenario in cases.items():
        samples = scenario['samples']
        mean = np.zeros((model.vertex_count, 3))
        m2 = np.zeros_like(mean)
        for n, sample in enumerate(samples, 1):
            points = replay_vertices(model, sample)
            delta = points-mean
            mean += delta/n
            m2 += delta*(points-mean)
        variance = finite_array(m2/(count-1), 'sample variance')
        sd = np.sqrt(np.maximum(variance, 0.))  # guard negative floating-point roundoff only
        spread = finite_array(np.linalg.norm(sd, axis=1), '3D spread')
        region_stats = {key: dict(vertex_count=len(ids), mean_spread_rms_mm=float(spread[ids].mean()),
            spatial_p025_spread_rms_mm=float(np.quantile(spread[ids], .025)),
            spatial_p975_spread_rms_mm=float(np.quantile(spread[ids], .975)),
            mean_coordinate_sd_mm=sd[ids].mean(axis=0).tolist()) for key, ids in selected_regions.items()}
        chosen = representative_indices(samples, variants)
        meshes, selection = [], []
        for index in chosen:
            vertices = replay_vertices(model, samples[index])
            distance = np.linalg.norm(vertices-mean, axis=1)
            meshes.append(vertices)
            selection.append(dict(sample_index=index, coefficients=samples[index]['coefficients'],
                max_distance_from_mean_mm=float(distance.max()),
                fraction_vertices_within_one_spread=float(np.mean(distance <= spread)),
                regional_mean_distance_mm={key: float(distance[ids].mean()) for key, ids in selected_regions.items()}))
        outputs[name] = dict(mean=mean, sd_xyz=sd, spread=spread, variant_meshes=meshes,
            summary=dict(sample_count=count, ddof=1, numerical_status='converged',
                clipped_indices=scenario['clipped_indices'], baseline_clipped=scenario['baseline']['clipped_active_count'],
                regions=region_stats, selected_variants=selection, requested_variants=variants,
                actual_variants=len(chosen), selection_method='nearest beta-centroid then farthest beta; ties by index; exact replay deduplication'))
    return outputs


def export_spread_ply(path, vertices, triangles, sd, spread, color_max, status):
    """ASCII PLY on the mean surface, with numeric fields and shared greyscale."""
    with atomic_text(path) as stream:
        stream.write('ply\nformat ascii 1.0\ncomment units mm; original world frame; no re-alignment\n')
        stream.write('comment uncalibrated simulated spread; NOT face accuracy or confidence intervals\n')
        stream.write(f'comment analysis_status {status}\n')
        stream.write('comment sample coordinate SD ddof=1; spread_rms_mm=sqrt(sd_x^2+sd_y^2+sd_z^2)\n')
        stream.write(f'comment common_color_scale_mm 0 {color_max:.17g}; black=0 white=max; all zero=black\n')
        stream.write(f'element vertex {len(vertices)}\nproperty double x\nproperty double y\nproperty double z\n')
        stream.write('property uchar red\nproperty uchar green\nproperty uchar blue\n')
        stream.write('property double sd_x_mm\nproperty double sd_y_mm\nproperty double sd_z_mm\nproperty double spread_rms_mm\n')
        stream.write(f'element face {len(triangles)}\nproperty list uchar int vertex_indices\nend_header\n')
        for point, sigma, magnitude in zip(vertices, sd, spread):
            grey = int(round(255*float(magnitude)/color_max)) if color_max else 0
            stream.write(' '.join([*(f'{v:.17g}' for v in point), *([str(grey)]*3),
                                   *(f'{v:.17g}' for v in sigma), f'{magnitude:.17g}'])+'\n')
        for triangle in triangles:
            stream.write('3 '+' '.join(str(int(i)) for i in triangle)+'\n')


def export_bundle(ensemble_path, model_path, output_dir, *, variants=3, regions_path=None):
    """Publish to a new directory; summary is the completion marker, written last.

    Temporary sibling staging is cleaned on failure. No source paths embedded in
    JSON are opened. Both current inputs and explicit region data are hash pinned.
    """
    from .backend import GNMBackend
    from .tissue import _json
    destination = Path(output_dir).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Output directory must be new')
    paths = [Path(p).expanduser().resolve() for p in (ensemble_path, model_path, regions_path) if p is not None]
    hashes = {str(p): sha256_file(p) for p in paths}
    record = _json(paths[0].read_text(encoding='utf-8-sig'))
    model_hash = hashes[str(paths[1])]
    recorded = record.get('input_hashes', {}) if isinstance(record, dict) else {}
    if not isinstance(recorded, dict) or model_hash not in recorded.values():
        raise ValueError('Selected NPZ hash is not recorded among ensemble inputs')
    metadata = record.get('marker_metadata', {})
    if not isinstance(metadata, dict):
        raise ValueError('marker_metadata must be an object')
    marker_hash = metadata.get('model_sha256')
    if marker_hash and marker_hash != model_hash:
        raise ValueError('Marker/model hash mismatch')
    regions = _json(paths[2].read_text(encoding='utf-8-sig')) if regions_path is not None else None
    model = GNMBackend(paths[1]).load()
    surfaces = summarize_ensemble(model, record, variants=variants, regions=regions, model_hash=model_hash)
    color_max = max(float(s['spread'].max()) for s in surfaces.values())
    warnings = copy.deepcopy(record.get('warnings', []))
    warnings.extend(['Uncalibrated simulated spread, not anatomical accuracy or a confidence interval.',
        'World-frame mean includes pose/scale variation; no re-alignment. Mean geometry is not guaranteed to be a single GNM fit.',
        'Regional statistics are equally weighted vertices, not surface area. Spatial P2.5/P97.5 are NOT 95% confidence limits.',
        'Selected variants are actual simulations, not validated plausible faces; they need not lie within one SD.'])
    if regions is None:
        warnings.append('No anatomical regions configured; all_vertices includes internal geometry.')
    for name, surface in surfaces.items():
        summary = surface['summary']
        if summary['clipped_indices'] or summary['baseline_clipped']:
            warnings.append(f'Prior {name}: coefficient clipping active; dispersion can be truncated.')
        if summary['actual_variants'] < variants:
            warnings.append(f'Prior {name}: only {summary["actual_variants"]} distinct replay samples available.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.gnm-ensemble-', dir=destination.parent) as temporary:
        stage = Path(temporary)/'bundle'
        stage.mkdir()
        outputs = {}
        for name, surface in surfaces.items():
            folder = stage/f'prior_{name}'
            folder.mkdir()
            comments = ('Uncalibrated simulated ensemble; NOT anatomical accuracy or confidence bounds',
                        'Original world-mm frame; no re-alignment', 'analysis_status '+record['analysis_status'])
            export_obj(folder/'mean.obj', surface['mean'], model.triangles,
                       comments=(*comments, 'Mean of posed sample vertices, not a single fitted identity'))
            export_spread_ply(folder/'spread.ply', surface['mean'], model.triangles,
                              surface['sd_xyz'], surface['spread'], color_max, record['analysis_status'])
            for ordinal, mesh in enumerate(surface['variant_meshes'], 1):
                sample_index = surface['summary']['selected_variants'][ordinal-1]['sample_index']
                export_obj(folder/f'variant_{ordinal:02d}.obj', mesh, model.triangles,
                           comments=(*comments, f'Actual simulation sample index {sample_index}; no 1-SD bound imposed'))
            outputs[name] = surface['summary']
        if any(sha256_file(p) != digest for p, digest in hashes.items()):
            raise ValueError('An export input changed; no bundle published')
        from . import __version__
        summary = dict(schema_version=1, status='completed', units='world_mm',
            calibration_status='uncalibrated', analysis_status=record['analysis_status'],
            source_hashes=hashes, model_sha256=model_hash, region_definition=regions,
            common_color_max_mm=color_max, prior_scenarios=outputs, warnings=warnings,
            source_settings=record.get('settings'), source_seed=record.get('seed'),
            omitted_error_inputs=record.get('omitted_error_inputs'),
            software=dict(cranio=__version__, numpy=np.__version__, exporter_sha256=sha256_file(__file__)),
            output_sha256={str(p.relative_to(stage)): sha256_file(p) for p in sorted(stage.rglob('*')) if p.is_file()})
        with atomic_text(stage/'summary.json') as stream:
            json.dump(summary, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write('\n')
        if destination.exists() or destination.is_symlink():
            raise ValueError('Output directory appeared during export; refusing to replace it')
        stage.rename(destination)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ensemble', required=True)
    parser.add_argument('--npz', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--variants', type=int, choices=(3, 4, 5), default=3)
    parser.add_argument('--regions', help='Explicit model-hash-bound region vertex sets')
    args = parser.parse_args(argv)
    try:
        result = export_bundle(args.ensemble, args.npz, args.output_dir,
                               variants=args.variants, regions_path=args.regions)
        print(str(Path(args.output_dir)/'summary.json'))
        for warning in result['warnings']:
            print('WARNING: '+warning)
        return 0
    except (ValueError, OSError, OverflowError, np.linalg.LinAlgError) as exc:
        print(f'Ensemble export unavailable: {exc}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

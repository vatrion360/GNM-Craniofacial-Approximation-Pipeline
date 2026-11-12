"""Read-only association of A2.1 evidence, never uncertainty of the final mesh.

Shared input hashes establish a recorded relationship, not equivalent algorithms,
valid calibration, or authenticity. Source inputs and model are not reopened.
"""
import copy
from types import SimpleNamespace

import numpy as np

from .record import canonical_bytes, _hash
from .uncertainty import placement_config
from .uncertainty_export import _sample
from .validation import finite_array

INTERPRETATION = (
    'Related uncalibrated marker-only analysis; NOT uncertainty of this fitted final mesh. '
    'Shared recorded input hashes do not establish equivalent fitting or scientific validity. '
    'No calibration multiplier, SD field or confidence interval is applied.')


def _strings(value, name):
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise ValueError(name+' must be a list of strings')
    return value


def _fit(row, dimension):
    """Use A2.2 replay validation while retaining true convergence diagnostics.

    A2.2 only exports converged surfaces. Here nonconvergence is deliberately
    retained as diagnostic evidence, never exported or relabelled converged.
    """
    if not isinstance(row, dict) or type(row.get('converged')) is not bool:
        raise ValueError('Every fit needs explicit boolean convergence')
    _sample(SimpleNamespace(identity_dim=dimension), dict(row, converged=True))
    return row


def summarize_link(report: dict, ensemble: dict, scenario: str, digest: str) -> dict:
    """Validate and summarize a supplied A2.1 CLI record without running a fit.

    Only the explicitly selected prior scenario is associated. Other scenario
    diagnostics remain visible. All settings comparisons are descriptive; even
    exact equality does not authorize applying this analysis to the final mesh.
    """
    _hash(digest)
    if (not isinstance(ensemble, dict) or type(ensemble.get('schema_version')) is not int
            or ensemble['schema_version'] != 1 or ensemble.get('method') != 'marker_error_propagation'
            or ensemble.get('units') != 'world_mm' or ensemble.get('calibration_status') != 'uncalibrated'
            or ensemble.get('analysis_status') not in ('configured_input_propagation', 'partial_conditional_sensitivity')):
        raise ValueError('Expected an uncalibrated A2.1 world-mm ensemble')
    canonical_bytes(ensemble)
    hashes = ensemble.get('input_hashes')
    if not isinstance(hashes, dict) or not hashes or any(not isinstance(p, str) or not p for p in hashes):
        raise ValueError('CLI ensemble input hashes are required')
    for value in hashes.values():
        _hash(value)
    matched = {name: report['inputs'][name]['sha256'] for name in ('model', 'markers')}
    if any(value not in hashes.values() for value in matched.values()):
        raise ValueError('Ensemble must record both run model and marker CSV hashes')
    metadata = ensemble.get('marker_metadata')
    if not isinstance(metadata, dict) or metadata.get('model_sha256') not in (None, matched['model']):
        raise ValueError('Ensemble marker/model provenance mismatch')
    cases, count, seed = ensemble.get('variants'), ensemble.get('samples'), ensemble.get('seed')
    if (not isinstance(cases, dict) or not cases or set(cases)-{'off', 'on'}
            or scenario not in cases or type(count) is not int or count < 2
            or type(seed) is not int or seed < 0):
        raise ValueError('Invalid scenario, sample count or seed')
    expected = 'on' if 'prior' in report['inputs'] else 'off'
    if scenario != expected:
        raise ValueError('Selected uncertainty scenario must match the run prior state')
    if scenario == 'on':
        prior = ensemble.get('prior_record')
        if (not isinstance(prior, dict) or prior.get('sha256') != report['inputs']['prior']['sha256']
                or prior['sha256'] not in hashes.values()):
            raise ValueError('Selected uncertainty prior hash must match the run prior')
    labels = _strings(ensemble.get('labels'), 'labels')
    indices = ensemble.get('vertex_indices')
    if (not labels or any(not x.strip() for x in labels) or len(set(labels)) != len(labels)
            or not isinstance(indices, list) or len(indices) != len(labels)
            or any(type(i) is not int or i < 0 for i in indices) or len(set(indices)) != len(indices)):
        raise ValueError('Distinct labels and corresponding vertex indices are required')
    shape = (len(labels), 3)
    finite_array(ensemble.get('original_targets_mm'), 'original targets', shape)
    central = finite_array(ensemble.get('central_targets_mm'), 'central targets', shape)
    weights = finite_array(ensemble.get('weights'), 'weights', (len(labels),))
    if np.any(weights <= 0):
        raise ValueError('Ensemble weights must be positive')
    placement = placement_config(dict(schema_version=1, placement=ensemble.get('placement')), labels)
    omitted = _strings(ensemble.get('omitted_error_inputs'), 'omitted_error_inputs')
    warnings = _strings(ensemble.get('warnings'), 'warnings')
    if bool(omitted) != (ensemble['analysis_status'] == 'partial_conditional_sensitivity'):
        raise ValueError('Inconsistent partial-analysis status')
    settings = ensemble.get('settings')
    # JSON serialization may reorder the scenario keys; ordering is not evidence.
    variants = settings.get('prior_variants') if isinstance(settings, dict) else None
    if (not isinstance(variants, list) or any(v not in ('off', 'on') for v in variants)
            or len(variants) != len(set(variants)) or set(variants) != set(cases)):
        raise ValueError('Inconsistent ensemble scenario settings')
    dimension = len(report['identity_coefficients'])
    diagnostics = {}
    for name, case in cases.items():
        if not isinstance(case, dict) or not isinstance(case.get('samples'), list) or len(case['samples']) != count:
            raise ValueError('Incomplete ensemble samples')
        baseline = _fit(case.get('baseline'), dimension)
        samples = [_fit(row, dimension) for row in case['samples']]
        nonconverged = [i for i, row in enumerate(samples) if not row['converged']]
        clipped = [i for i, row in enumerate(samples) if row['clipped_active_count']]
        status = 'nonconverged' if nonconverged or not baseline['converged'] else 'converged'
        for field, actual in (('nonconverged_indices', nonconverged), ('clipped_indices', clipped)):
            recorded = case.get(field)
            if (not isinstance(recorded, list) or any(type(i) is not int for i in recorded) or recorded != actual):
                raise ValueError('Inconsistent ensemble '+field)
        if case.get('numerical_status') != status:
            raise ValueError('Inconsistent ensemble numerical_status')
        diagnostics[name] = dict(numerical_status=status, baseline_converged=baseline['converged'],
            baseline_clipped_active_count=baseline['clipped_active_count'],
            nonconverged_indices=nonconverged, clipped_indices=clipped, sample_count=count)
    cfg = report['config']
    comparison = {key: dict(run=cfg.get(run_key), ensemble=settings.get(key)) for key, run_key in
                  [('regularization', 'regularization'), ('identity_subspace', 'identity_subspace'),
                   ('max_iter', 'max_iter'), ('tol', 'tolerance'), ('clip_sigma', 'clip_sigma'),
                   ('prior_weight', 'prior_weight')]}
    by_label = {label: i for i, label in enumerate(labels)}
    targets_match = len(labels) == len(report['landmarks']) and all(
        row['label'] in by_label and row['vertex'] == indices[by_label[row['label']]]
        and row['weight'] == weights[by_label[row['label']]]
        and np.array_equal(row['target_mm'], central[by_label[row['label']]]) for row in report['landmarks'])
    features = {key: copy.deepcopy(cfg.get(key)) for key in
                ('skip_tps', 'no_dense_fit', 'depth_weighting', 'exclude', 'exclude_outliers',
                 'symmetry_weight', 'distance_weight', 'measurement_weight', 'prior_soft_sigma')}
    features.update(skull_supplied='skull' in report['inputs'], profile_supplied='profile_constraint' in report['inputs'])
    return dict(status='linked_uncalibrated_analysis', source_sha256=digest,
        interpretation=INTERPRETATION, applies_to='related_marker_only_analysis',
        final_mesh_uncertainty='not_assessed', calibration_status='uncalibrated',
        input_association=dict(status='hashes_present_in_recorded_inputs', **matched),
        selected_prior_scenario=scenario, analysis_status=ensemble['analysis_status'],
        samples=count, seed=seed, scenario_diagnostics=diagnostics,
        placement=placement, omitted_error_inputs=copy.deepcopy(omitted),
        source_warnings=copy.deepcopy(warnings), settings=copy.deepcopy(settings),
        depth_parameters=copy.deepcopy(ensemble.get('depth_parameters')),
        tissue_application=copy.deepcopy(ensemble.get('tissue_application')),
        source_software=copy.deepcopy(ensemble.get('software')),
        source_implementation=copy.deepcopy(ensemble.get('implementation')),
        comparison=dict(equivalence='not_established', settings=comparison,
                        central_targets_vertices_weights_exact_match=bool(targets_match), run_features=features))

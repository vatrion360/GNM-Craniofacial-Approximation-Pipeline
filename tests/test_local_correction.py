"""Shared preparation against the pre-extraction pipeline algorithm and geometry."""
import builtins
import json
import os
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial import cKDTree

from cranio.local_correction import prepare_local_correction
from cranio.optimize import bounded_tps_correction


def fixture(seed=17, size=150):
    rng = np.random.default_rng(seed)
    vertices = rng.normal(size=(size, 3))*70
    markers = np.arange(12)
    dense = np.arange(8, size)
    return dict(vertices=vertices, marker_indices=markers,
        targets=vertices[markers]+rng.normal(size=(len(markers), 3))*4,
        confidence=np.linspace(.1, 1.2, len(markers)), scalp_indices=np.arange(0, size, 3),
        protected_indices=np.arange(0, size, 7), face_cap_mm=8., scalp_cap_mm=15.,
        protect_damping=.25, seed=seed, scalp_centres=23, face_centres=19,
        dense_indices=dense, dense_targets=vertices[dense]+rng.normal(size=(len(dense), 3))*3,
        dense_regions=np.asarray(['scalp' if i % 3 else 'synthetic_face' for i in dense]))


def legacy(data):
    """Frozen PR #46 assembly oracle: SciPy KDTree and two separate RNG draws."""
    v = data['vertices']
    lm = v[data['marker_indices']]
    centers = [lm]
    vectors = [(data['targets']-lm)*data['confidence'][:, None]]
    selected_ids = [data['marker_indices']]
    if data.get('dense_indices') is not None:
        indices, targets, regions = (data[k] for k in ('dense_indices', 'dense_targets', 'dense_regions'))
        distances, _ = cKDTree(lm).query(v[indices])
        far = distances > 3.
        indices, targets, regions = indices[far], targets[far], regions[far]
        rng = np.random.default_rng(data['seed'])
        for scalp, cap in [(True, data['scalp_centres']), (False, data['face_centres'])]:
            candidates = np.where((regions == 'scalp') if scalp else (regions != 'scalp'))[0]
            if not len(candidates):
                continue
            selected = np.sort(rng.choice(candidates, size=min(cap, len(candidates)), replace=False))
            centers.append(v[indices[selected]])
            vectors.append(targets[selected]-v[indices[selected]])
            selected_ids.append(indices[selected])
    caps = np.full(len(v), data['face_cap_mm'])
    caps[data['scalp_indices']] = data['scalp_cap_mm']
    return np.vstack(centers), np.vstack(vectors), caps, np.concatenate(selected_ids)


@pytest.mark.parametrize('seed', [0, 42, 917])
@pytest.mark.parametrize('case', ['mixed', 'markers', 'scalp_only', 'face_only', 'zero_budget', 'all_rows'])
def test_exact_legacy_selection_and_default_scipy_output(seed, case):
    data = fixture(seed)
    if case == 'markers':
        for key in ('dense_indices', 'dense_targets', 'dense_regions'): data.pop(key)
    elif case == 'scalp_only': data['dense_regions'][:] = 'scalp'
    elif case == 'face_only': data['dense_regions'][:] = 'synthetic_face'
    elif case == 'zero_budget': data['scalp_centres'] = data['face_centres'] = 0
    elif case == 'all_rows': data['scalp_centres'] = data['face_centres'] = 1000
    expected_centers, expected_vectors, expected_caps, expected_ids = legacy(data)
    plan = prepare_local_correction(**data)
    for a, b in [(plan.centers, expected_centers), (plan.vectors, expected_vectors),
                 (plan.caps, expected_caps), (plan.record()['centre_vertex_indices'], expected_ids)]:
        np.testing.assert_array_equal(a, b)
    old = bounded_tps_correction(data['vertices'], expected_centers, expected_vectors,
        expected_caps, data['protected_indices'], data['protect_damping'])
    for a, b in zip(plan.apply(), old): np.testing.assert_array_equal(a, b)


def test_exclusion_is_at_statistical_marker_not_target_and_strict_boundary():
    v = np.array([[0., 0, 0], [100, 0, 0], [0, 100, 0], [0, 0, 100],
                  [np.nextafter(3., 0), 0, 0], [3., 0, 0], [np.nextafter(3., 4), 0, 0]])
    data = dict(vertices=v, marker_indices=[0, 1, 2, 3], targets=v[:4]+50, confidence=np.ones(4),
        scalp_indices=[], protected_indices=[], face_cap_mm=8., scalp_cap_mm=15.,
        protect_damping=1., seed=0, scalp_centres=20, face_centres=20,
        dense_indices=[4, 5, 6], dense_targets=v[4:]+1, dense_regions=['scalp']*3)
    info = prepare_local_correction(**data).record()
    assert info['dense_near_marker_rows'] == [0, 1]
    assert info['dense_selected_rows'] == [2]
    assert info['centre_vertex_indices'] == [0, 1, 2, 3, 6]


def test_partial_regions_do_not_generate_centres_and_row_provenance_replays():
    data = fixture()
    # Arbitrary surviving anatomical regions, not a perfect left/right half.
    data['dense_regions'] = np.array(['right_vault', 'nasal_fragment', 'left_mandible']*
                                    (len(data['dense_indices'])//3+1))[:len(data['dense_indices'])]
    data['dense_regions'][::5] = 'scalp'
    plan = prepare_local_correction(**data)
    audit = plan.record()
    rows = np.asarray(audit['dense_selected_rows'])
    n = audit['counts']['markers']
    ids = data['dense_indices'][rows]
    np.testing.assert_array_equal(plan.centers[n:], data['vertices'][ids])
    np.testing.assert_array_equal(plan.vectors[n:], data['dense_targets'][rows]-data['vertices'][ids])
    assert set(audit['dense_candidate_regions']) == set(data['dense_regions'])
    assert audit['counts']['total'] == sum(audit['counts'][key] for key in ('markers', 'scalp', 'face'))
    assert audit['marker_exclusion']['provenance'] == 'legacy_hardcoded'
    assert json.dumps(audit, allow_nan=False, sort_keys=True) == json.dumps(
        prepare_local_correction(**data).record(), allow_nan=False, sort_keys=True)


def test_marker_confidence_is_not_normalized_and_dense_vectors_are_unweighted():
    data = fixture()
    data['confidence'][0] = 0
    plan = prepare_local_correction(**data)
    np.testing.assert_array_equal(plan.vectors[:12],
        (data['targets']-data['vertices'][:12])*data['confidence'][:, None])
    np.testing.assert_array_equal(plan.vectors[0], np.zeros(3))
    assert data['confidence'][-1] > 1


def test_detached_snapshot_and_repeat_apply_never_accumulate():
    data = fixture()
    plan = prepare_local_correction(**data)
    expected = plan.apply(backend='numpy')
    for value in data.values():
        if isinstance(value, np.ndarray): value[:] = 0
    for array in (plan.vertices, plan.centers, plan.vectors, plan.caps, plan.protected):
        assert not array.flags.writeable
    audit = plan.record()
    audit['centre_vertex_indices'][0] = 999
    assert plan.record()['centre_vertex_indices'][0] == 0
    for a, b in zip(expected, plan.apply(backend='numpy')): np.testing.assert_array_equal(a, b)


def test_markerless_dense_and_empty_dense_contracts():
    data = fixture()
    data.update(marker_indices=[], targets=np.empty((0, 3)), confidence=[])
    plan = prepare_local_correction(**data)
    assert plan.record()['counts']['markers'] == 0
    assert plan.record()['dense_near_marker_rows'] == []
    assert np.isfinite(plan.apply(backend='numpy')[0]).all()
    data = fixture()
    data.update(dense_indices=[], dense_targets=np.empty((0, 3)), dense_regions=[])
    plan = prepare_local_correction(**data)
    assert plan.record()['counts'] == dict(markers=12, scalp=0, face=0, total=12)


@pytest.mark.parametrize('field', ['marker_indices', 'scalp_indices', 'protected_indices', 'dense_indices'])
@pytest.mark.parametrize('bad', [[-1], [9999], [1, 1], [1.], [True], [[1]], 1])
def test_invalid_indices(field, bad):
    data = fixture()
    data[field] = bad
    with pytest.raises(ValueError): prepare_local_correction(**data)


@pytest.mark.parametrize('field,value', [
    ('vertices', np.zeros((4, 2))), ('vertices', np.empty((0, 3))),
    ('targets', [[1., 2., 3.]]), ('confidence', np.ones(11)),
    ('confidence', [-1.]*12), ('confidence', [np.nan]*12),
    ('face_cap_mm', 0), ('face_cap_mm', np.nan), ('scalp_cap_mm', -1),
    ('protect_damping', 1.1), ('protect_damping', np.nan), ('protect_damping', True),
    ('seed', -1), ('seed', True), ('seed', 1.5), ('scalp_centres', -1), ('face_centres', 1.5),
    ('dense_targets', np.zeros((5, 3))), ('dense_regions', ['scalp']),
])
def test_invalid_values(field, value):
    data = fixture()
    data[field] = value
    with pytest.raises(ValueError): prepare_local_correction(**data)


@pytest.mark.parametrize('field', ['dense_indices', 'dense_targets', 'dense_regions'])
def test_partial_dense_arguments_rejected(field):
    data = fixture()
    data.pop(field)
    with pytest.raises(ValueError, match='together'): prepare_local_correction(**data)


@pytest.mark.parametrize('label', ['', ' ', None, 4])
def test_dense_region_labels_are_not_guessed(label):
    data = fixture()
    data['dense_regions'] = data['dense_regions'].astype(object)
    data['dense_regions'][0] = label
    with pytest.raises(ValueError, match='region'): prepare_local_correction(**data)


@pytest.mark.parametrize('field', ['vertices', 'targets', 'dense_targets'])
def test_nonfinite_positions_refused(field):
    data = fixture()
    data[field][0, 0] = np.inf
    with pytest.raises(ValueError): prepare_local_correction(**data)


@pytest.mark.parametrize('mode', ['coincident_markers', 'coincident_dense', 'coplanar', 'few'])
def test_degenerate_selected_centres_fail_without_synthesizing_anatomy(mode):
    data = fixture()
    data['scalp_centres'] = data['face_centres'] = 1000
    if mode == 'coincident_markers': data['vertices'][1] = data['vertices'][0]
    elif mode == 'coincident_dense': data['vertices'][-1] = data['vertices'][-2]
    elif mode == 'coplanar': data['vertices'][:, 2] = 0
    else:
        data.update(marker_indices=[0, 1, 2], targets=data['targets'][:3], confidence=np.ones(3),
                    scalp_centres=0, face_centres=0)
    with pytest.raises(ValueError, match='centres'): prepare_local_correction(**data)


def test_integer_face_cap_does_not_truncate_fractional_scalp_cap():
    data = fixture()
    data.update(face_cap_mm=8, scalp_cap_mm=12.5)
    plan = prepare_local_correction(**data)
    np.testing.assert_array_equal(plan.caps[data['scalp_indices']], 12.5)


def test_preparation_and_numpy_application_import_no_optional_modules(monkeypatch):
    data = fixture()
    original = builtins.__import__
    def guard(name, *args, **kwargs):
        if name.split('.')[0] in ('scipy', 'trimesh', 'tensorflow', 'bpy'):
            raise AssertionError('Forbidden numerical import: '+name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guard)
    assert np.isfinite(prepare_local_correction(**data).apply(backend='numpy')[0]).all()


@pytest.mark.integration
def test_official_model_dense_preparation_exact_and_numpy_result_parity():
    from cranio.backend import GNMBackend
    from cranio.geometry import build_scalp_mask, build_protected_mask
    path = os.environ.get('GNM_MODEL_PATH')
    if not path or not Path(path).is_file(): pytest.skip('Set GNM_MODEL_PATH for official-mesh preparation')
    model = GNMBackend(path).load()
    data = fixture(size=len(model.mu))
    _, unique = np.unique(model.mu, axis=0, return_index=True)
    rng = np.random.default_rng(71)
    ids = rng.choice(unique, 1100, replace=False)
    data.update(vertices=model.mu.copy(), marker_indices=ids[:48],
        targets=model.mu[ids[:48]]+rng.normal(size=(48, 3)), confidence=np.linspace(.1, 1.2, 48),
        dense_indices=ids[48:], dense_targets=model.mu[ids[48:]]+rng.normal(size=(1052, 3)),
        dense_regions=np.where(np.arange(1052) % 2, 'scalp', 'synthetic_face'),
        scalp_indices=build_scalp_mask(model.mu, model.vertex_groups, model.vertex_group_names),
        protected_indices=build_protected_mask(model.vertex_groups, model.vertex_group_names),
        scalp_centres=500, face_centres=200)
    centers, vectors, caps, expected_ids = legacy(data)
    plan = prepare_local_correction(**data)
    for a, b in [(plan.centers, centers), (plan.vectors, vectors), (plan.caps, caps),
                 (plan.record()['centre_vertex_indices'], expected_ids)]:
        np.testing.assert_array_equal(a, b)
    old = bounded_tps_correction(model.mu, centers, vectors, caps, data['protected_indices'], .25)
    for a, b in zip(plan.apply(backend='numpy'), old): np.testing.assert_allclose(a, b, rtol=0, atol=1e-6)


@pytest.mark.parametrize('enabled', [False, True])
def test_pipeline_routes_optional_stage_and_records_exact_selection(tmp_path, model_file, marker_file, monkeypatch, enabled):
    from cranio import pipeline
    from cranio.config import PipelineConfig
    calls = []
    def checked(*args, **kwargs):
        plan = prepare_local_correction(*args, **kwargs)
        calls.append(plan)
        return plan
    monkeypatch.setattr(pipeline, 'prepare_local_correction', checked)
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), regularization='30',
                         output=str(tmp_path/'face.obj'), skip_tps=not enabled, exclude=['P0'])
    assert pipeline.run_pipeline(cfg) == 0
    report = json.loads(Path(cfg.output_json).read_text())
    assert len(calls) == int(enabled)
    meta = report['marker_metadata']
    if enabled:
        plan = calls[0]
        assert meta['local_correction_preparation'] == plan.record()
        assert 0 not in plan.record()['marker_vertex_indices']
        np.testing.assert_array_equal(meta['local_correction_centres_world_mm'], plan.centers)
        np.testing.assert_array_equal(meta['local_correction_prescribed_vectors_mm'], plan.vectors)
    else:
        assert 'local_correction_preparation' not in meta
        assert Path(cfg.output).read_bytes() == Path(cfg.output_statistical).read_bytes()

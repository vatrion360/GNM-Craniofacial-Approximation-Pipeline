"""Synthetic geometry only: these numbers are not anatomical norms or depths."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

from cranio.backend.base import FaceModelData
from cranio.profile import empty_manifest, prepare, refine, main
from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline
from cranio.validation import sha256_file

HASH = 'a'*64
BONE = 'b'*64


@pytest.fixture
def profile_case():
    mu = np.array([[0, 0, 2], [0, 0, 1], [0, 0, 0],
                   [-2, -2, 0], [2, -2, 0], [0, -2, 3], [0, 2, 0.]], dtype=float)
    basis = np.zeros((2, 7, 3))
    basis[0, :3, 1] = 1
    basis[1, 3:, 0] = 1
    model = FaceModelData(mu, basis, np.array([[0, 1, 2], [3, 4, 5]]),
                          np.arange(7), np.ones((1, 7)), ['skin'])
    metadata = dict(case_id='synthetic', mandible_articulation_reviewed=True,
                    bone_sources=[dict(id='bone', geometry_sha256=BONE)])
    manifest = empty_manifest()
    manifest.update(model_sha256=HASH, case_id='synthetic', source='Synthetic engineering fixture',
        mapping_reviewed=True, mandible_reviewed=True,
        plane=dict(origin_mm=[0, 0, 0], normal_world=[1, 0, 0], source='Synthetic x=0 plane', reviewed=True),
        plane_tolerance_mm=.01, segments=[[0, 1, 2]], strength=3., delta_regularization=1.,
        marker_preservation_weight=1., marker_displacement_limit_mm=0.)
    manifest['samples'] = [dict(label=label, bone_xyz_mm=model.mu[i].tolist(),
        normal_world=[0, 1, 0], source_id='bone', source_geometry_sha256=BONE,
        status='observed', reviewed=True, depth_mm=1., sd_mm=1., tissue_source='Synthetic unit offset',
        direction='bone_normal') for i, label in enumerate(['Glabella', 'SyntheticMiddle', 'Menton'])]
    return model, manifest, metadata


def fitted(case, *, coefficients=None, active=None, clip=3.):
    model, manifest, metadata = case
    return refine(model, np.zeros(2) if coefficients is None else coefficients, 1., np.eye(3), np.zeros(3),
                  np.array([3, 4, 5, 6]), np.ones(4), prepare(manifest, model, HASH, metadata),
                  clip_sigma=clip, active=active)


def test_hand_computed_ridge_and_preserved_markers(profile_case):
    # 3*(delta-1)^2 + delta^2 -> delta=.75; other coefficient remains zero.
    c, report = fitted(profile_case)
    np.testing.assert_allclose(c, [.75, 0], atol=1e-14)
    assert report['status'] == 'accepted'
    assert report['final_marker_max_displacement_mm'] == 0
    assert all(p['before_mm'] == 1 for p in report['points'])
    np.testing.assert_allclose([p['final_mm'] for p in report['points']], .25)
    assert report == fitted(profile_case)[1]


def test_world_scale_rotation_translation(profile_case):
    model, manifest, metadata = profile_case
    r = np.array([[0., -1, 0], [1, 0, 0], [0, 0, 1]])
    t = np.array([10., 20, 30])
    manifest['plane'].update(origin_mm=t.tolist(), normal_world=(r@np.array([1., 0, 0])).tolist())
    for i, row in enumerate(manifest['samples']):
        row.update(bone_xyz_mm=(2*r@model.mu[i]+t).tolist(), normal_world=[-1., 0, 0], depth_mm=2.)
    c, report = refine(model, np.zeros(2), 2., r, t, np.array([3, 4, 5, 6]), np.ones(4),
                       prepare(manifest, model, HASH, metadata), clip_sigma=3.)
    # 12*(delta-1)^2+delta^2 -> 12/13, mm displacement includes scale.
    np.testing.assert_allclose(c, [12/13, 0], atol=1e-14)
    np.testing.assert_allclose([p['final_mm'] for p in report['points']], 2/13)


def test_larger_sd_reduces_influence(profile_case):
    c, _ = fitted(profile_case)
    for row in profile_case[1]['samples']:
        row['sd_mm'] = 2.
    c2, _ = fitted(profile_case)
    assert 0 < c2[0] < c[0]


def test_clip_and_inactive_components(profile_case):
    c, report = fitted(profile_case, clip=.2, coefficients=np.array([0., .1]), active=[0])
    np.testing.assert_array_equal(c, [.2, .1])
    assert report['active_indices'] == [0]


def test_one_worsening_point_retains_exact_baseline(profile_case):
    profile_case[1]['samples'][0]['depth_mm'] = 0.
    c, report = fitted(profile_case)
    np.testing.assert_array_equal(c, [0., 0.])
    assert report['status'] == 'baseline_retained'
    assert report['points'][0]['candidate_mm'] > report['points'][0]['before_mm']
    assert all(p['final_mm'] == p['before_mm'] for p in report['points'])


def test_marker_displacement_limit_is_hard_gate(profile_case):
    profile_case[0].basis[0, 3:, 1] = 1.
    c, report = fitted(profile_case)
    assert report['status'] == 'baseline_retained'
    assert report['candidate_marker_max_displacement_mm'] > 0
    np.testing.assert_array_equal(c, [0., 0.])


def test_plane_gate_rejects_candidate(profile_case):
    profile_case[0].basis[0, :3, 0] = 1.
    c, report = fitted(profile_case)
    assert report['status'] == 'baseline_retained'
    np.testing.assert_array_equal(c, [0., 0.])


@pytest.mark.parametrize('field,value', [('sd_mm', None), ('sd_mm', 0), ('sd_mm', float('nan')),
    ('depth_mm', -1), ('depth_mm', float('inf')), ('source_geometry_sha256', 'c'*64),
    ('source_id', []), ('status', 'mirrored'), ('reviewed', False), ('direction', 'vertical'),
    ('normal_world', [0, 0, 0]), ('normal_world', [0, float('nan'), 0]),
    ('tissue_source', 'TODO(verify-source)'), ('bone_xyz_mm', [1, 0, 2])])
def test_untrusted_sample_rejected(profile_case, field, value):
    profile_case[1]['samples'][0][field] = value
    with pytest.raises(ValueError):
        prepare(profile_case[1], profile_case[0], HASH, profile_case[2])


@pytest.mark.parametrize('field,value', [('case_id', 'other'), ('model_sha256', 'c'*64),
    ('mapping_reviewed', False), ('mandible_reviewed', False), ('strength', None),
    ('delta_regularization', 0), ('marker_displacement_limit_mm', -1),
    ('plane_tolerance_mm', True), ('segments', [[0, 1, 0]]), ('segments', [[0, 1, 3]]),
    ('segments', [[0, 1], [2, 3]]), ('schema_version', True)])
def test_untrusted_manifest_rejected(profile_case, field, value):
    profile_case[1][field] = value
    with pytest.raises(ValueError):
        prepare(profile_case[1], profile_case[0], HASH, profile_case[2])


def test_nonmedian_vertex_and_unreviewed_mandible(profile_case):
    model, manifest, metadata = profile_case
    model.mirror_indices[[0, 3]] = [3, 0]
    with pytest.raises(ValueError, match='self-mirrored'):
        prepare(manifest, model, HASH, metadata)
    model.mirror_indices = np.arange(7)
    metadata['mandible_articulation_reviewed'] = False
    with pytest.raises(ValueError, match='mandibular'):
        prepare(manifest, model, HASH, metadata)


def test_gaps_are_explicit_and_never_interpolated(profile_case):
    model, manifest, metadata = profile_case
    model.mu[3] = [0, 0, -1]
    model.basis[:, 3] = 0
    manifest['segments'] = [[0, 1], [2, 3]]
    model.triangles = np.vstack([model.triangles, [2, 3, 4]])
    row = copy.deepcopy(manifest['samples'][-1]); row['bone_xyz_mm'] = model.mu[3].tolist()
    manifest['samples'][-1]['label'] = 'SyntheticLower'
    manifest['samples'].append(row)
    manifest['gap_notes'] = ['Synthetic missing connection; do not fill']
    p = prepare(manifest, model, HASH, metadata)
    np.testing.assert_array_equal(p['indices'], [0, 1, 2, 3])
    assert len(p['targets']) == 4


def test_template_safe_and_unconfigured(tmp_path, profile_case):
    path = tmp_path/'profile.json'
    assert main(['--template', str(path)]) == 0
    assert json.loads(path.read_text()) == empty_manifest()
    with pytest.raises(SystemExit):
        main(['--template', str(path)])
    with pytest.raises(ValueError):
        prepare(empty_manifest(), profile_case[0], HASH, profile_case[2])


@pytest.mark.parametrize('kwargs', [dict(skip_tps=False), dict(measurement_weight=1.),
    dict(symmetry_weight=1.), dict(distance_weight=1.), dict(prior_soft_sigma=1.),
    dict(exclude_outliers=True), dict(prior='missing.npz'), dict(skull='missing.obj'),
    dict(protocol='missing.json'), dict(tissue_compare='a,b')])
def test_incompatible_losses_fail_before_any_export(tmp_path, model_file, marker_file, kwargs):
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file),
        output=str(tmp_path/'face.obj'), profile_constraint='missing.json', **kwargs)
    assert run_pipeline(cfg) == 2
    assert not Path(cfg.output).exists()


def pipeline_manifest(model_file, marker_file, manifest_path):
    from cranio.backend import GNMBackend
    model = GNMBackend(str(model_file)).load()
    lines = marker_file.read_text().splitlines()
    metadata = json.loads(lines[1][1:])
    metadata.update(case_id='synthetic', mandible_articulation_reviewed=True,
                    bone_sources=[dict(id='bone', geometry_sha256=BONE)])
    lines[1] = '# '+json.dumps(metadata)
    marker_file.write_text('\n'.join(lines)+'\n')
    manifest = empty_manifest()
    manifest.update(model_sha256=sha256_file(model_file), case_id='synthetic',
        source='Synthetic pipeline fixture', mapping_reviewed=True, mandible_reviewed=True,
        plane=dict(origin_mm=[0, 0, 0], normal_world=[1, 0, 0], source='Synthetic wide plane band', reviewed=True),
        plane_tolerance_mm=1000., segments=[[0, 1, 2]], strength=30., delta_regularization=1.,
        marker_preservation_weight=.1, marker_displacement_limit_mm=1000.)
    targets = model.generate(np.array([.2, 0, 0]))
    manifest['samples'] = [dict(label=label, bone_xyz_mm=targets[i].tolist(), normal_world=[0, 1, 0],
        source_id='bone', source_geometry_sha256=BONE, status='observed', reviewed=True,
        depth_mm=0., sd_mm=1., tissue_source='Synthetic zero offset', direction='bone_normal')
        for i, label in enumerate(['Glabella', 'SyntheticMiddle', 'Menton'])]
    manifest_path.write_text(json.dumps(manifest))


def test_pipeline_report_replay_and_disabled_mesh_parity(tmp_path, model_file, marker_file):
    from gnm_reconstruct import parse_args
    manifest_path = tmp_path/'profile.json'
    pipeline_manifest(model_file, marker_file, manifest_path)
    baseline = PipelineConfig(input=str(marker_file), npz=str(model_file),
        output=str(tmp_path/'baseline.obj'), regularization='30')
    assert run_pipeline(baseline) == 0
    cfg = parse_args(['--input', str(marker_file), '--npz', str(model_file), '--output', str(tmp_path/'profile.obj'),
        '--regularization', '30', '--profile-constraint', str(manifest_path)])
    assert run_pipeline(cfg) == 0
    report = json.loads(Path(cfg.output_json).read_text())
    record = report['marker_metadata']['profile_constraint']
    assert record['status'] == 'accepted'
    assert all(p['final_mm'] <= p['before_mm']+1e-12 for p in record['points'])
    assert report['inputs']['profile_constraint']['sha256'] == sha256_file(manifest_path)
    assert report['identity_coefficients'] == record['final_coefficients']
    assert report['solver']['scope'].startswith('Baseline')
    assert 'Optional reviewed profile' in Path(cfg.output_stats).read_text()
    original = json.loads(Path(baseline.output_json).read_text())
    assert original['transform'] == report['transform']
    assert original['identity_coefficients'] == record['baseline_coefficients']
    assert Path(cfg.output).read_bytes() != Path(baseline.output).read_bytes()
    cfg.output = str(tmp_path/'replay.obj')
    for name in ('output_json', 'output_statistical', 'output_stats', 'output_error_mesh'):
        setattr(cfg, name, None)
    assert run_pipeline(cfg) == 0
    replay = json.loads(Path(cfg.output_json).read_text())
    assert replay['marker_metadata']['profile_constraint'] == record
    assert (tmp_path/'profile.obj').read_bytes() == (tmp_path/'replay.obj').read_bytes()
    cfg.profile_constraint = None
    cfg.output = str(tmp_path/'disabled.obj')
    for name in ('output_json', 'output_statistical', 'output_stats', 'output_error_mesh'):
        setattr(cfg, name, None)
    assert run_pipeline(cfg) == 0
    for name in ('output', 'output_statistical', 'output_error_mesh'):
        assert Path(getattr(cfg, name)).read_bytes() == Path(getattr(baseline, name)).read_bytes()


def test_manifest_input_output_collision(tmp_path, model_file, marker_file):
    path = tmp_path/'profile.json'
    pipeline_manifest(model_file, marker_file, path)
    before = path.read_bytes()
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), profile_constraint=str(path),
                         output=str(path), overwrite=True)
    assert run_pipeline(cfg) == 2
    assert path.read_bytes() == before


def test_frozen_protocol_refuses_profile():
    from cranio.protocol import frozen_from_report
    with pytest.raises(ValueError, match='Profile refinement'):
        frozen_from_report({'config': {'profile_constraint': 'profile.json'}}, 'synthetic', HASH)


def test_numerically_rank_deficient_system_is_not_silently_accepted(profile_case):
    profile_case[0].basis[1] = 0.
    profile_case[1]['delta_regularization'] = 1e-300
    with pytest.raises(ValueError, match='rank-deficient'):
        fitted(profile_case)


def test_reflection_and_nonfinite_pose_rejected(profile_case):
    model, manifest, metadata = profile_case
    prepared = prepare(manifest, model, HASH, metadata)
    for rotation in (np.diag([-1., 1, 1]), np.eye(3)*float('nan')):
        with pytest.raises(ValueError):
            refine(model, np.zeros(2), 1., rotation, np.zeros(3), np.array([3, 4, 5, 6]),
                   np.ones(4), prepared, clip_sigma=3.)

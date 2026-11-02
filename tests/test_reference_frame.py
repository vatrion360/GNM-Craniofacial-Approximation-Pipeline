"""Synthetic geometry/provenance checks; no anatomical accuracy claims."""
import copy
import json

import numpy as np
import pytest

from cranio import craniometry as cm, reference_frame as rf


@pytest.fixture
def case():
    xyz = dict(po_R=[50, 0, 0], po_L=[-50, 0, 0], or_L=[-25, 60, 0],
               or_R=[25, 60, 0], n=[0, 60, 30], b=[0, 0, 80], op=[0, -65, 10])
    doc = cm.empty_document('synthetic-frame')
    doc['bone_sources'] = [dict(id='synthetic', geometry_sha256='a'*64)]
    doc['points'] = [dict(code=c, xyz_mm=p, status='observed', definition_reviewed=True,
        source_id='synthetic', source_geometry_sha256='a'*64,
        definition_text='Synthetic definition, not anatomical evidence',
        definition_source='Synthetic software test') for c, p in xyz.items()]
    config = dict(schema_version=1, orbitale='or_L', superior_code='b', midline_codes=['n', 'b', 'op'],
                  source='Synthetic test configuration', placement_error=None)
    return doc, config


def test_known_pose_and_rigid_equivariance(case):
    doc, config = case
    saved = copy.deepcopy(case)
    frame = rf.compute_frame(*case)
    np.testing.assert_allclose(frame['geometry']['axes_world'], np.eye(3), atol=1e-14)
    np.testing.assert_allclose(frame['geometry']['origin_mm'], 0)
    assert frame['uncertainty']['status'] == 'not_assessed'
    assert frame['geometry']['midsagittal']['residual_rms_mm'] == 0
    q, _ = np.linalg.qr(np.random.default_rng(3).normal(size=(3, 3)))
    q[:, 0] *= np.linalg.det(q)
    offset = [12, -43, 7]
    for row in doc['points']:
        row['xyz_mm'] = (q@row['xyz_mm']+offset).tolist()
    frame = rf.compute_frame(doc, config)
    geometry = frame['geometry']
    np.testing.assert_allclose(geometry['axes_world'], q, atol=1e-14)
    np.testing.assert_allclose(geometry['origin_mm'], offset, atol=1e-14)
    np.testing.assert_allclose(np.array(geometry['world_to_frame'])@geometry['frame_to_world'], np.eye(4), atol=1e-12)
    for original, rotated in zip(saved[0]['points'], doc['points']):
        restored = np.array(geometry['world_to_frame']) @ [*rotated['xyz_mm'], 1]
        np.testing.assert_allclose(restored[:3], original['xyz_mm'], atol=1e-12)
    for view in ('front', 'profile', 'left', '3quarter'):
        camera = rf.camera_basis(frame, view)
        np.testing.assert_allclose(camera[:, 1], q[:, 2], atol=1e-14)
        np.testing.assert_allclose(camera.T@camera, np.eye(3), atol=1e-14)
        assert np.linalg.det(camera) == pytest.approx(1)


@pytest.mark.parametrize('field,value', [('status', 'reconstructed'), ('definition_reviewed', False),
    ('source_geometry_sha256', 'b'*64), ('source_id', 'absent'), ('xyz_mm', [float('nan'), 0, 0])])
def test_ineligible_evidence_refused(case, field, value):
    doc, config = case
    doc['points'][0][field] = value
    with pytest.raises(ValueError):
        rf.compute_frame(doc, config)


def test_missing_references_and_changed_source_refused(case):
    doc, config = case
    doc['points'][0].update(status='missing', xyz_mm=None)
    with pytest.raises(ValueError, match='observed'):
        rf.compute_frame(doc, config)
    doc['points'][0].update(status='observed', xyz_mm=[50, 0, 0])
    doc['bone_sources'][0]['geometry_sha256'] = 'b'*64
    with pytest.raises(ValueError, match='stale'):
        rf.compute_frame(doc, config)


@pytest.mark.parametrize('failure', ['swap', 'coincident', 'collinear_fh', 'collinear_midline', 'inferior', 'ambiguous'])
def test_geometrical_failures(case, failure):
    doc, config = case
    points = {p['code']: p for p in doc['points']}
    if failure == 'swap':
        points['po_R']['xyz_mm'], points['po_L']['xyz_mm'] = points['po_L']['xyz_mm'], points['po_R']['xyz_mm']
    elif failure == 'coincident':
        points['po_R']['xyz_mm'] = points['po_L']['xyz_mm']
    elif failure == 'collinear_fh':
        points['or_L']['xyz_mm'] = [0, 0, 0]
    elif failure == 'collinear_midline':
        for c, z in [('n', 20), ('b', 80), ('op', 50)]:
            points[c]['xyz_mm'] = [0, 0, z]
    elif failure == 'inferior':
        config['superior_code'] = 'op'
        points['op']['xyz_mm'] = [0, -65, -10]
    else:
        # Equal second/third singular values: no unique best-fit normal.
        for c, xyz in zip(('n', 'b', 'op'), ([20, 20, 20], [20, -20, -20], [-20, 20, -20])):
            points[c]['xyz_mm'] = xyz
        doc['points'].append(dict(points['n'], code='g', xyz_mm=[-20, -20, 20]))
        doc['points'].append(dict(points['n'], code='ss', xyz_mm=[0, 0, 80]))
        config.update(superior_code='ss', midline_codes=['n', 'b', 'op', 'g'])
    with pytest.raises(ValueError):
        rf.compute_frame(doc, config)


@pytest.mark.parametrize('patch', [dict(orbitale=None), dict(superior_code='me'), dict(superior_code=[]),
    dict(midline_codes=['n', 'b', 'me']), dict(midline_codes=['n', 'b', 'b']), dict(source=''), dict(unknown=3)])
def test_no_implicit_anatomical_choices(case, patch):
    case[1].update(patch)
    with pytest.raises(ValueError):
        rf.compute_frame(*case)


def test_midline_is_independent_and_signature_tracks_only_used_points(case):
    doc, config = case
    before = rf.input_signature(doc, config)
    next(p for p in doc['points'] if p['code'] == 'or_R')['xyz_mm'][0] += 5
    assert rf.input_signature(doc, config) == before
    for p in doc['points']:
        if p['code'] in config['midline_codes']:
            p['xyz_mm'][0] = .1*p['xyz_mm'][1]
    assert rf.input_signature(doc, config) != before
    g = rf.compute_frame(doc, config)['geometry']
    assert g['midsagittal']['normal_to_right_angle_deg'] == pytest.approx(np.degrees(np.arctan(.1)))
    np.testing.assert_allclose(g['axes_world'], np.eye(3), atol=1e-14)


def test_conditional_mc_seed_zero_sd_and_failed_draw_policy(case):
    doc, config = case
    codes = rf.validate_config(config)
    config['placement_error'] = dict(samples=100, seed=17,
        points={c: dict(sigma_mm=.1, source='Synthetic perturbation SD') for c in codes})
    original = copy.deepcopy(case)
    state = np.random.get_state()
    first = rf.compute_frame(*case)
    assert first == rf.compute_frame(*case)
    assert case == original
    np.testing.assert_array_equal(state[1], np.random.get_state()[1])
    assert first['uncertainty']['status'] == 'conditional_uncalibrated'
    assert min(first['uncertainty']['axis_angle_p95_deg']) > 0
    for row in config['placement_error']['points'].values():
        row['sigma_mm'] = 0
    assert rf.compute_frame(*case)['uncertainty']['axis_angle_p95_deg'] == [0., 0., 0.]
    for row in config['placement_error']['points'].values():
        row['sigma_mm'] = 10000
    with pytest.raises(ValueError, match='no draws discarded'):
        rf.compute_frame(*case)
    config['placement_error']['points'].pop(codes[0])
    with pytest.raises(ValueError, match='every used point'):
        rf.compute_frame(*case)


def test_cli_safe_repeatable_outputs(case, tmp_path):
    doc, config = case
    source, cfg = tmp_path/'bones.json', tmp_path/'config.json'
    source.write_text(json.dumps(doc)); cfg.write_text(json.dumps(config))
    first, second = tmp_path/'first.json', tmp_path/'second.json'
    for path in (first, second):
        assert rf.main(['compute', '--input', str(source), '--config', str(cfg), '--output', str(path)]) == 0
    assert first.read_bytes() == second.read_bytes()
    for path in (first, source, cfg):
        before = path.read_bytes()
        with pytest.raises(SystemExit):
            rf.main(['compute', '--input', str(source), '--config', str(cfg), '--output', str(path)])
        assert path.read_bytes() == before
    template = tmp_path/'blank.json'
    assert rf.main(['template', '--output', str(template)]) == 0
    with pytest.raises(ValueError):
        rf.validate_config(json.loads(template.read_text()))


def test_frame_metadata_does_not_change_fit(marker_file, model_file, tmp_path, case):
    from cranio.config import PipelineConfig
    from cranio.pipeline import run_pipeline
    from pathlib import Path
    lines = marker_file.read_text().splitlines(keepends=True)
    metadata = json.loads(lines[1].lstrip('# '))
    doc, _ = case
    doc['reference_frame'] = rf.compute_frame(*case)
    metadata['craniometry'] = doc
    lines[1] = '# '+json.dumps(metadata)+'\n'
    extra = tmp_path/'frame.csv'; extra.write_text(''.join(lines))
    results = []
    for name, source in [('base', marker_file), ('frame', extra)]:
        config = PipelineConfig(input=str(source), npz=str(model_file), output=str(tmp_path/f'{name}.obj'), regularization='30')
        assert run_pipeline(config) == 0
        results.append(config)
    for field in ('output', 'output_statistical', 'output_error_mesh'):
        assert Path(getattr(results[0], field)).read_bytes() == Path(getattr(results[1], field)).read_bytes()
    report = json.loads(Path(results[1].output_json).read_text())
    assert report['marker_metadata']['craniometry']['reference_frame'] == doc['reference_frame']

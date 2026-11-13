"""Metric camera planning, snapshot binding and capture-result integrity."""
import copy
from pathlib import Path

import numpy as np
import pytest

from cranio import craniometry as cm, reference_frame as rf
from cranio.capture_plan import plan, settings, reviewed_frame, load_inputs, assert_unchanged, VIEWS
from cranio.capture_job import prepare_request, read_result, start
from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline
from cranio.record import canonical_bytes, _digest
from cranio.review_export import export_bundle
from cranio.tissue import _json


def read(path):
    return _json(Path(path).read_text(encoding='utf-8'))


def document():
    xyz = dict(po_R=[50, 0, 0], po_L=[-50, 0, 0], or_L=[-25, 60, 0],
               n=[0, 60, 30], b=[0, 0, 80], op=[0, -65, 10])
    doc = cm.empty_document('synthetic captures')
    doc['bone_sources'] = [dict(id='fixture', geometry_sha256='a'*64)]
    doc['points'] = [dict(code=c, xyz_mm=p, status='observed', definition_reviewed=True,
        source_id='fixture', source_geometry_sha256='a'*64, definition_text='Synthetic definition',
        definition_source='Synthetic software fixture') for c, p in xyz.items()]
    config = dict(schema_version=1, orbitale='or_L', superior_code='b', midline_codes=['n', 'b', 'op'],
                  source='Synthetic software fixture', placement_error=None)
    doc['reference_frame'] = rf.compute_frame(doc, config)
    return doc


@pytest.fixture
def case(tmp_path, model_file, marker_file):
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), regularization='30',
                         output=str(tmp_path/'fit'/'face.obj'))
    assert run_pipeline(cfg) == 0
    report = read(cfg.output_json)
    report['marker_metadata']['craniometry'] = document()
    Path(cfg.output_json).write_bytes(canonical_bytes(report))
    bundle = tmp_path/'bundle'
    export_bundle(cfg.output_json, bundle, mode='illustrative')
    return cfg, report, bundle


def test_exact_metric_projection_and_common_scale():
    frame = document()['reference_frame']
    vertices = np.array([[-70, -30, -20], [60, 80, 60], [40, -10, 90]])
    result = plan(vertices, frame, resolution=512, bar_mm=50.)
    assert len(result['views']) == 3
    assert len({r['ortho_scale_mm'] for r in result['views']}) == 1
    for view in result['views']:
        basis = np.array(view['camera_to_world_rotation'])
        np.testing.assert_allclose(basis.T@basis, np.eye(3), atol=1e-14)
        np.testing.assert_allclose(basis[:, 1], [0, 0, 1], atol=1e-14)
        assert np.linalg.det(basis) == pytest.approx(1)
        a, b = np.array(view['bar_endpoints_world_mm'])
        assert np.linalg.norm(b-a) == pytest.approx(50.)
        assert view['bar_length_pixels'] == pytest.approx(50*512/view['ortho_scale_mm'])
        camera_xy = (vertices-np.array(view['look_at_mm']))@basis[:, :2]
        assert abs(camera_xy).max() < view['ortho_scale_mm']/2
        px = np.array(view['bar_endpoints_pixels'])
        assert np.linalg.norm(px[1]-px[0]) == pytest.approx(view['bar_length_pixels'])
        np.testing.assert_allclose(px[:, 1], .92*512)


def test_rigid_transform_equivariance_and_no_input_mutation():
    doc = document()
    vertices = np.array([[-70, -30, -20], [60, 80, 60], [40, -10, 90]])
    original = plan(vertices, doc['reference_frame'])
    q, _ = np.linalg.qr(np.random.default_rng(2).normal(size=(3, 3)))
    q[:, 0] *= np.linalg.det(q)
    shift = np.array([15, -23, 9])
    for p in doc['points']: p['xyz_mm'] = (q@p['xyz_mm']+shift).tolist()
    frame = rf.compute_frame(doc, doc['reference_frame']['configuration'])
    transformed = plan(vertices@q.T+shift, frame)
    for a, b in zip(original['views'], transformed['views']):
        np.testing.assert_allclose(np.array(b['camera_to_world_rotation']), q@a['camera_to_world_rotation'], atol=1e-14)
        np.testing.assert_allclose(b['camera_location_mm'], q@a['camera_location_mm']+shift, atol=1e-12)
        np.testing.assert_allclose(b['bar_endpoints_pixels'], a['bar_endpoints_pixels'], atol=1e-12)
    before = copy.deepcopy(frame)
    assert canonical_bytes(plan(vertices@q.T+shift, frame)) == canonical_bytes(transformed)
    assert frame == before


@pytest.mark.parametrize('kwargs', [dict(resolution=True), dict(resolution=127), dict(resolution=4097),
    dict(resolution=256.), dict(samples=0), dict(samples=True), dict(samples=129),
    dict(bar_mm=0), dict(bar_mm=-1), dict(bar_mm=float('nan')), dict(bar_mm=float('inf')), dict(bar_mm=True)])
def test_invalid_capture_options_rejected(kwargs):
    with pytest.raises(ValueError): settings(**kwargs)


def test_oversized_bar_and_degenerate_mesh_rejected():
    frame = document()['reference_frame']
    with pytest.raises(ValueError): plan(np.zeros((3, 3)), frame)
    with pytest.raises(ValueError): plan([[1, 2, 3]], frame, bar_mm=50)
    with pytest.raises(ValueError): plan([[1, 2, float('nan')]], frame)


@pytest.mark.parametrize('change', ['missing', 'stale', 'signature', 'unreviewed', 'reconstructed', 'missing_porion'])
def test_frame_never_guessed_for_incomplete_or_unreviewed_evidence(case, change):
    report = case[1]
    doc = report['marker_metadata']['craniometry']
    if change == 'missing': doc.pop('reference_frame')
    elif change == 'stale': doc['reference_frame']['status'] = 'stale'
    elif change == 'signature': doc['reference_frame']['input_signature'] = 'b'*64
    elif change == 'unreviewed': doc['points'][0]['definition_reviewed'] = False
    elif change == 'reconstructed': doc['points'][0]['status'] = 'reconstructed'
    else: doc['points'] = [p for p in doc['points'] if p['code'] != 'po_L']
    with pytest.raises(ValueError): reviewed_frame(report)


def test_cached_axes_not_trusted(case):
    frame = reviewed_frame(case[1])
    case[1]['marker_metadata']['craniometry']['reference_frame']['geometry']['axes_world'] = [[999]*3]*3
    assert reviewed_frame(case[1])['geometry'] == frame['geometry']


def test_load_bound_bundle_and_pin_all_fixed_sources(case):
    cfg, _, bundle = case
    vertices, triangles, recipe, pinned = load_inputs(cfg.output_json, bundle, resolution=256, samples=2)
    assert vertices.shape == (12, 3) and triangles.shape == (2, 3)
    assert recipe['export_mode'] == 'illustrative'
    assert recipe['final_mesh_uncertainty'] == 'not_assessed'
    assert len(pinned) == 8
    assert_unchanged(pinned)
    path = bundle/'face.obj'
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError, match='changed'): assert_unchanged(pinned)
    with pytest.raises(ValueError, match='checksum'): load_inputs(cfg.output_json, bundle)


def test_prepare_refuses_wrong_report_or_blocked_bundle(case, tmp_path):
    cfg, _, bundle = case
    marker = bundle/'export_decision.json'
    req = prepare_request(cfg.output_json, marker)
    assert req['bundle_sha256'] == _digest(marker.read_bytes())
    decision = read(marker)
    decision['status'] = 'blocked'
    marker.write_bytes(canonical_bytes(decision))
    with pytest.raises(ValueError): prepare_request(cfg.output_json, marker)
    with pytest.raises(ValueError): load_inputs(cfg.output_json, bundle)
    with pytest.raises(ValueError): prepare_request(cfg.output_json, tmp_path/'other.json')


def fake_completion(case, tmp_path):
    """Integrity-only fixture: not presented as a rendered-image test."""
    cfg, _, bundle = case
    request = prepare_request(cfg.output_json, bundle/'export_decision.json')
    _, _, result, _ = load_inputs(cfg.output_json, bundle)
    out = tmp_path/'captures'
    out.mkdir()
    files = {}
    for view in VIEWS:
        raw = b'\x89PNG\r\n\x1a\nsynthetic integrity payload'
        (out/(view+'.png')).write_bytes(raw)
        files[view+'.png'] = dict(sha256=_digest(raw))
    result.update(kind='standardized_saved_fit_captures', status='completed', files=files)
    (out/'capture_manifest.json').write_bytes(canonical_bytes(result))
    return request, out


def test_fixed_output_manifest_and_source_binding(case, tmp_path):
    req, out = fake_completion(case, tmp_path)
    assert read_result(out, req)['status'] == 'completed'
    marker = out/'capture_manifest.json'
    result = read(marker)
    result['files']['../outside.png'] = dict(sha256='a'*64)
    marker.write_bytes(canonical_bytes(result))
    with pytest.raises(ValueError, match='Unexpected'): read_result(out, req)


@pytest.mark.parametrize('change', ['image', 'report', 'bundle', 'settings'])
def test_changed_capture_or_request_not_displayed(case, tmp_path, change):
    req, out = fake_completion(case, tmp_path)
    if change == 'settings': req['bar_mm'] = 51.
    else:
        path = out/'front.png' if change == 'image' else Path(req[change+'_path'])
        path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError): read_result(out, req)


def test_fixed_background_command_and_no_shell(case, tmp_path, monkeypatch):
    import cranio.capture_job as job
    req = prepare_request(case[0].output_json, case[2]/'export_decision.json')
    executable = tmp_path/'blender'
    executable.write_text('synthetic executable placeholder', encoding='utf-8')
    calls = []
    monkeypatch.setattr(job.subprocess, 'Popen', lambda command, **kwargs: calls.append((command, kwargs)))
    with (tmp_path/'log').open('w', encoding='utf-8') as log:
        start(executable, Path(__file__).resolve().parents[1], req, tmp_path/'captures șță', log)
    command, kwargs = calls[0]
    assert command[:3] == [str(executable), '--background', '--factory-startup']
    assert '--python-exit-code' in command and '--' in command
    assert str(Path(__file__).resolve().parents[1]/'cranio'/'capture_render.py') in command
    assert kwargs['shell'] is False

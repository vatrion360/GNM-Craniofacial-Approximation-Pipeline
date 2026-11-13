"""Saved QC aggregation, serialized geometry and honest incomplete assessments."""
import copy
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import pytest

from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline
from cranio.consistency import triangle_angles, clearance_summary, summarize, build_summary, read_result, FILES
from cranio.record import canonical_bytes, _digest
from cranio.record_job import prepare_consistency_request, start_consistency


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


@pytest.fixture
def case(tmp_path, model_file, marker_file):
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), regularization='30',
                         output=str(tmp_path/'fit'/'face.obj'))
    assert run_pipeline(cfg) == 0
    return cfg


def simple_mesh():
    return np.array([[0., 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]]), np.array([[0, 1, 2], [1, 2, 3]])


@pytest.mark.parametrize('scale', [1e-100, 1., 1e100])
def test_triangle_angles_known_geometry_and_scale(scale):
    vertices = scale*np.array([[0., 0, 0], [1, 0, 0], [.5, np.sqrt(3)/2, 0], [2, 0, 0]])
    result = triangle_angles(vertices, [[0, 1, 2]])
    assert result['minimum_angle_deg'] == pytest.approx(60)
    assert result['degenerate_face_indices'] == []
    result = triangle_angles(vertices, [[0, 1, 3]])
    assert result['minimum_angle_deg'] == 0 and result['degenerate_face_indices'] == [0]
    assert triangle_angles(np.zeros((3, 3)), [[0, 1, 2]])['degenerate_face_indices'] == [0]


def test_right_triangle_and_rigid_motion():
    v, t = simple_mesh()
    reference = triangle_angles(v, t)
    q, _ = np.linalg.qr(np.random.default_rng(3).normal(size=(3, 3)))
    assert reference['minimum_angle_deg'] == pytest.approx(45.)
    assert triangle_angles(v@q+10, t)['minimum_angle_deg'] == pytest.approx(45.)


@pytest.mark.parametrize('v,t', [([], [[0, 1, 2]]), ([[0., 0, float('nan')]], [[0, 0, 0]]),
    ([[0., 0, 0]], [[-1, 0, 0]]), ([[0., 0, 0]], [[0, 1, 2]]),
    ([[0., 0, 0]], [[0., 0., 0.]]), ([[0., 0, 0]], [[True, True, True]]),
    ([[0., 0, 0]], []), ([[1e308, 0, 0], [-1e308, 0, 0], [0, 1, 0]], [[0, 1, 2]])])
def test_bad_geometry_rejected(v, t):
    with pytest.raises(ValueError): triangle_angles(v, t)


def samples():
    # Synthetic signed local offsets, not tissue-table or anatomical values.
    return dict(sample_indices=[1, 3, 5, 7], outward_clearance_mm=[-2., -.1, 2., 4.],
                negative_clearance_count=1, tolerance_mm=.1)


def test_local_sample_statistics_do_not_claim_tissue_depth_or_area():
    s = clearance_summary(samples())
    assert s['sample_count'] == 4 and s['negative_sample_percent'] == 25.
    assert s['median_mm'] == pytest.approx(.95)
    assert s['p10_mm'] == pytest.approx(-1.43)
    assert s['p90_mm'] == pytest.approx(3.4)
    assert s['tolerance_provenance'] == 'legacy_hardcoded'
    assert 'not surface-area fraction' in s['interpretation']
    assert clearance_summary(None)['status'] == 'not_assessed'
    assert clearance_summary(dict(negative_clearance_count=0))['status'] == 'not_assessed'


@pytest.mark.parametrize('key,value', [('sample_indices', [1, 1, 5, 7]),
    ('outward_clearance_mm', [-2., -.1, 2.]), ('outward_clearance_mm', [True, 0., 2., 4.]),
    ('outward_clearance_mm', [float('nan'), 0., 2., 4.]), ('negative_clearance_count', 0),
    ('negative_clearance_count', True), ('tolerance_mm', -1.), ('tolerance_mm', float('inf'))])
def test_invalid_or_contradictory_clearance_is_not_reported(key, value):
    s = samples()
    s[key] = value
    with pytest.raises(ValueError): clearance_summary(s)


def test_basic_and_missing_qc_never_become_complete(case):
    report = read(case.output_json)
    before = copy.deepcopy(report)
    meshes = dict(statistical=simple_mesh(), final=simple_mesh())
    summary = summarize(report, meshes)
    assert report == before
    assert summary['recorded_geometry_check']['status'] == 'warn'
    assert summary['status'] == 'not_assessed' and summary['light'] == 'gray'
    assert summary['correction_applied'] is False
    assert all(row['status'] == 'not_assessed' for row in summary['unavailable_checks'].values())
    report.pop('geometry_quality')
    assert summarize(report, meshes)['recorded_geometry_check']['status'] == 'not_assessed'


@pytest.mark.parametrize('defect', ['collapse', 'solver', 'legacy', 'clearance', 'reversal'])
def test_known_failures_remain_red_with_unassessed_checks(case, defect):
    report = read(case.output_json)
    meshes = dict(statistical=simple_mesh(), final=simple_mesh())
    if defect == 'collapse': meshes['final'][0][:] = 0
    elif defect == 'solver': report['solver']['converged'] = False
    elif defect == 'legacy': report['geometry_quality']['status'] = 'needs_review'
    elif defect == 'reversal': report['geometry_quality']['final']['normal_reversed_faces'] = [0]
    else: report['geometry_quality']['final']['bone_clearance'] = samples()
    s = summarize(report, meshes)
    assert s['status'] == 'block' and s['light'] == 'red'


def test_complete_recorded_qc_still_does_not_establish_anatomical_completeness(case):
    report = read(case.output_json)
    q = report['geometry_quality']
    q.update(mode='full', status='passed_full_checks', baseline_contacts=dict(complete=True, pairs=[]))
    for stage in ('statistical', 'final'):
        q[stage].update(contacts=dict(complete=True, pairs=[], candidate_pairs_tested=0), new_contact_face_pairs=[],
            bone_clearance=dict(sample_indices=[0], outward_clearance_mm=[3.], negative_clearance_count=0, tolerance_mm=.1))
    s = summarize(report, dict(statistical=simple_mesh(), final=simple_mesh()))
    assert s['recorded_geometry_check']['status'] == 'pass'
    assert s['status'] == 'not_assessed'
    q['final']['contacts']['complete'] = False
    assert summarize(report, dict(statistical=simple_mesh(), final=simple_mesh()))['stages']['final']['recorded_contacts']['status'] == 'incomplete'


def test_malformed_indices_and_topology_rejected(case):
    report = read(case.output_json)
    meshes = dict(statistical=simple_mesh(), final=simple_mesh())
    meshes['final'][1][0] = [1, 0, 2]
    with pytest.raises(ValueError, match='topology'): summarize(report, meshes)
    meshes = dict(statistical=simple_mesh(), final=simple_mesh())
    report['geometry_quality']['final']['normal_reversed_faces'] = [99]
    with pytest.raises(ValueError, match='indices'): summarize(report, meshes)


@pytest.mark.parametrize('pairs', [[[1, 0]], [[0, 0]], [[0, 2]], [[False, 1]], [[0, 1], [0, 1]]])
def test_recorded_contact_index_spaces_are_validated(case, pairs):
    report = read(case.output_json)
    report['geometry_quality']['contact_face_indices'] = [0, 1]
    report['geometry_quality']['final']['contacts'] = dict(complete=True, pairs=pairs)
    with pytest.raises(ValueError, match='contact pairs'):
        summarize(report, dict(statistical=simple_mesh(), final=simple_mesh()))


def test_new_contacts_preserved_as_red_even_with_basic_status(case):
    report = read(case.output_json)
    report['geometry_quality']['contact_face_indices'] = [0, 1]
    report['geometry_quality']['final'].update(contacts=dict(complete=True, pairs=[[0, 1]]), new_contact_face_pairs=[[0, 1]])
    s = summarize(report, dict(statistical=simple_mesh(), final=simple_mesh()))
    assert s['status'] == 'block'
    assert s['stages']['final']['recorded_contacts']['new_count'] == 1


def test_huge_numeric_values_fail_cleanly():
    with pytest.raises(ValueError): triangle_angles([[10**1000, 0, 0]]*3, [[0, 1, 2]])
    for key in ('tolerance_mm', 'outward_clearance_mm'):
        value = samples()
        value[key] = 10**1000 if key == 'tolerance_mm' else [10**1000]*4
        with pytest.raises(ValueError): clearance_summary(value)


def test_build_reproducible_metrics_and_immutable_inputs(case, tmp_path):
    request = prepare_consistency_request(case.output_json)
    before = {p: p.read_bytes() for p in Path(case.output).parent.iterdir() if p.is_file()}
    for name in ('first', 'second'):
        build_summary(case.output_json, tmp_path/name)
    a, b = tmp_path/'first', tmp_path/'second'
    assert (a/'consistency.json').read_bytes() == (b/'consistency.json').read_bytes()
    summary, page = read_result(a, request)
    assert summary['source_report_sha256'] == request['report_sha256']
    assert 'NOT ASSESSED' in page and 'No correction applied' in page
    assert all(p.read_bytes() == data for p, data in before.items())
    with pytest.raises(ValueError, match='exists'): build_summary(case.output_json, a)


@pytest.mark.parametrize('name', FILES)
def test_changed_result_refused(case, tmp_path, name):
    out = tmp_path/'summary'
    build_summary(case.output_json, out)
    path = out/name
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError, match='checksum'): read_result(out, prepare_consistency_request(case.output_json))


def test_unexpected_manifest_paths_and_source_drift_refused(case, tmp_path):
    req = prepare_consistency_request(case.output_json)
    out = tmp_path/'summary'
    build_summary(case.output_json, out)
    marker = out/'consistency_manifest.json'
    raw = marker.read_bytes()
    value = read(marker)
    value['files']['../outside'] = dict(sha256='a'*64)
    marker.write_bytes(canonical_bytes(value))
    with pytest.raises(ValueError, match='Unexpected'): read_result(out, req)
    marker.write_bytes(raw)
    path = Path(case.output_json)
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError, match='changed after submission'): read_result(out, req)


@pytest.mark.parametrize('target', ['report', 'mesh', 'page'])
def test_mid_export_drift_has_no_completion_marker(case, tmp_path, monkeypatch, target):
    import cranio.export as export
    original = export.atomic_text
    out = tmp_path/'summary'
    @contextmanager
    def changed(path, **kwargs):
        with original(path, **kwargs) as stream: yield stream
        if Path(path).name == 'consistency.json':
            path = {'report': Path(case.output_json), 'mesh': Path(case.output), 'page': out/'consistency.json'}[target]
            path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(export, 'atomic_text', changed)
    if target == 'page':
        # Corrupt during the final manifest transaction, after output hashes exist.
        @contextmanager
        def changed(path, **kwargs):
            if Path(path).name == 'consistency_manifest.json':
                p = out/'consistency.txt'
                p.write_bytes(p.read_bytes()+b' ')
            with original(path, **kwargs) as stream: yield stream
        monkeypatch.setattr(export, 'atomic_text', changed)
    with pytest.raises(ValueError, match='changed'): build_summary(case.output_json, out)
    assert not (out/'consistency_manifest.json').exists()


def test_moved_windows_artifacts_and_external_process(case, tmp_path, monkeypatch):
    artifacts = tmp_path/'moved șță & literal'
    shutil.copytree(Path(case.output).parent, artifacts)
    document = read(case.output_json)
    for row in document['outputs'].values(): row['path'] = 'C:\\old\\'+Path(row['path']).name
    report = tmp_path/'relocated.json'
    report.write_bytes(canonical_bytes(document))
    req = prepare_consistency_request(report, artifacts=artifacts)
    assert req['kind'] == 'postfit_consistency'
    monkeypatch.setenv('PYTHONHOME', '/wrong/blender/python')
    monkeypatch.setenv('PYTHONPATH', '/wrong/blender/modules')
    out, log = tmp_path/'result șță & literal', tmp_path/'run.log'
    with log.open('w', encoding='utf-8') as stream:
        process = start_consistency(dict(executable=sys.executable), Path(__file__).resolve().parents[1], req, out, stream)
        assert process.wait(timeout=30) == 0, log.read_text(encoding='utf-8')
    assert read_result(out, req)[0]['status'] == 'not_assessed'


def test_corrupt_mesh_and_unsupported_obj_never_complete(case, tmp_path):
    path = Path(case.output)
    path.write_bytes(path.read_bytes()+b'mtllib /not-opened/external.mtl\n')
    with pytest.raises(ValueError, match='checksum'): build_summary(case.output_json, tmp_path/'checksum')
    report = read(case.output_json)
    report['outputs']['output']['sha256'] = _digest(path.read_bytes())
    Path(case.output_json).write_bytes(canonical_bytes(report))
    with pytest.raises(ValueError, match='Unsupported'): build_summary(case.output_json, tmp_path/'dialect')
    assert not (tmp_path/'dialect'/'consistency_manifest.json').exists()

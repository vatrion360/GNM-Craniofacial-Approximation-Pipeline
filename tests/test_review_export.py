"""Saved-mesh export gates and provenance; synthetic data, no anatomical validation."""
import json
from contextlib import contextmanager
from pathlib import Path
import sys

import numpy as np
import pytest

from cranio.check_policy import empty_policy
from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline
from cranio.record import canonical_bytes
from cranio.record_job import prepare_export_request, start_export
from cranio.review_export import export_bundle, geometry_lines, read_result, main, RECORD_FILES
from cranio.validation import sha256_file


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


@pytest.fixture
def case(tmp_path, model_file, marker_file):
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), regularization='30',
                         output=str(tmp_path/'fit șță & literal'/'face.obj'))
    assert run_pipeline(cfg) == 0
    policy = tmp_path/'policy.json'
    policy.write_bytes(canonical_bytes(empty_policy()))
    return cfg, policy


def request(case, mode='scientific', **kwargs):
    return prepare_export_request(case[0].output_json, mode=mode,
                                  check_policy=case[1] if mode == 'scientific' else None, **kwargs)


def mesh_rows(path):
    return [line.split() for line in Path(path).read_text(encoding='utf-8').splitlines()
            if line.startswith(('v ', 'f '))]


def test_held_export_has_diagnostics_but_no_mesh(case, tmp_path):
    cfg, policy = case
    output = tmp_path/'held'
    path = export_bundle(cfg.output_json, output, mode='scientific', check_policy_path=policy)
    result, page = read_result(output, request(case))
    assert result == read(path)
    assert result['status'] == 'blocked' and result['label'] == 'SCIENTIFIC EXPORT BLOCKED'
    assert set(result['files']) == {'README.txt', *RECORD_FILES}
    assert not (output/'face.obj').exists() and not (output/'face.mtl').exists()
    assert result['check_gate']['proceed'] is False
    assert 'No face mesh was exported' in page


def test_override_retains_findings_and_exact_geometry(case, tmp_path):
    cfg, policy = case
    before = {Path(p): Path(p).read_bytes() for p in (cfg.output, cfg.output_json, cfg.input, cfg.npz)}
    out = tmp_path/'overridden'
    export_bundle(cfg.output_json, out, mode='scientific', check_policy_path=policy,
                  check_override='Synthetic investigation; not approval')
    result, page = read_result(out, request(case, check_override='Synthetic investigation; not approval'))
    assert result['status'] == 'completed'
    assert result['check_gate']['status'] == 'overridden'
    assert result['check_policy_status'] == 'not_assessed'
    assert 'WITH RECORDED OVERRIDE' in result['label']
    assert result['scientific_export_authorization'] == 'not_assessed'
    assert result['textures'] is False and result['geometry_transformed'] is False
    assert mesh_rows(out/'face.obj') == mesh_rows(cfg.output)
    assert 'Synthetic investigation; not approval' in page
    assert 'Synthetic investigation; not approval' in (out/'face.obj').read_text(encoding='utf-8')
    assert 'map_' not in (out/'face.mtl').read_text(encoding='utf-8')
    assert all(path.read_bytes() == data for path, data in before.items())
    assert read(out/'record'/'approximation_record.json')['status'] == 'diagnostic_only'
    with pytest.raises(ValueError, match='exists'):
        export_bundle(cfg.output_json, out, mode='scientific', check_policy_path=policy)


def test_illustrative_is_labelled_even_with_failed_policy(case, tmp_path):
    cfg, policy = case
    report = read(cfg.output_json)
    report['solver']['converged'] = False
    Path(cfg.output_json).write_bytes(canonical_bytes(report))
    out = tmp_path/'illustrative'
    export_bundle(cfg.output_json, out, mode='illustrative', check_policy_path=policy)
    result, page = read_result(out, prepare_export_request(cfg.output_json, mode='illustrative', check_policy=policy))
    assert result['status'] == 'completed' and result['check_gate']['proceed'] is False
    assert result['check_policy_status'] == 'block'
    assert result['policy_applied_to_export'] is False
    assert result['label'] == 'ILLUSTRATIVE — NOT VALIDATED'
    assert 'ILLUSTRATIVE' in page and 'ILLUSTRATIVE' in (out/'face.obj').read_text(encoding='utf-8')
    assert mesh_rows(out/'face.obj') == mesh_rows(cfg.output)


def test_illustrative_without_policy_does_not_imply_checks_passed(case, tmp_path):
    out = tmp_path/'illustrative'
    export_bundle(case[0].output_json, out, mode='illustrative')
    result, _ = read_result(out, request(case, 'illustrative'))
    assert result['check_gate'] is None and result['check_policy_status'] is None
    assert result['final_mesh_uncertainty'] == 'not_assessed'


@pytest.mark.parametrize('options', [dict(mode='NONE'), dict(mode='scientific'), dict(mode='other')])
def test_missing_mode_or_policy_fails_before_output(case, tmp_path, options):
    with pytest.raises(ValueError): export_bundle(case[0].output_json, tmp_path/'bad', **options)
    assert not (tmp_path/'bad').exists()
    with pytest.raises(ValueError): prepare_export_request(case[0].output_json, **options)


@pytest.mark.parametrize('line', ['mtllib secret.mtl', 'usemtl Textured', 'vt 0 1', 'vn 0 0 1',
    'f 1/1 2/2 3/3', 'f -1 -2 -3', 'f 1 1 2', 'f 1 2 99', 'f 1 2 3 4',
    'v nan 0 0', 'v inf 0 0', 'v 0 0', 'v 1e999 0 0', 'call other.obj'])
def test_rejects_non_pipeline_obj_dialects(line):
    valid = 'v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n'
    with pytest.raises(ValueError): geometry_lines((valid+line+'\n').encode())


def test_geometry_literals_and_faces_preserved():
    raw = b'# input comment\n v +0.0 0.000000 1e-3\nv 1 0 0\nv 0 1 0\nf 1 2 3\n'
    lines, counts = geometry_lines(raw)
    assert lines[0] == 'v +0.0 0.000000 1e-3'
    assert counts == dict(vertices=3, triangles=1)
    with pytest.raises(ValueError): geometry_lines(b'# empty')


def test_material_in_source_refused_even_with_valid_checksum(case, tmp_path):
    cfg, _ = case
    path = Path(cfg.output)
    path.write_bytes(path.read_bytes()+b'mtllib /not-opened/secret.mtl\n')
    report = read(cfg.output_json)
    report['outputs']['output']['sha256'] = sha256_file(path)
    Path(cfg.output_json).write_bytes(canonical_bytes(report))
    with pytest.raises(ValueError, match='Unsupported saved-fit OBJ'):
        export_bundle(cfg.output_json, tmp_path/'bad', mode='illustrative')
    assert not (tmp_path/'bad').exists()


def test_mesh_checksum_mismatch_refused(case, tmp_path):
    cfg, _ = case
    Path(cfg.output).write_bytes(Path(cfg.output).read_bytes()+b'# changed\n')
    with pytest.raises(ValueError, match='checksum'):
        export_bundle(cfg.output_json, tmp_path/'bad', mode='illustrative')
    assert not (tmp_path/'bad').exists()


@pytest.mark.parametrize('name', ['face.obj', 'face.mtl', 'README.txt', *RECORD_FILES])
def test_result_hashes_verified(case, tmp_path, name):
    out = tmp_path/'out'
    export_bundle(case[0].output_json, out, mode='illustrative')
    path = out/name
    path.write_bytes(path.read_bytes()+b'changed')
    with pytest.raises(ValueError, match='checksum'): read_result(out, request(case, 'illustrative'))


@pytest.mark.parametrize('field,value', [('mode', 'scientific'), ('status', 'unknown'),
    ('source_report_sha256', 'a'*64), ('source_final_mesh_sha256', 'b'*64), ('kind', 'other'), ('schema_version', True)])
def test_wrong_result_binding_rejected(case, tmp_path, field, value):
    out = tmp_path/'out'
    path = export_bundle(case[0].output_json, out, mode='illustrative')
    result = read(path)
    result[field] = value
    path.write_bytes(canonical_bytes(result))
    with pytest.raises(ValueError): read_result(out, request(case, 'illustrative'))


def test_unexpected_manifest_path_never_opened(case, tmp_path):
    out = tmp_path/'out'
    path = export_bundle(case[0].output_json, out, mode='illustrative')
    result = read(path)
    result['files']['../external'] = dict(sha256='a'*64)
    path.write_bytes(canonical_bytes(result))
    with pytest.raises(ValueError, match='Unexpected export file manifest'):
        read_result(out, request(case, 'illustrative'))


@pytest.mark.parametrize('changing', ['report', 'mesh', 'policy', 'export'])
def test_input_or_output_drift_prevents_completion(case, tmp_path, monkeypatch, changing):
    import cranio.export
    cfg, policy = case
    out = tmp_path/'out'
    original = cranio.export.atomic_text
    @contextmanager
    def changed(path, **kwargs):
        with original(path, **kwargs) as stream:
            yield stream
        if Path(path).name == 'README.txt':
            target = {'report': Path(cfg.output_json), 'mesh': Path(cfg.output),
                      'policy': policy, 'export': out/'face.obj'}[changing]
            target.write_bytes(target.read_bytes()+b' ')
    monkeypatch.setattr(cranio.export, 'atomic_text', changed)
    with pytest.raises(ValueError, match='changed'):
        export_bundle(cfg.output_json, out, mode='illustrative', check_policy_path=policy)
    assert not (out/'export_decision.json').exists()


def test_process_and_exit_codes_preserve_blocked_result(case, tmp_path, monkeypatch):
    monkeypatch.setenv('PYTHONHOME', '/bad/blender/python')
    monkeypatch.setenv('PYTHONPATH', '/bad/blender/modules')
    req = request(case)
    out = tmp_path/'export șță & literal'
    log = tmp_path/'run.log'
    with log.open('w', encoding='utf-8') as stream:
        process = start_export(dict(executable=sys.executable), Path(__file__).resolve().parents[1], req, out, stream)
        assert process.wait(timeout=30) == 3, log.read_text(encoding='utf-8')
    assert read_result(out, req)[0]['status'] == 'blocked'
    assert main(['build', '--report', case[0].output_json, '--output-dir', str(tmp_path/'cli'),
                 '--mode', 'scientific', '--check-policy', str(case[1]), '--allow-blocked', 'Synthetic test']) == 0


def test_source_changed_after_click_cannot_display_result(case, tmp_path):
    req = request(case, 'illustrative')
    out = tmp_path/'out'
    export_bundle(case[0].output_json, out, mode='illustrative')
    path = Path(case[0].output_json)
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError, match='changed after submission'): read_result(out, req)


def test_no_external_symlink_output_accepted(case, tmp_path):
    out = tmp_path/'out'
    export_bundle(case[0].output_json, out, mode='illustrative')
    moved = tmp_path/'moved.obj'
    (out/'face.obj').rename(moved)
    try: (out/'face.obj').symlink_to(moved)
    except OSError: pytest.skip('Host does not permit symlinks')
    with pytest.raises(ValueError, match='escapes'): read_result(out, request(case, 'illustrative'))


def test_scientific_export_when_explicit_criteria_met(case, tmp_path):
    # Construct a software-only report snapshot with all criteria met; these
    # values and QC declarations are not observations on a human subject.
    from cranio import craniometry as cm, reference_frame as rf
    cfg, policy_path = case
    report = read(cfg.output_json)
    xyz = dict(po_R=[50, 0, 0], po_L=[-50, 0, 0], or_L=[-25, 60, 0],
               n=[0, 60, 30], b=[0, 0, 80], op=[0, -65, 10], eu_R=[50, 0, 20], eu_L=[-50, 0, 20])
    doc = cm.empty_document('synthetic export')
    doc['bone_sources'] = [dict(id='fixture', geometry_sha256='a'*64)]
    doc['points'] = [dict(code=c, xyz_mm=p, status='observed', definition_reviewed=True,
        source_id='fixture', source_geometry_sha256='a'*64, definition_text='Synthetic definition',
        definition_source='Synthetic software fixture') for c, p in xyz.items()]
    frame_config = dict(schema_version=1, orbitale='or_L', superior_code='b', midline_codes=['n', 'b', 'op'],
                        source='Synthetic software fixture', placement_error=None)
    doc['reference_frame'] = rf.compute_frame(doc, frame_config)
    report['marker_metadata']['craniometry'] = doc
    row, tf = report['landmarks'][0], report['transform']
    row['label'] = 'Gonion_Dr'
    row['target_mm'] = (tf['scale']*(np.array([-10., 0, 0])@np.array(tf['rotation']).T)+tf['translation_mm']).tolist()
    q = report['geometry_quality']
    q.update(mode='full', status='passed_full_checks', baseline_contacts=dict(complete=True, pairs=[]))
    for stage in ('statistical', 'final'):
        q[stage].update(contacts=dict(complete=True, pairs=[]), new_contact_face_pairs=[],
                        bone_clearance=dict(negative_clearance_count=0))
    policy = dict(schema_version=1, id='synthetic', revision='1', reviewed=True, rules=[
        dict(id='breadth', kind='bone_range', measurement='eu-eu', minimum_mm=90, maximum_mm=110,
             source='Synthetic criterion', on_fail='block'),
        dict(id='region', kind='marker_count', region='synthetic', labels=['Gonion_Dr'], minimum=1,
             source='Synthetic criterion', on_fail='block'),
        dict(id='plane', kind='midline_rms', maximum_mm=.01, source='Synthetic criterion', on_fail='block')])
    Path(cfg.output_json).write_bytes(canonical_bytes(report))
    policy_path.write_bytes(canonical_bytes(policy))
    out = tmp_path/'scientific'
    export_bundle(cfg.output_json, out, mode='scientific', check_policy_path=policy_path)
    result, _ = read_result(out, request(case))
    assert result['check_gate']['status'] == 'criteria_met' and result['status'] == 'completed'
    assert result['label'] == 'SCIENTIFIC EXPORT — NOT VALIDATED'
    assert result['scientific_export_authorization'] == 'not_assessed'


def test_moved_artifact_paths_support_windows_reports(case, tmp_path):
    import shutil
    cfg, _ = case
    document = read(cfg.output_json)
    artifacts = tmp_path/'moved'
    shutil.copytree(Path(cfg.output).parent, artifacts)
    for row in document['outputs'].values():
        row['path'] = 'C:\\old-case\\'+Path(row['path']).name
    source = tmp_path/'relocated-report.json'
    source.write_bytes(canonical_bytes(document))
    out = tmp_path/'export'
    export_bundle(source, out, mode='illustrative', artifacts=artifacts)
    assert read_result(out, prepare_export_request(source, mode='illustrative', artifacts=artifacts))[0]['status'] == 'completed'


def test_blocked_result_cannot_be_relabeled_complete(case, tmp_path):
    out = tmp_path/'held'
    path = export_bundle(case[0].output_json, out, mode='scientific', check_policy_path=case[1])
    result = read(path)
    result['check_gate']['proceed'] = True
    path.write_bytes(canonical_bytes(result))
    with pytest.raises(ValueError, match='differs from recorded gate'): read_result(out, request(case))
    result['check_gate']['proceed'] = False
    path.write_bytes(canonical_bytes(result))
    (out/'face.obj').write_text('unexpected mesh', encoding='utf-8')
    with pytest.raises(ValueError, match='unexpected mesh'): read_result(out, request(case))

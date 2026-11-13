"""Synthetic configured checks, incomplete skulls and audit integration."""
import copy
import json
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest

from cranio import craniometry as cm, reference_frame as rf
from cranio.check_policy import empty_policy, validate_policy, assess, main
from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline
from cranio.record import build_record, canonical_bytes, main as record_cli
from cranio.record_job import prepare_request
from cranio.validation import sha256_file


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


@pytest.fixture
def case(tmp_path, model_file, marker_file):
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), output=str(tmp_path/'fit'/'face.obj'), regularization='30')
    assert run_pipeline(cfg) == 0
    report = read(cfg.output_json)
    xyz = dict(po_R=[50, 0, 0], po_L=[-50, 0, 0], or_L=[-25, 60, 0],
               n=[0, 60, 30], b=[0, 0, 80], op=[0, -65, 10], eu_R=[50, 0, 20], eu_L=[-50, 0, 20])
    doc = cm.empty_document('synthetic-checks')
    doc['bone_sources'] = [dict(id='fixture', geometry_sha256='a'*64)]
    doc['points'] = [dict(code=c, xyz_mm=p, status='observed', definition_reviewed=True,
        source_id='fixture', source_geometry_sha256='a'*64, definition_text='Synthetic definition',
        definition_source='Synthetic software test') for c, p in xyz.items()]
    config = dict(schema_version=1, orbitale='or_L', superior_code='b', midline_codes=['n', 'b', 'op'],
                  source='Synthetic software test', placement_error=None)
    doc['reference_frame'] = rf.compute_frame(doc, config)
    report['marker_metadata']['craniometry'] = doc
    policy = dict(schema_version=1, id='synthetic-only', revision='test-1', reviewed=True, rules=[
        dict(id='breadth', kind='bone_range', measurement='eu-eu', minimum_mm=90., maximum_mm=110.,
             source='Synthetic range, not anatomical evidence', on_fail='block'),
        dict(id='region', kind='marker_count', region='synthetic region', labels=[r['label'] for r in report['landmarks']],
             minimum=len(report['landmarks']), source='Synthetic count, not anatomical evidence', on_fail='warn'),
        dict(id='midline', kind='midline_rms', maximum_mm=.01,
             source='Synthetic plane tolerance, not anatomical evidence', on_fail='block')])
    return cfg, report, policy


def rows(case, **kwargs):
    return {r['id']: r for r in assess(case[1], case[2], **kwargs)['checks']}


def test_opt_in_deterministic_and_no_claim(case):
    before = copy.deepcopy(case[1:])
    first = assess(case[1], case[2])
    assert canonical_bytes(first) == canonical_bytes(assess(case[1], case[2]))
    assert first['scientific_export_authorization'] == 'not_assessed'
    assert rows(case)['breadth']['observed'] == 100
    assert rows(case)['breadth']['status'] == rows(case)['midline']['status'] == 'pass'
    assert rows(case)['region']['status'] == 'pass'
    assert case[1:] == before
    # Synthetic P labels carry no laterality, so the overall gate stays held.
    assert first['status'] == 'not_assessed' and not first['gate']['proceed']


def test_rescaled_skull_recomputes_bone_chord_instead_of_cached_scalar(case):
    doc = case[1]['marker_metadata']['craniometry']
    for p in doc['points']:
        p['xyz_mm'] = (np.asarray(p['xyz_mm'])*1.33).tolist()
    case[1]['craniometry'] = dict(bone_measurements=[dict(measurement='eu-eu', bone_mm=100)])
    result = rows(case)
    assert result['breadth']['observed'] == pytest.approx(133.)
    assert result['breadth']['status'] == 'block'
    assert result['midline']['status'] == 'not_assessed'
    assert assess(case[1], case[2])['status'] == 'block'  # failure wins over unknown


@pytest.mark.parametrize('change', ['missing', 'reconstructed', 'unreviewed', 'stale'])
def test_fragment_unknown_never_uses_missing_or_reconstructed_bone(case, change):
    doc = case[1]['marker_metadata']['craniometry']
    row = next(p for p in doc['points'] if p['code'] == 'eu_L')
    if change == 'missing': row.update(status='missing', xyz_mm=None)
    elif change == 'reconstructed': row['status'] = 'reconstructed'
    elif change == 'unreviewed': row['definition_reviewed'] = False
    else: row['source_geometry_sha256'] = 'b'*64
    check = rows(case)['breadth']
    assert check['status'] == 'not_assessed' and check['observed'] is None


def test_mixed_fragments_do_not_imply_opposite_side_preserved(case):
    doc = case[1]['marker_metadata']['craniometry']
    doc['points'] = [p for p in doc['points'] if p['code'] != 'eu_L']
    doc['points'].append(dict(code='go_L', xyz_mm=[-40, 30, -30], status='observed', definition_reviewed=True,
        source_id='fixture', source_geometry_sha256='a'*64, definition_text='Synthetic definition',
        definition_source='Synthetic software test'))
    assert rows(case)['breadth']['status'] == 'not_assessed'


def test_actual_fitted_count_and_zero_weight(case):
    case[1]['landmarks'][0]['weight'] = 0
    assert rows(case)['region']['status'] == 'warn'
    assert rows(case)['region']['observed']['count'] == len(case[1]['landmarks'])-1
    case[2]['rules'][1]['on_fail'] = 'block'
    assert rows(case)['region']['status'] == 'block'


@pytest.mark.parametrize('mode', ['missing', 'stale', 'signature', 'tampered_cached_rms'])
def test_frame_uses_snapshot_and_recomputed_geometry(case, mode):
    doc = case[1]['marker_metadata']['craniometry']
    if mode == 'missing': doc.pop('reference_frame')
    elif mode == 'stale': doc['reference_frame']['status'] = 'stale'
    elif mode == 'signature': doc['reference_frame']['input_signature'] = 'b'*64
    else: doc['reference_frame']['geometry']['midsagittal']['residual_rms_mm'] = 999
    row = rows(case)['midline']
    assert row['status'] == ('pass' if mode == 'tampered_cached_rms' else 'not_assessed')
    if mode == 'tampered_cached_rms': assert row['observed'] == 0


def test_no_anatomical_configuration_cannot_be_green(case):
    result = assess(case[1], empty_policy())
    assert result['status'] == 'not_assessed'
    assert result['policy']['rules'] == []
    assert not result['gate']['proceed']
    assert len([r for r in result['checks'] if r['id'].startswith('builtin:missing_')]) == 3
    case[2]['reviewed'] = False
    assert not any(r['id'] == 'breadth' for r in assess(case[1], case[2])['checks'])


def test_convergence_failure_and_override_do_not_approve(case):
    case[1]['solver']['converged'] = False
    result = assess(case[1], case[2], 'Synthetic investigation of nonconvergence')
    assert result['status'] == 'block'
    assert result['gate'] == dict(status='overridden', proceed=True, override_reason='Synthetic investigation of nonconvergence')
    assert result['scientific_export_authorization'] == 'not_assessed'
    assert result['checks'][0]['status'] == 'block'


@pytest.mark.parametrize('rotation', [np.diag([-1., 1, 1]), np.diag([2., 1, 1])])
def test_reflected_or_nonorthogonal_transform_blocked(case, rotation):
    case[1]['transform']['rotation'] = rotation.tolist()
    result = rows(case)
    assert result['builtin:proper_transform']['status'] == 'block'
    assert result['builtin:side_labels']['status'] == 'not_assessed'


def test_existing_side_heuristic_explicit_legacy(case):
    r = case[1]['landmarks'][0]
    r['label'] = 'Gonion_Dr'
    tf = case[1]['transform']
    r['target_mm'] = (tf['scale']*(np.array([10., 0, 0])@np.array(tf['rotation']).T)+tf['translation_mm']).tolist()
    result = rows(case)['builtin:side_labels']
    assert result['status'] == 'block'
    assert result['provenance'] == 'legacy_hardcoded'
    assert result['observed']['suspect'] == ['Gonion_Dr']


def test_basic_full_and_incomplete_geometry_are_distinct(case):
    quality = case[1]['geometry_quality']
    assert rows(case)['builtin:geometry']['status'] == 'warn'
    quality.update(mode='full', status='passed_full_checks', baseline_contacts=dict(complete=True, pairs=[]))
    for stage in ('statistical', 'final'):
        quality[stage].update(contacts=dict(complete=True, pairs=[]), new_contact_face_pairs=[],
                              bone_clearance=dict(negative_clearance_count=0))
    assert rows(case)['builtin:geometry']['status'] == 'pass'
    quality['final']['contacts']['complete'] = False
    assert rows(case)['builtin:geometry']['status'] == 'not_assessed'
    quality['final']['new_contact_face_pairs'] = [[1, 2]]
    assert rows(case)['builtin:geometry']['status'] == 'block'
    quality['status'] = 'needs_review'
    assert rows(case)['builtin:geometry']['status'] == 'block'


@pytest.mark.parametrize('change', ['bool_schema', 'extra', 'id', 'reviewed', 'kind', 'duplicate', 'reserved',
    'source', 'on_fail', 'measurement', 'nan', 'reversed', 'bool_limit', 'infinite', 'huge',
    'labels', 'duplicate_label', 'minimum', 'float_minimum', 'plane_negative'])
def test_invalid_configuration_rejected(case, change):
    policy = case[2]
    a, b, c = policy['rules']
    if change == 'bool_schema': policy['schema_version'] = True
    elif change == 'extra': policy['unknown'] = 1
    elif change == 'id': policy['id'] = None
    elif change == 'reviewed': policy['reviewed'] = 1
    elif change == 'kind': a['kind'] = 'guess_age'
    elif change == 'duplicate': b['id'] = a['id']
    elif change == 'reserved': a['id'] = 'builtin:geometry'
    elif change == 'source': a['source'] = 'TODO(verify-source)'
    elif change == 'on_fail': a['on_fail'] = 'pass'
    elif change == 'measurement': a['measurement'] = 'guess'
    elif change == 'nan': a['minimum_mm'] = float('nan')
    elif change == 'reversed': a['minimum_mm'] = 999
    elif change == 'bool_limit': a['minimum_mm'] = True
    elif change == 'infinite': a['maximum_mm'] = float('inf')
    elif change == 'huge': a['maximum_mm'] = 10**400
    elif change == 'labels': b['labels'] = []
    elif change == 'duplicate_label': b['labels'].append(b['labels'][0])
    elif change == 'minimum': b['minimum'] = 0
    elif change == 'float_minimum': b['minimum'] = 1.
    else: c['maximum_mm'] = -1
    with pytest.raises(ValueError): validate_policy(policy)


@pytest.mark.parametrize('reason', ['', '  ', 'TODO', True])
def test_empty_or_invalid_override_rejected(case, reason):
    with pytest.raises(ValueError): assess(case[1], case[2], reason)


def test_cli_exit_codes_and_hash_binding(case, tmp_path):
    report, policy, output = tmp_path/'report.json', tmp_path/'policy.json', tmp_path/'checks.json'
    report.write_bytes(canonical_bytes(case[1]))
    policy.write_bytes(canonical_bytes(case[2]))
    args = ['assess', '--report', str(report), '--policy', str(policy), '--output', str(output)]
    assert main(args) == 3
    assert read(output)['source_hashes']['report_sha256'] == sha256_file(report)
    with pytest.raises(SystemExit): main(args)
    output.unlink()
    assert main(args+['--allow-blocked', 'Synthetic exploratory inspection']) == 0
    assert read(output)['status'] == 'not_assessed'
    assert main(['template', '--output', str(tmp_path/'blank.json')]) == 0
    assert read(tmp_path/'blank.json') == empty_policy()


def test_record_and_blender_request_preserve_default_and_input(case, tmp_path):
    cfg, report, policy = case
    Path(cfg.output_json).write_bytes(canonical_bytes(report))
    policy_path = tmp_path/'policy.json'
    policy_path.write_bytes(canonical_bytes(policy))
    source_bytes = Path(cfg.output_json).read_bytes()
    default = read(build_record(cfg.output_json, tmp_path/'default'))
    assert 'check_policy' not in default['assessments']
    first = build_record(cfg.output_json, tmp_path/'checked', check_policy_path=policy_path, check_override='Synthetic follow-up')
    second = build_record(cfg.output_json, tmp_path/'again', check_policy_path=policy_path, check_override='Synthetic follow-up')
    assert first.read_bytes() == second.read_bytes()
    result = read(first)
    assert result['status'] == 'diagnostic_only'
    assert result['assessments']['check_policy']['gate']['status'] == 'overridden'
    assert result['assessments']['scientific_export_authorization']['status'] == 'not_assessed'
    assert 'Synthetic follow-up' in (first.parent/'approximation_record.txt').read_text(encoding='utf-8')
    assert Path(cfg.output_json).read_bytes() == source_bytes
    request = prepare_request(cfg.output_json, check_policy=policy_path, check_override='Synthetic follow-up')
    assert request['arguments'][-2:] == ['--check-override', 'Synthetic follow-up']
    with pytest.raises(ValueError): prepare_request(cfg.output_json, check_override='Orphan exception')
    with pytest.raises(ValueError): build_record(cfg.output_json, tmp_path/'bad', check_override='Orphan exception')
    assert record_cli(['build', '--report', cfg.output_json, '--output-dir', str(tmp_path/'cli'),
                       '--check-policy', str(policy_path)]) == 0  # diagnostic record export is intentionally allowed


def test_policy_drift_prevents_record_completion(case, tmp_path, monkeypatch):
    import cranio.export
    policy = tmp_path/'policy.json'
    policy.write_bytes(canonical_bytes(case[2]))
    original = cranio.export.atomic_text
    @contextmanager
    def changed(path, **kwargs):
        with original(path, **kwargs) as stream:
            yield stream
        if Path(path).name == 'provenance.json': policy.write_bytes(policy.read_bytes()+b' ')
    monkeypatch.setattr(cranio.export, 'atomic_text', changed)
    with pytest.raises(ValueError, match='changed during export'):
        build_record(case[0].output_json, tmp_path/'failed', check_policy_path=policy)
    assert not (tmp_path/'failed'/'approximation_record.json').exists()


@pytest.mark.parametrize('change', ['input', 'output'])
def test_atomic_cli_refuses_changed_input_or_concurrent_destination(case, tmp_path, monkeypatch, change):
    import cranio.export
    source, policy, output = tmp_path/'source.json', tmp_path/'policy.json', tmp_path/'checks.json'
    source.write_bytes(canonical_bytes(case[1]))
    policy.write_bytes(canonical_bytes(case[2]))
    original = cranio.export.atomic_text
    @contextmanager
    def concurrent(path, **kwargs):
        with original(path, **kwargs) as stream:
            yield stream
            if change == 'input': source.write_bytes(source.read_bytes()+b' ')
            else: output.write_text('concurrent work', encoding='utf-8')
    monkeypatch.setattr(cranio.export, 'atomic_text', concurrent)
    with pytest.raises(SystemExit):
        main(['assess', '--report', str(source), '--policy', str(policy), '--output', str(output)])
    if change == 'output': assert output.read_text(encoding='utf-8') == 'concurrent work'
    else: assert not output.exists()


def test_all_configured_criteria_met_is_not_scientific_approval(case):
    report, policy = case[1:]
    row = report['landmarks'][0]
    policy['rules'][1]['labels'][0] = 'Gonion_Dr'
    row['label'] = 'Gonion_Dr'
    tf = report['transform']
    row['target_mm'] = (tf['scale']*(np.array([-10., 0, 0])@np.array(tf['rotation']).T)+tf['translation_mm']).tolist()
    q = report['geometry_quality']
    q.update(mode='full', status='passed_full_checks', baseline_contacts=dict(complete=True, pairs=[]))
    for stage in ('statistical', 'final'):
        q[stage].update(contacts=dict(complete=True, pairs=[]), new_contact_face_pairs=[],
                        bone_clearance=dict(negative_clearance_count=0))
    result = assess(report, policy)
    assert result['status'] == 'pass' and result['gate']['status'] == 'criteria_met'
    assert result['gate']['proceed'] is True
    assert result['scientific_export_authorization'] == 'not_assessed'
    # A missing baseline does not hide a later known negative clearance.
    q['baseline_contacts']['complete'] = False
    q['final']['bone_clearance']['negative_clearance_count'] = 1
    assert rows(case)['builtin:geometry']['status'] == 'block'


@pytest.mark.parametrize('bad', ['missing_frame_config', 'missing_target', 'nan_weight', 'bad_scale', 'overflow'])
def test_malformed_evidence_fails_without_success_output(case, bad):
    report = case[1]
    if bad == 'missing_frame_config': report['marker_metadata']['craniometry']['reference_frame'].pop('configuration')
    elif bad == 'missing_target': report['landmarks'][0].pop('target_mm')
    elif bad == 'nan_weight': report['landmarks'][0]['weight'] = float('nan')
    elif bad == 'bad_scale': report['transform']['scale'] = 0
    else: report['transform']['scale'] = 1e-320
    with pytest.raises(ValueError): assess(report, case[2])


def test_duplicate_json_is_refused(case, tmp_path):
    policy = tmp_path/'policy.json'
    policy.write_text('{"schema_version":1,"schema_version":1}', encoding='utf-8')
    with pytest.raises(SystemExit):
        main(['assess', '--report', case[0].output_json, '--policy', str(policy), '--output', str(tmp_path/'out.json')])
    assert not (tmp_path/'out.json').exists()


def test_partial_skull_without_porion_cannot_claim_midline_check(case):
    doc = case[1]['marker_metadata']['craniometry']
    doc['points'] = [p for p in doc['points'] if p['code'] != 'po_L']
    result = rows(case)['midline']
    assert result['status'] == 'not_assessed'
    assert result['observed'] is None
    assert 'cannot be reassessed' in result['reason']

"""Derived-record integrity, determinism and honest scientific status."""
import copy
import hashlib
import json
import shutil
from contextlib import contextmanager
from pathlib import Path

import pytest

from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline
from cranio.record import (build_record, compile_record, canonical_bytes, main,
                           empty_limitations, validate_limitations, OUTPUT_KEYS)


@pytest.fixture
def run(tmp_path, model_file, marker_file):
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file),
                         output=str(tmp_path/'fit'/'face.obj'), regularization='30')
    assert run_pipeline(cfg) == 0
    return cfg


def read(cfg):
    return json.loads(Path(cfg.output_json).read_text(encoding='utf-8'))


def test_preserves_evidence_and_unknowns(run):
    source = read(run)
    before = canonical_bytes(source)
    record = compile_record(source)
    for name in ('identity_coefficients', 'transform', 'metrics', 'marker_metadata', 'warnings'):
        assert record['run'][name] == source[name]
    assert record['status'] == 'recorded_not_validated'
    assert record['limitations'] == dict(status='not_configured', document=None)
    for name in ('uncertainty', 'calibration', 'validity_domain', 'scientific_export_authorization'):
        assert record['assessments'][name]['status'] == 'not_assessed'
    assert record['prior']['enabled'] is False
    assert record['markers'][0]['provenance'] == source['marker_metadata']['marker_records']['P0']
    record['run']['marker_metadata']['marker_records']['P0']['bone_status'] = 'changed copy'
    assert canonical_bytes(source) == before


def test_repeated_export_identical_and_inputs_untouched(run, tmp_path):
    paths = [Path(getattr(run, key)) for key in (*OUTPUT_KEYS, 'output_json', 'input', 'npz')]
    before = {p: p.read_bytes() for p in paths}
    records = []
    for name in ('one', 'two'):
        path = build_record(run.output_json, tmp_path/name)
        records.append(path.read_bytes())
        envelope = json.loads((path.parent/'provenance.json').read_text(encoding='utf-8'))
        assert envelope['source_report']['sha256'] == hashlib.sha256(before[Path(run.output_json)]).hexdigest()
        assert envelope['input_verification'] == 'hashes_recorded_not_revalidated'
        for filename, row in envelope['derived_files'].items():
            assert row['sha256'] == hashlib.sha256((path.parent/filename).read_bytes()).hexdigest()
    assert records[0] == records[1]
    assert all(p.read_bytes() == content for p, content in before.items())
    with pytest.raises(ValueError, match='exists'):
        build_record(run.output_json, tmp_path/'one')


def test_pipeline_rerun_other_directory_has_identical_record(run, tmp_path):
    second = PipelineConfig(input=run.input, npz=run.npz, output=str(tmp_path/'second'/'face.obj'), regularization='30')
    assert run_pipeline(second) == 0
    assert canonical_bytes(compile_record(read(run))) == canonical_bytes(compile_record(read(second)))


@pytest.mark.parametrize('windows', [False, True])
def test_moved_bundle_and_cross_platform_paths(run, tmp_path, windows):
    document = read(run)
    if windows:
        for row in document['outputs'].values():
            row['path'] = 'C:\\case\\'+Path(row['path']).name
    source = tmp_path/'moved.json'
    source.write_bytes(canonical_bytes(document))
    artifacts = tmp_path/'artifacts'
    shutil.copytree(Path(run.output).parent, artifacts)
    path = build_record(source, tmp_path/'record', artifacts=artifacts)
    assert path.is_file()


@pytest.mark.parametrize('key', OUTPUT_KEYS)
def test_tampered_output_refused(run, tmp_path, key):
    path = Path(getattr(run, key))
    path.write_bytes(path.read_bytes()+b'changed')
    with pytest.raises(ValueError, match='checksum'):
        build_record(run.output_json, tmp_path/'record')
    assert not (tmp_path/'record').exists()


def test_missing_output_refused(run, tmp_path):
    Path(run.output).unlink()
    with pytest.raises(OSError):
        build_record(run.output_json, tmp_path/'record')
    assert not (tmp_path/'record').exists()


@pytest.mark.parametrize('kind', ['schema', 'bool_schema', 'status', 'units', 'missing_model', 'bad_hash',
    'records', 'duplicate', 'solver', 'require_qc', 'nan', 'overflow', 'missing_list',
    'string_lambda', 'bool_lambda', 'zero_lambda', 'huge_lambda'])
def test_malformed_report_rejected(run, kind):
    report = read(run)
    if kind == 'schema': report['schema_version'] = 1
    elif kind == 'bool_schema': report['schema_version'] = True
    elif kind == 'status': report['status'] = 'partial'
    elif kind == 'units': report['units'] = 'm'
    elif kind == 'missing_model': del report['inputs']['model']
    elif kind == 'bad_hash': report['inputs']['model']['sha256'] = None
    elif kind == 'records': report['marker_metadata']['marker_records'] = []
    elif kind == 'duplicate': report['landmarks'].append(copy.deepcopy(report['landmarks'][0]))
    elif kind == 'solver': report['solver']['converged'] = 1
    elif kind == 'require_qc': report['config']['require_qc'] = 'yes'
    elif kind == 'missing_list': del report['warnings']
    else:
        report['lambda'] = dict(nan=float('nan'), overflow=float('inf'), string_lambda='30',
                                bool_lambda=True, zero_lambda=0, huge_lambda=10**400)[kind]
    with pytest.raises(ValueError):
        compile_record(report)


def test_completed_is_not_qc_approval(run):
    report = read(run)
    report['config']['require_qc'] = True
    report['geometry_quality'] = dict(status='needs_review')
    record = compile_record(report)
    assert record['status'] == 'diagnostic_only'
    assert record['assessments']['geometry_gate_from_report'] == 'not_met'
    report['geometry_quality']['status'] = 'passed_full_checks'
    assert compile_record(report)['assessments']['geometry_gate_from_report'] == 'met'
    report['solver']['converged'] = False
    report['config']['profile_constraint'] = 'reviewed.json'
    record = compile_record(report)
    assert record['status'] == 'diagnostic_only'
    assert record['assessments']['solver_scope'] == 'baseline_before_profile'


def test_prior_case_metadata_and_exclusions_preserved(run):
    report = read(run)
    report['inputs']['prior'] = dict(path='some_prior.npz', sha256='a'*64)
    report['config']['prior_justification'] = 'Synthetic sensitivity scenario'
    for name in ('age_context', 'tissue_application', 'mandible_pose', 'restoration_regions'):
        report['marker_metadata'][name] = dict(synthetic=True)
    report['skipped'] = [['P99', 'not placed']]
    report['auto_excluded'] = [['P98', 42.0]]
    record = compile_record(report)
    assert record['prior'] == dict(enabled=True, sha256='a'*64, justification='Synthetic sensitivity scenario')
    for name in ('marker_metadata', 'skipped', 'auto_excluded'):
        assert record['run'][name] == report[name]


def test_missing_marker_provenance_stays_unknown(run):
    report = read(run)
    report['marker_metadata'].pop('marker_records')
    assert all(row['provenance'] is None and row['provenance_status'] == 'not_recorded'
               for row in compile_record(report)['markers'])


def test_limitations_template_and_approved_text(run, tmp_path):
    path = tmp_path/'limits.json'
    assert main(['limitations-template', '--output', str(path)]) == 0
    assert json.loads(path.read_text(encoding='utf-8')) == empty_limitations()
    with pytest.raises(ValueError, match='approved'):
        build_record(run.output_json, tmp_path/'unapproved', limitations_path=path)
    document = dict(schema_version=1, revision='fixture', approved=True,
                    ro='Text sintetic pentru test.', en='Synthetic test text.')
    path.write_bytes(canonical_bytes(document))
    output = build_record(run.output_json, tmp_path/'approved', limitations_path=path)
    assert json.loads(output.read_text(encoding='utf-8'))['limitations']['document'] == document
    assert document['ro'] in (output.parent/'approximation_record.txt').read_text(encoding='utf-8')
    with pytest.raises(SystemExit):
        main(['limitations-template', '--output', str(path)])
    assert json.loads(path.read_text(encoding='utf-8')) == document


@pytest.mark.parametrize('key,value', [('approved', False), ('approved', 1), ('revision', None),
                                     ('ro', ''), ('en', 'TODO'), ('ro', '[[LIPSĂ: text]]')])
def test_limitations_reject_unapproved_or_empty(key, value):
    document = dict(schema_version=1, revision='r1', approved=True, ro='Text test.', en='Test text.')
    document[key] = value
    with pytest.raises(ValueError):
        validate_limitations(document)


def test_cli_duplicate_json_and_valid_export(run, tmp_path):
    bad = tmp_path/'bad.json'
    bad.write_text('{"schema_version":2,"schema_version":2}', encoding='utf-8')
    with pytest.raises(SystemExit):
        main(['build', '--report', str(bad), '--output-dir', str(tmp_path/'bad-out')])
    assert not (tmp_path/'bad-out').exists()
    args = ['build', '--report', run.output_json, '--output-dir', str(tmp_path/'good')]
    assert main(args) == 0
    with pytest.raises(SystemExit):
        main(args)


def test_source_drift_prevents_completion_marker(run, tmp_path, monkeypatch):
    import cranio.export
    original = cranio.export.atomic_text
    @contextmanager
    def change_source(path):
        with original(path) as stream:
            yield stream
        if Path(path).name == 'provenance.json':
            source = Path(run.output_json)
            source.write_bytes(source.read_bytes()+b' ')
    monkeypatch.setattr(cranio.export, 'atomic_text', change_source)
    with pytest.raises(ValueError, match='changed'):
        build_record(run.output_json, tmp_path/'record')
    assert not (tmp_path/'record'/'approximation_record.json').exists()


def test_explicit_null_limitations_rejected(run, tmp_path):
    path = tmp_path/'null.json'
    path.write_text('null', encoding='utf-8')
    with pytest.raises(ValueError, match='Limitations'):
        build_record(run.output_json, tmp_path/'record', limitations_path=path)
    assert not (tmp_path/'record').exists()


def test_duplicate_output_basenames_rejected(run, tmp_path):
    report = read(run)
    report['outputs']['output_statistical'] = copy.deepcopy(report['outputs']['output'])
    Path(run.output_json).write_bytes(canonical_bytes(report))
    with pytest.raises(ValueError, match='distinct'):
        build_record(run.output_json, tmp_path/'record')


def test_external_output_symlink_rejected(run, tmp_path):
    path = Path(run.output)
    outside = tmp_path/'outside.obj'
    path.rename(outside)
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip('Host does not permit symlink creation')
    with pytest.raises(ValueError, match='escapes'):
        build_record(run.output_json, tmp_path/'record')
    assert not (tmp_path/'record').exists()


def test_record_does_not_reopen_original_inputs(run, tmp_path):
    Path(run.npz).unlink()
    Path(run.input).unlink()
    path = build_record(run.output_json, tmp_path/'record')
    envelope = json.loads((path.parent/'provenance.json').read_text(encoding='utf-8'))
    assert envelope['input_verification'] == 'hashes_recorded_not_revalidated'


def test_output_drift_prevents_completion_marker(run, tmp_path, monkeypatch):
    import cranio.export
    original = cranio.export.atomic_text
    @contextmanager
    def change_output(path):
        with original(path) as stream:
            yield stream
        if Path(path).name == 'provenance.json':
            source = Path(run.output)
            source.write_bytes(source.read_bytes()+b' ')
    monkeypatch.setattr(cranio.export, 'atomic_text', change_output)
    with pytest.raises(ValueError, match='changed'):
        build_record(run.output_json, tmp_path/'record')
    assert not (tmp_path/'record'/'approximation_record.json').exists()

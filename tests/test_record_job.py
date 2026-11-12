"""External record export and completion integrity, using synthetic pipeline data."""
import copy
import json
from pathlib import Path
import sys

import pytest

from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline
from cranio.record import build_record, canonical_bytes
from cranio.record_job import prepare_request, start_record, read_result


@pytest.fixture
def request_data(tmp_path, model_file, marker_file):
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), regularization='30',
                         output=str(tmp_path/'caz șță & literal'/'face.obj'))
    assert run_pipeline(cfg) == 0
    return prepare_request(cfg.output_json)


def test_external_cli_uses_checkout_and_safe_unicode_paths(request_data, tmp_path, monkeypatch):
    monkeypatch.setenv('PYTHONPATH', '/nonexistent/blender/modules')
    monkeypatch.setenv('PYTHONHOME', '/nonexistent/blender/python')
    monkeypatch.setenv('PYTHONSAFEPATH', '1')
    output = tmp_path/'record șță & literal'
    log = tmp_path/'run.log'
    with log.open('w', encoding='utf-8') as stream:
        process = start_record(dict(executable=sys.executable), Path(__file__).resolve().parents[1],
                               request_data, output, stream)
        assert process.wait(timeout=30) == 0, log.read_text(encoding='utf-8')
    result, page = read_result(output, request_data)
    assert result['status'] == 'recorded_not_validated'
    assert 'not a new fit or scientific approval' in page
    assert 'Command arguments:' in log.read_text(encoding='utf-8')
    assert Path(request_data['report_path']).is_file()


def test_optional_paths_are_explicit_without_embedded_file_access(request_data, tmp_path):
    limit = tmp_path/'limits.json'
    ensemble = tmp_path/'ensemble.json'
    limit.write_text('not loaded during request preparation', encoding='utf-8')
    ensemble.write_text('not loaded during request preparation', encoding='utf-8')
    request = prepare_request(request_data['report_path'], artifacts=tmp_path, limitations=limit,
                              uncertainty=ensemble, scenario='off')
    assert request['arguments'][-2:] == ['--uncertainty-scenario', 'off']
    assert str(limit.resolve()) in request['arguments']
    assert str(ensemble.resolve()) in request['arguments']
    assert request['report_sha256'] == request_data['report_sha256']


@pytest.mark.parametrize('kwargs', [dict(scenario='off'), dict(uncertainty='missing.json'),
    dict(uncertainty='missing.json', scenario='NONE'), dict(artifacts='missing-dir'), dict(limitations='missing.json')])
def test_bad_request_rejected_before_launch(request_data, kwargs):
    with pytest.raises(ValueError):
        prepare_request(request_data['report_path'], **kwargs)


def test_report_request_requires_canonical_completed_report(tmp_path):
    path = tmp_path/'bad.json'
    path.write_text('{"schema_version":2,"schema_version":2}', encoding='utf-8')
    with pytest.raises(ValueError): prepare_request(path)
    path.write_text('{"schema_version":2,"status":"in_progress"}', encoding='utf-8')
    with pytest.raises(ValueError): prepare_request(path)


@pytest.mark.parametrize('name', ['approximation_record.json', 'approximation_record.txt', 'provenance.json'])
def test_partial_result_not_displayed(request_data, tmp_path, name):
    directory = tmp_path/'record'
    build_record(request_data['report_path'], directory)
    (directory/name).unlink()
    with pytest.raises(OSError): read_result(directory, request_data)


@pytest.mark.parametrize('name', ['approximation_record.json', 'approximation_record.txt'])
def test_changed_result_not_displayed(request_data, tmp_path, name):
    directory = tmp_path/'record'
    build_record(request_data['report_path'], directory)
    path = directory/name
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError, match='checksum'): read_result(directory, request_data)


def test_source_changed_after_click_is_not_displayed(request_data, tmp_path):
    directory = tmp_path/'record'
    build_record(request_data['report_path'], directory)
    path = Path(request_data['report_path'])
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError, match='changed after submission'): read_result(directory, request_data)
    changed = prepare_request(path)
    with pytest.raises(ValueError, match='differs from the submitted'): read_result(directory, changed)


def test_external_failure_creates_no_completion_marker(request_data, tmp_path):
    report = json.loads(Path(request_data['report_path']).read_text(encoding='utf-8'))
    Path(report['outputs']['output']['path']).write_text('corrupt', encoding='utf-8')
    output = tmp_path/'failed'
    with (tmp_path/'run.log').open('w', encoding='utf-8') as stream:
        process = start_record(dict(executable=sys.executable), Path(__file__).resolve().parents[1],
                               request_data, output, stream)
        assert process.wait(timeout=30) != 0
    assert not (output/'approximation_record.json').exists()


def test_missing_addon_module_rejected(request_data, tmp_path):
    with (tmp_path/'run.log').open('w', encoding='utf-8') as stream:
        with pytest.raises(ValueError, match='complete ZIP'):
            start_record(dict(executable=sys.executable), tmp_path, request_data, tmp_path/'record', stream)


def test_diagnostic_only_result_stays_diagnostic(request_data, tmp_path):
    path = Path(request_data['report_path'])
    report = json.loads(path.read_text(encoding='utf-8'))
    report['solver']['converged'] = False
    path.write_bytes(canonical_bytes(report))
    updated = prepare_request(path)
    build_record(path, tmp_path/'record')
    record, page = read_result(tmp_path/'record', updated)
    assert record['status'] == 'diagnostic_only'
    assert 'Status: diagnostic_only' in page


def test_wrong_completion_kind_even_with_matching_checksum_rejected(request_data, tmp_path):
    import hashlib
    directory = tmp_path/'record'
    build_record(request_data['report_path'], directory)
    path = directory/'approximation_record.json'
    record = json.loads(path.read_text(encoding='utf-8'))
    record['kind'] = 'other'
    path.write_bytes(canonical_bytes(record))
    provenance = directory/'provenance.json'
    envelope = json.loads(provenance.read_text(encoding='utf-8'))
    envelope['derived_files']['approximation_record.json']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    provenance.write_bytes(canonical_bytes(envelope))
    with pytest.raises(ValueError, match='Unsupported'): read_result(directory, request_data)


def test_unexpected_manifest_path_never_opened(request_data, tmp_path):
    directory = tmp_path/'record'
    build_record(request_data['report_path'], directory)
    provenance = directory/'provenance.json'
    envelope = json.loads(provenance.read_text(encoding='utf-8'))
    envelope['derived_files']['../outside'] = copy.deepcopy(envelope['derived_files']['approximation_record.txt'])
    provenance.write_bytes(canonical_bytes(envelope))
    with pytest.raises(ValueError, match='integrity manifest'): read_result(directory, request_data)

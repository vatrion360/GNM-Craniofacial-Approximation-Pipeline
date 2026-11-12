"""Synthetic declared-domain comparisons; no anatomical/CT validation data."""
import copy
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline
from cranio.record import build_record, canonical_bytes, main as record_cli
from cranio.record_job import prepare_request
from cranio.validation import sha256_file
from cranio.validity_domain import (empty_domain, validate_domain, run_signature,
                                    case_template, assess, main)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


@pytest.fixture
def case(tmp_path, model_file, marker_file):
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file),
                         output=str(tmp_path/'fit'/'face.obj'), regularization='30')
    assert run_pipeline(cfg) == 0
    report = read(cfg.output_json)
    domain = empty_domain()
    domain.update(id='synthetic-domain', revision='test-1', reviewed=True,
                  model_sha256=report['inputs']['model']['sha256'], run_signatures=[run_signature(report)],
                  evidence=dict(reference='Synthetic software fixture, not CT evidence', sha256='a'*64, n_subjects=3),
                  conditions={'skull_completeness': dict(definition='Synthetic completeness category',
                             allowed_values=['complete'], source='Synthetic fixture definition')},
                  regional_errors=[dict(region='synthetic-region', metric='synthetic signed error', units='mm',
                      estimate=-.2, n_subjects=2, interval=dict(lower=-.5, upper=.1, kind='synthetic interval', level=.95),
                      source='Synthetic software values, not anatomical measurements')])
    observation = case_template(sha256_file(cfg.output_json), domain)
    observation['observations']['skull_completeness'] = dict(value='complete', source='Synthetic case review', reviewed=True)
    return cfg, report, domain, observation


def comparison(case):
    cfg, report, domain, observation = case
    return assess(report, sha256_file(cfg.output_json), domain, observation)


def files(case, tmp_path):
    domain_path, case_path = tmp_path/'domain.json', tmp_path/'case.json'
    domain_path.write_bytes(canonical_bytes(case[2]))
    case_path.write_bytes(canonical_bytes(case[3]))
    return domain_path, case_path


def test_matching_conditions_never_claim_validation(case):
    before = copy.deepcopy(case[1:])
    result = comparison(case)
    assert result['status'] == 'within_declared_conditions'
    assert 'NOT INDEPENDENT VALIDATION' in result['banner']
    assert result['domain']['regional_errors'] == case[2]['regional_errors']
    assert result['evidence_verification'] == 'operator_declared_not_revalidated'
    assert case[1:] == before


def test_partial_skull_outside_complete_only_domain(case):
    case[3]['observations']['skull_completeness']['value'] = 'partial'
    result = comparison(case)
    assert result['status'] == 'outside_declared_domain'
    assert result['banner'] == 'OUTSIDE DECLARED DOMAIN'
    assert result['checks'][-1]['status'] == 'outside'


@pytest.mark.parametrize('kind', ['missing', 'null', 'unreviewed', 'source_fingerprint', 'software_version'])
def test_unknown_is_not_accepted(case, kind):
    if kind == 'missing': case[3]['observations'] = {}
    elif kind == 'null': case[3]['observations']['skull_completeness'] = dict(value=None, source=None, reviewed=False)
    elif kind == 'unreviewed': case[3]['observations']['skull_completeness']['reviewed'] = False
    elif kind == 'software_version': case[1]['software']['numpy'] = None
    else: case[1]['software'].pop('implementation')
    assert comparison(case)['status'] == 'indeterminate'


def test_known_outside_takes_precedence_over_unknown(case):
    case[3]['observations'] = {}
    case[2]['model_sha256'] = 'b'*64
    result = comparison(case)
    assert result['status'] == 'outside_declared_domain'
    assert any(c['status'] == 'unknown' for c in result['checks'])


def test_empty_unreviewed_domain_degrades_without_inventing(case):
    cfg, report, _, _ = case
    domain = empty_domain()
    result = assess(report, sha256_file(cfg.output_json), domain, case_template(sha256_file(cfg.output_json)))
    assert result['status'] == 'not_configured'
    assert result['domain']['evidence']['n_subjects'] is None
    assert result['domain']['regional_errors'] == []
    assert result['checks'] == []


@pytest.mark.parametrize('kind', ['model', 'settings', 'source', 'shared_asset', 'input_role', 'environment'])
def test_incompatible_run_is_outside(case, kind):
    report = case[1]
    if kind == 'model': report['inputs']['model']['sha256'] = 'b'*64
    elif kind == 'settings': report['config']['regularization'] = 'auto'
    elif kind == 'source': report['software']['implementation']['source_sha256'] = 'b'*64
    elif kind == 'shared_asset': report['inputs']['prior'] = dict(path='prior.npz', sha256='b'*64)
    elif kind == 'input_role': report['inputs']['skull'] = dict(path='skull.obj', sha256='b'*64)
    else: report['software']['numerical_environment'] = {'changed': 'synthetic environment'}
    assert comparison(case)['status'] == 'outside_declared_domain'


def test_signature_ignores_paths_timestamps_and_subject_geometry(case):
    report = case[1]
    signature = run_signature(report)
    report['generated_utc'] = 'other timestamp'
    report['inputs']['markers']['sha256'] = 'b'*64
    report['inputs']['markers']['path'] = 'D:\\moved\\markers.csv'
    report['config']['output'] = '/moved/face.obj'
    report['config']['input'] = '/moved/markers.csv'
    report['software']['implementation']['git_commit'] = 'other commit with same sources'
    report['software']['implementation']['git_dirty'] = False
    assert run_signature(report) == signature


@pytest.mark.parametrize('bad', ['schema', 'extra', 'reviewed', 'no_id', 'no_source', 'bad_hash',
    'no_signature', 'duplicate_signature', 'no_conditions', 'reserved', 'allowed_empty', 'allowed_duplicate',
    'allowed_space', 'condition_source', 'count_bool', 'count_zero', 'regional_count', 'regional_nan',
    'regional_duplicate', 'interval_reversed', 'interval_level', 'interval_bool', 'metric_missing'])
def test_invalid_domain_rejected(case, bad):
    domain = case[2]
    if bad == 'schema': domain['schema_version'] = True
    elif bad == 'extra': domain['guess'] = True
    elif bad == 'reviewed': domain['reviewed'] = 1
    elif bad == 'no_id': domain['id'] = None
    elif bad == 'no_source': domain['evidence']['reference'] = 'TODO(verify-source)'
    elif bad == 'bad_hash': domain['evidence']['sha256'] = 'bad'
    elif bad == 'no_signature': domain['run_signatures'] = []
    elif bad == 'duplicate_signature': domain['run_signatures'] *= 2
    elif bad == 'no_conditions': domain['conditions'] = {}
    elif bad == 'reserved': domain['conditions']['run_signature'] = domain['conditions'].pop('skull_completeness')
    elif bad == 'allowed_empty': domain['conditions']['skull_completeness']['allowed_values'] = []
    elif bad == 'allowed_duplicate': domain['conditions']['skull_completeness']['allowed_values'] *= 2
    elif bad == 'allowed_space': domain['conditions']['skull_completeness']['allowed_values'] = [' complete']
    elif bad == 'condition_source': domain['conditions']['skull_completeness']['source'] = None
    elif bad == 'count_bool': domain['evidence']['n_subjects'] = True
    elif bad == 'count_zero': domain['evidence']['n_subjects'] = 0
    elif bad == 'regional_count': domain['regional_errors'][0]['n_subjects'] = 4
    elif bad == 'regional_nan': domain['regional_errors'][0]['estimate'] = float('nan')
    elif bad == 'regional_duplicate': domain['regional_errors'] *= 2
    elif bad == 'interval_reversed': domain['regional_errors'][0]['interval']['lower'] = 10
    elif bad == 'interval_level': domain['regional_errors'][0]['interval']['level'] = 95
    elif bad == 'interval_bool': domain['regional_errors'][0]['interval']['upper'] = True
    elif bad == 'metric_missing': domain['regional_errors'][0]['metric'] = ''
    with pytest.raises(ValueError): validate_domain(domain)


@pytest.mark.parametrize('bad', ['hash', 'key', 'reviewed', 'no_source', 'null_reviewed', 'value_space'])
def test_invalid_or_wrong_case_rejected(case, bad):
    observation = case[3]
    row = observation['observations']['skull_completeness']
    if bad == 'hash': observation['report_sha256'] = 'b'*64
    elif bad == 'key': observation['observations']['typo'] = observation['observations'].pop('skull_completeness')
    elif bad == 'reviewed': row['reviewed'] = 1
    elif bad == 'no_source': row['source'] = None
    elif bad == 'null_reviewed': row['value'] = None
    elif bad == 'value_space': row['value'] = 'complete '
    with pytest.raises(ValueError): comparison(case)


def test_missing_intervals_preserved_and_warned(case):
    case[2]['regional_errors'][0]['interval'] = None
    result = comparison(case)
    assert result['domain']['regional_errors'][0]['interval'] is None
    assert any('no interval' in warning for warning in result['warnings'])


def test_no_embedded_evidence_is_opened(case, monkeypatch):
    digest = sha256_file(case[0].output_json)
    case[2]['evidence']['reference'] = '/not-opened/study.json'
    def forbidden(*args, **kwargs):
        raise AssertionError('Embedded evidence must not be opened')
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    assert assess(case[1], digest, case[2], case[3])['status'] == 'within_declared_conditions'


def test_record_banner_and_determinism_without_fit_changes(case, tmp_path):
    cfg = case[0]
    case[3]['observations']['skull_completeness']['value'] = 'partial'
    domain, observations = files(case, tmp_path)
    inputs = [Path(cfg.output_json), Path(cfg.output), Path(cfg.input), Path(cfg.npz)]
    before = {p: p.read_bytes() for p in inputs}
    first = build_record(cfg.output_json, tmp_path/'one', validity_domain_path=domain, domain_case_path=observations)
    second = build_record(cfg.output_json, tmp_path/'two', validity_domain_path=domain, domain_case_path=observations)
    assert first.read_bytes() == second.read_bytes()
    record = read(first)
    assert record['assessments']['validity_domain']['status'] == 'outside_declared_domain'
    assert record['status'] == 'recorded_not_validated'
    assert record['assessments']['calibration']['status'] == 'not_assessed'
    assert record['assessments']['scientific_export_authorization']['status'] == 'not_assessed'
    text = (first.parent/'approximation_record.txt').read_text(encoding='utf-8')
    assert text.splitlines()[1] == '[DOMAIN] OUTSIDE DECLARED DOMAIN'
    assert 'not errors of this face' in text
    assert read(first.parent/'provenance.json')['domain_case_file']['sha256'] == sha256_file(observations)
    assert all(p.read_bytes() == data for p, data in before.items())


def test_cli_templates_and_explicit_pair(case, tmp_path):
    cfg = case[0]
    blank = tmp_path/'blank.json'
    assert main(['template', '--output', str(blank)]) == 0
    assert read(blank) == empty_domain()
    seeded = tmp_path/'seeded.json'
    assert main(['template', '--report', cfg.output_json, '--output', str(seeded)]) == 0
    assert read(seeded)['reviewed'] is False and read(seeded)['conditions'] == {}
    assert read(seeded)['run_signatures'] == [run_signature(case[1])]
    domain, observations = files(case, tmp_path)
    draft = tmp_path/'draft-case.json'
    assert main(['case-template', '--report', cfg.output_json, '--domain', str(domain), '--output', str(draft)]) == 0
    assert read(draft)['observations']['skull_completeness'] == dict(value=None, source=None, reviewed=False)
    with pytest.raises(SystemExit): main(['template', '--output', str(blank)])
    with pytest.raises(SystemExit): main(['case-template', '--output', str(tmp_path/'bad')])
    base = ['build', '--report', cfg.output_json, '--output-dir', str(tmp_path/'record')]
    with pytest.raises(SystemExit): record_cli(base+['--validation-domain', str(domain)])
    assert record_cli(base+['--validation-domain', str(domain), '--domain-case', str(observations)]) == 0
    request = prepare_request(cfg.output_json, validity_domain=domain, domain_case=observations)
    assert '--validation-domain' in request['arguments'] and str(observations.resolve()) in request['arguments']
    with pytest.raises(ValueError): prepare_request(cfg.output_json, validity_domain=domain)


@pytest.mark.parametrize('which', ['domain', 'case'])
def test_input_drift_prevents_completion(case, tmp_path, monkeypatch, which):
    import cranio.export
    domain, observations = files(case, tmp_path)
    changing = domain if which == 'domain' else observations
    original = cranio.export.atomic_text
    @contextmanager
    def changed(path):
        with original(path) as stream:
            yield stream
        if Path(path).name == 'provenance.json':
            changing.write_bytes(changing.read_bytes()+b' ')
    monkeypatch.setattr(cranio.export, 'atomic_text', changed)
    with pytest.raises(ValueError, match='changed during export'):
        build_record(case[0].output_json, tmp_path/'failed', validity_domain_path=domain, domain_case_path=observations)
    assert not (tmp_path/'failed'/'approximation_record.json').exists()


def test_duplicate_json_and_wrong_binding_refused_before_output(case, tmp_path):
    domain, observations = files(case, tmp_path)
    domain.write_text('{"schema_version":1,"schema_version":1}', encoding='utf-8')
    with pytest.raises(ValueError):
        build_record(case[0].output_json, tmp_path/'bad', validity_domain_path=domain, domain_case_path=observations)
    assert not (tmp_path/'bad').exists()


@pytest.mark.parametrize('change', ['input', 'output'])
def test_template_race_preserves_files(case, tmp_path, monkeypatch, change):
    import cranio.export
    original = cranio.export.atomic_text
    output = tmp_path/'template.json'
    source = Path(case[0].output_json)
    @contextmanager
    def concurrent(path, *, validate=None):
        with original(path, validate=validate) as stream:
            yield stream
            if change == 'input':
                source.write_bytes(source.read_bytes()+b' ')
            else:
                output.write_text('concurrent work', encoding='utf-8')
    monkeypatch.setattr(cranio.export, 'atomic_text', concurrent)
    with pytest.raises(SystemExit):
        main(['template', '--report', str(source), '--output', str(output)])
    if change == 'output':
        assert output.read_text(encoding='utf-8') == 'concurrent work'
    else:
        assert not output.exists()

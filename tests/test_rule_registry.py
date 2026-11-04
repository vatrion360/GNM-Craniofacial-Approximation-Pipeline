"""Registry contracts; synthetic review claims are not scientific evidence."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
from cranio import rules


def sample():
    document = rules.empty_registry('fixture')
    document['rules'] = [rules.empty_rule('fixture_rule', 'eyes')]
    return document


def test_bundled_sources_are_unverified_and_unconfigured():
    loaded = rules.load_registry()
    document = loaded.document
    assert len(document['rules']) == 6
    assert {row['feature'] for row in document['rules']} == {'eyes', 'nose', 'mouth', 'ears'}
    assert all(row['status'] == 'needs_verification' and row['tested_error'] is None
               and row['implementation_id'] is None for row in document['rules'])
    assert all(row['reference']['citation'] is None for row in document['rules'])
    assert len([row for row in document['rules'] if row['reference']['doi']]) == 4
    assert len(loaded.warnings) == 7
    assert 'case applicability' in loaded.warnings[0]
    assert loaded.sha256 == hashlib.sha256((rules.DATA_DIR/'registry.json').read_bytes()).hexdigest()
    assert loaded.schema_sha256 == hashlib.sha256((rules.DATA_DIR/'schema.json').read_bytes()).hexdigest()
    document['rules'][0]['status'] = 'validated'
    assert loaded.document['rules'][0]['status'] == 'needs_verification'


def test_validation_keeps_unknowns_and_preserves_input():
    document = sample()
    before = copy.deepcopy(document)
    normalized, warnings = rules.validate_registry(document)
    assert document == before == normalized
    normalized['rules'][0]['reference']['citation'] = 'Changed copy'
    assert document == before
    assert warnings and before['rules'][0]['applicability']['ancestry'] is None
    assert rules.validate_registry(rules.empty_registry())[1][-1] == 'No anatomical rules configured'


@pytest.mark.parametrize('path,value', [
    (('schema_version',), True), (('schema_version',), 2), (('id',), '../escape'),
    (('revision',), '  '), (('extra',), 1), (('rules',), {}),
    (('rules', 0, 'id'), 'Fixture'), (('rules', 0, 'feature'), 'jaw'),
    (('rules', 0, 'status'), 'approved'), (('rules', 0, 'notes'), ''),
    (('rules', 0, 'reference', 'doi'), 'https://doi.org/10.1234/example'),
    (('rules', 0, 'reference', 'citation'), '  '),
    (('rules', 0, 'implementation_id'), 'os.system'),
    (('rules', 0, 'applicability', 'sex'), 'all'),
    (('rules', 0, 'applicability', 'ancestry'), []),
    (('rules', 0, 'applicability', 'dentition'), [None]),
    (('rules', 0, 'verification', 'external', 'status'), 'validated'),
])
def test_schema_rejects_malformed_metadata(path, value):
    document = sample()
    current = document
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value
    with pytest.raises(ValueError):
        rules.validate_registry(document)


def error_fixture():
    return dict(metric='Signed synthetic offset', mean=-2., sd=1., n=4,
                units='mm', cohort='Engineering points, no humans', source_locator='Synthetic test array')


@pytest.mark.parametrize('field,value', [('mean', float('nan')), ('mean', float('inf')),
    ('sd', -1), ('mean', True), ('n', True), ('n', 0), ('n', 1.5),
    ('units', None), ('metric', None), ('cohort', None), ('source_locator', None),
    ('source_locator', 'TODO(verify-source)')])
def test_error_values_require_valid_units_and_context(field, value):
    document = sample()
    error = error_fixture()
    error[field] = value
    document['rules'][0]['tested_error'] = error
    with pytest.raises(ValueError):
        rules.validate_registry(document)


def test_signed_error_and_partial_statistics_are_not_imputed():
    document = sample()
    error = error_fixture()
    error['sd'] = None
    document['rules'][0]['tested_error'] = error
    result, warnings = rules.validate_registry(document)
    assert result['rules'][0]['tested_error']['mean'] == -2.
    assert result['rules'][0]['tested_error']['sd'] is None
    assert 'tested_error.sd' in ' '.join(warnings)


def test_duplicate_ids_missing_fields_and_source_text_are_not_normalized():
    document = sample()
    document['rules'].append(copy.deepcopy(document['rules'][0]))
    with pytest.raises(ValueError, match='Duplicate rule id'):
        rules.validate_registry(document)
    document = sample()
    del document['rules'][0]['reference']['doi']
    with pytest.raises(ValueError, match='missing fields'):
        rules.validate_registry(document)
    document = sample()
    labels = ['Source-specific label Ș', 'unknown within supplied cohort']
    document['rules'][0]['applicability']['ancestry'] = labels
    assert rules.validate_registry(document)[0]['rules'][0]['applicability']['ancestry'] == labels


@pytest.mark.parametrize('kind,completed', [('source', 'verified'), ('implementation', 'tested'), ('external', 'documented')])
def test_completed_review_cannot_be_a_bare_status(kind, completed):
    document = sample()
    document['rules'][0]['verification'][kind]['status'] = completed
    with pytest.raises(ValueError, match='requires documented'):
        rules.validate_registry(document)


def reviewed_fixture():
    document = sample()
    row = document['rules'][0]
    row['reference']['citation'] = 'Synthetic fixture citation, not a publication'
    row['implementation_id'] = 'synthetic_only'
    for key, states in rules.REVIEW_STATES.items():
        row['verification'][key] = dict(status=states[1], reviewer='Synthetic reviewer',
            evidence='Synthetic evidence text', scope='Synthetic points only; no clinical claim')
    row['status'] = 'validated'
    return document


def test_validated_requires_separate_review_claims_and_does_not_enable_execution(tmp_path):
    document = sample()
    document['rules'][0]['status'] = 'validated'
    with pytest.raises(ValueError, match='requires source, implementation and external'):
        rules.validate_registry(document)
    document = reviewed_fixture()
    path = tmp_path/'registry.json'
    path.write_text(json.dumps(document))
    loaded = rules.load_registry(path)
    assert loaded.record()['execution'] == 'not_implemented'
    assert loaded.document['rules'][0]['status'] == 'validated'
    assert any('case applicability' in w for w in loaded.warnings)
    for kind, field in [('source', 'citation'), ('implementation', 'implementation_id')]:
        broken = copy.deepcopy(document)
        if kind == 'source':
            broken['rules'][0]['reference'][field] = None
        else:
            broken['rules'][0][field] = None
        with pytest.raises(ValueError):
            rules.validate_registry(broken)


def test_unused_feature_stays_unspecified():
    document = sample()
    document['rules'][0].update(feature='ears', status='unused')
    assert 'feature remains unspecified' in rules.validate_registry(document)[1][-1]


@pytest.mark.parametrize('content', ['{"id":"a","id":"b"}', '{"rules":[{"id":"x","id":"y"}]}',
    '{"rules":NaN}', '{"rules":Infinity}', '[]', 'null'])
def test_loader_rejects_ambiguous_json(tmp_path, content):
    path = tmp_path/'bad.json'
    path.write_text(content)
    with pytest.raises(ValueError):
        rules.load_registry(path)


def test_cli_is_deterministic_and_templates_do_not_replace_inputs(tmp_path):
    from cranio.rules.__main__ import main
    output = tmp_path/'template.json'
    assert main(['template', '--id', 'fixture', '--output', str(output)]) == 0
    before = output.read_bytes()
    assert rules.load_registry(output).document == rules.empty_registry('fixture')
    assert main(['template', '--id', 'fixture', '--output', str(output)]) == 2
    assert output.read_bytes() == before
    assert main(['template', '--id', 'bad id', '--output', str(tmp_path/'invalid.json')]) == 2
    assert not (tmp_path/'invalid.json').exists()
    for name in ('registry.json', 'schema.json'):
        bundled = rules.DATA_DIR/name
        original = bundled.read_bytes()
        assert main(['template', '--id', 'fixture', '--output', str(bundled)]) == 2
        assert bundled.read_bytes() == original
    command = [sys.executable, '-m', 'cranio.rules', 'inspect']
    first = subprocess.run(command, capture_output=True, check=True).stdout
    assert first == subprocess.run(command, capture_output=True, check=True).stdout
    assert json.loads(first)['record']['execution'] == 'not_implemented'
    missing = subprocess.run(command+['--input', str(tmp_path/'missing.json')], capture_output=True)
    assert missing.returncode == 2 and b'Rule registry:' in missing.stderr


def test_registry_inspection_needs_no_numerical_or_network_modules():
    script = '''import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'numpy', 'scipy', 'tensorflow', 'bpy', 'socket', 'urllib'}:
        raise AssertionError('Unneeded import: '+name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from cranio.rules import load_registry
assert len(load_registry().document['rules']) == 6
'''
    subprocess.run([sys.executable, '-c', script], check=True, capture_output=True)

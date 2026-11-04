"""Synthetic representation checks only; no anatomical formula is implemented."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from dataclasses import FrozenInstanceError

import pytest
from cranio.rules import load_registry, RuleRegistry
from cranio.rules.contracts import Prediction, RuleResult, NotConfigured
from cranio.rules.engine import predict, readiness


def altered_registry(change):
    registry = load_registry()
    document = registry.document
    change(document)
    # Test-only metadata claims. These deliberately cannot authorize execution.
    return RuleRegistry(document, registry.warnings, registry.sha256, registry.schema_sha256)


def test_scalar_and_point_contract_preserves_units_and_unknown_sd():
    scalar = Prediction(12., 'mm')
    result = RuleResult(scalar, None, True, ('Synthetic measurement; SD unknown',))
    value, sd, applicable, notes = result
    assert (value, sd, applicable, notes) == (scalar, None, True, result.notes)
    point = Prediction((1., 2., 3.), 'mm', 'world')
    result = RuleResult(point, (0., 1., 2.), True, ('Synthetic coordinate SDs only',))
    record = result.as_dict()
    assert record['prediction'] == dict(value=[1., 2., 3.], units='mm', coordinate_space='world')
    assert record['sd'] == [0., 1., 2.]
    record['prediction']['value'][0] = 999
    assert point.value == (1., 2., 3.)
    with pytest.raises(FrozenInstanceError):
        point.units = 'm'


@pytest.mark.parametrize('value,units,frame', [
    (True, 'mm', None), (float('nan'), 'mm', None), (float('inf'), 'mm', None),
    ('1', 'mm', None), (1., 'm', None), (1., 'mm', 'world'),
    ((1., 2.), 'mm', 'world'), ((1., 2., float('nan')), 'mm', 'world'),
    ((1., 2., 3.), 'mm', None), ((1., 2., 3.), 'm', 'world'),
    ([1., 2., 3.], 'mm', 'world'), ((True, 2., 3.), 'mm', 'world')])
def test_invalid_prediction_representation(value, units, frame):
    with pytest.raises(ValueError):
        Prediction(value, units, frame)


@pytest.mark.parametrize('prediction,sd,applicable,notes', [
    (None, 0., None, ('Missing prediction',)), (None, None, True, ('Missing prediction',)),
    (None, None, 1, ('Invalid applicability',)), (None, None, None, ()),
    (None, None, None, ['Mutable notes']), (None, None, None, (' ',)),
    (Prediction(1., 'mm'), -1., True, ('Invalid SD',)),
    (Prediction(1., 'mm'), float('nan'), True, ('Invalid SD',)),
    (Prediction(1., 'mm'), True, True, ('Invalid SD',)),
    (Prediction(1., 'mm'), (1., 2., 3.), True, ('Invalid scalar SD',)),
    (Prediction((1., 2., 3.), 'mm', 'world'), 1., True, ('No inferred isotropy',)),
    (Prediction(1., 'mm'), None, False, ('Inapplicable prediction',)),
    (Prediction(1., 'mm'), None, None, ('Unknown applicability',)),
])
def test_invalid_or_ambiguous_result(prediction, sd, applicable, notes):
    with pytest.raises(ValueError):
        RuleResult(prediction, sd, applicable, notes)


def test_unknown_and_inapplicable_are_distinct():
    for applicable in (False, None):
        result = RuleResult(None, None, applicable, ('Synthetic state',))
        assert result.as_dict()['applicable'] is applicable
        assert result.as_dict()['prediction'] is None
        assert result.as_dict()['sd'] is None


@pytest.mark.parametrize('rule_id', [row['id'] for row in load_registry().document['rules'] if row['feature'] != 'ears'])
def test_unconfigured_rules_never_read_or_modify_observations(rule_id):
    observations = {'synthetic': [1., 2., 3.]}
    original = copy.deepcopy(observations)
    with pytest.raises(NotConfigured) as error:
        predict(rule_id, observations)
    assert error.value.rule_id == rule_id
    assert error.value.missing and 'verify-source' in str(error.value)
    assert observations == original
    # Even malformed observations cannot turn an unconfigured stub into a fit.
    with pytest.raises(NotConfigured):
        predict(rule_id, object())


def test_ear_is_unused_not_an_assessed_inapplicable_case():
    result = predict('ears_guyomarch_stephan_2012')
    assert tuple(result)[:3] == (None, None, None)
    assert 'unspecified' in ' '.join(result.notes)
    row = readiness(rule_id='ears_guyomarch_stephan_2012')['rules'][0]
    assert row['registry_status'] == 'needs_verification'
    assert row['execution_status'] == 'unused'


def test_review_claims_and_implementation_ids_cannot_enable_formula():
    def change(document):
        row = document['rules'][0]
        row['reference']['citation'] = 'Synthetic test citation, not evidence'
        row['implementation_id'] = 'arbitrary_identifier'
        row['status'] = 'validated'
        for key, status in [('source', 'verified'), ('implementation', 'tested'), ('external', 'documented')]:
            row['verification'][key] = dict(status=status, reviewer='Synthetic reviewer',
                evidence='Synthetic fixture', scope='Software test only')
    registry = altered_registry(change)
    with pytest.raises(NotConfigured):
        predict(registry.document['rules'][0]['id'], registry=registry)
    report = readiness(registry)
    assert report['rules'][0]['registry_status'] == 'validated'
    assert report['rules'][0]['execution_status'] == 'not_configured'


def test_unknown_implementation_unused_policy_and_conflicts():
    registry = altered_registry(lambda d: d['rules'][0].update(id='custom_rule', implementation_id='not_imported'))
    assert readiness(registry)['rules'][0]['execution_status'] == 'not_configured'
    with pytest.raises(NotConfigured, match='code-owned'):
        predict('custom_rule', registry=registry)
    registry = altered_registry(lambda d: d['rules'][0].update(status='unused'))
    assert readiness(registry)['rules'][0]['execution_status'] == 'unused'
    registry = altered_registry(lambda d: d['rules'][0].update(feature='mouth'))
    with pytest.raises(ValueError, match='conflicts'):
        readiness(registry)
    with pytest.raises(ValueError, match='Unknown rule id'):
        predict('absent_rule')
    with pytest.raises(ValueError, match='Unknown rule id'):
        readiness(rule_id='absent_rule')


def test_readiness_is_deterministic_and_does_not_mutate_registry():
    registry = load_registry()
    before = registry.document
    first = readiness(registry)
    assert first == readiness(registry) and before == registry.document
    assert [row['execution_status'] for row in first['rules']].count('not_configured') == 5
    assert first['rules'][-1]['execution_status'] == 'unused'
    assert all(row['result']['prediction'] is None and row['result']['sd'] is None
               and row['result']['applicable'] is None for row in first['rules'])
    assert first['registry']['sha256'] == registry.sha256


@pytest.mark.parametrize('encoding', ['ascii', 'cp1252', 'utf-8'])
def test_status_cli_is_portable_and_invalid_rule_fails(encoding):
    command = [sys.executable, '-m', 'cranio.rules', 'status']
    env = dict(os.environ, PYTHONIOENCODING=encoding)
    result = subprocess.run(command, capture_output=True, env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.isascii() and json.loads(result.stdout) == readiness()
    selected = subprocess.run(command+['--rule', 'nose_projection_guidelines'], capture_output=True, env=env)
    assert selected.returncode == 0, selected.stderr
    assert len(json.loads(selected.stdout)['rules']) == 1
    invalid = subprocess.run(command+['--rule', 'missing'], capture_output=True, env=env)
    assert invalid.returncode == 2 and b'Unknown rule id' in invalid.stderr


def test_contract_engine_loads_without_numpy_bpy_or_network():
    script = '''import sys, builtins
sys.path.insert(0, sys.argv[1])
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'numpy', 'scipy', 'tensorflow', 'bpy'}:
        raise AssertionError(name)
    return original(name, *args, **kwargs)
def no_network(event, args):
    if event.startswith('socket.'):
        raise AssertionError(event)
builtins.__import__ = guarded
sys.addaudithook(no_network)
from cranio.rules.engine import readiness
assert len(readiness()['rules']) == 6
'''
    result = subprocess.run([sys.executable, '-I', '-S', '-c', script,
                             str(Path(__file__).resolve().parents[1])], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

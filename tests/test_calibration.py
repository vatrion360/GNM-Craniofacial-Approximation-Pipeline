"""Synthetic calibration plumbing; no human data or population validity claims."""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from cranio.calibration import (coverage_metrics, fit_multiplier, load_manifest, main,
                                protocol_hash, fit_calibration, evaluate_calibration, empty_manifest)
from cranio.validation import sha256_file


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def manifest_case(tmp_path):
    protocol = dict(model_sha256=digest('model'), fit_settings_sha256=digest('settings'),
        region_definition_sha256=digest('regions'), units='world_mm', prediction_kind='statistical_ensemble_mean',
        error_definition='euclidean_correspondence', target_coverage=.75, quantile_method='higher',
        pooling='pooled_vertices', alignment_protocol='synthetic fixed common frame; no registration',
        source='synthetic software test only')
    cases = []
    for i, errors in enumerate(([1, 2], [3, 4], [5, 6])):
        path = tmp_path/f'case{i}.csv'
        path.write_text('vertex_index,region,error_mm,spread_rms_mm\n'+
                        ''.join(f'{j},{region},{e},1\n' for j, (region, e) in enumerate(zip(['nose', 'chin'], errors))))
        cases.append(dict(case_id=f'case{i}', subject_id=f'subject{i}', split='calibration' if i < 2 else 'validation',
                          measurements=path.name, measurements_sha256=sha256_file(path),
                          ensemble_sha256=digest(f'ensemble{i}'), reference_sha256=digest(f'reference{i}'),
                          conditioning='skull_only'))
    doc = dict(schema_version=1, protocol=protocol, cases=cases)
    path = tmp_path/'manifest.json'
    path.write_text(json.dumps(doc))
    return doc, path


def write_doc(path, doc):
    path.write_text(json.dumps(doc))


def test_known_factor_and_disjoint_validation_not_used_for_fit(manifest_case):
    _, path = manifest_case
    manifest, cases, _ = load_manifest(path)
    result = fit_calibration(manifest, cases)
    assert result['factor'] == 4  # higher quantile at .75 of [1,2,3,4]
    assert result['calibration']['before']['pooled']['coverage'] == .25
    assert result['calibration']['after']['pooled']['coverage'] == 1
    assert result['validation']['after']['pooled']['coverage'] == 0
    assert result['validation']['after']['subject_count'] == 1
    assert result['calibration_status'] == 'exploratory'
    cases[2]['errors'] *= 100
    assert fit_calibration(manifest, cases)['factor'] == 4


def test_inclusive_boundary_and_zero_spread_policy():
    result = coverage_metrics([0, 1, 2, 3], [0, 0, 1, 1], 2.)
    assert result['coverage'] == .5
    assert result['zero_spread_vertices'] == 2
    assert result['zero_spread_positive_error_vertices'] == 1
    with pytest.raises(ValueError, match='no finite'):
        fit_multiplier([0, 1], [0, 0], .95)
    with pytest.raises(ValueError, match='No positive'):
        fit_multiplier([0, 0], [0, 0], .95)
    assert fit_multiplier([0, 2], [0, 1], .95) == 2


@pytest.mark.parametrize('errors,spread,factor', [([], [], 1.), ([-1], [1], 1.), ([1], [-1], 1.),
    ([np.nan], [1], 1.), ([1], [np.inf], 1.), ([1, 2], [1], 1.), ([1], [1], -1.), ([1], [1], True)])
def test_invalid_numeric_inputs(errors, spread, factor):
    with pytest.raises(ValueError):
        coverage_metrics(errors, spread, factor)


def test_cli_deterministic_fit_evaluate_and_no_overwrite(manifest_case, tmp_path):
    doc, path = manifest_case
    output, second = tmp_path/'fit.json', tmp_path/'fit2.json'
    assert main(['fit', '--manifest', str(path), '--output', str(output)]) == 0
    assert main(['fit', '--manifest', str(path), '--output', str(second)]) == 0
    assert output.read_bytes() == second.read_bytes()
    assert main(['fit', '--manifest', str(path), '--output', str(output)]) == 2
    assert main(['fit', '--manifest', str(path), '--output', str(path)]) == 2
    validation = dict(doc, cases=doc['cases'][2:])
    vpath = tmp_path/'validation.json'
    write_doc(vpath, validation)
    evaluated = tmp_path/'evaluation.json'
    assert main(['evaluate', '--manifest', str(vpath), '--calibration', str(output), '--output', str(evaluated)]) == 0
    report = json.loads(evaluated.read_text())
    assert report['factor'] == 4 and report['calibration_subject_count'] == 2
    assert report['after']['pooled']['coverage'] == 0


@pytest.mark.parametrize('field', ['subject_id', 'case_id', 'measurements_sha256', 'ensemble_sha256', 'reference_sha256'])
def test_duplicate_cases_and_split_leakage_refused(manifest_case, field):
    doc, path = manifest_case
    doc['cases'][2][field] = doc['cases'][0][field]
    write_doc(path, doc)
    with pytest.raises(ValueError, match='Reused'):
        load_manifest(path)


@pytest.mark.parametrize('field', ['subject_id', 'case_id', 'measurements_sha256', 'ensemble_sha256', 'reference_sha256'])
def test_frozen_evaluation_refuses_training_identity(manifest_case, field):
    _, path = manifest_case
    doc, cases, _ = load_manifest(path)
    record = fit_calibration(doc, cases)
    vcase = copy.deepcopy(cases[2])
    vcase['metadata'][field] = cases[0]['metadata'][field]
    with pytest.raises(ValueError, match='leakage'):
        evaluate_calibration(record, doc, [vcase])


@pytest.mark.parametrize('change', ['hash', 'conditioning', 'units', 'unknown', 'coverage', 'pooling', 'quantile', 'source'])
def test_manifest_rejection(manifest_case, change):
    doc, path = manifest_case
    if change == 'hash': doc['cases'][0]['measurements_sha256'] = '0'*64
    if change == 'conditioning': doc['cases'][0]['conditioning'] = 'ct_conditioned'
    if change == 'units': doc['protocol']['units'] = 'm'
    if change == 'unknown': doc['protocol']['guess'] = True
    if change == 'coverage': doc['protocol']['target_coverage'] = None
    if change == 'pooling': doc['protocol']['pooling'] = None
    if change == 'quantile': doc['protocol']['quantile_method'] = 'linear'
    if change == 'source': doc['protocol']['source'] = 'unspecified'
    write_doc(path, doc)
    with pytest.raises(ValueError):
        load_manifest(path)


@pytest.mark.parametrize('rows', ['0,nose,1,1\n0,chin,2,1\n', '0,nose,nan,1\n',
                                 '0,nose,1\n', '0,nose,1,1,extra\n', '-1,nose,1,1\n'])
def test_malformed_csv_refused(manifest_case, rows):
    doc, path = manifest_case
    csv = path.parent/doc['cases'][0]['measurements']
    csv.write_text('vertex_index,region,error_mm,spread_rms_mm\n'+rows)
    doc['cases'][0]['measurements_sha256'] = sha256_file(csv)
    write_doc(path, doc)
    with pytest.raises(ValueError):
        load_manifest(path)


def test_missing_region_reports_actual_subject_count(manifest_case):
    _, path = manifest_case
    doc, cases, _ = load_manifest(path)
    cases[1]['regions'][:] = 'other'
    record = fit_calibration(doc, cases)
    assert record['calibration']['after']['regions']['nose']['subject_count'] == 1
    assert record['calibration']['after']['subject_count'] == 2


def test_protocol_change_refused_without_recalibration(manifest_case):
    _, path = manifest_case
    doc, cases, _ = load_manifest(path)
    record = fit_calibration(doc, cases)
    different = copy.deepcopy(doc)
    different['protocol']['region_definition_sha256'] = digest('new ROI')
    with pytest.raises(ValueError, match='protocol mismatch'):
        evaluate_calibration(record, different, cases[2:])


def test_no_holdout_and_minimum_case_guard(manifest_case):
    _, path = manifest_case
    doc, cases, _ = load_manifest(path)
    with pytest.raises(ValueError, match='At least two'):
        fit_calibration(doc, cases[:1])
    result = fit_calibration(doc, cases[:2])
    assert result['validation']['after'] is None
    assert any('No held-out' in w for w in result['warnings'])


def test_template_has_no_scientific_defaults(tmp_path):
    path = tmp_path/'template.json'
    assert main(['template', '--output', str(path)]) == 0
    assert json.loads(path.read_text()) == empty_manifest()
    with pytest.raises(ValueError):
        protocol_hash(empty_manifest()['protocol'])
    assert main(['fit', '--manifest', str(path), '--output', str(tmp_path/'no.json')]) == 2


def test_input_change_prevents_output(manifest_case, tmp_path, monkeypatch):
    import cranio.calibration as module
    _, path = manifest_case
    original = module.fit_calibration
    def change(*a, **kw):
        result = original(*a, **kw)
        path.write_text(path.read_text()+'\n')
        return result
    monkeypatch.setattr(module, 'fit_calibration', change)
    output = tmp_path/'changed.json'
    assert main(['fit', '--manifest', str(path), '--output', str(output)]) == 2
    assert not output.exists()


def test_direct_api_refuses_repeated_subject(manifest_case):
    _, path = manifest_case
    doc, cases, _ = load_manifest(path)
    with pytest.raises(ValueError, match='Reused'):
        fit_calibration(doc, [cases[0], cases[0]])


def test_unequal_case_sizes_show_both_weightings(manifest_case):
    _, path = manifest_case
    doc, cases, _ = load_manifest(path)
    # At factor one, case0 covers 1/2, case1 covers all 3.
    cases[1]['errors'] = np.array([0., 0., 0.])
    cases[1]['spread'] = np.ones(3)
    cases[1]['regions'] = np.array(['nose', 'chin', 'chin'])
    report = fit_calibration(doc, cases)
    pooled = report['calibration']['before']['pooled']
    assert pooled['coverage'] == .8
    assert pooled['equal_case_mean_coverage'] == .75


def test_external_zero_spread_failure_count_is_retained(manifest_case):
    _, path = manifest_case
    doc, cases, _ = load_manifest(path)
    record = fit_calibration(doc, cases[:2])
    cases[2]['spread'][:] = 0
    report = evaluate_calibration(record, doc, cases[2:])
    assert report['after']['pooled']['coverage'] == 0
    assert report['after']['pooled']['zero_spread_positive_error_vertices'] == 2


def test_bundled_example_hashes_and_known_negative_holdout():
    path = Path(__file__).resolve().parents[1]/'examples/calibration_synthetic/manifest.json'
    manifest, cases, _ = load_manifest(path)
    report = fit_calibration(manifest, cases)
    assert report['factor'] == 4
    assert report['calibration']['after']['pooled']['coverage'] == 1
    assert report['validation']['after']['pooled']['coverage'] == 0

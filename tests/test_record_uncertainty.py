"""Synthetic association checks, not CT calibration or anatomical validation."""
import copy
import json
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest

from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline
from cranio.record import build_record, canonical_bytes, main
from cranio.record_uncertainty import summarize_link
from cranio.uncertainty import main as ensemble_cli
from cranio.validation import sha256_file


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


@pytest.fixture
def evidence(tmp_path, model_file, marker_file):
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), regularization='30',
                         output=str(tmp_path/'fit'/'face.obj'))
    assert run_pipeline(cfg) == 0
    placement = tmp_path/'placement.json'
    placement.write_bytes(canonical_bytes(dict(schema_version=1, placement={
        f'P{i}': dict(sigma_mm=0., source='Synthetic zero-error replay') for i in range(12)})))
    path = tmp_path/'ensemble.json'
    args = ['--input', str(marker_file), '--npz', str(model_file), '--placement', str(placement),
            '--samples', '2', '--output', str(path)]
    assert ensemble_cli(args) == 0
    return cfg, path


def summary(evidence):
    cfg, path = evidence
    return summarize_link(read(cfg.output_json), read(path), 'off', sha256_file(path))


def test_link_preserves_diagnostics_without_mesh_uncertainty(evidence, tmp_path):
    cfg, source = evidence
    before = {Path(p): Path(p).read_bytes() for p in
              (cfg.output_json, cfg.output, cfg.output_statistical, cfg.output_error_mesh, cfg.input, cfg.npz, source)}
    output = build_record(cfg.output_json, tmp_path/'record', uncertainty_path=source, uncertainty_scenario='off')
    result = read(output)
    link = result['assessments']['uncertainty']
    assert link['status'] == 'linked_uncalibrated_analysis'
    assert link['final_mesh_uncertainty'] == 'not_assessed'
    assert link['calibration_status'] == 'uncalibrated'
    assert link['source_sha256'] == sha256_file(source)
    assert link['comparison']['central_targets_vertices_weights_exact_match'] is True
    assert link['comparison']['equivalence'] == 'not_established'
    assert link['scenario_diagnostics']['off']['sample_count'] == 2
    assert any('All configured SDs are zero' in w for w in link['source_warnings'])
    for key in ('calibration', 'validity_domain', 'scientific_export_authorization'):
        assert result['assessments'][key]['status'] == 'not_assessed'
    text = (output.parent/'approximation_record.txt').read_text(encoding='utf-8')
    assert 'NOT uncertainty of this fitted final mesh' in text
    assert 'Samples: 2' in text
    envelope = read(output.parent/'provenance.json')
    assert envelope['uncertainty_file']['sha256'] == sha256_file(source)
    assert all(p.read_bytes() == content for p, content in before.items())


def test_same_source_moved_and_repeat_exports_identical(evidence, tmp_path):
    cfg, path = evidence
    first = build_record(cfg.output_json, tmp_path/'one', uncertainty_path=path, uncertainty_scenario='off')
    moved = tmp_path/'moved.json'
    moved.write_bytes(path.read_bytes())
    path.unlink()
    second = build_record(cfg.output_json, tmp_path/'two', uncertainty_path=moved, uncertainty_scenario='off')
    assert first.read_bytes() == second.read_bytes()
    assert read(first.parent/'provenance.json')['uncertainty_file']['path'] != str(moved.resolve())


def test_unrequested_link_has_no_new_fields(evidence, tmp_path):
    cfg, _ = evidence
    output = build_record(cfg.output_json, tmp_path/'plain')
    assert read(output)['assessments']['uncertainty']['status'] == 'not_assessed'
    assert 'uncertainty_file' not in read(output.parent/'provenance.json')


@pytest.mark.parametrize('bad', ['model', 'markers', 'metadata', 'schema', 'method', 'units',
    'calibrated', 'count', 'seed', 'sample_missing', 'nonconverged_index', 'clipped_index',
    'status', 'bool_converged', 'reflection', 'dimension', 'nan', 'duplicate_labels',
    'duplicate_vertices', 'weights', 'central_shape', 'partial', 'placement', 'warnings', 'scenarios'])
def test_invalid_or_unrelated_evidence_refused(evidence, tmp_path, bad):
    cfg, path = evidence
    report, ensemble = read(cfg.output_json), read(path)
    scenario = ensemble['variants']['off']
    if bad in ('model', 'markers'):
        digest = report['inputs'][bad]['sha256']
        ensemble['input_hashes'] = {k: v for k, v in ensemble['input_hashes'].items() if v != digest}
    elif bad == 'metadata': ensemble['marker_metadata']['model_sha256'] = 'b'*64
    elif bad == 'schema': ensemble['schema_version'] = True
    elif bad == 'method': ensemble['method'] = 'posterior'
    elif bad == 'units': ensemble['units'] = 'm'
    elif bad == 'calibrated': ensemble['calibration_status'] = 'calibrated'
    elif bad == 'count': ensemble['samples'] = True
    elif bad == 'seed': ensemble['seed'] = -1
    elif bad == 'sample_missing': scenario['samples'].pop()
    elif bad == 'nonconverged_index': scenario['nonconverged_indices'] = [False]
    elif bad == 'clipped_index': scenario['clipped_indices'] = [0]
    elif bad == 'status': scenario['numerical_status'] = 'nonconverged'
    elif bad == 'bool_converged': scenario['samples'][0]['converged'] = 1
    elif bad == 'reflection': scenario['samples'][0]['rotation'] = [[-1,0,0], [0,1,0], [0,0,1]]
    elif bad == 'dimension': scenario['samples'][0]['coefficients'] = [0.]
    elif bad == 'nan': ensemble['settings']['max_iter'] = float('nan')
    elif bad == 'duplicate_labels': ensemble['labels'][1] = ensemble['labels'][0]
    elif bad == 'duplicate_vertices': ensemble['vertex_indices'][1] = ensemble['vertex_indices'][0]
    elif bad == 'weights': ensemble['weights'][0] = -1
    elif bad == 'central_shape': ensemble['central_targets_mm'] = []
    elif bad == 'partial': ensemble['omitted_error_inputs'] = ['placement:P0']
    elif bad == 'placement': ensemble['placement']['P0']['sigma_mm'] = -1
    elif bad == 'warnings': ensemble['warnings'] = 'none'
    elif bad == 'scenarios': ensemble['settings']['prior_variants'] = ['off', 'off']
    path.write_text(json.dumps(ensemble), encoding='utf-8')
    with pytest.raises(ValueError):
        build_record(cfg.output_json, tmp_path/'bad', uncertainty_path=path, uncertainty_scenario='off')
    assert not (tmp_path/'bad').exists()


def test_nonconvergence_clipping_and_partial_sources_retained(evidence):
    cfg, path = evidence
    ensemble = read(path)
    case = ensemble['variants']['off']
    case['samples'][0]['converged'] = False
    case['baseline']['converged'] = False
    case['samples'][1]['clipped_active_count'] = 1
    case.update(nonconverged_indices=[0], clipped_indices=[1], numerical_status='nonconverged')
    ensemble.update(analysis_status='partial_conditional_sensitivity', omitted_error_inputs=['placement:P0'])
    ensemble['placement']['P0'] = dict(sigma_mm=None, source=None)
    before = copy.deepcopy(ensemble)
    result = summarize_link(read(cfg.output_json), ensemble, 'off', sha256_file(path))
    assert result['scenario_diagnostics']['off']['numerical_status'] == 'nonconverged'
    assert result['scenario_diagnostics']['off']['nonconverged_indices'] == [0]
    assert result['scenario_diagnostics']['off']['clipped_indices'] == [1]
    assert result['placement']['P0']['sigma_mm'] is None
    assert result['omitted_error_inputs'] == ['placement:P0']
    assert ensemble == before


def test_different_targets_settings_and_extra_losses_never_claim_equivalence(evidence):
    cfg, path = evidence
    report = read(cfg.output_json)
    report['landmarks'][0]['target_mm'][0] += 1  # synthetic diagnostic difference
    report['config'].update(regularization='adaptive', skip_tps=False, measurement_weight=1.)
    result = summarize_link(report, read(path), 'off', sha256_file(path))
    assert result['comparison']['central_targets_vertices_weights_exact_match'] is False
    assert result['comparison']['settings']['regularization'] == dict(run='adaptive', ensemble=30.)
    assert result['comparison']['run_features']['skip_tps'] is False
    assert result['comparison']['run_features']['measurement_weight'] == 1.
    assert result['comparison']['equivalence'] == 'not_established'
    assert result['final_mesh_uncertainty'] == 'not_assessed'


def test_prior_scenario_must_match_state_and_hash(evidence, tmp_path):
    cfg, path = evidence
    report = read(cfg.output_json)
    ensemble = read(path)
    ensemble['variants']['on'] = copy.deepcopy(ensemble['variants']['off'])
    ensemble['settings']['prior_variants'] = ['on', 'off']
    with pytest.raises(ValueError, match='prior state'):
        summarize_link(report, ensemble, 'on', sha256_file(path))
    report['inputs']['prior'] = dict(path='prior.npz', sha256='a'*64)
    with pytest.raises(ValueError, match='prior hash'):
        summarize_link(report, ensemble, 'on', sha256_file(path))
    ensemble['prior_record'] = dict(sha256='a'*64)
    ensemble['input_hashes']['prior.npz'] = 'a'*64
    assert summarize_link(report, ensemble, 'on', sha256_file(path))['selected_prior_scenario'] == 'on'


def test_real_prior_cli_link(tmp_path, model_file, marker_file):
    prior = tmp_path/'prior.npz'
    np.savez(prior, mean=np.zeros(3), scale=np.ones(3))
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), prior=str(prior),
                         regularization='30', output=str(tmp_path/'face.obj'))
    assert run_pipeline(cfg) == 0
    placement = tmp_path/'placement.json'
    placement.write_bytes(canonical_bytes(dict(schema_version=1, placement={
        f'P{i}': dict(sigma_mm=0., source='Synthetic zero replay') for i in range(12)})))
    source = tmp_path/'ensemble.json'
    assert ensemble_cli(['--input', str(marker_file), '--npz', str(model_file), '--placement', str(placement),
        '--samples', '2', '--prior', str(prior), '--prior-variants', 'off', 'on', '--output', str(source)]) == 0
    output = build_record(cfg.output_json, tmp_path/'record', uncertainty_path=source, uncertainty_scenario='on')
    link = read(output)['assessments']['uncertainty']
    assert link['selected_prior_scenario'] == 'on'
    assert set(link['scenario_diagnostics']) == {'off', 'on'}


def test_cli_requires_explicit_pair_and_rejects_duplicate_json(evidence, tmp_path):
    cfg, path = evidence
    base = ['build', '--report', cfg.output_json, '--output-dir', str(tmp_path/'record')]
    for extra in (['--uncertainty', str(path)], ['--uncertainty-scenario', 'off']):
        with pytest.raises(SystemExit): main(base+extra)
    assert not (tmp_path/'record').exists()
    assert main(base+['--uncertainty', str(path), '--uncertainty-scenario', 'off']) == 0
    bad = tmp_path/'bad.json'
    bad.write_text('{"schema_version":1,"schema_version":1}', encoding='utf-8')
    with pytest.raises(ValueError):
        build_record(cfg.output_json, tmp_path/'bad-record', uncertainty_path=bad, uncertainty_scenario='off')


def test_linked_input_drift_prevents_completion(evidence, tmp_path, monkeypatch):
    import cranio.export
    cfg, source = evidence
    original = cranio.export.atomic_text
    @contextmanager
    def change(path):
        with original(path) as stream:
            yield stream
        if Path(path).name == 'provenance.json':
            source.write_bytes(source.read_bytes()+b' ')
    monkeypatch.setattr(cranio.export, 'atomic_text', change)
    with pytest.raises(ValueError, match='Uncertainty source changed'):
        build_record(cfg.output_json, tmp_path/'record', uncertainty_path=source, uncertainty_scenario='off')
    assert not (tmp_path/'record'/'approximation_record.json').exists()

"""Known synthetic ensembles check geometry, sample statistics and safe publication."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

from cranio.backend import GNMBackend
from cranio.export import export_obj
from cranio.uncertainty_export import (export_bundle, main, region_indices, replay_vertices,
                                      representative_indices, summarize_ensemble)
from cranio.validation import sha256_file


@pytest.fixture
def ensemble(model_file, tmp_path):
    model = GNMBackend(model_file).load()
    rows = [dict(coefficients=[0.]*model.identity_dim, scale=1., rotation=np.eye(3).tolist(),
                 translation_mm=[float(x), 0., 0.], converged=True, clipped_active_count=0) for x in (-2, 0, 2, 4)]
    scenario = dict(baseline=copy.deepcopy(rows[1]), samples=rows, numerical_status='converged',
                    nonconverged_indices=[], clipped_indices=[])
    record = dict(schema_version=1, method='marker_error_propagation', calibration_status='uncalibrated',
        analysis_status='configured_input_propagation', units='world_mm', samples=len(rows),
        variants={'off': scenario}, input_hashes={str(model_file): sha256_file(model_file)},
        marker_metadata={}, warnings=['synthetic fixture'], settings={}, seed=0, omitted_error_inputs=[])
    path = tmp_path/'ensemble.json'
    path.write_text(json.dumps(record))
    return model, record, path, model_file


def test_translation_known_mean_sd_and_pose_is_not_removed(ensemble):
    model, record, *_ = ensemble
    result = summarize_ensemble(model, record)['off']
    np.testing.assert_allclose(result['mean'], model.mu+[1., 0., 0.], atol=1e-13)
    expected = np.std([-2., 0., 2., 4.], ddof=1)
    np.testing.assert_allclose(result['sd_xyz'], np.tile([expected, 0., 0.], (model.vertex_count, 1)), atol=1e-13)
    np.testing.assert_allclose(result['spread'], expected, atol=1e-13)
    assert result['summary']['regions']['all_vertices']['vertex_count'] == model.vertex_count
    # Beta ties are ordered deterministically, but distinct poses are kept.
    assert [r['sample_index'] for r in result['summary']['selected_variants']] == [0, 1, 2]
    assert result['summary']['selected_variants'][0]['fraction_vertices_within_one_spread'] == 0


def test_mean_of_posed_vertices_not_mean_parameters_and_numpy_reference(ensemble):
    model, record, *_ = ensemble
    samples = record['variants']['off']['samples']
    samples[0].update(coefficients=[1., 0., 0.], scale=2., rotation=[[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
    samples[1].update(coefficients=[-1., 1., 0.], scale=.5)
    vertices = np.array([replay_vertices(model, s) for s in samples])
    result = summarize_ensemble(model, record)['off']
    np.testing.assert_allclose(result['mean'], vertices.mean(axis=0), atol=1e-13)
    np.testing.assert_allclose(result['sd_xyz'], vertices.std(axis=0, ddof=1), atol=1e-13)
    np.testing.assert_allclose(result['spread']**2, ((vertices-vertices.mean(0))**2).sum(axis=(0, 2))/3, atol=1e-11)
    assert not np.allclose(result['mean'], model.generate(np.mean([s['coefficients'] for s in samples], axis=0)))


def test_world_rigid_transform_rotates_mean_preserves_total_spread(ensemble):
    model, record, *_ = ensemble
    original = summarize_ensemble(model, record)['off']
    q, _ = np.linalg.qr(np.random.default_rng(2).normal(size=(3, 3)))
    q[:, 0] *= np.linalg.det(q)
    shift = np.array([40., 15., -20.])
    for row in [record['variants']['off']['baseline'], *record['variants']['off']['samples']]:
        row['rotation'] = (q @ np.array(row['rotation'])).tolist()
        row['translation_mm'] = (q @ row['translation_mm'] + shift).tolist()
    changed = summarize_ensemble(model, record)['off']
    np.testing.assert_allclose(changed['mean'], original['mean'] @ q.T + shift, atol=1e-13)
    np.testing.assert_allclose(changed['spread'], original['spread'], atol=1e-13)
    assert not np.allclose(changed['sd_xyz'], original['sd_xyz'])


def test_zero_and_duplicate_ensemble_does_not_invent_variants(ensemble):
    model, record, *_ = ensemble
    scenario = record['variants']['off']
    scenario['samples'] = [copy.deepcopy(scenario['baseline']) for _ in range(4)]
    result = summarize_ensemble(model, record, variants=5)['off']
    assert not result['sd_xyz'].any() and not result['spread'].any()
    assert result['summary']['actual_variants'] == 1
    assert result['summary']['selected_variants'][0]['sample_index'] == 0


def test_beta_selection_centroid_then_farthest():
    rows = [dict(coefficients=[x], scale=1., rotation=np.eye(3).tolist(), translation_mm=[0., 0., 0.])
            for x in (-3., -1., 0., 1., 3.)]
    assert representative_indices(rows, 3) == [2, 0, 4]


def test_separate_priors_regions_and_no_input_mutation(ensemble):
    model, record, _, model_path = ensemble
    record['variants']['on'] = copy.deepcopy(record['variants']['off'])
    for row in record['variants']['on']['samples']:
        row['translation_mm'][0] *= 2
    regions = dict(schema_version=1, model_sha256=sha256_file(model_path),
                   regions={'reviewed': dict(vertex_indices=[0, 2, 1], source='synthetic mask')})
    original = copy.deepcopy(record)
    results = summarize_ensemble(model, record, regions=regions, model_hash=sha256_file(model_path))
    assert original == record
    np.testing.assert_allclose(results['on']['spread'], 2*results['off']['spread'])
    region = results['off']['summary']['regions']['reviewed']
    assert region['vertex_count'] == 3
    assert region['spatial_p025_spread_rms_mm'] == pytest.approx(region['spatial_p975_spread_rms_mm'])


@pytest.mark.parametrize('bad', ['count', 'status', 'baseline', 'sample', 'rotation', 'reflection', 'scale',
                               'nan', 'coefficients', 'clipping', 'units', 'calibrated', 'method', 'scenario'])
def test_invalid_or_nonconverged_ensemble_never_drops_rows(ensemble, bad):
    model, record, *_ = ensemble
    s = record['variants']['off']
    if bad == 'count': record['samples'] = 3
    if bad == 'status': s['numerical_status'] = 'nonconverged'
    if bad == 'baseline': s['baseline']['converged'] = False
    if bad == 'sample': s['samples'][0]['converged'] = False
    if bad == 'rotation': s['samples'][0]['rotation'][0][0] = 2.
    if bad == 'reflection': s['samples'][0]['rotation'][0][0] = -1.
    if bad == 'scale': s['samples'][0]['scale'] = -1.
    if bad == 'nan': s['samples'][0]['translation_mm'][0] = np.nan
    if bad == 'coefficients': s['samples'][0]['coefficients'] = [0.]
    if bad == 'clipping': s['clipped_indices'] = [0]
    if bad == 'units': record['units'] = 'm'
    if bad == 'calibrated': record['calibration_status'] = 'calibrated'
    if bad == 'method': record['method'] = 'posterior'
    if bad == 'scenario': record['variants']['../../escape'] = s
    with pytest.raises(ValueError):
        summarize_ensemble(model, record)


@pytest.mark.parametrize('indices', [[], [-1], [0, 0], [9999], [True], [1.5]])
def test_invalid_regions_fail(indices):
    doc = dict(schema_version=1, model_sha256='a'*64, regions={'x': dict(vertex_indices=indices, source='synthetic')})
    with pytest.raises(ValueError): region_indices(doc, 12, 'a'*64)


def test_region_hash_and_reserved_name():
    doc = dict(schema_version=1, model_sha256='a'*64, regions={})
    with pytest.raises(ValueError, match='hash'): region_indices(doc, 12, 'b'*64)
    doc['regions']['all_vertices'] = dict(vertex_indices=[0], source='x')
    with pytest.raises(ValueError, match='reserved'): region_indices(doc, 12, 'a'*64)


def test_export_determinism_hashes_numeric_ply_and_obj(ensemble, tmp_path):
    model, record, path, model_path = ensemble
    outputs = [tmp_path/'out1', tmp_path/'out2']
    summaries = [export_bundle(path, model_path, out) for out in outputs]
    assert summaries[0] == summaries[1]
    for name, digest in summaries[0]['output_sha256'].items():
        assert sha256_file(outputs[0]/name) == sha256_file(outputs[1]/name) == digest
    assert (outputs[0]/'summary.json').read_bytes() == (outputs[1]/'summary.json').read_bytes()
    text = (outputs[0]/'prior_off/spread.ply').read_text()
    assert 'NOT face accuracy' in text and 'ddof=1' in text and 'common_color_scale_mm' in text
    lines = text.split('end_header\n')[1].splitlines()[:model.vertex_count]
    numbers = np.array([[float(x) for x in line.split()] for line in lines])
    np.testing.assert_allclose(numbers[:, :3], model.mu+[1, 0, 0], atol=1e-13)
    np.testing.assert_allclose(numbers[:, 6], np.std([-2, 0, 2, 4], ddof=1), atol=1e-13)
    np.testing.assert_array_equal(numbers[:, 7:9], 0)
    assert 'Actual simulation sample index 0' in (outputs[0]/'prior_off/variant_01.obj').read_text()
    assert 'not a single fitted identity' in (outputs[0]/'prior_off/mean.obj').read_text()
    with pytest.raises(ValueError, match='new'): export_bundle(path, model_path, outputs[0])
    assert json.loads((outputs[0]/'summary.json').read_text()) == summaries[0]


def test_clipping_partial_and_fewer_variants_remain_visible(ensemble, tmp_path):
    _, record, path, model_path = ensemble
    record['analysis_status'] = 'partial_conditional_sensitivity'
    record['omitted_error_inputs'] = ['placement:P0']
    s = record['variants']['off']
    s['samples'][0]['clipped_active_count'] = 1
    s['clipped_indices'] = [0]
    path.write_text(json.dumps(record))
    summary = export_bundle(path, model_path, tmp_path/'partial', variants=5)
    assert summary['analysis_status'] == 'partial_conditional_sensitivity'
    assert summary['omitted_error_inputs'] == ['placement:P0']
    assert any('clipping active' in w for w in summary['warnings'])
    assert any('4 distinct' in w for w in summary['warnings'])
    assert 'partial_conditional_sensitivity' in (tmp_path/'partial/prior_off/spread.ply').read_text()


def test_failure_and_input_changes_publish_nothing(ensemble, tmp_path, monkeypatch):
    import cranio.uncertainty_export as module
    _, _, path, model_path = ensemble
    original = module.export_spread_ply
    def fail(*args, **kwargs):
        raise OSError('synthetic disk failure')
    monkeypatch.setattr(module, 'export_spread_ply', fail)
    output = tmp_path/'failed'
    with pytest.raises(OSError): export_bundle(path, model_path, output)
    assert not output.exists() and not list(tmp_path.glob('.gnm-ensemble-*'))
    def change(*args, **kwargs):
        original(*args, **kwargs)
        path.write_text('{}')
    monkeypatch.setattr(module, 'export_spread_ply', change)
    with pytest.raises(ValueError, match='input changed'): export_bundle(path, model_path, output)
    assert not output.exists() and not list(tmp_path.glob('.gnm-ensemble-*'))


def test_cli_and_wrong_model_hash(ensemble, tmp_path):
    _, record, path, model_path = ensemble
    args = ['--ensemble', str(path), '--npz', str(model_path)]
    assert main(args+['--output-dir', str(tmp_path/'cli')]) == 0
    record['input_hashes'] = {'old/file': 'a'*64}
    path.write_text(json.dumps(record))
    assert main(args+['--output-dir', str(tmp_path/'bad')]) == 2
    assert not (tmp_path/'bad').exists()


@pytest.mark.parametrize('field,value', [('marker_metadata', None), ('warnings', 'bad'), ('warnings', [None])])
def test_cli_rejects_malformed_metadata(ensemble, tmp_path, field, value):
    _, record, path, model_path = ensemble
    record[field] = value
    path.write_text(json.dumps(record))
    assert main(['--ensemble', str(path), '--npz', str(model_path), '--output-dir', str(tmp_path/'bad')]) == 2
    assert not (tmp_path/'bad').exists()


def test_output_appearing_midrun_is_preserved(ensemble, tmp_path, monkeypatch):
    import cranio.uncertainty_export as module
    _, _, path, model_path = ensemble
    output = tmp_path/'appeared'
    original = module.export_spread_ply
    def concurrent(*args, **kwargs):
        original(*args, **kwargs)
        output.mkdir()
        (output/'keep.txt').write_text('existing work')
    monkeypatch.setattr(module, 'export_spread_ply', concurrent)
    with pytest.raises(ValueError, match='appeared'): export_bundle(path, model_path, output)
    assert (output/'keep.txt').read_text() == 'existing work'
    assert not (output/'summary.json').exists()
    assert not list(tmp_path.glob('.gnm-ensemble-*'))


def test_legacy_obj_bytes_unchanged_and_comment_newlines_safe(tmp_path):
    point, tri = np.array([[1., 2., 3.]]), np.array([[0, 0, 0]])
    path = tmp_path/'old.obj'
    export_obj(path, point, tri)
    assert path.read_text() == '# GNM Reconstructie Craniofaciala - mesh reconstruit (mm)\nv 1.000000 2.000000 3.000000\nf 1 1 1\n'
    export_obj(path, point, tri, comments=['line1\nv 999 999 999'])
    assert '\n# v 999 999 999\n' in path.read_text()

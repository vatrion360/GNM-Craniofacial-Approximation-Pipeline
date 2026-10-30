"""Synthetic engineering checks only; these SD values are not anatomical data."""
import copy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from numpy.testing import assert_allclose, assert_array_equal
from cranio.config import PipelineConfig
from cranio.depth_weighting import marker_weights, multiply_weights, precision_factors, region_factors
from cranio.fit_contract import dense_fit_weights, normalized_dense_weights
from cranio.geometry import dense_correspondences
from cranio.optimize import fit_identity
from cranio.pipeline import run_pipeline
from cranio.preview import fit_preview
from cranio.tissue import empty_table, load_table, write_table
from test_fit_contract import sphere_problem
from gnm_reconstruct import parse_args


@pytest.fixture
def sd_table(tmp_path):
    doc = empty_table('synthetic_sd')
    doc['landmarks'] = {'P0': dict(central_mm=None, sd_mm=.5), 'P1': dict(central_mm=None, sd_mm=2.),
                        'P2': dict(central_mm=None, sd_mm=None)}
    doc['regions'] = {'scalp': dict(central_mm=None, sd_mm=2.)}
    path = tmp_path/'sd.json'
    write_table(path, doc)
    return path


def test_formula_fallback_and_source_audit(sd_table):
    table = load_table(sd_table)
    base = np.array([.5, .8, .7, .6])
    effective, record, warnings = marker_weights(table, ['P0', 'P1', 'P2', 'absent'], base)
    assert_array_equal(effective, [2., .2, .7, .6])
    assert_array_equal(base, [.5, .8, .7, .6])
    assert len(warnings) == 2 and record['table']['sha256'] == table.sha256
    assert record['landmarks']['P1']['effective_weight'] == .2
    assert record['landmarks']['P2']['fallback'] == 'missing SD'
    assert record['landmarks']['absent']['fallback'] == 'missing table row'


@pytest.mark.parametrize('sd', [0., 1e-300, 1e300])
def test_unrepresentable_precision_rejected_only_when_used(sd_table, sd):
    doc = load_table(sd_table).document
    doc['landmarks']['P0']['sd_mm'] = sd
    write_table(sd_table, doc)
    table = load_table(sd_table)
    with pytest.raises(ValueError, match='SD'):
        marker_weights(table, ['P0'], [1.])
    assert marker_weights(table, ['P1'], [1.])[0][0] == .25


@pytest.mark.parametrize('base,factor', [([1e300], [1e300]), ([1e-300], [1e-300]), ([0.], [1.]), ([1.], [-1.])])
def test_bad_effective_weight_is_not_silently_dropped(base, factor):
    with pytest.raises(ValueError, match='positive'):
        multiply_weights(base, factor)


def test_larger_sd_reduces_pull_in_actual_fit(sd_table):
    mu = np.random.default_rng(42).normal(size=(20, 3))*30
    target = mu.copy()
    target[0] += [4., 3., -2.]
    weights, _, _ = marker_weights(load_table(sd_table), ['P1']+[f'A{i}' for i in range(19)], np.ones(20))
    args = (mu, np.zeros((1, 20, 3)), np.arange(20), target)
    base = fit_identity(*args, np.ones(20), lam=30)
    weighted = fit_identity(*args, weights, lam=30)
    assert np.linalg.norm(weighted.residuals_mm[1:]) < np.linalg.norm(base.residuals_mm[1:])
    assert weighted.residuals_mm[0] > base.residuals_mm[0]


def test_dense_precision_follows_sampling_and_does_not_renormalize(sd_table):
    mu, dense = sphere_problem()
    dense['regions'] = np.where(np.arange(len(mu)) % 2, 'scalp', 'unknown')
    dense['max_rows'] = 13
    factors, records, warnings = precision_factors(load_table(sd_table), 'regions', dense['regions'])
    dense.update(depth_precision_factors=factors, depth_base_marker_weights=np.array([.5, 1.]))
    ids, _, _, _ = dense_correspondences(mu, dense)
    keep, effective = dense_fit_weights(np.array([20., 30.]), dense)
    expected_keep, base = normalized_dense_weights([.5, 1.], dense['last_relative_weights'], .5)
    assert_array_equal(keep, expected_keep)
    assert_array_equal(effective, base*factors[ids])
    assert_array_equal(effective[ids % 2 == 0], base[ids % 2 == 0])
    assert len(warnings) == 1 and records['unknown']['factor'] == 1.
    dense['depth_precision_factors'] = np.full(len(mu), .25)
    dense_correspondences(mu, dense)
    assert dense_fit_weights([20., 30.], dense)[1].sum() == pytest.approx(.25*.5*1.5)


@pytest.mark.parametrize('marker_count', [2, 14])
def test_preview_consumes_same_sd_dense_contract(marker_count):
    mu, dense = sphere_problem()
    basis = np.random.default_rng(4).normal(size=(3, len(mu), 3))
    ids = np.arange(marker_count)
    original = np.linspace(.5, 1., marker_count)
    weights = original * .25
    dense.update(depth_precision_factors=np.full(len(mu), .25), depth_base_marker_weights=original)
    snapshot = dict(labels=[f'P{i}' for i in ids], verts=ids, targets=mu[ids], weights=weights)
    model = SimpleNamespace(mu=mu, basis=basis, identity_dim=3, generate=lambda c: mu+np.einsum('i,ivk->vk', c, basis))
    preview = fit_preview(model, snapshot, 30., {}, copy.deepcopy(dense))
    if marker_count >= 3:
        offline = fit_identity(mu, basis, ids, mu[ids], weights, lam=30., dense=copy.deepcopy(dense))
        audit = preview.info.diagnostics['dense']
        assert_array_equal(audit['weights'], np.array(audit['depth_base_weights'])*audit['depth_precision_factors'])
    else:
        selected, dt, _, _ = dense_correspondences(mu, dense)
        _, dw = dense_fit_weights(weights, dense)
        offline = fit_identity(mu, basis, np.r_[ids, selected], np.r_[mu[ids], dt], np.r_[weights, dw], lam=30., huber_rows=marker_count)
    assert_allclose(preview.coefficients, offline.coefficients, atol=1e-12)


@pytest.mark.parametrize('local', [False, True])
def test_missing_sd_is_exact_baseline_including_tps(tmp_path, model_file, marker_file, local):
    meshes, reports = [], []
    for mode in ('none', 'sd'):
        cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), output=str(tmp_path/mode/'face.obj'),
            regularization='30', tissue_table='legacy_hardcoded', depth_weighting=mode, skip_tps=not local)
        assert run_pipeline(cfg) == 0
        meshes.append(Path(cfg.output).read_bytes())
        reports.append(json.loads(Path(cfg.output_json).read_text()))
    assert meshes[0] == meshes[1]
    for key in ('identity_coefficients', 'transform', 'metrics', 'solver'):
        assert reports[0][key] == reports[1][key]
    assert len(reports[1]['marker_metadata']['depth_weighting']['landmarks']) == 12


def write_case_points(marker_file, perturb=False):
    from cranio.io_csv import read_marker_csv, write_marker_csv_v3
    targets, _, metadata = read_marker_csv(marker_file, {}, {})
    rows = [dict(label=t.label, vertex=t.vertex, placed=1, x=t.xyz[0]+(3 if perturb and i == 0 else 0),
        y=t.xyz[1], z=t.xyz[2], bone_x=t.xyz[0]+(3 if perturb and i == 0 else 0), bone_y=t.xyz[1], bone_z=t.xyz[2]-2,
        tissue_depth_mm=2, weight=t.weight, tissue_source='synthetic fixture') for i, t in enumerate(targets)]
    write_marker_csv_v3(marker_file, rows, metadata)


def expected_tps(model_file, marker_file, report, exclude=()):
    from cranio.backend import GNMBackend
    from cranio.io_csv import read_marker_csv
    model = GNMBackend(str(model_file)).load()
    targets, _, _ = read_marker_csv(marker_file, {}, {})
    tr = report['transform']
    world = tr['scale']*((model.mu+np.einsum('i,ivk->vk', report['identity_coefficients'], model.basis)) @ np.array(tr['rotation']).T)+tr['translation_mm']
    return [t.weight*(t.xyz-world[t.vertex]) for t in targets if t.label not in exclude]


def test_cli_sd_preserves_case_targets_and_tps_confidence(tmp_path, model_file, marker_file, sd_table):
    write_case_points(marker_file, perturb=True)
    before = marker_file.read_bytes()
    cfg = parse_args(['--input', str(marker_file), '--npz', str(model_file), '--output', str(tmp_path/'fit.obj'),
        '--tissue-table', str(sd_table), '--depth-weighting', 'sd', '--regularization', '30', '--local-correction'])
    assert run_pipeline(cfg) == 0
    report = json.loads(Path(cfg.output_json).read_text())
    meta = report['marker_metadata']
    assert_allclose(meta['local_correction_prescribed_vectors_mm'], expected_tps(model_file, marker_file, report), atol=1e-10)
    assert meta['depth_weighting']['landmarks']['P0']['effective_weight'] == 4.
    assert marker_file.read_bytes() == before and meta['tissue_application']['status'] == 'selected_only'


def test_sd_requires_explicit_reference_table(tmp_path, model_file, marker_file):
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), output=str(tmp_path/'bad.obj'), depth_weighting='sd')
    assert run_pipeline(cfg) == 2 and not Path(cfg.output).exists()
    cfg.depth_weighting = 'guessed'
    assert run_pipeline(cfg) == 2


def test_self_comparison_carries_weighting(tmp_path, model_file, marker_file, sd_table):
    write_case_points(marker_file)
    doc = load_table(sd_table).document
    doc['landmarks']['P0']['central_mm'] = 3.
    write_table(sd_table, doc)
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), output=str(tmp_path/'compare.obj'),
        tissue_compare=f'{sd_table},{sd_table}', tissue_labels=['P0'], tissue_axis='existing', depth_weighting='sd', regularization='30')
    assert run_pipeline(cfg) == 0
    folder = tmp_path/'compare_tissue_compare'
    summary = json.loads((folder/'summary.json').read_text())
    assert summary['depth_weighting'] == 'sd' and summary['color_scale_max_mm'] == 0
    for run in summary['tables']:
        report = json.loads((folder/run['report']).read_text())
        assert report['marker_metadata']['depth_weighting']['landmarks']['P0']['effective_weight'] == 4.
    doc['landmarks']['P0']['sd_mm'] = 0.
    write_table(sd_table, doc)
    cfg = replace(cfg, output=str(tmp_path/'badcompare.obj'))
    assert run_pipeline(cfg) == 2 and not (tmp_path/'badcompare_tissue_compare').exists()


def test_zero_strength_nose_needs_no_sd(sd_table):
    doc = load_table(sd_table).document
    doc['regions']['punte_nazala'] = dict(central_mm=None, sd_mm=0.)
    write_table(sd_table, doc)
    factors, records, warnings = region_factors(load_table(sd_table), ['scalp', 'punte_nazala'], 0.)
    assert_array_equal(factors, [.25, 1.])
    assert set(records) == {'scalp'} and not warnings
    with pytest.raises(ValueError, match='SD'):
        region_factors(load_table(sd_table), ['scalp', 'punte_nazala'], .7)


def test_pipeline_refit_retains_original_dense_budget_and_tps_weights(tmp_path, model_file, marker_file, sd_table, monkeypatch):
    import cranio.pipeline as pipeline
    import trimesh
    skull = tmp_path/'skull.stl'
    mesh = trimesh.creation.icosphere(subdivisions=1, radius=80)
    mesh.apply_translation([0, 350, 90])
    mesh.export(skull)
    calls = []
    original = pipeline.fit_identity
    def controlled(mu, basis, idx, targets, weights, **kwargs):
        dense = kwargs['dense']
        calls.append((idx.copy(), weights.copy(), dense['depth_base_marker_weights'].copy()))
        assert_array_equal(dense['depth_precision_factors'], np.full(len(dense['dense_idx']), .25))
        result = original(mu, basis, idx, targets, weights, **kwargs)
        if len(calls) == 1:
            residuals = result.residuals_mm.copy()
            residuals[1] = 1000.  # deterministic exclusion fixture, not a scientific threshold
            return result._replace(residuals_mm=residuals)
        return result
    monkeypatch.setattr(pipeline, 'fit_identity', controlled)
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), output=str(tmp_path/'refit.obj'),
        skull=str(skull), skull_normals_reviewed=True, dense_samples=100, no_face_dense=True, regularization='30', skip_tps=False,
        tissue_table=str(sd_table), depth_weighting='sd', exclude_outliers=True)
    assert run_pipeline(cfg) == 0 and len(calls) == 2
    assert len(calls[1][0]) == 11 and 1 not in calls[1][0]
    assert_array_equal(calls[0][2], np.ones(12))
    assert_array_equal(calls[1][2], np.ones(11))
    assert calls[1][1][0] == 4.
    report = json.loads(Path(cfg.output_json).read_text())
    meta = report['marker_metadata']
    assert 'P1' not in meta['depth_weighting']['retained_labels']
    assert_allclose(meta['local_correction_prescribed_vectors_mm'][:11], expected_tps(model_file, marker_file, report, ['P1']), atol=1e-10)


def test_protocol_freezes_sd_mode(tmp_path, model_file, marker_file, sd_table):
    from cranio.protocol import frozen_from_report
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), output=str(tmp_path/'freeze.obj'),
        tissue_table=str(sd_table), depth_weighting='sd', regularization='30', geometry_qc='full')
    assert run_pipeline(cfg) == 0
    report = json.loads(Path(cfg.output_json).read_text())
    frozen = frozen_from_report(report, 'synthetic/v1', 'a'*64)
    assert frozen['settings']['depth_weighting'] == 'sd'
    assert frozen['optional_inputs']['tissue_table'] == load_table(sd_table).sha256

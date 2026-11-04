"""Prior sensitivity is an engineering scenario, never demographic validation."""
import copy
from dataclasses import asdict, replace
import json
import os
from pathlib import Path

import numpy as np
import pytest

from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline
from cranio.prior_compare import run_comparison
from cranio.tissue_compare import export_difference_ply, read_exported_vertices
from cranio.validation import sha256_file


@pytest.fixture
def comparison(tmp_path, model_file, marker_file):
    prior = tmp_path/'synthetic_prior.npz'
    np.savez(prior, mean=np.array([.6, -.4, .2]), scale=np.ones(3), n_samples=12)
    return PipelineConfig(input=str(marker_file), npz=str(model_file), output=str(tmp_path/'case.obj'),
        prior=str(prior), prior_compare=True, prior_justification='Synthetic software scenario; no cohort claim',
        regularization='30', max_iter=100)


def read_summary(cfg):
    directory = Path(cfg.output).parent/(Path(cfg.output).stem+'_prior_compare')
    return directory, json.loads((directory/'summary.json').read_text(encoding='utf-8'))


def test_paired_fit_matches_standalone_and_preserves_inputs(comparison, tmp_path):
    before = copy.deepcopy(asdict(comparison))
    inputs = {p: Path(p).read_bytes() for p in (comparison.input, comparison.npz, comparison.prior)}
    assert run_pipeline(comparison) == 0
    assert asdict(comparison) == before
    folder, summary = read_summary(comparison)
    assert summary['justification'] == comparison.prior_justification
    assert summary['prior']['mean'] == [.6, -.4, .2]
    assert summary['prior']['n_samples'] == 12
    assert summary['differences_to_neutral']['final']['all_vertices']['max_mm'] > 0
    reports = [json.loads((folder/r['report']).read_text(encoding='utf-8')) for r in summary['scenarios']]
    assert reports[0]['config']['prior'] is None
    assert reports[0]['config']['prior_justification'] is None
    assert reports[1]['config']['prior_justification'] == comparison.prior_justification
    for i, prior in enumerate((None, comparison.prior)):
        direct = replace(comparison, prior=prior, prior_compare=False,
                         prior_justification=None, output=str(tmp_path/f'direct{i}.obj'))
        assert run_pipeline(direct) == 0
        for name in ('output', 'output_statistical'):
            assert Path(direct.__dict__[name]).read_bytes() == Path(reports[i]['outputs'][name]['path']).read_bytes()
    for key in ('final', 'statistical'):
        path = folder/summary['differences_to_neutral'][key]['ply']
        text = path.read_text(encoding='utf-8')
        assert 'identity-prior scenario difference; NOT uncertainty' in text
        assert 'property double vertex_difference_mm' in text
        assert sha256_file(path) == summary['differences_to_neutral'][key]['sha256']
    assert comparison.prior_justification in (folder/'comparison.txt').read_text(encoding='utf-8')
    assert comparison.prior_justification in (folder/'prior'/'face_statistici.txt').read_text(encoding='utf-8')
    for path, data in inputs.items(): assert Path(path).read_bytes() == data
    comparison.overwrite = True
    assert run_pipeline(comparison) == 2
    assert read_summary(comparison)[1] == summary


def test_zero_mean_unit_scale_prior_matches_neutral(comparison):
    np.savez(comparison.prior, mean=np.zeros(3), scale=np.ones(3))
    assert run_pipeline(comparison) == 0
    _, summary = read_summary(comparison)
    assert summary['prior']['n_samples'] is None
    assert summary['color_scale_max_mm'] == 0
    assert summary['differences_to_neutral']['final']['all_vertices']['max_mm'] == 0


def test_geometry_and_difference_metrics_repeat(comparison):
    assert run_pipeline(comparison) == 0
    folder, first = read_summary(comparison)
    second_cfg = replace(comparison, output=str(Path(comparison.output).with_name('repeat.obj')))
    assert run_pipeline(second_cfg) == 0
    other, second = read_summary(second_cfg)
    assert first['differences_to_neutral'] == second['differences_to_neutral']
    for scenario in ('neutral', 'prior'):
        assert (folder/scenario/'face.obj').read_bytes() == (other/scenario/'face.obj').read_bytes()


@pytest.mark.parametrize('kind', ['missing_prior', 'missing_reason', 'blank', 'placeholder', 'number',
                                 'protocol', 'profile', 'tissue_compare', 'auto_exclude', 'custom_output',
                                 'bad_scale', 'bad_dimension'])
def test_invalid_requests_prevent_creation(comparison, kind):
    if kind == 'missing_prior': comparison.prior = None
    elif kind == 'missing_reason': comparison.prior_justification = None
    elif kind == 'blank': comparison.prior_justification = '  '
    elif kind == 'placeholder': comparison.prior_justification = 'TODO(verify-source): choose rationale'
    elif kind == 'number': comparison.prior_justification = 42
    elif kind == 'protocol': comparison.protocol = 'not-used.json'
    elif kind == 'profile': comparison.profile_constraint = 'not-used.json'
    elif kind == 'tissue_compare': comparison.tissue_compare = 'a,b'
    elif kind == 'auto_exclude': comparison.exclude_outliers = True
    elif kind == 'custom_output': comparison.output_json = 'not-used.json'
    elif kind == 'bad_scale': np.savez(comparison.prior, mean=np.zeros(3), scale=[1, 0, 1])
    elif kind == 'bad_dimension': np.savez(comparison.prior, mean=np.zeros(2), scale=np.ones(2))
    assert run_pipeline(comparison) == 2
    assert not (Path(comparison.output).parent/'case_prior_compare').exists()


def test_legacy_prior_and_default_fit_remain_opt_in(comparison, tmp_path):
    cfg = replace(comparison, prior_compare=False, prior_justification=None, output=str(tmp_path/'legacy.obj'))
    assert run_pipeline(cfg) == 0
    assert not (tmp_path/'legacy_prior_compare').exists()
    assert PipelineConfig().prior is None and PipelineConfig().prior_compare is False
    cfg = replace(comparison, prior=None, prior_compare=False, output=str(tmp_path/'invalid.obj'))
    assert run_pipeline(cfg) == 2  # A rationale alone must not silently activate a prior.


def test_cli_audit_flags_and_unicode_reason(comparison):
    from gnm_reconstruct import main, parse_args
    args = ['--input', comparison.input, '--npz', comparison.npz, '--output', comparison.output,
            '--prior', comparison.prior, '--prior-compare', '--prior-justification', 'Scenariu verificabil șță',
            '--regularization', '30']
    assert parse_args(args).prior_compare
    assert main(args) == 0
    assert read_summary(comparison)[1]['justification'] == 'Scenariu verificabil șță'


def test_justification_is_case_metadata_not_a_frozen_numeric_setting(comparison):
    from cranio.protocol import scientific_settings
    first = scientific_settings(comparison)
    comparison.prior_justification = 'Another documented case rationale'
    assert scientific_settings(comparison) == first
    comparison.prior_weight = 2
    assert scientific_settings(comparison) != first


def test_required_qc_exit_preserved_without_summary(comparison, monkeypatch):
    import cranio.pipeline
    original, calls = cranio.pipeline.run_pipeline, []
    def fail(cfg):
        calls.append(cfg)
        return 3 if len(calls) == 2 else original(cfg)
    monkeypatch.setattr(cranio.pipeline, 'run_pipeline', fail)
    assert run_comparison(comparison) == 3
    assert not (Path(comparison.output).parent/'case_prior_compare'/'summary.json').exists()


@pytest.mark.parametrize('change', ['input', 'mesh'])
def test_changed_input_or_child_artifact_has_no_summary(comparison, monkeypatch, change):
    import cranio.pipeline
    original = cranio.pipeline.run_pipeline
    def altered(cfg):
        code = original(cfg)
        target = Path(cfg.input if change == 'input' else cfg.output)
        target.write_bytes(target.read_bytes()+b'\n')
        return code
    monkeypatch.setattr(cranio.pipeline, 'run_pipeline', altered)
    with pytest.raises(ValueError, match='changed'):
        run_comparison(comparison)
    assert not (Path(comparison.output).parent/'case_prior_compare'/'summary.json').exists()


def test_nonconvergence_is_not_labelled_stable(comparison):
    comparison.max_iter = 1
    assert run_pipeline(comparison) == 0
    _, summary = read_summary(comparison)
    assert summary['comparison_status'] == 'diagnostic_only_nonconverged'
    assert any('did not converge' in warning for warning in summary['warnings'])


def test_local_correction_keeps_separate_statistical_differences(comparison):
    comparison.skip_tps = False
    assert run_pipeline(comparison) == 0
    folder, summary = read_summary(comparison)
    assert set(summary['differences_to_neutral']) == {'final', 'statistical'}
    for row in summary['scenarios']:
        report = json.loads((folder/row['report']).read_text(encoding='utf-8'))
        assert report['local_correction']['enabled']
    assert summary['differences_to_neutral']['statistical']['all_vertices']['max_mm'] > 0


def test_tissue_ply_default_caption_bytes_unchanged(tmp_path):
    path = tmp_path/'difference.ply'
    export_difference_ply(path, np.zeros((1, 3)), [[0, 0, 0]], [0.], 0.)
    assert path.read_text().splitlines()[3] == 'comment tissue scenario difference; NOT uncertainty or face accuracy'


@pytest.mark.integration
def test_official_head_only_prior_comparison(tmp_path):
    path = os.environ.get('GNM_MODEL_PATH')
    if not path or not Path(path).is_file(): pytest.skip('Set GNM_MODEL_PATH')
    prior = tmp_path/'synthetic.npz'
    # Intentional synthetic changes also outside head; inactive components must stay zero.
    mean = np.full(253, .1)
    np.savez(prior, mean=mean, scale=np.ones(253))
    cfg = PipelineConfig(input=str(Path(__file__).resolve().parents[1]/'examples'/'synthetic_markers.csv'),
        npz=path, output=str(tmp_path/'head.obj'), prior=str(prior), prior_compare=True,
        prior_justification='Synthetic named-component integration', identity_subspace='head', regularization='30')
    assert run_pipeline(cfg) == 0
    folder, summary = read_summary(cfg)
    assert summary['prior']['active_components'] == list(range(170))
    assert summary['differences_to_neutral']['final']['skin_exterior']['count'] > 0
    for row in summary['scenarios']:
        report = json.loads((folder/row['report']).read_text(encoding='utf-8'))
        assert not any(report['identity_coefficients'][170:])
        assert len(read_exported_vertices(folder/row['id']/'face.obj', 17821)) == 17821

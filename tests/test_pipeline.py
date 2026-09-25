import json
import socket
import numpy as np
import pytest
from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline, _nasal_diagnostic_report
from cranio.validation import sha256_file


def test_complete_offline_run(tmp_path, model_file, marker_file, monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('Reconstruction must not access the network')
    monkeypatch.setattr(socket, 'create_connection', blocked)
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file),
                         output=str(tmp_path / 'output' / 'face.obj'), regularization='30', strict=True)
    assert run_pipeline(cfg) == 0
    report = json.loads(open(cfg.output_json).read())
    assert report['status'] == 'completed'
    assert report['metrics']['final_fit']['rmse_mm'] < .001
    assert report['outputs']['output']['sha256'] == sha256_file(cfg.output)
    assert report['inputs']['model']['sha256'] == sha256_file(model_file)
    assert report['local_correction']['enabled'] is False
    assert report['lambda_selection']['independent_validation'] is False
    assert len(report['identity_coefficients']) == 3
    assert run_pipeline(cfg) == 2  # Never silently replace a case.


def test_local_correction_pipeline(tmp_path, model_file, marker_file):
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file),
                         output=str(tmp_path / 'corrected.obj'), regularization='30', skip_tps=False)
    assert run_pipeline(cfg) == 0
    report = json.loads(open(cfg.output_json).read())
    assert report['local_correction']['enabled']
    assert report['metrics']['local_displacement']['max_mm'] <= cfg.max_correction_mm


@pytest.mark.parametrize('setting,value', [('face_cap_mm', 0), ('dense_weight', -1), ('protect_damping', 2),
                                          ('regularization', 'nan'), ('seed', -2), ('dense_samples', 0)])
def test_config_failures_are_actionable(tmp_path, model_file, marker_file, setting, value):
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), output=str(tmp_path / 'face.obj'))
    setattr(cfg, setting, value)
    assert run_pipeline(cfg) == 2
    assert not (tmp_path / 'face.obj').exists()


def test_output_input_collision(tmp_path, model_file, marker_file):
    original = marker_file.read_bytes()
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), output=str(marker_file), overwrite=True)
    assert run_pipeline(cfg) == 2
    assert marker_file.read_bytes() == original


def test_model_mismatch_fails_before_export(tmp_path, model_file, marker_file):
    text = marker_file.read_text().replace(sha256_file(model_file), '0' * 64)
    marker_file.write_text(text)
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), output=str(tmp_path / 'bad.obj'))
    assert run_pipeline(cfg) == 2
    assert not (tmp_path / 'bad.obj').exists()


def test_nasal_diagnostic_does_not_fabricate_bone_points():
    assert _nasal_diagnostic_report({}, None, None) == (None, None)


def test_conditional_lambda_search_is_reported(tmp_path, model_file, marker_file):
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), output=str(tmp_path / 'auto.obj'))
    assert run_pipeline(cfg) == 0
    report = json.loads(open(cfg.output_json).read())
    assert report['lambda_selection']['method'] == 'conditional fixed-pose landmark LOO'
    assert len(report['lambda_selection']['scores_model_space_mm']) == 8

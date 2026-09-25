"""Opt-in integration test against the actual, separately obtained GNM asset."""
import json
import os
from pathlib import Path
import pytest
from cranio.backend import GNMBackend
from cranio.backend.gnm_backend import OFFICIAL_V3_SHA256
from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline
from cranio.validation import sha256_file


@pytest.mark.integration
def test_official_asset_end_to_end(tmp_path):
    model_path = os.environ.get('GNM_MODEL_PATH')
    if not model_path or not Path(model_path).is_file():
        pytest.skip('Set GNM_MODEL_PATH to the reviewed official v3 asset')
    assert sha256_file(model_path) == OFFICIAL_V3_SHA256
    model = GNMBackend(model_path).load()
    assert model.vertex_count == 17821 and model.identity_dim == 253
    markers = Path(__file__).resolve().parents[1] / 'examples' / 'synthetic_markers.csv'
    cfg = PipelineConfig(input=str(markers), npz=model_path, output=str(tmp_path / 'face.obj'),
                         regularization='30', strict=True, skip_tps=False)
    assert run_pipeline(cfg) == 0
    report = json.loads(Path(cfg.output_json).read_text())
    assert report['metrics']['final_fit']['rmse_mm'] < .001
    assert len(report['landmarks']) == 27

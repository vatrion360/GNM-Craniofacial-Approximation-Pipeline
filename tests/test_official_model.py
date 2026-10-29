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
    from cranio.identity import active_components
    assert model.identity_names[170:173] == ['eyes_000', 'eyes_001', 'eyes_002']
    assert active_components(model, 'head').tolist() == list(range(170))
    markers = Path(__file__).resolve().parents[1] / 'examples' / 'synthetic_markers.csv'
    cfg = PipelineConfig(input=str(markers), npz=model_path, output=str(tmp_path / 'face.obj'),
                         regularization='30', strict=True, skip_tps=False)
    assert run_pipeline(cfg) == 0
    report = json.loads(Path(cfg.output_json).read_text())
    assert report['metrics']['final_fit']['rmse_mm'] < .001
    assert len(report['landmarks']) == 48
    mapping = GNMBackend(model_path).landmark_vertex_map
    assert len(set(mapping.values())) == 48
    assert not model.group_mask('lower_lip')[mapping['Pogonion']]
    assert model.group_mask('lower_lip')[mapping['Infradentale_BuzaInf']]
    for label, index in mapping.items():
        assert model.group_mask('skin_exterior')[index]
    from cranio.landmarks import bilateral_pairs
    import numpy as np
    assert len(bilateral_pairs()) == 17
    for right, left in bilateral_pairs():
        assert model.mirror_indices[mapping[right]] == mapping[left]
        # Pinned asset: max bilateral landmark deviation is 0.2341 mm.
        assert np.linalg.norm(model.mu[mapping[right]]*[-1, 1, 1]-model.mu[mapping[left]]) < .25


@pytest.mark.integration
def test_official_head_pipeline_preview_and_replay(tmp_path):
    import numpy as np
    from cranio.io_csv import write_marker_csv_v3
    from cranio.preview import fit_preview
    model_path = os.environ.get('GNM_MODEL_PATH')
    if not model_path or not Path(model_path).is_file():
        pytest.skip('Set GNM_MODEL_PATH to the reviewed official v3 asset')
    assert sha256_file(model_path) == OFFICIAL_V3_SHA256
    backend = GNMBackend(model_path)
    model = backend.load()
    ids = np.array(list(backend.landmark_vertex_map.values()))
    labels = list(backend.landmark_vertex_map)
    # Perturbation exercises the engineering path, not reconstruction accuracy.
    targets = model.mu[ids].astype(float)+np.random.default_rng(1901).normal(size=(48, 3))
    path = tmp_path/'synthetic.csv'
    write_marker_csv_v3(path, [dict(label=label, vertex=int(vid), placed=1,
        x=float(p[0]), y=float(p[1]), z=float(p[2]), weight=1, tissue_source='synthetic test')
        for label, vid, p in zip(labels, ids, targets)], {'model_sha256': OFFICIAL_V3_SHA256})
    cfg = PipelineConfig(input=str(path), npz=model_path, output=str(tmp_path/'head.obj'),
                         regularization='3', identity_subspace='head')
    assert run_pipeline(cfg) == 0
    report = json.loads(Path(cfg.output_json).read_text())
    coefficients = np.asarray(report['identity_coefficients'])
    assert coefficients.shape == (253,) and np.count_nonzero(coefficients[170:]) == 0
    assert report['config']['identity_subspace'] == 'head'
    info = report['solver']['identity_fit']
    assert info['active_components'] == 170 and info['inactive_policy'] == 'zero'
    live = fit_preview(model, dict(labels=labels, verts=ids, targets=targets, weights=np.ones(48)),
                       3., {'identity_subspace': 'head'})
    np.testing.assert_allclose(coefficients, live.coefficients, atol=1e-12)
    transform = report['transform']
    replay = transform['scale']*(model.generate(coefficients) @ np.array(transform['rotation']).T)+transform['translation_mm']
    exported = np.array([[float(x) for x in line.split()[1:]] for line in Path(cfg.output).read_text().splitlines() if line.startswith('v ')])
    np.testing.assert_allclose(exported, replay, atol=5.1e-7, rtol=0)

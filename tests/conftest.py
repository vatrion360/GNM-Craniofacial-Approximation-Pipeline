from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pytest


@pytest.fixture
def model_file(tmp_path):
    rng = np.random.default_rng(4)
    points = rng.normal(size=(12, 3)) * .04 + [0, .35, .09]
    groups = ['skin', 'ears', 'hockey_mask', 'forehead_region', 'left_temple_region', 'right_temple_region']
    weights = np.zeros((len(groups), len(points)), dtype=np.float32)
    weights[0] = 1
    path = tmp_path / 'model.npz'
    np.savez(path, template_vertex_positions=points.astype(np.float32),
             vertex_identity_basis=rng.normal(size=(3, 12, 3)).astype(np.float32) * .002,
             triangles=np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int32),
             mirror_indices=np.arange(12, dtype=np.int32),
             vertex_groups=weights, vertex_group_names=np.asarray(groups))
    return path


@pytest.fixture
def marker_file(tmp_path, model_file):
    from cranio.backend import GNMBackend
    from cranio.io_csv import write_marker_csv_v3
    from cranio.validation import sha256_file
    model = GNMBackend(str(model_file)).load()
    rows = [dict(label=f'P{i}', vertex=i, placed=1, x=float(x), y=float(y), z=float(z),
                 weight=1, tissue_source='synthetic software fixture')
            for i, (x, y, z) in enumerate(model.mu)]
    path = tmp_path / 'markers.csv'
    write_marker_csv_v3(path, rows, {'model_sha256': sha256_file(model_file), 'synthetic': True})
    return path

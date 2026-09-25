import numpy as np
from cranio.backend import GNMBackend
from cranio.evaluation import landmark_holdout
from cranio.export import _heat_color


def test_holdout_does_not_leak_excluded_target(model_file):
    model = GNMBackend(str(model_file)).load()
    targets = model.mu.astype(float)
    original = landmark_holdout(model, np.arange(12), targets, np.ones(12))
    targets[0] += [20, 10, 15]
    perturbed = landmark_holdout(model, np.arange(12), targets, np.ones(12))
    np.testing.assert_allclose(original['predictions_mm'][0], perturbed['predictions_mm'][0], atol=1e-10)
    assert perturbed['errors_mm'][0] > 20


def test_heatmap_maximum_is_red():
    assert _heat_color(1) == (255, 0, 0)
    assert _heat_color(0) == (0, 0, 255)


def test_skull_sampling_is_reproducible(tmp_path):
    import trimesh
    from cranio.geometry import load_skull_samples
    path = tmp_path / 'sphere.stl'
    trimesh.creation.icosphere(radius=80).export(path)
    _, first, normals = load_skull_samples(path, 100, seed=8)
    _, second, _ = load_skull_samples(path, 100, seed=8)
    np.testing.assert_array_equal(first, second)
    np.testing.assert_allclose(np.linalg.norm(normals, axis=1), 1)

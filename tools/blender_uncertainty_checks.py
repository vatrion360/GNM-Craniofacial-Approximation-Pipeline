"""Exercise the packaged NumPy engine in actual Blender; no anatomy claims."""
import numpy as np


def run_uncertainty_checks(addon):
    engine = addon._core_module('uncertainty')
    backend = addon._core_module('backend')
    marker = addon._core_module('io_csv').MarkerTarget
    rng = np.random.default_rng(7)
    mu = rng.normal(size=(8, 3))*30
    model = backend.FaceModelData(mu, rng.normal(size=(2, 8, 3)),
        np.array([[0, 1, 2]]), np.arange(8), np.ones((1, 8)), ['synthetic'])
    targets = [marker(str(i), i, p, 1.) for i, p in enumerate(mu)]
    placement = dict(schema_version=1, placement={str(i): dict(sigma_mm=.1, source='synthetic') for i in range(8)})
    result = engine.monte_carlo_identity(model, targets, {'version': 3}, placement=placement, samples=2)
    assert result == engine.monte_carlo_identity(model, targets, {'version': 3}, placement=placement, samples=2)
    assert result['calibration_status'] == 'uncalibrated'
    assert len(result['variants']['off']['samples']) == 2
    print('BLENDER_UNCERTAINTY_NUMPY_PASS')

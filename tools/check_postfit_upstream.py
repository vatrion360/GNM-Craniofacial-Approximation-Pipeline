"""Optional parity check: PYTHONPATH=/path/to/google/GNM python tools/check_postfit_upstream.py MODEL.npz.

Uses upstream gnm_common and its optional dependencies only for verification;
the addon itself has no runtime dependency on upstream Python packages.
"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cranio.postfit import load_asset, evaluate
from gnm.shape import gnm_common

asset = load_asset(sys.argv[1])
rng = np.random.default_rng(1900)
beta = rng.normal(size=253)*.05
expr = rng.normal(size=383)*.01
angles = np.zeros((4, 3)); angles[2:] = rng.normal(size=(2, 3))*.03
native = asset.mu + np.einsum('i,ivk->vk', beta, asset.identity)
residual = rng.normal(size=native.shape)*.02
base = native + residual
joints = asset.joints + np.einsum('i,ijk->jk', beta, asset.joint_basis) + asset.joint_regressor @ residual
expected = gnm_common.linear_blend_skinning(base + np.einsum('i,ivk->vk', expr, asset.expression),
    joints, angles, np.zeros(3), asset.weights, asset.parents)
actual, stats = evaluate(asset, base, np.eye(4), beta, expr, np.zeros(253), angles, 20.)
assert stats['attenuation'] == 1.
np.testing.assert_allclose(actual, expected, atol=1e-9, rtol=1e-10)
print('POSTFIT_UPSTREAM_LBS_PARITY_PASS max_mm=', float(abs(actual-expected).max()))

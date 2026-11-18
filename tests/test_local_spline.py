"""Independent NumPy spline parity against the existing SciPy backend."""
import builtins
import os
from pathlib import Path

import numpy as np
import pytest
from scipy.interpolate import RBFInterpolator

from cranio.tps import LinearPolyharmonic3D
from cranio.optimize import bounded_tps_correction


def sample(seed=12, n=48, m=139):
    rng = np.random.default_rng(seed)
    centers = rng.normal(size=(n, 3))*70
    values = rng.normal(size=(n, 3))*4
    queries = rng.normal(size=(m, 3))*100
    return centers, values, queries


def scipy_field(c, d, q):
    origin = c.mean(axis=0)
    return RBFInterpolator(c-origin, d, kernel='linear', degree=1, smoothing=0.)(q-origin)


@pytest.mark.parametrize('n', [4, 12, 48, 128])
@pytest.mark.parametrize('seed', [3, 19, 42])
def test_random_interpolation_and_extrapolation_parity(n, seed):
    c, d, q = sample(seed, n)
    before = tuple(x.copy() for x in (c, d, q))
    fit = LinearPolyharmonic3D(c, d)
    np.testing.assert_allclose(fit(q), scipy_field(c, d, q), rtol=0, atol=1e-6)
    np.testing.assert_allclose(fit(c), d, rtol=0, atol=1e-8)
    for a, b in zip(before, (c, d, q)): np.testing.assert_array_equal(a, b)
    info = fit.diagnostics
    assert info['numerical_rank'] == n+4 and info['condition_number'] >= 1
    assert info['relative_backward_error'] <= info['backward_error_limit']


def test_affine_reproduction_and_zero_field():
    c, _, q = sample()
    a = np.array([[.1, .02, 0], [0, -.03, .01], [0, 0, .05]])
    offset = np.array([2., -1, 3])
    fit = LinearPolyharmonic3D(c, c@a+offset)
    np.testing.assert_allclose(fit(q), q@a+offset, atol=1e-10, rtol=0)
    zero = LinearPolyharmonic3D(c, np.zeros_like(c))
    np.testing.assert_array_equal(zero(q), np.zeros_like(q))


@pytest.mark.parametrize('scale', [.001, 1., 1000.])
def test_rigid_transform_and_uniform_scale_equivariance(scale):
    c, d, q = sample()
    rotation, _ = np.linalg.qr(np.random.default_rng(4).normal(size=(3, 3)))
    translation = np.array([1e6, -1e6, 1e6])
    transformed = LinearPolyharmonic3D(scale*c@rotation+translation, d@rotation)
    np.testing.assert_allclose(transformed(scale*q@rotation+translation),
                               LinearPolyharmonic3D(c, d)(q)@rotation, rtol=0, atol=1e-6)


def test_chunking_empty_queries_and_detached_state():
    c, d, q = sample()
    fit = LinearPolyharmonic3D(c, d)
    expected = fit(q)
    for chunk in (1, 7, 2048):
        np.testing.assert_allclose(fit(q, chunk_size=chunk), expected, atol=1e-10, rtol=0)
    assert fit(np.empty((0, 3))).shape == (0, 3)
    c[:] = d[:] = 999
    np.testing.assert_array_equal(fit(q), expected)
    info = fit.diagnostics
    info['coordinate_origin_mm'][0] = 999
    assert fit.diagnostics != info


@pytest.mark.parametrize('kind', ['duplicate', 'coplanar', 'collinear', 'nearly_coplanar',
                                 'nan', 'inf', 'few', 'shape', 'values_nan', 'values_shape'])
def test_invalid_centres_and_values_rejected(kind):
    c, d, _ = sample(n=12)
    if kind == 'duplicate': c[-1] = c[0]
    elif kind == 'coplanar': c[:, 2] = 0
    elif kind == 'collinear': c[:, 1:] = 0
    elif kind == 'nearly_coplanar': c[:, 2] *= 1e-9
    elif kind == 'nan': c[0, 0] = np.nan
    elif kind == 'inf': c[0, 0] = np.inf
    elif kind == 'few': c, d = c[:3], d[:3]
    elif kind == 'shape': c = c[:, :2]
    elif kind == 'values_nan': d[0, 0] = np.nan
    else: d = d[:, :2]
    with pytest.raises(ValueError): LinearPolyharmonic3D(c, d)


def test_unresolvable_near_duplicates_refused_without_smoothing():
    c, d, _ = sample(n=12)
    c[-1] = c[0]+[1e-12, 0, 0]
    with pytest.raises(ValueError, match='rank deficient'): LinearPolyharmonic3D(c, d)


def test_solver_failure_does_not_fall_back_to_lstsq(monkeypatch):
    c, d, _ = sample()
    def fail(*args, **kwargs): raise np.linalg.LinAlgError('synthetic failure')
    monkeypatch.setattr(np.linalg, 'solve', fail)
    with pytest.raises(ValueError, match='no fallback'): LinearPolyharmonic3D(c, d)


@pytest.mark.parametrize('query', [np.zeros(3), np.zeros((2, 2)), [[0, 0, np.nan]], [[0, 0, np.inf]]])
def test_bad_evaluation_points(query):
    c, d, _ = sample()
    with pytest.raises(ValueError): LinearPolyharmonic3D(c, d)(query)


@pytest.mark.parametrize('chunk', [0, -1, True, 1.5])
def test_bad_chunk_sizes(chunk):
    c, d, q = sample()
    with pytest.raises(ValueError): LinearPolyharmonic3D(c, d)(q, chunk_size=chunk)


@pytest.mark.parametrize('damping', [0., .25, 1.])
def test_shared_caps_and_damping_parity(damping):
    c, d, q = sample()
    d *= 30
    caps = np.linspace(1, 15, len(q))  # synthetic caps, not new defaults
    protected = np.arange(0, len(q), 3)
    before = [x.copy() for x in (c, d, q, caps, protected)]
    a = bounded_tps_correction(q, c, d, caps, protected, damping)
    b = bounded_tps_correction(q, c, d, caps, protected, damping, backend='numpy')
    for va, vb in zip(a, b): np.testing.assert_allclose(va, vb, rtol=0, atol=1e-6)
    assert np.all(np.linalg.norm(b[1], axis=1) <= caps+1e-12)
    assert np.all(np.linalg.norm(b[1][protected], axis=1) <= damping*caps[protected]+1e-12)
    for old, new in zip(before, (c, d, q, caps, protected)): np.testing.assert_array_equal(old, new)


def test_default_scipy_arithmetic_is_exactly_unchanged():
    c, d, q = sample(m=2055)
    caps = np.linspace(1, 15, len(q))
    protected = np.arange(5)
    origin = c.mean(axis=0)
    interpolator = RBFInterpolator(c-origin, d, kernel='linear', degree=1, smoothing=0.)
    expected = np.vstack([interpolator(q[i:i+2048]-origin) for i in range(0, len(q), 2048)])
    magnitudes = np.linalg.norm(expected, axis=1)
    expected *= (caps*np.tanh(magnitudes/caps)/np.maximum(magnitudes, 1e-12))[:, None]
    expected[protected] *= .25
    actual = bounded_tps_correction(q, c, d, caps, protected, .25)
    np.testing.assert_array_equal(actual[0], q+expected)
    np.testing.assert_array_equal(actual[1], expected)
    np.testing.assert_array_equal(actual[2], np.linalg.norm(d, axis=1))


@pytest.mark.parametrize('indices', [[-1], [999], [1, 1], [1.], [True], [[1]], 1])
@pytest.mark.parametrize('backend', ['numpy', 'scipy'])
def test_invalid_protected_indices_rejected(indices, backend):
    c, d, q = sample()
    with pytest.raises(ValueError): bounded_tps_correction(q, c, d, np.ones(len(q)), indices, backend=backend)


def test_numpy_path_does_not_import_optional_runtime_modules(monkeypatch):
    c, d, q = sample()
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split('.')[0] in ('scipy', 'trimesh', 'tensorflow', 'bpy'):
            raise AssertionError('Unexpected numerical dependency: '+name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    result = bounded_tps_correction(q, c, d, np.ones(len(q)), backend='numpy')
    assert np.isfinite(result[0]).all()


@pytest.mark.parametrize('backend', ['scipy', 'numpy'])
@pytest.mark.parametrize('invalid', ['empty_mesh', 'mesh_shape', 'zero_cap', 'nan_cap', 'damping'])
def test_shared_input_contracts_for_both_backends(backend, invalid):
    c, d, q = sample()
    caps = np.ones(len(q))
    damping = .25
    if invalid == 'empty_mesh': q, caps = np.empty((0, 3)), np.empty(0)
    elif invalid == 'mesh_shape': q = q[:, :2]
    elif invalid == 'zero_cap': caps[0] = 0
    elif invalid == 'nan_cap': caps[0] = np.nan
    else: damping = np.nan
    with pytest.raises(ValueError): bounded_tps_correction(q, c, d, caps, protect_damping=damping, backend=backend)


def test_no_implicit_backend_fallback():
    c, d, q = sample()
    with pytest.raises(ValueError, match='backend'): bounded_tps_correction(q, c, d, np.ones(len(q)), backend='auto')


@pytest.mark.integration
def test_official_mesh_700_centres_numpy_scipy_parity():
    from cranio.backend import GNMBackend
    path = os.environ.get('GNM_MODEL_PATH')
    if not path or not Path(path).is_file(): pytest.skip('Set GNM_MODEL_PATH for official-mesh parity')
    model = GNMBackend(path).load()
    rng = np.random.default_rng(3101)
    vertices = model.mu.astype(float)
    # Distinct physical locations, rather than different IDs at a seam.
    _, unique = np.unique(vertices, axis=0, return_index=True)
    ids = rng.choice(unique, 700, replace=False)
    centers = vertices[ids]
    values = rng.normal(size=(700, 3))*3  # synthetic prescribed displacements
    caps = np.full(len(vertices), 8.)
    protected = np.flatnonzero(model.group_mask('eyes'))
    a = bounded_tps_correction(vertices, centers, values, caps, protected, .25)
    b = bounded_tps_correction(vertices, centers, values, caps, protected, .25, backend='numpy')
    for va, vb in zip(a, b): np.testing.assert_allclose(va, vb, atol=1e-6, rtol=0)

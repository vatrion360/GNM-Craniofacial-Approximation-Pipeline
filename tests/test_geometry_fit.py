import numpy as np
import pytest
from numpy.testing import assert_allclose
from cranio.optimize import weighted_umeyama, fit_identity, bounded_tps_correction, _symmetry_rows
from cranio.validation import rmse


def test_rmse_is_not_mean_distance():
    assert rmse([3, 4]) == pytest.approx(np.sqrt(12.5))
    assert rmse([3, 4]) != 3.5


@pytest.mark.parametrize('planar', [False, True])
def test_similarity_recovers_known_pose_including_planar_case(planar):
    rng = np.random.default_rng(5)
    src = rng.normal(size=(10, 3))
    if planar:
        src[:, 2] = 0
    angle = .8
    rotation = np.array([[np.cos(angle), 0, np.sin(angle)], [0, 1, 0],
                         [-np.sin(angle), 0, np.cos(angle)]])
    dst = 1.3 * (src @ rotation.T) + [50, -20, 80]
    scale, r, t = weighted_umeyama(src, dst, np.arange(1, 11))
    assert_allclose(scale * (src @ r.T) + t, dst, atol=1e-10)
    assert np.linalg.det(r) == pytest.approx(1)
    assert scale == pytest.approx(1.3)


def test_reflection_never_produces_improper_rotation():
    src = np.random.default_rng(1).normal(size=(20, 3))
    dst = src * [-1, 1, 1]
    scale, r, t = weighted_umeyama(src, dst, np.ones(20))
    assert np.linalg.det(r) == pytest.approx(1)
    assert rmse(np.linalg.norm(scale * (src @ r.T) + t - dst, axis=1)) > .2


@pytest.mark.parametrize('bad', [np.zeros((4, 3)), np.arange(12).reshape(4, 3), np.full((4, 3), np.nan)])
def test_degenerate_alignment_fails(bad):
    with pytest.raises(ValueError):
        weighted_umeyama(bad, bad, np.ones(4))


@pytest.mark.parametrize('weight', [0, -1, np.nan, np.inf])
def test_invalid_weight_fails(weight):
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]])
    with pytest.raises(ValueError):
        weighted_umeyama(pts, pts, [1, 1, 1, weight])


def test_symmetric_basis_has_no_symmetry_penalty():
    basis = np.array([[[-1, 2, 3], [1, 2, 3]]], dtype=float)
    assert _symmetry_rows(basis, [1, 0]) is None
    basis[0, 1, 1] += 2
    assert _symmetry_rows(basis, [1, 0]) is not None


def test_fit_reproduces_mean_under_rigid_transform():
    rng = np.random.default_rng(42)
    mu = rng.normal(size=(18, 3)) * 20
    basis = rng.normal(size=(3, 18, 3))
    targets = 1.2 * mu + [8, 5, 15]
    c, scale, rot, trans, _, _, residuals = fit_identity(mu, basis, np.arange(18), targets, np.ones(18), lam=30)
    assert_allclose(c, 0, atol=1e-10)
    assert_allclose(residuals, 0, atol=1e-10)
    assert scale == pytest.approx(1.2)


def test_local_correction_caps_and_protected_regions():
    centers = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10]], dtype=float)
    vertices = np.vstack([centers, [3, 3, 3]])
    caps = np.array([1, 2, 3, 4, 5], dtype=float)
    result, field, _ = bounded_tps_correction(vertices, centers, np.full((4, 3), 50.), caps,
                                             protected_idx=[0], protect_damping=.25)
    assert np.all(np.linalg.norm(field, axis=1) <= caps + 1e-10)
    assert np.linalg.norm(field[0]) <= .25
    assert_allclose(result, vertices + field)


@pytest.mark.parametrize('kind', ['coplanar', 'duplicate', 'zero_cap', 'nan', 'damping'])
def test_local_correction_rejects_bad_inputs(kind):
    centers = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float)
    if kind == 'coplanar': centers[:, 2] = 0
    if kind == 'duplicate': centers = np.vstack([centers, centers[0]])
    if kind == 'nan': centers[0, 0] = np.nan
    with pytest.raises(ValueError):
        bounded_tps_correction(centers, centers, np.ones_like(centers),
                               np.zeros(len(centers)) if kind == 'zero_cap' else np.ones(len(centers)),
                               protect_damping=2 if kind == 'damping' else .25)

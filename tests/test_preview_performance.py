"""Regression coverage for exact LOO reuse; wall-clock times are not CI gates."""
import numpy as np
import pytest
from numpy.testing import assert_allclose
from cranio.optimize import loo_select_lambda


@pytest.mark.parametrize('count,dimensions,rank_deficient', [(4, 9, False), (12, 4, False),
    (48, 253, False), (8, 20, True)])
def test_loo_path_matches_independent_augmented_solves(count, dimensions, rank_deficient):
    rng = np.random.default_rng(4818)
    basis = rng.normal(size=(dimensions, count, 3))
    # Exercise poorly scaled components and an exactly deficient design.
    basis *= np.geomspace(1e-5, 1e3, dimensions)[:, None, None]
    if rank_deficient:
        basis[1:] = basis[:1]
    mean, target = rng.normal(size=(2, count, 3))*50
    weights = np.geomspace(.01, 1., count)
    grid = [.3, 1., 3., 10., 30., 100., 300., 1000.]
    expected = []
    for lam in grid:
        errors = []
        for j in range(count):
            keep = np.arange(count) != j
            sw = np.sqrt(np.repeat(weights[keep], 3))
            a = basis[:, keep, :].reshape(dimensions, -1).T*sw[:, None]
            b = (target[keep]-mean[keep]).ravel()*sw
            augmented = np.vstack((a, np.sqrt(lam)*np.eye(dimensions)))
            c = np.linalg.lstsq(augmented, np.r_[b, np.zeros(dimensions)], rcond=None)[0]
            errors.append(np.linalg.norm(mean[j]+c @ basis[:, j, :]-target[j]))
        expected.append((float(np.mean(errors)), lam))
    expected.sort()
    chosen, actual = loo_select_lambda(basis, mean, target, weights, grid, dimensions)
    assert chosen == expected[0][1]
    assert_allclose(sorted(actual, key=lambda row: row[1]),
                    sorted(expected, key=lambda row: row[1]), rtol=1e-8, atol=1e-8)


def test_loo_factorizes_once_per_landmark(monkeypatch):
    rng = np.random.default_rng(18)
    basis, mean = rng.normal(size=(6, 8, 3)), rng.normal(size=(8, 3))
    original, calls = np.linalg.svd, []
    def svd(a, **kwargs):
        calls.append(a.shape)
        return original(a, **kwargs)
    monkeypatch.setattr(np.linalg, 'svd', svd)
    loo_select_lambda(basis, mean, mean+1, np.ones(8), [.3, 1., 3., 30.], 6)
    assert calls == [(21, 6)]*8

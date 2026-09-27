"""Numerical regressions and actual preview/offline parity."""
import copy
from types import SimpleNamespace
import numpy as np
from numpy.testing import assert_allclose
import pytest
from scipy.spatial import cKDTree
import trimesh
from cranio.fit_contract import normalized_dense_weights, balanced_indices
from cranio.geometry import dense_correspondences, model_winding_flip, PointQueryAdapter
from cranio.optimize import fit_identity, weighted_umeyama, huber_downweight
from cranio.preview import fit_preview


def sphere_problem(inward=False):
    mesh = trimesh.creation.icosphere(subdivisions=1, radius=80)
    points, triangles = np.asarray(mesh.vertices), np.asarray(mesh.faces)
    dense = dict(points=points, normals=points/80*(-1 if inward else 1), tree=cKDTree(points), triangles=triangles,
        dense_idx=np.arange(len(points)), max_dists=np.full(len(points), 30.), offsets=np.full(len(points), 5.),
        min_dot=.5, flip=model_winding_flip(points, triangles), regions=np.full(len(points), 'scalp'), weight_ratio=.5)
    return points, dense


def test_normal_orientation_is_explicit():
    points, dense = sphere_problem()
    ids, targets, _, _ = dense_correspondences(points*1.1, dense)
    assert len(ids) == len(points)
    assert_allclose(np.linalg.norm(targets, axis=1), 85.)
    points, dense = sphere_problem(True)
    normals = dense['normals'].copy()
    assert len(dense_correspondences(points*1.1, dense)[0]) == 0
    dense['use_normal'], dense['max_dists'] = False, np.full(len(points), .01)
    dense_correspondences(points*1.1, dense)
    assert_allclose(normals, dense['normals'])


def test_zero_nose_weight_and_sampling_independent_mass():
    points, dense = sphere_problem()
    dense['regions'] = np.where(np.arange(len(points))%2, 'scalp', 'punte_nazala')
    dense['nose_weight'] = 0
    ids, _, _, _ = dense_correspondences(points, dense)
    assert np.all(ids%2 == 1)
    for count in (15, 1500, 3000):
        keep, weights = normalized_dense_weights(np.ones(48), np.ones(count), .5)
        assert keep.all() and weights.sum() == pytest.approx(24.)
    keep, weights = normalized_dense_weights([1, 1], [0, 1, 2], .5)
    assert keep.tolist() == [False, True, True]
    assert_allclose(weights, [1/3, 2/3])


def test_budget_reallocation_has_no_duplicates():
    regions = np.array(['scalp']*100 + ['face']*2)
    ids = balanced_indices(regions, 30)
    assert len(ids) == len(set(ids)) == 30
    assert np.sum(regions[ids] == 'face') == 2


@pytest.mark.parametrize('lam', [3., 'auto'])
def test_preview_and_offline_match_nontrivial_dense_fit(lam):
    points, dense = sphere_problem()
    rng = np.random.default_rng(23)
    mu, basis = points*1.07, rng.normal(size=(4, len(points), 3))*2
    model = SimpleNamespace(mu=mu, basis=basis, identity_dim=4)
    ids = np.arange(0, len(mu), 3)
    target = (mu+np.einsum('i,ivk->vk', [.6, -.3, .2, .1], basis))[ids]+[2, -3, 1]
    snapshot = dict(labels=['P'+str(i) for i in ids], verts=ids, targets=target, weights=np.linspace(.5, 1., len(ids)))
    live_dense = copy.deepcopy(dense)
    def find(point):
        distance, index = dense['tree'].query(point)
        return points[index], index, distance
    live_dense['tree'] = PointQueryAdapter(find)
    live = fit_preview(model, snapshot, lam, {}, live_dense)
    offline = fit_identity(mu, basis, ids, target, snapshot['weights'], lam=lam, dense=dense)
    for a, b in zip(live[:5], offline[:5]):
        assert_allclose(a, b, atol=1e-10)
    assert np.linalg.norm(live.coefficients) > .1
    assert live.info.diagnostics['dense']['weights'] == offline.info.diagnostics['dense']['weights']


def test_replicated_dense_rows_do_not_change_objective():
    mu, dense = sphere_problem()
    rng = np.random.default_rng(8)
    basis, ids = rng.normal(size=(3, len(mu), 3)), np.arange(0, len(mu), 2)
    targets = mu[ids]+rng.normal(size=(len(ids), 3))
    first = fit_identity(mu, basis, ids, targets, np.ones(len(ids)), lam=3, dense=copy.deepcopy(dense))
    for key in ('dense_idx', 'max_dists', 'offsets', 'regions'):
        dense[key] = np.repeat(dense[key], 3)
    second = fit_identity(mu, basis, ids, targets, np.ones(len(ids)), lam=3, dense=dense)
    assert_allclose(first.coefficients, second.coefficients, atol=1e-10)


def test_single_huber_layer_does_not_stop_on_unchanged_coefficients():
    mu = np.random.default_rng(93).normal(size=(25, 3))*40
    target = mu.copy()
    target[0] += [80, -50, 100]
    result = fit_identity(mu, np.zeros((1, len(mu), 3)), np.arange(len(mu)), target, np.ones(len(mu)), lam=1, max_iter=100)
    assert result.info.diagnostics['converged'] and result.info.diagnostics['iterations'] > 2
    vectors = result.scale*(mu @ result.rotation.T)+result.translation-target
    expected = huber_downweight(np.linalg.norm(vectors, axis=1), np.ones(len(mu)), 10)
    assert_allclose(result.info.diagnostics['final_irls_weights'], expected)
    assert np.linalg.norm(np.sum(expected[:, None]*vectors, axis=0)) < 1e-4
    short = fit_identity(mu, np.zeros((1, len(mu), 3)), np.arange(len(mu)), target, np.ones(len(mu)), lam=1, max_iter=1)
    assert not short.info.diagnostics['converged']


def test_weighted_rank_accepts_planarity_but_rejects_effective_collinearity():
    points = np.array([[0., 0, 0], [10, 0, 0], [20, 0, 0], [0, 10, 0]])
    with pytest.raises(ValueError, match='geometry'):
        weighted_umeyama(points, points, [1, 1, 1, 1e-20])
    scale, rotation, translation = weighted_umeyama(points, points, np.ones(4))
    assert_allclose(scale*(points @ rotation.T)+translation, points, atol=1e-12)

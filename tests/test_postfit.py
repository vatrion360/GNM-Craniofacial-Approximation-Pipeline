"""Presentation geometry invariants, distinct from anatomical validation."""
import os
import numpy as np
import pytest
from cranio.postfit import PresentationAsset, evaluate, check_topology, load_asset, similarity_matrix


@pytest.fixture
def asset():
    mu = np.array([[0., 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]])
    identity = np.zeros((3, 4, 3))
    identity[1, 3, 0] = 2
    identity[2, :, 1] = 1  # Deliberate teeth leakage; skin must remain frozen.
    expression = np.ones((2, 4, 3))
    groups = np.array([[1, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 0], [0, 0, 0, 1]])
    weights = np.zeros((4, 4)); weights[1, :3] = 1; weights[2, 3] = 1
    regressor = np.zeros((4, 4)); regressor[:, 0] = 1
    return PresentationAsset(mu, identity, expression, ['head_000', 'eyes_000', 'teeth_000'],
        ['left_eye_region_000', 'lower_face_region_000'], np.array([[0, 1, 2], [1, 3, 2]]),
        np.zeros((2, 3, 2)), groups, ['skin', 'teeth', 'gums', 'eyes'],
        np.zeros((4, 3)), np.zeros((3, 4, 3)), regressor, weights,
        np.array([-1, 0, 1, 1]), ['neck', 'head', 'left_eye', 'right_eye'])


def call(asset, base=None, **kwargs):
    options = dict(model_to_world=np.eye(4), fitted_identity=np.zeros(3),
        expression=np.zeros(2), identity_delta=np.zeros(3), eye_angles=np.zeros((4, 3)))
    options.update(kwargs)
    return evaluate(asset, asset.mu if base is None else base, **options)


def test_zero_is_exact_frozen_final_even_with_local_correction(asset):
    base = asset.mu + np.random.default_rng(19).normal(size=(4, 3))
    result, _ = call(asset, base)
    np.testing.assert_array_equal(result, base)


def test_additive_expression_preserves_residual_and_never_accumulates(asset):
    base = asset.mu + 7.123
    expected = base + .2*asset.expression[1]
    for _ in range(3):
        result, _ = call(asset, base, expression=[0, .2])
        np.testing.assert_allclose(result, expected)


def test_combined_world_mm_bound(asset):
    matrix = np.eye(4); matrix[:3, :3] *= 2.; matrix[:3, 3] = [4, 5, 6]
    base = asset.mu*2 + matrix[:3, 3]
    result, stats = call(asset, base, model_to_world=matrix, expression=[3, 3], max_displacement_mm=.5)
    assert np.max(np.linalg.norm(result-base, axis=1)) <= .5+1e-12
    assert stats['attenuation'] < 1.


def test_teeth_offset_does_not_change_skin_or_eye(asset):
    result, _ = call(asset, identity_delta=[0, 0, 1])
    np.testing.assert_array_equal(result[[0, 1, 3]], asset.mu[[0, 1, 3]])
    np.testing.assert_allclose(result[2], asset.mu[2]+[0, 1, 0])


def test_eye_rotation_about_fitted_pivot_and_zero_cap(asset):
    angles = np.zeros((4, 3)); angles[2, 2] = .1
    result, _ = call(asset, eye_angles=angles)
    np.testing.assert_allclose(result[3], [np.cos(.1)-np.sin(.1), np.sin(.1)+np.cos(.1), 0])
    np.testing.assert_array_equal(result[:3], asset.mu[:3])
    result, _ = call(asset, eye_angles=angles, max_displacement_mm=0)
    np.testing.assert_array_equal(result, asset.mu)


@pytest.mark.parametrize('options', [dict(expression=[np.nan, 0]), dict(expression=[4, 0]),
    dict(identity_delta=[1, 0, 0]), dict(eye_angles=np.ones((4, 3))*.1),
    dict(max_displacement_mm=-1), dict(max_displacement_mm=np.inf), dict(fitted_identity=[0])])
def test_invalid_or_locked_controls_rejected(asset, options):
    with pytest.raises(ValueError):
        call(asset, **options)


def test_uv_topology_order_not_just_counts(asset):
    with pytest.raises(ValueError, match='Topology'):
        check_topology(asset.mu, asset.triangles[::-1], asset)


@pytest.mark.parametrize('linear', [np.diag([-1, 1, 1]), np.diag([1, 2, 1]), np.zeros((3, 3))])
def test_non_similarity_transform_rejected(linear):
    matrix = np.eye(4); matrix[:3, :3] = linear
    with pytest.raises(ValueError):
        similarity_matrix(matrix)


def test_official_postfit_asset_and_neutral():
    path = os.environ.get('GNM_MODEL_PATH')
    if not path:
        pytest.skip('Set GNM_MODEL_PATH to exercise the reviewed presentation asset')
    asset = load_asset(path)
    assert asset.expression.shape == (383, 17821, 3)
    assert asset.uvs.shape == (35324, 3, 2)
    assert sum(n.startswith('teeth_') for n in asset.identity_names) == 80
    assert sum(n.startswith('eyes_') for n in asset.identity_names) == 3
    rng = np.random.default_rng(19)
    base = asset.mu + rng.normal(size=asset.mu.shape)*.1
    result, _ = evaluate(asset, base, np.eye(4), np.zeros(253), np.zeros(383), np.zeros(253), np.zeros((4, 3)))
    np.testing.assert_array_equal(result, base)

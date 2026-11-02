"""Synthetic numerical checks, not measurements of human uncertainty."""
import copy
import json

import numpy as np
import pytest

from cranio.backend import GNMBackend
from cranio.linear_uncertainty import (linear_gaussian, fixed_pose_design, propagate_covariance,
                                       covariance_crosscheck, main)
from cranio.optimize import _ridge_solve
from cranio.validation import sha256_file


def test_scalar_hand_calculation():
    result = linear_gaussian([[2]], [4], [[9]], [1], [[4]])
    np.testing.assert_allclose(result.mean, [41/25])
    np.testing.assert_allclose(result.posterior_covariance, [[36/25]])
    np.testing.assert_allclose(result.estimator_covariance, [[576/625]])


def test_unobserved_direction_keeps_prior_variance():
    result = linear_gaussian([[1, 0]], [2], [[1]], [0, 3], np.diag([4, 9]))
    np.testing.assert_allclose(result.mean, [1.6, 3])
    np.testing.assert_allclose(result.posterior_covariance, np.diag([.8, 9]))
    np.testing.assert_allclose(result.estimator_covariance, np.diag([.64, 0]))


def test_correlated_covariance_and_prior_direct_small_algebra():
    a = np.array([[1, 2], [3, -1], [2, 0.]])
    c = np.array([[2, .2, 0], [.2, 1, .1], [0, .1, 3]])
    p = np.array([[4, .3], [.3, 2]])
    y, m = np.array([2, 1, 4]), np.array([.2, -.3])
    expected = np.linalg.inv(a.T @ np.linalg.solve(c, a)+np.linalg.inv(p))
    gain = expected @ a.T @ np.linalg.inv(c)
    result = linear_gaussian(a, y, c, m, p)
    np.testing.assert_allclose(result.mean, expected @ (a.T @ np.linalg.solve(c, y)+np.linalg.solve(p, m)))
    np.testing.assert_allclose(result.posterior_covariance, expected)
    np.testing.assert_allclose(result.estimator_covariance, gain @ c @ gain.T)


def test_fixed_unclipped_ridge_matches_shared_solver():
    rng = np.random.default_rng(5)
    a, y = rng.normal(size=(12, 3)), rng.normal(size=12)
    weights, lam, tau = np.linspace(.2, 2, 12), 7., .3
    expected = _ridge_solve(a, y, weights, lam, 3)
    result = linear_gaussian(a, y, np.diag(tau**2/weights), np.zeros(3), tau**2/lam*np.eye(3))
    np.testing.assert_allclose(result.mean, expected, atol=1e-14)


def test_mc_independent_lstsq_matches_both_covariances_and_vertex_sd():
    a = [[1, 2, 0], [0, 1, 1], [2, 0, -.5], [1, -1, 1]]
    result = linear_gaussian(a, [1, 2, 3, 4], 2*np.eye(4), [0, .5, 0], np.diag([2, 3, 4]))
    before = np.random.get_state()
    mc = covariance_crosscheck(result, 50000, 17)
    assert mc == covariance_crosscheck(result, 50000, 17)
    after = np.random.get_state()
    np.testing.assert_array_equal(before[1], after[1])
    assert before[2:] == after[2:]
    j = np.random.default_rng(33).normal(size=(20, 3, 3))
    for name, expected in [('posterior', result.posterior_covariance), ('estimator', result.estimator_covariance)]:
        assert mc[name]['relative_covariance_error'] < .03  # synthetic MC tolerance, not clinical threshold
        assert mc[name]['mean_error_norm'] < .03
        exact = propagate_covariance(j, expected)['sd_xyz_mm']
        empirical = propagate_covariance(j, mc[name]['covariance'])['sd_xyz_mm']
        assert np.linalg.norm(exact-empirical)/np.linalg.norm(exact) < .03


def test_zero_design_and_singular_estimator_covariance():
    r = linear_gaussian(np.zeros((2, 2)), [0, 0], np.eye(2), [1, 2], np.diag([4, 9]))
    np.testing.assert_allclose(r.posterior_covariance, np.diag([4, 9]))
    assert not r.estimator_covariance.any()
    assert not propagate_covariance(np.ones((4, 3, 2)), r.estimator_covariance)['sd_xyz_mm'].any()


def test_world_pose_and_active_order(model_file):
    model = GNMBackend(model_file).load()
    r = np.array([[0., -1, 0], [1, 0, 0], [0, 0, 1]])
    s, t = 2., np.array([10, 20, -4])
    active, beta, ids = [2, 0], np.array([.3, -.2]), [3, 2, 0]
    coefficients = np.zeros(3)
    coefficients[active] = beta
    targets = s*(model.generate(coefficients)[ids] @ r.T)+t
    a, y, j = fixed_pose_design(model, ids, targets, scale=s, rotation=r, translation_mm=t, active=active)
    np.testing.assert_allclose(a @ beta, y, atol=1e-13)
    np.testing.assert_allclose(j, s*np.einsum('ab,ivb->vai', r, model.basis[active]))
    c = np.array([[2., .1], [.1, 3]])
    result = propagate_covariance(j, c)
    expected = np.array([np.diag(x @ c @ x.T) for x in j])
    np.testing.assert_allclose(result['sd_xyz_mm']**2, expected)
    np.testing.assert_allclose(result['spread_rms_mm']**2, expected.sum(axis=1))


@pytest.mark.parametrize('bad', [np.zeros((2, 2)), [[1, 2], [2, 1]], [[1, .1], [0, 1]],
                               [[1, 0], [0, np.nan]], [[1, 0], [0, np.inf]], [[1]]])
def test_invalid_covariance_refused(bad):
    with pytest.raises(ValueError):
        linear_gaussian(np.eye(2), [0, 0], bad, [0, 0], np.eye(2))
    with pytest.raises(ValueError):
        linear_gaussian(np.eye(2), [0, 0], np.eye(2), [0, 0], bad)


def test_rank_loss_and_nonfinite_design():
    with pytest.raises(ValueError, match='rank deficient'):
        linear_gaussian([[1e20, 0]], [0], [[1]], [0, 0], np.eye(2))
    with pytest.raises(ValueError):
        linear_gaussian([[np.nan]], [0], [[1]], [0], [[1]])
    with pytest.raises(ValueError):
        propagate_covariance(np.ones((2, 3, 2)), np.diag([1, -1]))


@pytest.mark.parametrize('draws,seed', [(1, 0), (True, 0), (2.2, 0), (3, -1), (3, True), (3, .5)])
def test_bad_mc_settings(draws, seed):
    r = linear_gaussian([[1]], [0], [[1]], [0], [[1]])
    with pytest.raises(ValueError):
        covariance_crosscheck(r, draws, seed)


@pytest.fixture
def cli_case(model_file, marker_file, tmp_path):
    model = GNMBackend(model_file).load()
    document = dict(schema_version=1, model_sha256=sha256_file(model_file), units='mm', coordinate_space='world',
        source='synthetic engineering assumption, not measured tissue', labels=[f'P{i}' for i in range(12)],
        pose=dict(scale=1., rotation=np.eye(3).tolist(), translation_mm=[0, 0, 0]),
        observation_covariance=dict(sd_mm=[.2]*36), prior_mean=[0]*model.identity_dim,
        prior_covariance=dict(sd=[1]*model.identity_dim))
    config = tmp_path/'assumptions.json'
    config.write_text(json.dumps(document))
    return document, config, ['--input', str(marker_file), '--npz', str(model_file),
                              '--assumptions', str(config), '--draws', '100', '--seed', '17']


def test_cli_deterministic_fresh_output_and_preserved_inputs(cli_case, tmp_path):
    document, config, args = cli_case
    output, other = tmp_path/'a.json', tmp_path/'b.json'
    assert main(args+['--output', str(output)]) == 0
    assert main(args+['--output', str(other)]) == 0
    assert output.read_bytes() == other.read_bytes()
    report = json.loads(output.read_text())
    assert report['assumptions'] == document
    assert report['calibration_status'] == 'uncalibrated'
    assert len(report['statistics']['posterior']['sd_xyz_mm']) == 12
    assert main(args+['--output', str(output)]) == 2
    assert main(args+['--output', str(config)]) == 2
    assert json.loads(config.read_text()) == document


@pytest.mark.parametrize('bad', ['labels', 'hash', 'zero', 'missing', 'reflection', 'source', 'unknown',
                                'unit', 'version', 'pose', 'correlated', 'prior_dimension'])
def test_bad_assumptions_block_output(cli_case, tmp_path, bad):
    document, config, args = cli_case
    doc = copy.deepcopy(document)
    if bad == 'labels': doc['labels'].reverse()
    if bad == 'hash': doc['model_sha256'] = '0'*64
    if bad == 'zero': doc['observation_covariance']['sd_mm'][0] = 0
    if bad == 'missing': del doc['observation_covariance']
    if bad == 'reflection': doc['pose']['rotation'][0][0] = -1
    if bad == 'source': doc['source'] = ' unspecified '
    if bad == 'unknown': doc['guessed_noise'] = 1
    if bad == 'unit': doc['units'] = 'm'
    if bad == 'version': doc['schema_version'] = True
    if bad == 'pose': doc['pose']['scale'] = 0
    if bad == 'correlated': doc['observation_covariance'] = dict(matrix_mm2=np.zeros((36, 36)).tolist())
    if bad == 'prior_dimension': doc['prior_mean'] = [0]
    config.write_text(json.dumps(doc))
    output = tmp_path/'bad.json'
    assert main(args+['--output', str(output)]) == 2
    assert not output.exists()


def test_input_change_during_run_refused(cli_case, tmp_path, monkeypatch):
    import cranio.linear_uncertainty as module
    _, config, args = cli_case
    original = module.covariance_crosscheck
    def change(*a, **kw):
        result = original(*a, **kw)
        config.write_text(config.read_text()+'\n')
        return result
    monkeypatch.setattr(module, 'covariance_crosscheck', change)
    output = tmp_path/'changed.json'
    assert main(args+['--output', str(output)]) == 2
    assert not output.exists()

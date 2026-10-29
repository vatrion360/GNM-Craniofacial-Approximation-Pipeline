"""Engineering invariants for restricted identity; no anatomical accuracy claims."""
from types import SimpleNamespace

import numpy as np
import pytest
from numpy.testing import assert_allclose

from cranio.backend import GNMBackend
from cranio.identity import active_components
from cranio.optimize import fit_identity, LossConfig, stability_warnings
from cranio.preview import fit_preview
from gnm_reconstruct import parse_args


def names():
    return ([f'head_{i:03d}' for i in range(170)] + [f'eyes_{i:03d}' for i in range(3)] +
            [f'teeth_{i:03d}' for i in range(80)])


def problem():
    rng = np.random.default_rng(19)
    mu = rng.normal(size=(20, 3))*30
    basis = rng.normal(size=(3, 20, 3))*2
    target = mu + np.einsum('i,ivk->vk', [.4, -.2, 1.5], basis)
    return mu, basis, np.arange(20), target, np.ones(20)


def test_component_selection_uses_names_not_offsets():
    model = SimpleNamespace(identity_dim=253, identity_names=names())
    assert active_components(model) is None
    assert active_components(model, 'head').tolist() == list(range(170))
    model.identity_names = model.identity_names[::-1]
    assert active_components(model, 'head').tolist() == list(range(83, 253))
    for invalid in (None, names()[:-1], ['unknown']*253):
        model.identity_names = invalid
        with pytest.raises(ValueError, match='identity_names'):
            active_components(model, 'head')
    with pytest.raises(ValueError, match='all or head'):
        active_components(model, 'teeth')


@pytest.mark.parametrize('indices', [[], [-1], [3], [0, 0], [0.5], [True], [[0, 1]]])
def test_bad_subspace_is_rejected(indices):
    with pytest.raises(ValueError, match='active_components'):
        fit_identity(*problem(), lam=3, active_components=indices)


@pytest.mark.parametrize('lam', [3., 'auto'])
@pytest.mark.parametrize('with_prior', [False, True])
def test_inactive_coefficients_are_exactly_zero_even_with_nonzero_prior(lam, with_prior):
    args = problem()
    options = dict(prior_mean=np.array([.1, -.1, 9.]), prior_scale=np.ones(3)) if with_prior else {}
    restricted = fit_identity(*args, lam=lam, active_components=[0, 1], **options)
    unrestricted = fit_identity(*args, lam=lam, **options)
    assert restricted.coefficients.shape == (3,)
    assert restricted.coefficients[2] == 0
    assert abs(unrestricted.coefficients[2]) > .5
    info = restricted.info.diagnostics['identity_fit']
    assert info['active_indices'] == [0, 1] and info['active_components'] == 2
    assert info['total_components'] == 3 and info['inactive_policy'] == 'zero'


def test_all_default_remains_exact_and_clip_counts_only_active_components():
    before = fit_identity(*problem(), lam=3)
    explicit = fit_identity(*problem(), lam=3, active_components=None)
    for a, b in zip(before[:5], explicit[:5]):
        np.testing.assert_array_equal(a, b)
    clipped = fit_identity(*problem(), lam=.01, loss_cfg=LossConfig(clip_sigma=.05), active_components=[0, 1])
    assert clipped.info.diagnostics['identity_fit']['clipped_active_count'] == 2
    assert '2 identity coefficients' in ' '.join(stability_warnings(3, None, [.05, -.05, 9], .05, [0, 1]))


def test_named_head_preview_matches_offline_with_prior_and_measurements():
    mu, small_basis, ids, target, weights = problem()
    basis = np.zeros((253, len(mu), 3))
    basis[:2] = small_basis[:2]
    basis[170] = small_basis[2]
    model = SimpleNamespace(mu=mu, basis=basis, identity_dim=253, identity_names=names())
    prior = dict(mean=np.full(253, .2), scale=np.ones(253))
    controls = [dict(vertices=[0, 1], target_mm=float(np.linalg.norm(target[0]-target[1]))+2,
                     sigma_mm=2., influence=1.)]
    snapshot = dict(labels=[str(i) for i in ids], verts=ids, targets=target, weights=weights,
                    measurement_controls=controls, measurement_weight=.5)
    live = fit_preview(model, snapshot, 3., {'identity_subspace': 'head'}, prior=prior)
    offline = fit_identity(mu, basis, ids, target, weights, lam=3., active_components=range(170),
                           prior_mean=prior['mean'], prior_scale=prior['scale'],
                           measurement_controls=controls, measurement_weight=.5)
    for a, b in zip(live[:5], offline[:5]):
        assert_allclose(a, b, atol=1e-12)
    assert np.count_nonzero(live.coefficients[170:]) == 0


def test_markerless_preview_discards_inactive_warm_start(monkeypatch):
    import cranio.preview
    mu, basis, _, _, _ = problem()
    full = np.zeros((253, len(mu), 3))
    full[:2], full[170] = basis[:2], basis[2]
    model = SimpleNamespace(mu=mu, basis=full, identity_dim=253, identity_names=names(),
                            generate=lambda c: mu+np.einsum('i,ivk->vk', c, full))
    seen = []
    def correspondences(world, dense):
        seen.append(world.copy())
        dense['last_relative_weights'] = np.ones(len(mu))
        return np.arange(len(mu)), mu.copy(), np.ones(len(mu), bool), 0.
    monkeypatch.setattr(cranio.preview, 'dense_correspondences', correspondences)
    initial = np.zeros(253)
    initial[170:] = 2.
    snapshot = dict(labels=[], verts=np.array([], int), targets=np.empty((0, 3)),
                    weights=np.empty(0), initial_coefficients=initial)
    result = fit_preview(model, snapshot, 3., {'identity_subspace': 'head'}, dense={'weight_ratio': .5})
    np.testing.assert_array_equal(seen[0], mu)
    assert np.count_nonzero(result.coefficients[170:]) == 0


def test_unnamed_models_remain_readable_but_cannot_claim_head_subspace(model_file):
    model = GNMBackend(model_file).load()
    assert model.identity_names is None and active_components(model) is None
    with pytest.raises(ValueError, match='identity_names'):
        active_components(model, 'head')


@pytest.mark.parametrize('invalid', [np.array([1, 2, 3]), np.array(['a', 'a', 'b']), np.array(['a'])])
def test_backend_rejects_inconsistent_identity_metadata(model_file, invalid):
    with np.load(model_file, allow_pickle=False) as z:
        arrays = dict(z)
    arrays['identity_names'] = invalid
    np.savez(model_file, **arrays)
    with pytest.raises(ValueError, match='identity_names'):
        GNMBackend(model_file).load()


def test_cli_defaults_to_all_and_accepts_head():
    assert parse_args(['--input', 'case.csv']).identity_subspace == 'all'
    assert parse_args(['--input', 'case.csv', '--identity-subspace', 'head']).identity_subspace == 'head'


def test_holdout_refits_the_selected_subspace_without_target_leakage():
    from cranio.evaluation import landmark_holdout
    mu, small, ids, targets, weights = problem()
    full = np.zeros((253, len(mu), 3))
    full[:2], full[170] = small[:2], small[2]
    model = SimpleNamespace(mu=mu, basis=full, identity_dim=253, identity_names=names(),
                            generate=lambda c: mu+np.einsum('i,ivk->vk', c, full))
    first = landmark_holdout(model, ids, targets, weights, identity_subspace='head')
    changed = targets.copy()
    changed[0] += 100
    second = landmark_holdout(model, ids, changed, weights, identity_subspace='head')
    assert first['identity_subspace'] == 'head'
    assert_allclose(first['predictions_mm'][0], second['predictions_mm'][0], atol=1e-12)

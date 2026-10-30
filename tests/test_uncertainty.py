"""Synthetic engineering checks; fixture SDs are not human tissue measurements."""
import copy
import json
import numpy as np
import pytest
from cranio.backend import GNMBackend
from cranio.io_csv import MarkerTarget, read_marker_csv
from cranio.optimize import fit_identity
from cranio.tissue import empty_table, load_table, write_table
from cranio.uncertainty import _truncated_depths, main, monte_carlo_identity, placement_config


@pytest.fixture
def case(model_file, tmp_path):
    model = GNMBackend(model_file).load()
    targets = [MarkerTarget(f'P{i}', i, p.copy(), 1.) for i, p in enumerate(model.mu)]
    placement = dict(schema_version=1, placement={t.label: dict(sigma_mm=.2, source='synthetic') for t in targets})
    metadata = dict(version=3, marker_records={t.label: dict(bone_xyz_mm=(t.xyz-[0, 0, 2]).tolist()) for t in targets})
    document = empty_table('synthetic')
    document['landmarks'] = {t.label: dict(central_mm=2., sd_mm=.5, estimator='mean',
                                          measurement_direction='bone_normal') for t in targets}
    path = tmp_path/'table.json'
    write_table(path, document)
    return model, targets, metadata, placement, load_table(path)


def run(case, **kwargs):
    return monte_carlo_identity(*case[:3], **dict(dict(placement=case[3], samples=3), **kwargs))


def test_seed_replay_inputs_and_direct_solver_parity(case):
    model, targets, metadata, placement, _ = case
    before = copy.deepcopy((targets, metadata, placement))
    a, b = run(case, seed=17), run(case, seed=17)
    assert json.dumps(a, allow_nan=False) == json.dumps(b, allow_nan=False)
    assert a['target_draws_mm'] != run(case, seed=18)['target_draws_mm']
    assert a['calibration_status'] == 'uncalibrated'
    for old, new in zip(before[0], targets):
        np.testing.assert_array_equal(old.xyz, new.xyz)
    assert before[1:] == (metadata, placement)
    for points, record in zip(a['target_draws_mm'], a['variants']['off']['samples']):
        fit = fit_identity(model.mu, model.basis, np.arange(len(targets)), points, np.ones(len(targets)), lam=30.)
        np.testing.assert_array_equal(record['coefficients'], fit.coefficients)
        np.testing.assert_array_equal(record['rotation'], fit.rotation)
        assert record['regularization'] == fit.regularization
    fixed = copy.deepcopy(placement)
    for row in fixed['placement'].values():
        row['sigma_mm'] = 0.
    result = run(case, placement=fixed)
    for item in result['variants']['off']['samples']:
        vertices = item['scale']*(model.generate(item['coefficients']) @ np.array(item['rotation']).T)+item['translation_mm']
        np.testing.assert_allclose(vertices, model.mu, atol=1e-10)
    assert any('not evidence of certainty' in w for w in result['warnings'])


def test_truncation_is_not_clipping_and_has_half_normal_moments():
    rng = np.random.Generator(np.random.PCG64(19))
    x = _truncated_depths(rng, np.array([0., 3.]), np.array([2., 0.]), 50000)
    assert np.all(x[:, 0] > 0)
    assert np.all(x[:, 1] == 3)
    assert abs(x[:, 0].mean()-2*np.sqrt(2/np.pi)) < .025
    assert abs(x[:, 0].var()-4*(1-2/np.pi)) < .04


def test_depth_and_placement_geometry(case):
    result = run(case, table=case[4], depth_labels=['P1', 'P0'], axis_policy='existing')
    targets = np.asarray(result['target_draws_mm'])
    expected = np.asarray(result['central_targets_mm'])[None]+result['placement_draws_mm']
    depths = np.asarray(result['depth_draws_mm'])
    expected[:, 1, 2] += depths[:, 0]-2
    expected[:, 0, 2] += depths[:, 1]-2
    np.testing.assert_array_equal(targets, expected)
    assert np.all(depths >= 0)
    assert result['depth_parameters'][0]['parent_sd_mm'] == .5


def test_reviewed_source_axis_is_used_and_bound_to_table(case, tmp_path):
    from cranio.tissue_directions import load_directions
    bone = case[2]['marker_records']['P0']['bone_xyz_mm']
    path = tmp_path/'directions.json'
    doc = dict(schema_version=1, units='mm', coordinate_space='world', table_sha256s=[case[4].sha256],
        landmarks={'P0': dict(bone_xyz_mm=bone, axis_world=[1., 0., 0.], measurement_direction='bone_normal',
                              reviewed=True, definition='synthetic reviewed axis')})
    path.write_text(json.dumps(doc))
    result = run(case, table=case[4], depth_labels=['P0'], axis_policy='source', directions=load_directions(path))
    points = np.array(result['target_draws_mm'])[:, 0]-np.array(result['placement_draws_mm'])[:, 0]
    expected = np.tile(bone, (3, 1))
    expected[:, 0] += np.array(result['depth_draws_mm'])[:, 0]
    np.testing.assert_allclose(points, expected, atol=1e-13)
    assert result['tissue_application']['source_direction_enforced']
    doc['table_sha256s'] = ['a'*64]
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='table hash'):
        run(case, table=case[4], depth_labels=['P0'], axis_policy='source', directions=load_directions(path))


def test_auto_lambda_is_refitted_in_every_sample(case):
    result = run(case, regularization='auto')
    for points, record in zip(result['target_draws_mm'], result['variants']['off']['samples']):
        direct = fit_identity(case[0].mu, case[0].basis, np.arange(len(case[1])), points,
                              np.ones(len(case[1])), lam='auto')
        assert record['regularization'] == direct.regularization
        np.testing.assert_array_equal(record['coefficients'], direct.coefficients)


def test_no_seed_changes_global_numpy_random_state(case):
    state = np.random.get_state()
    run(case)
    after = np.random.get_state()
    assert state[0] == after[0] and state[2:] == after[2:]
    np.testing.assert_array_equal(state[1], after[1])


def test_missing_errors_fail_closed_and_partial_is_explicit(case):
    with pytest.raises(ValueError, match='Uncalibrated/missing'):
        run(case, placement=None)
    with pytest.raises(ValueError, match='No error SD'):
        run(case, placement=None, allow_partial=True)
    result = run(case, placement=None, table=case[4], depth_labels=['P0'], axis_policy='existing', allow_partial=True)
    assert result['analysis_status'] == 'partial_conditional_sensitivity'
    assert result['placement']['P0']['sigma_mm'] is None
    assert 'placement:P0' in result['omitted_error_inputs']
    assert not np.asarray(result['placement_draws_mm']).any()
    assert any('Conditional sensitivity only' in w for w in result['warnings'])


def test_missing_depth_sd_stays_null(case, tmp_path):
    data = case[4].document
    data['landmarks']['P0']['sd_mm'] = None
    write_table(tmp_path/'missing.json', data)
    table = load_table(tmp_path/'missing.json')
    with pytest.raises(ValueError, match='depth:P0'):
        run(case, table=table, depth_labels=['P0'], axis_policy='existing')
    result = run(case, table=table, depth_labels=['P0'], axis_policy='existing', allow_partial=True)
    assert result['depth_parameters'][0]['parent_sd_mm'] is None
    assert np.all(np.array(result['depth_draws_mm']) == 2)


@pytest.mark.parametrize('estimator', ['median', 'shorth', '75-shormax', None])
def test_no_gaussian_mean_invented_from_other_estimators(case, tmp_path, estimator):
    data = case[4].document
    data['landmarks']['P0']['estimator'] = estimator
    write_table(tmp_path/'estimator.json', data)
    with pytest.raises(ValueError, match='requires a supplied mean'):
        run(case, table=load_table(tmp_path/'estimator.json'), depth_labels=['P0'], axis_policy='existing')


def test_prior_scenarios_paired_not_pooled(case):
    dim = case[0].identity_dim
    prior = dict(mean=np.zeros(dim), scale=np.ones(dim))
    a = run(case, prior=prior, prior_variants=['off', 'on'])
    b = run(case, prior=prior, prior_variants=['on', 'off'])
    assert a['variants']['off'] == a['variants']['on']
    assert a['variants'] == b['variants']
    assert a['target_draws_mm'] == b['target_draws_mm']
    prior['mean'][0] = 1
    c = run(case, prior=prior, prior_variants=['off', 'on'])
    assert c['variants']['off'] == a['variants']['off']
    assert c['variants']['off']['baseline']['coefficients'] != c['variants']['on']['baseline']['coefficients']


@pytest.mark.parametrize('kwargs', [dict(samples=1), dict(samples=True), dict(seed=-1), dict(seed=None),
    dict(allow_partial='yes'), dict(prior_variants=[]), dict(prior_variants=['off', 'off']),
    dict(prior_variants=['on']), dict(prior={'mean': []}), dict(depth_labels=['P0']),
    dict(regularization=float('nan')), dict(identity_subspace='head'), dict(max_iter=True), dict(max_iter=0)])
def test_invalid_options(case, kwargs):
    with pytest.raises(ValueError):
        run(case, **kwargs)


@pytest.mark.parametrize('sigma,source', [(float('nan'), 'x'), (float('inf'), 'x'), (-1, 'x'),
                                       (True, 'x'), ('1', 'x'), (1, None), (1, 'unspecified')])
def test_invalid_placement(sigma, source):
    with pytest.raises(ValueError):
        placement_config(dict(schema_version=1, placement={'P': dict(sigma_mm=sigma, source=source)}), ['P'])


def test_config_typo_and_unknown_marker_rejected():
    for document in [dict(schema_version=1, placement={}, typo=1),
                     dict(schema_version=1, placement={'absent': {}}),
                     dict(schema_version=True, placement={}),
                     dict(schema_version=1, placement={'P': dict(sigma_mm=1, source='x', typo=1)})]:
        with pytest.raises(ValueError):
            placement_config(document, ['P'])


def test_failed_draw_aborts_and_nonconvergence_retained(case, monkeypatch):
    import cranio.uncertainty as module
    count = 0
    def failure(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 3:
            raise ValueError('synthetic degenerate draw')
        return fit_identity(*args, **kwargs)
    monkeypatch.setattr(module, 'fit_identity', failure)
    with pytest.raises(ValueError, match='off sample 1.*ensemble aborted'):
        run(case)
    def limited(*args, **kwargs):
        return fit_identity(*args, **dict(kwargs, max_iter=1))
    monkeypatch.setattr(module, 'fit_identity', limited)
    result = run(case)
    assert len(result['variants']['off']['samples']) == 3
    assert result['variants']['off']['nonconverged_indices']
    assert result['variants']['off']['numerical_status'] == 'nonconverged'
    assert any('did not converge' in w for w in result['warnings'])


def test_cli_reproducibility_safe_outputs_and_config_errors(model_file, marker_file, tmp_path):
    placement = tmp_path/'placement.json'
    placement.write_text(json.dumps(dict(schema_version=1, placement={f'P{i}': dict(sigma_mm=.1, source='synthetic')
                                                                      for i in range(12)})))
    output = tmp_path/'result.json'
    args = ['--input', str(marker_file), '--npz', str(model_file), '--placement', str(placement), '--samples', '2']
    assert main(args+['--output', str(output)]) == 0
    original = output.read_bytes()
    result = json.loads(original)
    assert result['input_hashes'][str(placement)]
    assert result['variants']['off']['samples'][0]['coefficients']
    assert main(args+['--output', str(output)]) == 2
    assert output.read_bytes() == original
    another = tmp_path/'again.json'
    assert main(args+['--output', str(another)]) == 0
    assert another.read_bytes() == original
    assert main(args+['--output', str(marker_file)]) == 2
    placement.write_text('{"schema_version": 1, "schema_version": 1, "placement": {}}')
    absent = tmp_path/'absent.json'
    assert main(args+['--output', str(absent)]) == 2
    assert not absent.exists()


def test_cli_input_change_refuses_publication(model_file, marker_file, tmp_path, monkeypatch):
    import cranio.uncertainty as module
    placement = tmp_path/'placement.json'
    placement.write_text(json.dumps(dict(schema_version=1, placement={'P0': dict(sigma_mm=.1, source='synthetic')})))
    original = module.monte_carlo_identity
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        placement.write_text('{}')
        return result
    monkeypatch.setattr(module, 'monte_carlo_identity', changed)
    out = tmp_path/'changed.json'
    assert main(['--input', str(marker_file), '--npz', str(model_file), '--placement', str(placement),
                 '--allow-partial', '--samples', '2', '--output', str(out)]) == 2
    assert not out.exists()


def test_csv_default_baseline_uses_shared_fit(model_file, marker_file):
    backend = GNMBackend(model_file)
    targets, _, metadata = read_marker_csv(marker_file, backend.index_to_label, backend.landmark_vertex_map)
    result = monte_carlo_identity(backend.load(), targets, metadata, samples=2,
        placement=dict(schema_version=1, placement={t.label: dict(sigma_mm=0., source='synthetic zero') for t in targets}))
    assert result['variants']['off']['samples'][0] == result['variants']['off']['baseline']

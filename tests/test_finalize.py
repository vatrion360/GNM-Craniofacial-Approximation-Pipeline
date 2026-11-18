import json

import numpy as np
import pytest

from cranio.backend import GNMBackend
from cranio.config import PipelineConfig
from cranio.finalize import finalize_snapshot
from cranio.io_csv import write_marker_csv_v3
from cranio.pipeline import run_pipeline


@pytest.fixture
def case(model_file):
    model = GNMBackend(str(model_file)).load(dtype=np.float32)
    xyz = model.mu.astype(float) + np.random.default_rng(48).normal(size=model.mu.shape)
    snap = dict(labels=[f'P{i}' for i in range(len(xyz))], verts=np.arange(len(xyz)),
                targets=xyz, weights=np.linspace(.5, 1., len(xyz)), dense=False)
    settings = dict(loo_auto=False, lambda_base=1., lambda_min=.3, lambda_max=1000.)
    return model, snap, settings


def test_matches_cli_with_actual_corrected_geometry(case, model_file, tmp_path):
    model, snap, settings = case
    stored, record = finalize_snapshot(model, snap, settings)
    json.dumps(record, allow_nan=False)
    assert record['local_displacement']['max_mm'] > .1
    csv, obj = tmp_path/'markers.csv', tmp_path/'face.obj'
    write_marker_csv_v3(csv, [dict(label=l, vertex=int(i), placed=1, x=x, y=y, z=z, weight=w)
        for l, i, (x,y,z), w in zip(snap['labels'], snap['verts'], snap['targets'], snap['weights'])])
    assert run_pipeline(PipelineConfig(input=str(csv), npz=str(model_file), output=str(obj),
                         regularization='adaptive', skip_tps=False)) == 0
    coords = np.array([line.split()[1:] for line in obj.read_text().splitlines() if line.startswith('v ')], float)
    assert np.linalg.norm(stored-coords, axis=1).max() < .01
    assert stored.dtype == np.float32
    assert record['preparation']['counts']['markers'] == len(snap['labels'])
    np.testing.assert_allclose(record['final_marker_residuals_mm'], np.linalg.norm(stored-snap['targets'],axis=1))
    assert not record['geometry_quality']['anatomical_accuracy_established']


@pytest.mark.parametrize('problem', ['few', 'out_of_bounds', 'duplicate', 'collinear', 'missing_dense', 'bad_weight'])
def test_no_result_on_invalid_input(case, problem):
    model, snap, settings = case
    if problem=='few': snap['labels'] = snap['labels'][:3]
    if problem=='out_of_bounds': snap['verts'][0] = model.vertex_count
    if problem=='duplicate': snap['verts'][1] = snap['verts'][0]
    if problem=='collinear': snap['targets'][:,1:] = 0
    if problem=='missing_dense': snap['dense'] = True
    if problem=='bad_weight': snap['weights'][0] = np.inf
    with pytest.raises(ValueError): finalize_snapshot(model, snap, settings)


def test_repeat_refit_from_current_inputs_not_previous_output(case):
    model, snap, settings = case
    initial = finalize_snapshot(model, snap, settings)[0]
    snap['targets'][0] += [2., 0., 0.]
    changed = finalize_snapshot(model, snap, settings)[0]
    assert np.linalg.norm(initial-changed, axis=1).max() > .1
    np.testing.assert_array_equal(changed, finalize_snapshot(model, snap, settings)[0])


def test_incomplete_dense_support(case):
    from scipy.spatial import cKDTree
    model, snap, settings = case
    snap.update(labels=snap['labels'][:6], verts=snap['verts'][:6], targets=snap['targets'][:6],
                weights=snap['weights'][:6], dense=True)
    ids = np.arange(6, 12)
    bones = model.mu[ids]-[0., 0., 2.]
    dense = dict(dense_idx=ids, offsets=np.full(6, 2.), tree=cKDTree(bones), points=bones,
        normals=np.tile([0.,0.,1.], (6,1)), use_normal=False, max_dists=np.full(6, 20.),
        min_dot=.2, triangles=model.triangles, regions=np.array(['scalp','nasal']*3), weight_ratio=.5)
    _, rec = finalize_snapshot(model, snap, settings, dense=dense)
    assert rec['preparation']['counts'] == dict(markers=6, scalp=3, face=3, total=12)
    assert 'last_diagnostics' not in dense
    dense['max_dists'][:] = 0
    with pytest.raises(ValueError, match='accepted dense'): finalize_snapshot(model, snap, settings, dense=dense)

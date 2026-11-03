import numpy as np
import pytest
from cranio.articulation import rigid_delta, point_distances, closed_manifold


def test_rigid_delta_and_distance():
    a = np.eye(4); a[:3, 3] = [1, 2, 3]
    b = a.copy(); b[:3, :3] = [[0,-1,0],[1,0,0],[0,0,1]]; b[:3, 3] = [4,5,6]
    delta = rigid_delta(a, b)
    np.testing.assert_allclose(delta@a, b)
    points = np.array([[1.,2,3,1],[4,6,3,1]])@delta.T
    assert np.linalg.norm(points[0,:3]-points[1,:3]) == 5


@pytest.mark.parametrize('linear', [np.diag([2.,1,1]), np.diag([-1.,1,1]),
    np.array([[1.,.2,0],[0,1,0],[0,0,1]]), np.full((3,3), np.nan)])
def test_invalid_transform(linear):
    b = np.eye(4); b[:3,:3] = linear
    with pytest.raises(ValueError): rigid_delta(np.eye(4), b)


def test_partial_reference_distances():
    r = point_distances({'left': [[0,0,0],[3,4,0]]})
    assert r['left']['distance_mm'] == 5
    assert r['right'] == dict(status='unavailable', distance_mm=None)


def test_open_surface_not_assumed_closed():
    faces = [[0,1,2],[0,3,1],[1,3,2],[2,3,0]]
    assert closed_manifold(faces)
    assert not closed_manifold(faces[:-1])
    assert not closed_manifold([[0,0,1]])


def test_offline_preserves_pose_record_and_does_not_rearticulate(tmp_path,model_file,marker_file):
    import json
    from cranio.config import PipelineConfig
    from cranio.pipeline import run_pipeline
    cfg=PipelineConfig(input=str(marker_file),npz=str(model_file),output=str(tmp_path/'base.obj'),regularization='30')
    assert run_pipeline(cfg)==0
    original=(tmp_path/'base.obj').read_bytes()
    lines=marker_file.read_text().splitlines()
    meta=json.loads(lines[1][1:])
    record={'status':'reviewed_current','history':[{'assumption':'Synthetic recorded rigid pose',
             'rigid_delta_world':np.eye(4).tolist()}]}
    meta['mandible_pose']=record
    lines[1]='# '+json.dumps(meta)
    marker_file.write_text('\n'.join(lines)+'\n')
    cfg=PipelineConfig(input=str(marker_file),npz=str(model_file),output=str(tmp_path/'recorded.obj'),regularization='30')
    assert run_pipeline(cfg)==0
    assert (tmp_path/'recorded.obj').read_bytes()==original
    assert json.loads((tmp_path/'recorded_report.json').read_text())['marker_metadata']['mandible_pose']==record

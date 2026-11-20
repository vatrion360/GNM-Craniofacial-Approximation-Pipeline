"""Analytical directional thickness on synthetic registered meshes in mm."""
import json

import numpy as np
import pytest

from cranio.coherence import main, measure
from cranio.export import export_obj

pytest.importorskip('rtree')

BASE = np.array([[0., 0., 0.], [12., 0., 0.], [0., 12., 0.]])


def site(**changes):
    return dict(dict(bone_triangle=0, barycentric=[.5,.25,.25], axis_world=[0,0,2],
                     direction_source='Fixture plane and signed world vector', reviewed=True), **changes)


def fixture(folder, *, bones=None, skins=None, sites=None, reach=10):
    skull, face, review = (folder/name for name in ('bone.obj', 'face.obj', 'review.json'))
    for path, triangles in [(skull, [BASE] if bones is None else bones),
                            (face, [BASE+[0,0,3]] if skins is None else skins)]:
        points = np.asarray(triangles).reshape(-1,3)
        export_obj(path, points, np.arange(len(points)).reshape(-1,3))
    hashes = measure(skull, face)['input_sha256']
    region = dict(skin_triangles=list(range(len(skins) if skins is not None else 1)),
                  sites=sites if sites is not None else {'A':site()})
    data = dict(schema='gnm.thickness-review.v1', skull_sha256=hashes['skull'], face_sha256=hashes['face'],
                review_source='Analytical paired surfaces in a shared frame', max_distance_mm=reach,
                regions={'patch':region})
    review.write_text(json.dumps(data))
    return skull, face, review


def metric(paths):
    return measure(*paths[:2], thickness_review_path=paths[2])['regional_thickness']


def point(paths):
    return metric(paths)['regions']['patch']['sites']['A']


def test_signed_oblique_depths_and_skin_positions(tmp_path, capsys):
    paths = fixture(tmp_path, sites={'A':site(), 'B':site(axis_world=[3,0,4])})
    skull, face, review = paths
    assert main(['--skull',str(skull),'--face',str(face),'--thickness-review',str(review)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['skin_in_bone']['status'] == 'not_assessed'
    section = result['regional_thickness']
    assert section == metric(paths)
    region = section['regions']['patch']
    assert region['status'] == 'measured' and region['site_count'] == region['measured_count'] == 2
    assert region['measured_site_summary'] == dict(min_mm=3., median_mm=3.375, max_mm=3.75)
    b = region['sites']['B']
    assert b['bone_xyz_mm'] == [3,3,0]
    assert b['skin_xyz_mm'] == pytest.approx([5.25,3,3])
    assert b['skin_triangles'] == [0]


def test_separate_skin_masks_and_partial_regional_summary(tmp_path):
    paths = fixture(tmp_path, skins=[BASE+[0,0,2],BASE+[0,0,4]])
    review = paths[2]
    data = json.loads(review.read_bytes())
    first = data['regions']['patch']
    first.update(skin_triangles=[0])
    first['sites']['missing'] = site(axis_world=None, direction_source=None, reviewed=False)
    data['regions']['other'] = dict(skin_triangles=[1], sites={'B':site()})
    review.write_text(json.dumps(data))
    result = metric(paths)
    assert (result['status'], result['measured_count'],result['site_count']) == ('partial',2,3)
    region = result['regions']['patch']
    assert region['status'] == 'partial' and region['measured_site_summary']['median_mm'] == 2
    assert region['sites']['missing']['thickness_mm'] is None
    assert result['regions']['other']['sites']['B']['thickness_mm'] == 4


@pytest.mark.parametrize('z,expected', [(0.,0.), (10.,10.), (10.01,None), (-1,None)])
def test_segment_endpoints_and_misses(tmp_path, z, expected):
    row = point(fixture(tmp_path, skins=[BASE+[0,0,z]]))
    assert row['thickness_mm'] == expected
    assert (row['reason'] is None) == (expected is not None)


def test_same_hit_on_shared_edge_and_distinct_layers(tmp_path):
    p = np.array([[0,0,3.], [8,0,3.], [8,8,3.], [0,8,3.]])
    skins = [p[[0,1,2]],p[[0,2,3]]]
    row = point(fixture(tmp_path, skins=skins))
    assert row['skin_triangles'] == [0,1] and row['thickness_mm'] == 3
    row = point(fixture(tmp_path, skins=[*skins, BASE+[0,0,4]]))
    assert row['thickness_mm'] is None and 'Multiple' in row['reason']


@pytest.mark.parametrize('extra_bone_z,expected', [(1,None), (7,3)])
def test_second_bone_on_path_or_beyond_skin(tmp_path, extra_bone_z, expected):
    row = point(fixture(tmp_path, bones=[BASE,BASE+[0,0,extra_bone_z]]))
    assert row['thickness_mm'] == expected


def test_grazing_skin_and_unrelated_vertical_patch(tmp_path):
    wall = np.array([[3.,0,1],[3,7,1],[3,3,6]])
    row = point(fixture(tmp_path, skins=[wall, BASE+[0,0,4]]))
    assert row['thickness_mm'] is None and 'coplanar' in row['reason']
    wall[1] = [3,4,8]  # triangle bbox overlaps the segment; actual wall misses the site below 4 mm
    wall[2] = [3,0,8]
    assert point(fixture(tmp_path, skins=[wall, BASE+[0,0,4]], reach=4))['thickness_mm'] == 4


@pytest.mark.parametrize('bones,axis,reason', [([BASE],[0,0,-1],'outward'), ([BASE],[1,0,0],'outward'),
                                               ([BASE[[0,0,2]]],[0,0,1],'Degenerate')])
def test_unusable_source_surfaces_or_directions(tmp_path,bones,axis,reason):
    result = metric(fixture(tmp_path, bones=bones, sites={'A':site(axis_world=axis)}))
    region = result['regions']['patch']
    assert result['status'] == 'not_assessed' and region['measured_site_summary'] is None
    assert reason in region['sites']['A']['reason']


def test_rotated_translated_pair_in_stl_frame(tmp_path):
    bone = BASE[:, [2,0,1]] + [700,80,-630]
    skull, face, review = fixture(tmp_path, bones=[bone], skins=[bone+[3,0,0]],
                                  sites={'A':site(axis_world=[4,0,3])})
    import trimesh
    skull = skull.with_suffix('.stl')
    trimesh.Trimesh(bone,[[0,1,2]],process=False).export(skull)
    data = json.loads(review.read_bytes())
    data['skull_sha256'] = measure(skull, face)['input_sha256']['skull']
    review.write_text(json.dumps(data))
    row = point((skull, face, review))
    assert row['thickness_mm'] == pytest.approx(3.75)
    assert row['skin_xyz_mm'] == pytest.approx([703,83,-624.75])


@pytest.mark.parametrize('changes', [
    {'bone_triangle':True}, {'bone_triangle':1}, {'barycentric':[0,.5,.6]}, {'barycentric':[-.1,.1,1]},
    {'axis_world':[0,0,0]}, {'axis_world':[0,0,True]}, {'axis_world':None}, {'direction_source':'unknown'},
    {'direction_source':'TODO(verify-source): missing'}, {'reviewed':1},
])
def test_malformed_review_fails_without_metric(tmp_path,changes):
    with pytest.raises(ValueError):
        metric(fixture(tmp_path,sites={'A':site(**changes)}))


def test_changed_mesh_refuses_review(tmp_path, capsys):
    skull, face, review = fixture(tmp_path)
    skull.write_bytes(skull.read_bytes()+b'\n')
    assert main(['--skull',str(skull),'--face',str(face),'--thickness-review',str(review)]) == 2
    captured = capsys.readouterr()
    assert not captured.out and 'exact skull and face' in captured.err

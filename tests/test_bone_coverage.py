"""Analytical surface-coverage examples, all dimensions in synthetic mm."""
import json

import numpy as np
import pytest

from cranio.coherence import main, measure
from cranio.export import export_obj

pytest.importorskip('rtree')
pytest.importorskip('shapely')


def mesh(path, triangles):
    vertices = np.asarray(triangles, dtype=float).reshape(-1, 3)
    export_obj(path, vertices, np.arange(len(vertices)).reshape(-1, 3))
    return path


BASE = np.array([[0., 0., 0.], [4., 0., 0.], [0., 4., 0.]])


def case(folder, bones, skins, **options):
    skull = mesh(folder/'bone.obj', bones)
    face = mesh(folder/'face.obj', skins)
    hashes = measure(skull, face)['input_sha256']
    review = dict(schema='gnm.bone-coverage-review.v1', review_source='Synthetic registered bone and skin patches',
                  skull_sha256=hashes['skull'], face_sha256=hashes['face'], outward_normals_reviewed=True,
                  skin_extent_reviewed=True, max_distance_mm=1., eligible_bone_triangles=list(range(len(bones))),
                  skin_triangles=list(range(len(skins))))
    path = folder/'coverage.json'
    path.write_text(json.dumps({**review, **options}))
    return skull, face, path


def coverage(skull, face, path):
    return measure(skull, face, coverage_review_path=path)['bone_without_skin_coverage']


def test_subset_partial_area_and_overlapping_skin(tmp_path, capsys):
    # The first bone facet has area 2, the second 8. Two skin layers cover
    # the same 2 mm² on the larger facet. A full skin sheet is outside the mask.
    small = BASE/2 + [10, 0, 0]
    skull, face, path = case(tmp_path, [small, BASE], [BASE/2+[0,0,.25], BASE/2+[0,0,.75], BASE+[0,0,.5]],
                            skin_triangles=[1,0])
    assert main(['--face', str(face), '--skull', str(skull), '--coverage-review', str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['skin_in_bone']['status'] == 'not_assessed'  # open bone patch
    metric = result['bone_without_skin_coverage']
    assert metric['eligible_area_mm2'] == 10
    assert metric['covered_area_mm2'] == 2
    assert metric['uncovered_area_mm2'] == 8
    assert metric['percent'] == 80
    assert metric == coverage(skull, face, path)
    review = json.loads(path.read_text())
    path.write_text(json.dumps({**review, 'eligible_bone_triangles':[1]}))
    assert coverage(skull, face, path)['percent'] == 75


@pytest.mark.parametrize('height,percent', [(-.1,100), (0,0), (1,0), (1.01,100)])
def test_inclusive_normal_segment_in_rotated_frame(tmp_path, height, percent):
    # Rotate into the yz plane and translate both patches in world coordinates.
    bone = BASE[:, [2, 0, 1]] + [876, -12, 97]
    metric = coverage(*case(tmp_path, [bone], [bone + [height, 0, 0]]))
    assert metric['percent'] == percent


def test_clip_both_ends_of_slanted_triangle_and_reverse_normal(tmp_path):
    # z=x-1. Only the strip 1<=x<=2 projects into the unit-height prism.
    skin = BASE.copy()
    skin[:, 2] = skin[:, 0] - 1
    metric = coverage(*case(tmp_path, [BASE], [skin]))
    assert metric['covered_area_mm2'] == pytest.approx(2.5)
    metric = coverage(*case(tmp_path, [BASE[::-1]], [skin]))
    assert metric['covered_area_mm2'] == pytest.approx(3.5)


@pytest.mark.parametrize('option', ['outward_normals_reviewed', 'skin_extent_reviewed'])
def test_missing_review_has_no_area_score(tmp_path, option):
    metric = coverage(*case(tmp_path, [BASE], [BASE], **{option: False}))
    assert metric['status'] == 'not_assessed' and metric['percent'] is None


@pytest.mark.parametrize('options', [
    {'skin_triangles':[]}, {'eligible_bone_triangles':[True]}, {'skin_triangles':[2]},
    {'eligible_bone_triangles':[0,0]}, {'max_distance_mm':0}, {'max_distance_mm':True}])
def test_refuse_invalid_review(tmp_path, options):
    with pytest.raises(ValueError):
        coverage(*case(tmp_path, [BASE], [BASE], **options))


def test_stale_skin_review_refused(tmp_path, capsys):
    skull, face, path = case(tmp_path, [BASE], [BASE])
    face.write_bytes(face.read_bytes()+b'\n')
    assert main(['--face', str(face), '--skull', str(skull), '--coverage-review', str(path)]) == 2
    captured = capsys.readouterr()
    assert not captured.out and 'exact skull and face' in captured.err


@pytest.mark.parametrize('bones,skins', [
    ([BASE, BASE[::-1]], [BASE]), ([BASE], [BASE[[1,1,2]]]),
    ([BASE, BASE + [1, 0, 0]], [BASE[[0,0,0]]]),
    ([BASE, np.array([BASE[0], BASE[1], [2, -2, 0]])], [BASE]),
])
def test_invalid_selected_facets_are_not_assessed(tmp_path, bones, skins):
    metric = coverage(*case(tmp_path, bones, skins))
    assert metric['status'] == 'not_assessed' and metric['percent'] is None


def test_skin_on_vertical_wall_only_touches_a_line(tmp_path):
    wall = np.array([[1,0,-1],[1,3,.5],[1,0,2]])
    assert coverage(*case(tmp_path, [BASE], [wall]))['percent'] == 100


def test_refining_oblique_bone_triangle_preserves_the_area(tmp_path):
    # (0,.6,.8) is the normal. Subdivide one bone facet at its edge midpoint.
    bone = BASE.copy()
    bone[:, 1], bone[:, 2] = BASE[:, 1]*.8, BASE[:, 1]*-.6
    skin = bone/2 + [0,.3,.4]
    midpoint = (bone[1]+bone[2])/2
    coarse = coverage(*case(tmp_path, [bone], [skin]))
    split = coverage(*case(tmp_path, [[bone[0], bone[1], midpoint], [bone[0], midpoint, bone[2]]], [skin]))
    for metric in (coarse, split):
        assert metric['percent'] == pytest.approx(75)
        assert metric['uncovered_area_mm2'] == pytest.approx(6)

import numpy as np
from cranio.quality import triangles_contact, self_contacts, geometry_quality, sampled_bone_clearance


def test_triangle_contact_coplanar_crossing_and_separated():
    a = np.array([[[0., 0, 0], [2, 0, 0], [0, 2, 0]]]*3)
    b = np.array([[[.2, .2, 0], [1, .2, 0], [.2, 1, 0]],
        [[.2, .2, -1], [.2, .2, 1], [.8, .8, 1]], [[3, 3, 0], [4, 3, 0], [3, 4, 0]]])
    assert triangles_contact(a, b).tolist() == [True, True, False]


def test_tiny_displacement_can_still_create_new_contacts():
    v = np.array([[0., 0, 0], [1, 0, 0], [0, 1, 0], [.1, .1, .01], [.8, .1, .01], [.1, .8, .01]])
    ts = np.array([[0, 1, 2], [3, 4, 5]])
    final = v.copy()
    final[3:, 2] = 0
    report = geometry_quality(v, v, final, ts, 'full')
    assert report['status'] == 'needs_review' and report['final']['new_contact_face_pairs'] == [[0, 1]]
    assert not self_contacts(final, ts, candidate_limit=0)['complete']
    assert self_contacts(v, np.array([[0, 1, 2], [0, 2, 3]]))['pairs'] == []


def test_reversed_triangle_normal_is_reported():
    v = np.array([[0., 0, 0], [1, 0, 0], [0, 1, 0]])
    report = geometry_quality(v, v, v[[0, 2, 1]], np.array([[0, 1, 2]]))
    assert report['status'] == 'needs_review' and report['final']['normal_reversed_faces'] == [0]


def test_clearance_detects_inward_surface():
    skin = np.array([[0., 0, 5], [10, 0, 5], [0, 10, 5]])
    ts, points, normals = np.array([[0, 1, 2]]), np.array([[1., 1, 0]]), np.array([[0., 0, 1]])
    assert sampled_bone_clearance(skin, ts, points, normals)['minimum_outward_clearance_mm'] == 5
    skin[:, 2] = -2
    assert sampled_bone_clearance(skin, ts, points, normals)['negative_clearance_count'] == 1

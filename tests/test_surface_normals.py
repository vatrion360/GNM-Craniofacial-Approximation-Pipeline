"""Observable geometric regressions for perpendicular marker placement."""
import numpy as np
import pytest
from cranio.surface_normals import estimate_normal


def grid(x=None, y=None, height=None):
    x = np.linspace(-5, 5, 41) if x is None else np.asarray(x)
    y = np.linspace(-5, 5, 41) if y is None else np.asarray(y)
    xx, yy = np.meshgrid(x, y)
    zz = np.zeros_like(xx) if height is None else height(xx, yy)
    vertices = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
    faces = []
    for row in range(len(y)-1):
        for col in range(len(x)-1):
            a = row*len(x)+col
            faces += [(a, a+1, a+len(x)+1), (a, a+len(x)+1, a+len(x))]
    return vertices, np.array(faces)


def near(vertices, faces, point=(.1, .1, 0.)):
    index = np.argmin(np.linalg.norm(vertices[faces].mean(axis=1)-point, axis=1))
    return vertices[faces[index]].mean(axis=0), [index]


def test_noisy_plane_reduces_facet_tilt_without_changing_mesh_or_point():
    v, f = grid(height=lambda x, y: .055*np.sin(9*x)*np.cos(8*y))
    point, seed = near(v, f, (.2, .05, 0.))
    original, query = v.copy(), point.copy()
    face = estimate_normal(v, f, point, mode='FACE', seed_faces=seed)
    local = estimate_normal(v, f, point, seed_faces=seed)
    assert np.linalg.norm(local['normal'][:2]) < .02
    assert np.linalg.norm(face['normal'][:2]) > .08
    assert local['patch_faces'] > 100
    np.testing.assert_array_equal(v, original)
    np.testing.assert_array_equal(point, query)


def test_nearby_disconnected_fragments_are_not_averaged():
    v, f = grid()
    other = v.copy()
    other[:, 2] = .4*other[:, 0]+.05
    joined_v, joined_f = np.vstack((v, other)), np.vstack((f, f+len(v)))
    point, seed = near(v, f)
    alone = estimate_normal(v, f, point, seed_faces=seed)
    result = estimate_normal(joined_v, joined_f, point, seed_faces=seed)
    np.testing.assert_allclose(result['normal'], alone['normal'], atol=1e-12)
    assert result['patch_faces'] == alone['patch_faces']


def test_sharp_crease_is_not_crossed():
    v, f = grid(height=lambda x, y: .8*abs(x))
    point, seed = near(v, f, (.1, .1, .08))
    result = estimate_normal(v, f, point, seed_faces=seed)
    expected = np.array([-.8, 0., 1.])
    np.testing.assert_allclose(result['normal'], expected/np.linalg.norm(expected), atol=1e-10)
    assert any('Boundary' in s for s in result['warnings'])


def test_broken_edge_warns_but_does_not_invent_missing_surface():
    v, f = grid(x=np.linspace(0, 5, 21))
    point, seed = near(v, f)
    result = estimate_normal(v, f, point, seed_faces=seed)
    np.testing.assert_allclose(result['normal'], [0, 0, 1], atol=1e-12)
    assert any('one-sided' in s for s in result['warnings'])


def test_spherical_patch_and_rigid_frame_invariance_in_mm():
    v, f = grid(height=lambda x, y: np.sqrt(30**2-x*x-y*y))
    point, seed = near(v, f, (.2, .2, 30))
    result = estimate_normal(v, f, point, radius_mm=2., seed_faces=seed)
    np.testing.assert_allclose(result['normal'], point/np.linalg.norm(point), atol=.005)
    rotation, _ = np.linalg.qr(np.random.default_rng(12).normal(size=(3, 3)))
    if np.linalg.det(rotation) < 0:
        rotation[:, 0] *= -1
    offset = np.array([125., -243., 842.])
    changed = estimate_normal(v @ rotation.T+offset, f, point @ rotation.T+offset,
                              radius_mm=2., seed_faces=seed)
    np.testing.assert_allclose(changed['normal'], rotation @ result['normal'], atol=1e-10)
    scaled = estimate_normal(v*2, f, point*2, radius_mm=4., seed_faces=seed)
    np.testing.assert_allclose(scaled['normal'], result['normal'], atol=1e-10)
    assert scaled['plane_rms_mm'] == pytest.approx(2*result['plane_rms_mm'])


def test_winding_controls_sign_never_viewer_or_skull_centre():
    v, f = grid()
    point, seed = near(v, f)
    result = estimate_normal(v, f[:, ::-1], point, seed_faces=seed)
    np.testing.assert_allclose(result['normal'], [0, 0, -1], atol=1e-12)


def test_sparse_support_requires_explicit_face_mode():
    v = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
    f = np.array([[0, 1, 2]])
    with pytest.raises(ValueError, match='Insufficient connected'):
        estimate_normal(v, f, [.2, .2, 0.])
    result = estimate_normal(v, f, [.2, .2, 0.], mode='FACE')
    np.testing.assert_array_equal(result['normal'], [0, 0, 1])


def test_narrow_fragment_cannot_supply_a_stable_plane():
    v, f = grid(y=np.linspace(-.02, .02, 5))
    point, seed = near(v, f)
    with pytest.raises(ValueError, match='narrow or non-planar'):
        estimate_normal(v, f, point, seed_faces=seed)


def test_nonmanifold_edge_is_not_a_bridge_to_another_sheet():
    v, f = grid()
    # Add a third incident face to every edge along x=0. This must act as a barrier.
    edge = np.flatnonzero(v[:, 0] == 0)
    extra = np.column_stack((edge[:-1], edge[1:], np.full(len(edge)-1, len(v))))
    v = np.vstack((v, [0, 0, 2]))
    f = np.vstack((f, extra))
    point, seed = near(v, f)
    result = estimate_normal(v, f, point, seed_faces=seed)
    np.testing.assert_allclose(result['normal'], [0, 0, 1], atol=1e-12)
    assert any('nonmanifold' in w for w in result['warnings'])


@pytest.mark.parametrize('kind', ['nan_vertex', 'inf_point', 'bad_index', 'float_index',
                                  'zero_radius', 'nan_radius', 'degenerate', 'off_surface', 'bad_seed'])
def test_invalid_or_unsupported_inputs_fail_explicitly(kind):
    v, f = grid()
    point, seed = near(v, f)
    radius = 3.
    if kind == 'nan_vertex': v[0, 0] = np.nan
    if kind == 'inf_point': point[1] = np.inf
    if kind == 'bad_index': f[0, 0] = len(v)
    if kind == 'float_index': f = f.astype(float)
    if kind == 'zero_radius': radius = 0.
    if kind == 'nan_radius': radius = np.nan
    if kind == 'degenerate': v[:] = 0.
    if kind == 'off_surface': point[2] += .2
    if kind == 'bad_seed': seed = [-1]
    with pytest.raises(ValueError):
        estimate_normal(v, f, point, radius_mm=radius, seed_faces=seed)

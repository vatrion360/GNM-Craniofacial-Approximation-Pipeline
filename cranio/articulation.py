"""Rigid pose and reference distances; no anatomical position inferred."""
import numpy as np
from .validation import finite_array

RIGID_ATOL = 2e-5  # numerical float32 transform tolerance, not anatomical


def rigid_delta(initial, current):
    matrices = [finite_array(m, 'control matrix', (4, 4)) for m in (initial, current)]
    for m in matrices:
        r = m[:3, :3]
        if (not np.allclose(m[3], [0, 0, 0, 1], atol=RIGID_ATOL, rtol=0)
                or not np.allclose(r.T@r, np.eye(3), atol=RIGID_ATOL, rtol=0) or np.linalg.det(r) <= 0):
            raise ValueError('Control must be rigid: no scale, shear or reflection')
    return matrices[1] @ np.linalg.inv(matrices[0])


def point_distances(pairs):
    result = {}
    for side in ('left', 'right'):
        pair = pairs.get(side)
        if pair is None:
            result[side] = dict(status='unavailable', distance_mm=None)
        else:
            points = finite_array(pair, side+' condyle/fossa', (2, 3))
            result[side] = dict(status='measured', distance_mm=float(np.linalg.norm(points[0]-points[1])),
                                condyle_mm=points[0].tolist(), fossa_mm=points[1].tolist())
    return result


def closed_manifold(triangles):
    """Necessary edge incidence check, not a proof of an embedded closed solid."""
    t = np.asarray(triangles)
    if t.ndim != 2 or t.shape[1] != 3 or not len(t):
        return False
    e = np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), axis=1)
    edges, counts = np.unique(e, axis=0, return_counts=True)
    return bool(np.all(edges[:, 0] != edges[:, 1]) and np.all(counts == 2))

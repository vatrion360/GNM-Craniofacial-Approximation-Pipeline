"""Explicit main-thread BVH diagnostics; no clinical occlusion inference."""
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from .articulation import closed_manifold
from .validation import finite_array


def _inside(points, triangles, tree, epsilon):
    if not closed_manifold(triangles):
        return dict(status='unavailable_open_surface', inside_vertices=None, ambiguous_vertices=None)
    rays = [Vector(v).normalized() for v in ((1., 1.41421356, 1.73205081),
            (-1.73205081, 1., 1.41421356), (1.41421356, -1.73205081, 1.))]
    inside, ambiguous, boundary = 0, 0, 0
    for p in points:
        origin = Vector(p)
        nearest = tree.find_nearest(origin)
        if nearest[0] is None:
            ambiguous += 1
            continue
        if nearest[3] <= epsilon:
            boundary += 1
            continue
        parity = []
        for ray in rays:
            start, hits = origin.copy(), 0
            for _ in range(len(triangles)+1):
                hit, _, _, _ = tree.ray_cast(start, ray)
                if hit is None:
                    parity.append(hits % 2)
                    break
                hits += 1
                start = hit + ray*epsilon
            else:
                parity.append(None)
        if None in parity or len(set(parity)) != 1:
            ambiguous += 1
        else:
            inside += parity[0]
    return dict(status='conditional_parity', inside_vertices=int(inside), ambiguous_vertices=ambiguous,
        boundary_vertices=boundary, note='Requires closed, non-self-intersecting surfaces; not certified by edge incidence')


def check_surfaces(lower, upper, tolerance_mm=None):
    """BVH overlap includes contact; sampled gaps are not exact triangle gaps."""
    if tolerance_mm is not None and (isinstance(tolerance_mm, bool) or not np.isfinite(tolerance_mm) or tolerance_mm < 0):
        raise ValueError('Contact tolerance must be nonnegative and finite, or unconfigured')
    surfaces = []
    for points, triangles in (lower, upper):
        p, t = finite_array(points, 'dental vertices'), np.asarray(triangles)
        if (p.ndim != 2 or p.shape[1] != 3 or not len(p) or t.ndim != 2 or t.shape[1] != 3
                or not len(t) or t.dtype.kind not in 'iu' or np.any(t < 0) or np.any(t >= len(p))):
            raise ValueError('Invalid dental mesh topology')
        if np.any(np.linalg.norm(np.cross(p[t[:, 1]]-p[t[:, 0]], p[t[:, 2]]-p[t[:, 0]]), axis=1) == 0):
            raise ValueError('Degenerate dental triangles')
        surfaces.append((p, t, BVHTree.FromPolygons(p.tolist(), t.tolist(), all_triangles=True)))
    (lp, lt, lb), (up, ut, ub) = surfaces
    epsilon = 64*np.finfo(np.float32).eps*max(1., float(np.abs(lp).max()), float(np.abs(up).max()))
    gaps = [float(b.find_nearest(Vector(p))[3]) for points, b in ((lp, ub), (up, lb)) for p in points]
    counts = [_inside(lp, ut, ub, epsilon), _inside(up, lt, lb, epsilon)]
    intersections = len(lb.overlap(ub))
    flagged = bool(intersections or any((c['inside_vertices'] or 0) > 0 for c in counts))
    return dict(status='flags_present' if flagged else 'no_flags_in_performed_checks',
        intersection_triangle_pairs=intersections, lower_in_upper=counts[0], upper_in_lower=counts[1],
        minimum_sampled_vertex_gap_mm=min(gaps), vertex_samples=len(gaps), contact_tolerance_mm=tolerance_mm,
        vertices_within_contact_tolerance=None if tolerance_mm is None else sum(g <= tolerance_mm for g in gaps),
        numerical_boundary_epsilon_mm=epsilon,
        interpretation='Geometric indicators only; no certified non-penetration, physiological occlusion or suitable jaw pose')

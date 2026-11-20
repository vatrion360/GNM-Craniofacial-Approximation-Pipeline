"""Area of reviewed bone reached by skin along outward facet normals."""
import hashlib
import math

import numpy as np
import trimesh

from .anomaly import documented
from .tissue import _json


def _facet_ids(values, count, name):
    if (not isinstance(values, list) or not values
            or any(type(i) is not int or not 0 <= i < count for i in values)
            or len(set(values)) != len(values)):
        raise ValueError(f'{name} must contain unique zero-based triangle indices')
    return sorted(values)


def _clip_height(points, height, above):
    """Clip a convex local xyz polygon to one horizontal half-space."""
    clipped = []
    previous = points[-1]
    for current in points:
        a, b = previous[2] - height, current[2] - height
        if (a < 0 < b) or (b < 0 < a):
            clipped.append(previous + (a / (a - b)) * (current - previous))
        if (above and b >= 0) or (not above and b <= 0):
            clipped.append(current)
        previous = current
    return clipped


def _facet_areas(triangle, normal, skin_triangles, tree, reach, shapely):
    """Intersect the bone prism with skin, then project and union its footprints."""
    edge = triangle[1] - triangle[0]
    axis = edge / np.linalg.norm(edge)
    basis = np.column_stack((axis, np.cross(normal, axis), normal))
    base = shapely.Polygon(((triangle - triangle[0]) @ basis)[:, :2])
    end = triangle + normal * reach
    # Pad the broad phase and snap heights at slab boundaries for roundoff.
    eps = 32 * np.finfo(float).eps * max(np.abs(triangle).max(), reach)
    if reach <= 2 * eps:
        raise ArithmeticError('Search distance cannot be resolved in this coordinate frame')
    lo = np.minimum(triangle.min(axis=0), end.min(axis=0)) - eps
    hi = np.maximum(triangle.max(axis=0), end.max(axis=0)) + eps
    candidates = sorted(tree.intersection(np.concatenate((lo, hi))))
    footprints = []
    for skin in skin_triangles[candidates]:
        local = (skin - triangle[0]) @ basis
        z = local[:, 2]
        z[np.abs(z) <= eps] = 0
        z[np.abs(z - reach) <= eps] = reach
        slab = _clip_height(local, 0., above=True)
        if len(slab) >= 3:
            slab = _clip_height(slab, reach, above=False)
        if len(slab) >= 3:
            footprint = shapely.Polygon(np.asarray(slab)[:, :2])
            if footprint.area > 0:
                overlap = base.intersection(footprint)
                if overlap.area > 0:
                    footprints.append(overlap)
    uncovered = base.difference(shapely.union_all(footprints)).area if footprints else base.area
    if not (math.isfinite(base.area) and base.area > 0 and 0 <= uncovered <= math.nextafter(base.area, math.inf)):
        raise ArithmeticError('Invalid projected area')
    return base.area, min(base.area, uncovered)


def measure_coverage(skull, face, hashes, raw):
    review = _json(raw.decode('utf-8-sig'))
    required = {'schema', 'skull_sha256', 'face_sha256', 'review_source', 'outward_normals_reviewed',
                'skin_extent_reviewed', 'eligible_bone_triangles', 'skin_triangles', 'max_distance_mm'}
    if (not isinstance(review, dict) or set(review) != required
            or review['schema'] != 'gnm.bone-coverage-review.v1'
            or any(review[key + '_sha256'] != digest for key, digest in hashes.items())
            or not documented(review['review_source'])
            or any(type(review[key]) is not bool for key in ('outward_normals_reviewed', 'skin_extent_reviewed'))):
        raise ValueError('Expected a documented coverage review bound to the exact skull and face files')
    reach = review['max_distance_mm']
    if type(reach) not in (int, float) or not math.isfinite(reach) or reach <= 0:
        raise ValueError('max_distance_mm must be a finite positive distance')
    bone_ids = _facet_ids(review['eligible_bone_triangles'], len(skull.faces), 'eligible_bone_triangles')
    skin_ids = _facet_ids(review['skin_triangles'], len(face[1]), 'skin_triangles')
    metric = dict(status='not_assessed', percent=None, reason=None,
                  definition='100 * uncovered area / selected bone area along outward facet normals',
                  eligible_bone_triangle_count=len(bone_ids), skin_triangle_count=len(skin_ids),
                  max_distance_mm=reach, review_source=review['review_source'],
                  review_sha256=hashlib.sha256(raw).hexdigest())
    if not review['outward_normals_reviewed'] or not review['skin_extent_reviewed']:
        metric['reason'] = 'Outward bone normals and extent of the skin surface both require review'
        return metric
    try:
        import rtree  # noqa: F401 -- spatial index for the selected skin
        import shapely
        from shapely.errors import GEOSException
    except ImportError as exc:
        raise ValueError('Install the offline coherence extra with pip install ".[coherence]"') from exc

    bone = trimesh.Trimesh(skull.vertices, skull.faces[bone_ids], process=False)
    skin = trimesh.Trimesh(face[0], face[1][skin_ids], process=False)
    if (not bone.unique_faces().all() or not bone.is_winding_consistent
            or np.any(np.bincount(bone.edges_unique_inverse) > 2)):
        metric['reason'] = 'Selected bone has duplicate, nonmanifold or inconsistently wound facets'
        return metric
    if not bone.nondegenerate_faces(height=0).all() or not skin.nondegenerate_faces(height=0).all():
        metric['reason'] = 'Selected bone or skin contains degenerate triangles'
        return metric
    try:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            # Use geometric areas and unit normals without a library mesh-size cutoff.
            triangles = bone.triangles
            cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
            twice_area = np.linalg.norm(cross, axis=1)
            normals = cross / twice_area[:, None]
            skin_triangles, tree = skin.triangles, skin.triangles_tree
            areas = [_facet_areas(tri, normal, skin_triangles, tree, reach, shapely)
                     for tri, normal in zip(triangles, normals)]
            area, uncovered = map(math.fsum, zip(*areas))
    except (ArithmeticError, GEOSException) as exc:
        metric['reason'] = f'Cannot resolve projected surface geometry: {exc}'
        return metric
    metric.update(status='measured', eligible_area_mm2=area, uncovered_area_mm2=uncovered,
                  covered_area_mm2=area-uncovered, percent=100 * (uncovered/area))
    return metric

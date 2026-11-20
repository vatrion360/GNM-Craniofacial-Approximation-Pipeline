"""Directional distances from reviewed bone sites to a selected skin surface."""
import hashlib
import math

import numpy as np
import trimesh

from .anomaly import documented
from .bone_coverage import _facet_ids
from .tissue import _json
from .tissue_directions import unit_vector


ROUND_OFF = 64 * np.finfo(float).eps


def _vector(value, label):
    if (not isinstance(value, list) or len(value) != 3 or
            any(type(x) not in (int, float) or not math.isfinite(x) for x in value)):
        raise ValueError(f'{label} must have three finite numbers')
    return np.asarray(value, dtype=float)


def _named_rows(value, label):
    if not isinstance(value, dict) or not value or not all(key.strip() for key in value):
        raise ValueError(f'Expected named {label}')
    return sorted(value.items())


def _intersections(mesh, origin, axis, reach, eps, *, skip=None):
    """Intersect a finite segment with candidate triangle planes inside their edge bounds."""
    end = origin + reach * axis
    bounds = np.r_[np.minimum(origin, end)-eps, np.maximum(origin, end)+eps]
    hits = []
    triangles = mesh.triangles
    for index in sorted(mesh.triangles_tree.intersection(bounds)):
        if index == skip:
            continue
        tri = triangles[index] - origin
        edges = np.roll(tri, -1, axis=0) - tri
        cross = np.cross(edges[0], -edges[2])
        norm = np.linalg.norm(cross)
        if norm == 0:
            raise ArithmeticError('Degenerate candidate triangle')
        normal = cross / norm
        # Clip the segment to the three inward edge half-spaces of the facet.
        inward = np.cross(normal, edges / np.linalg.norm(edges, axis=1)[:, None])
        start = -np.einsum('ij,ij->i', inward, tri) + eps
        stop = start + reach * (inward @ axis)
        if np.any((start < 0) & (stop < 0)):
            continue
        enters, exits = start < 0, stop < 0
        low = max((start[enters] / (start[enters]-stop[enters])), default=0.) * reach
        high = min((start[exits] / (start[exits]-stop[exits])), default=1.) * reach
        if low > high:
            continue
        height, slope = float(normal @ tri[0]), float(normal @ axis)
        if abs(slope) <= ROUND_OFF:
            residuals = (height-low*slope, height-high*slope)
            if min(residuals) <= eps and max(residuals) >= -eps:
                raise ArithmeticError('Grazing or coplanar segment does not define a unique crossing')
            continue
        t = height / slope
        if low-eps <= t <= high+eps:
            hits.append((min(reach, max(0., t)), index))
    return hits


def _site(row, skull, skin, skin_ids, reach):
    fields = {'bone_triangle', 'barycentric', 'axis_world', 'direction_source', 'reviewed'}
    if not isinstance(row, dict) or set(row) != fields or type(row['reviewed']) is not bool:
        raise ValueError('Expected a thickness site with anchor, direction, source and review flag')
    index = row['bone_triangle']
    if type(index) is not int or not 0 <= index < len(skull.faces):
        raise ValueError('Invalid source bone triangle index')
    weights = _vector(row['barycentric'], 'barycentric')
    if (np.any(weights < 0) or np.any(weights > 1) or abs(math.fsum(weights)-1.) > ROUND_OFF):
        raise ValueError('Barycentric weights must lie on the selected bone triangle and sum to one')
    tri = skull.triangles[index]
    origin = (weights / weights.sum()) @ tri
    result = dict(status='not_assessed', reason=None, thickness_mm=None, bone_triangle=index,
                  barycentric=weights.tolist(), bone_xyz_mm=origin.tolist(), direction_source=row['direction_source'])
    axis = None if row['axis_world'] is None else unit_vector(_vector(row['axis_world'], 'axis_world'), 'axis_world')
    if row['direction_source'] is not None and not isinstance(row['direction_source'], str):
        raise ValueError('direction_source must be text or null')
    if not row['reviewed']:
        result['reason'] = 'Site and direction have not been reviewed'
        return result
    if not documented(row['direction_source']) or 'todo(verify-source)' in row['direction_source'].casefold():
        raise ValueError('Reviewed sites require a documented direction source')
    if axis is None:
        raise ValueError('A reviewed site requires a signed axis_world')
    eps = ROUND_OFF * max(reach, np.abs(tri).max())
    result.update(axis_world=axis.tolist(), numerical_tolerance_mm=float(eps))
    try:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            normal = np.cross(tri[1]-tri[0], tri[2]-tri[0])
            length = np.linalg.norm(normal)
            if length == 0 or (normal/length) @ axis <= ROUND_OFF:
                raise ArithmeticError('Degenerate bone facet or direction does not point outward')
            if reach <= 2*eps:
                raise ArithmeticError('Search distance is unresolved at these world coordinates')
            hits = sorted(_intersections(skin, origin, axis, reach, eps))
            if not hits:
                raise ArithmeticError('No selected skin crossing within the search distance')
            distance = hits[0][0]
            if hits[-1][0] - distance > eps:
                raise ArithmeticError('Multiple distinct skin crossings within the search distance')
            if distance <= eps:
                distance = 0.
            if distance and any(t > eps for t, _ in _intersections(skull, origin, axis, distance, eps, skip=index)):
                raise ArithmeticError('Another bone surface intersects the path to skin')
            result.update(status='measured', thickness_mm=distance, skin_xyz_mm=(origin+distance*axis).tolist(),
                          skin_triangles=sorted(skin_ids[i] for _, i in hits))
    except ArithmeticError as exc:
        result['reason'] = str(exc)
    return result


def _status(count, total):
    if not count:
        return 'not_assessed'
    return 'measured' if count == total else 'partial'


def measure_thickness(skull, face, hashes, raw):
    review = _json(raw.decode('utf-8-sig'))
    fields = {'schema', 'skull_sha256', 'face_sha256', 'review_source', 'max_distance_mm', 'regions'}
    if (not isinstance(review, dict) or set(review) != fields or review['schema'] != 'gnm.thickness-review.v1'
            or any(review[k+'_sha256'] != digest for k, digest in hashes.items())
            or not documented(review['review_source'])):
        raise ValueError('Expected a documented thickness review bound to the exact skull and face files')
    reach = review['max_distance_mm']
    if type(reach) not in (float, int) or not math.isfinite(reach) or reach <= 0:
        raise ValueError('max_distance_mm must be a finite positive distance')
    try:
        import rtree  # noqa: F401 -- trimesh triangle AABB queries
    except ImportError as exc:
        raise ValueError('Install the offline coherence extra with pip install ".[coherence]"') from exc
    regions = {}
    measured = total = 0
    for label, region in _named_rows(review['regions'], 'regions'):
        if not isinstance(region, dict) or set(region) != {'skin_triangles', 'sites'}:
            raise ValueError('Each region needs selected skin triangles and named sites')
        ids = _facet_ids(region['skin_triangles'], len(face[1]), 'skin_triangles')
        skin = trimesh.Trimesh(face[0], face[1][ids], process=False)
        sites = {name: _site(row, skull, skin, ids, reach) for name, row in _named_rows(region['sites'], 'sites')}
        depths = [s['thickness_mm'] for s in sites.values() if s['status'] == 'measured']
        stats = None
        if depths:
            stats = dict(min_mm=min(depths), median_mm=float(np.median(depths)), max_mm=max(depths))
        regions[label] = dict(status=_status(len(depths), len(sites)), measured_count=len(depths),
                              site_count=len(sites), measured_site_summary=stats, sites=sites)
        measured += len(depths)
        total += len(sites)
    return dict(status=_status(measured, total), regions=regions, site_count=total, measured_count=measured,
                max_distance_mm=reach, review_source=review['review_source'],
                review_sha256=hashlib.sha256(raw).hexdigest())

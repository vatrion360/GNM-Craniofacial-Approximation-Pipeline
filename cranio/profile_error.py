"""Offline errors at homologous skin sites in a registered sagittal section."""
import hashlib
import math

import numpy as np

from .anomaly import documented
from .directional_thickness import _named_rows, _vector, barycentric_point
from .tissue import _json
from .tissue_directions import unit_vector
from .validation_cases import distance_summary


def _anchor(mesh, anchor):
    if not isinstance(anchor, dict) or set(anchor) != {'triangle', 'barycentric'}:
        raise ValueError('A profile anchor requires triangle and barycentric weights')
    vertices, faces = mesh
    index = anchor['triangle']
    if type(index) is not int or not 0 <= index < len(faces):
        raise ValueError('Profile triangle index outside saved surface')
    triangle = vertices[faces[index]]
    _, point = barycentric_point(triangle, anchor['barycentric'])
    edges = triangle[1:] - triangle[0]
    scale = np.abs(edges).max()
    valid = bool(scale and np.any(np.cross(*(edges / scale))))
    return point, valid


def _site(row, face, reference, origin, normal, tolerance, unavailable):
    result = dict(status='not_assessed', reason=None, distance_3d_mm=None, distance_in_plane_mm=None)
    if isinstance(row, dict) and set(row) == {'reason'} and documented(row['reason']):
        return dict(result, reason=row['reason'])
    if not isinstance(row, dict) or set(row) != {'approx', 'reference'}:
        raise ValueError('Each planned site needs two homologous anchors or a documented omission reason')
    approx, valid_approx = _anchor(face, row['approx'])
    target, valid_ref = _anchor(reference, row['reference'])
    if unavailable:
        return dict(result, reason=unavailable)
    if not (valid_approx and valid_ref):
        return dict(result, reason='Degenerate anchor triangle')
    offsets = [float((point-origin) @ normal) for point in (approx, target)]
    result.update(approx_xyz_mm=approx.tolist(), reference_xyz_mm=target.tolist(),
                  approx_plane_offset_mm=offsets[0], reference_plane_offset_mm=offsets[1])
    if max(map(abs, offsets)) > tolerance:
        return dict(result, reason='Anchor outside the reviewed profile-plane tolerance')
    return dict(result, status='measured', distance_3d_mm=math.dist(approx, target),
                distance_in_plane_mm=math.hypot(*np.cross(approx-target, normal)))


def measure_profile(face, reference, hashes, raw):
    result = dict(status='not_assessed', reason='No reviewed homologous profile sites',
                  measured_count=0, site_count=0, sites={}, summary_3d=None, summary_in_plane=None)
    if raw is None:
        return result
    review = _json(raw.decode('utf-8-sig'))
    fields = {'schema', 'skull_sha256', 'face_sha256', 'reference_sha256', 'reference_source',
              'reference_access', 'registration_source', 'plane', 'sites'}
    if (not isinstance(review, dict) or set(review) != fields or review['schema'] != 'gnm.profile-error-review.v1'
            or any(review[k+'_sha256'] != digest for k, digest in hashes.items())
            or not all(documented(review[k]) for k in ('reference_source', 'registration_source'))):
        raise ValueError('Expected a documented profile review bound to the exact skull, face and reference')
    access = review['reference_access']
    if access not in ('withheld', 'seen', 'used'):
        raise ValueError('Declare reference_access as withheld, seen or used')
    plane = review['plane']
    if (not isinstance(plane, dict) or set(plane) != {'origin_mm','normal_world','source','tolerance_mm'}
            or not documented(plane['source'])):
        raise ValueError('Expected a documented world-mm sagittal plane and tolerance')
    origin = _vector(plane['origin_mm'], 'plane origin')
    normal = unit_vector(_vector(plane['normal_world'], 'plane normal'), 'plane normal')
    tolerance = plane['tolerance_mm']
    if type(tolerance) not in (float, int) or not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError('Plane tolerance must be finite and nonnegative in mm')

    unavailable = None
    if access != 'withheld':
        unavailable = 'Reference was seen or used during fitting'
    elif hashes['reference'] in (hashes['face'], hashes['skull']):
        unavailable = 'Reference has identical bytes to a fitting input or output'
    reference_mesh = reference.vertices, reference.faces
    try:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            sites = {name: _site(row, face, reference_mesh, origin, normal, tolerance, unavailable)
                     for name, row in _named_rows(review['sites'], 'profile sites')}
    except FloatingPointError as exc:
        raise ValueError('Profile coordinates exceed the numerical range') from exc
    measured = [s for s in sites.values() if s['status'] == 'measured']
    result.update(review_sha256=hashlib.sha256(raw).hexdigest(), reference_source=review['reference_source'],
                  registration_source=review['registration_source'], reference_access=access, plane=plane,
                  sites=sites, site_count=len(sites), measured_count=len(measured))
    if not measured:
        result['reason'] = unavailable or 'No eligible homologous site pairs'
        return result
    for key, field in [('summary_3d', 'distance_3d_mm'), ('summary_in_plane', 'distance_in_plane_mm')]:
        values = [s[field] for s in measured]
        if not all(map(math.isfinite, values)):
            raise ValueError('Profile distances exceed the numerical range')
        result[key] = distance_summary(values, signed=False)
    result.update(status='measured' if len(measured) == len(sites) else 'partial', reason=None)
    return result

"""T0.3: deterministic offline measurements on registered world-mm surfaces."""
import argparse
import hashlib
import io
from pathlib import Path
import sys

import numpy as np
import trimesh

from .anomaly import documented
from .consistency import saved_obj_mesh, triangle_angles
from .record import canonical_bytes
from .tissue import _json


def _skull_mesh(raw, suffix):
    if suffix == '.obj':
        vertices, faces = saved_obj_mesh(raw)
    elif suffix in ('.ply', '.stl'):
        mesh = trimesh.load(io.BytesIO(raw), file_type=suffix[1:], process=False)
        if not isinstance(mesh, trimesh.Trimesh):
            raise ValueError('Expected one triangulated skull mesh')
        vertices, faces = mesh.vertices, mesh.faces
    else:
        raise ValueError('Supported skull formats are STL, PLY and pipeline OBJ')
    if (not len(faces) or faces.shape[1:] != (3,) or faces.min() < 0
            or faces.max() >= len(vertices) or not np.isfinite(vertices).all()):
        raise ValueError('Invalid skull triangle geometry')
    # STL repeats vertices per facet. Weld exact coordinate matches only.
    points, inverse = np.unique(vertices[faces].reshape(-1, 3), axis=0, return_inverse=True)
    return trimesh.Trimesh(points, inverse.reshape(-1, 3), process=False)


def _selection(review, hashes, face):
    required = {'schema', 'skull_sha256', 'face_sha256', 'review_source',
                'bone_solid_reviewed', 'eligible_face_vertices'}
    if (not isinstance(review, dict) or set(review) != required or review['schema'] != 'gnm.coherence-review.v1'
            or any(review[key+'_sha256'] != digest for key, digest in hashes.items())
            or not documented(review['review_source']) or type(review['bone_solid_reviewed']) is not bool):
        raise ValueError('Expected a documented review bound to the exact skull and face files')
    ids = review['eligible_face_vertices']
    if (not isinstance(ids, list) or not ids or any(type(i) is not int for i in ids)
            or len(set(ids)) != len(ids) or not set(ids).issubset(np.unique(face[1]))):
        raise ValueError('Eligible face vertices must be unique indices used in the face triangles')
    return np.asarray(sorted(ids), dtype=np.int64)


def _classify(mesh, points):
    """Classify normalized geometry. Both directions of two fixed rays must agree."""
    from trimesh.ray.ray_triangle import RayMeshIntersector
    from trimesh.constants import tol
    try:
        import rtree  # noqa: F401 -- used by trimesh for closest triangles and ray queries
    except ImportError as exc:
        raise ValueError('Install the optional coherence dependencies with pip install ".[coherence]"') from exc
    epsilon = float(tol.merge)
    lo, hi = mesh.bounds
    classes = np.full(len(points), 'outside', dtype='U9')
    candidates = np.flatnonzero(np.all((points >= lo-epsilon) & (points <= hi+epsilon), axis=1))
    rays = RayMeshIntersector(mesh)
    directions = np.array([[1., np.sqrt(2), np.sqrt(3)], [-np.sqrt(5), 1., np.sqrt(2)]])
    directions /= np.linalg.norm(directions, axis=1)[:, None]
    for start in range(0, len(candidates), 64):
        ids = candidates[start:start+64]
        _, distance, _ = trimesh.proximity.closest_point(mesh, points[ids])
        if not np.isfinite(distance).all():
            raise ValueError('Nonfinite distance to skull surface')
        boundary = distance <= epsilon
        classes[ids[boundary]] = 'boundary'
        ids = ids[~boundary]
        if not len(ids):
            continue
        origins = points[ids]
        parity = []
        for direction in np.vstack((directions, -directions)):
            _, hit_rays, _ = rays.intersects_location(origins, np.broadcast_to(direction, origins.shape))
            parity.append(np.bincount(hit_rays.astype(int), minlength=len(ids)) % 2)
        parities = np.asarray(parity)
        classes[ids[np.all(parities == 1, axis=0)]] = 'inside'
        classes[ids[np.any(parities != parities[0], axis=0)]] = 'ambiguous'
    return classes, epsilon


def measure(skull_path, face_path, review_path=None):
    skull_path, face_path = Path(skull_path), Path(face_path)
    skull_raw, face_raw = skull_path.read_bytes(), face_path.read_bytes()
    if face_path.suffix.lower() != '.obj':
        raise ValueError('Use a saved face OBJ with its original vertex order')
    skull = _skull_mesh(skull_raw, skull_path.suffix.lower())
    face = saved_obj_mesh(face_raw)
    hashes = dict(skull=hashlib.sha256(skull_raw).hexdigest(), face=hashlib.sha256(face_raw).hexdigest())
    metric = dict(status='not_assessed', percent=None,
                  definition='100 * strictly interior selected vertices / all eligible face vertices',
                  reason='No reviewed bone volume and facial vertex selection')
    result = dict(schema='gnm.mesh-coherence.v1', units='mm', input_sha256=hashes,
                  face_mesh_angles=triangle_angles(*face), skin_in_bone=metric)
    if review_path is None:
        return result
    raw = Path(review_path).read_bytes()
    review = _json(raw.decode('utf-8-sig'))
    ids = _selection(review, hashes, face)
    result.update(review_sha256=hashlib.sha256(raw).hexdigest(), review_source=review['review_source'])
    metric.update(eligible_vertex_count=len(ids), total_face_vertex_count=len(face[0]))
    if not review['bone_solid_reviewed']:
        metric['reason'] = 'Operator has not reviewed the bone volume'
        return result
    if (not skull.is_watertight or not skull.is_winding_consistent or not skull.unique_faces().all()
            or triangle_angles(skull.vertices, skull.faces)['degenerate_face_indices']):
        metric['reason'] = 'Skull is open, inconsistently wound, duplicated or degenerate'
        return result
    origin = skull.bounds[0]
    span = float(max(skull.extents))
    if not np.isfinite(span) or span <= 0:
        raise ValueError('Invalid skull extent')
    unit_mesh = trimesh.Trimesh((skull.vertices-origin)/span, skull.faces, process=False)
    with np.errstate(over='ignore', invalid='ignore'):
        queries = (face[0][ids]-origin)/span
    if not np.isfinite(queries).all():
        raise ValueError('Face coordinates exceed the numerical range of the normalized skull frame')
    classes, epsilon = _classify(unit_mesh, queries)
    counts = {key: int(np.count_nonzero(classes == key)) for key in ('inside', 'outside', 'boundary', 'ambiguous')}
    metric.update(counts=counts, boundary_epsilon_mm=epsilon*span, inside_vertex_indices=ids[classes=='inside'].tolist(),
                  ambiguous_vertex_indices=ids[classes=='ambiguous'].tolist())
    if counts['ambiguous']:
        metric['reason'] = 'Ray parity disagreed for one or more selected vertices'
    else:
        metric.update(status='measured', reason=None, percent=100.0*counts['inside']/len(ids))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skull', required=True)
    parser.add_argument('--face', required=True)
    parser.add_argument('--review')
    args = parser.parse_args(argv)
    try:
        result = measure(args.skull, args.face, args.review)
        print(canonical_bytes(result).decode('utf-8'), end='')
    except (OSError, ValueError, OverflowError) as exc:
        print(f'Cannot measure mesh coherence: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

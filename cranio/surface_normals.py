"""Local tangent normals in world millimetres, using NumPy only.

These are geometric placement aids, not landmark-specific tissue directions.
The mesh winding supplies the sign. No camera or skull-centre heuristic is used.
See docs/MARKER_NORMALS.md for scale, boundary and sampling limitations.
"""
from collections import defaultdict, deque
import numpy as np


METHOD_VERSION = 'connected-area-pca-v1'


def _closest_points(tri: np.ndarray, point: np.ndarray) -> np.ndarray:
    """Closest point on each nondegenerate triangle, including its boundary."""
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    ab, ac, ap = b-a, c-a, point-a
    aa = np.einsum('ij,ij->i', ab, ab)
    bb = np.einsum('ij,ij->i', ac, ac)
    abac = np.einsum('ij,ij->i', ab, ac)
    u = np.einsum('ij,ij->i', ap, ab)
    v = np.einsum('ij,ij->i', ap, ac)
    denom = np.einsum('ij,ij->i', np.cross(ab, ac), np.cross(ab, ac))
    s, t = (bb*u-abac*v)/denom, (aa*v-abac*u)/denom
    projected = a+s[:, None]*ab+t[:, None]*ac
    candidates = [projected]
    for start, end in ((a, b), (b, c), (c, a)):
        edge = end-start
        fraction = np.einsum('ij,ij->i', point-start, edge)/np.einsum('ij,ij->i', edge, edge)
        candidates.append(start+np.clip(fraction, 0, 1)[:, None]*edge)
    candidates = np.stack(candidates, axis=1)
    distance2 = np.sum((candidates-point)**2, axis=2)
    distance2[(s < 0) | (t < 0) | (s+t > 1), 0] = np.inf
    return candidates[np.arange(len(tri)), distance2.argmin(axis=1)]


def estimate_normal(vertices: np.ndarray, triangles: np.ndarray, point_mm: np.ndarray,
                    radius_mm: float = 3.0, *, mode: str = 'LOCAL_PLANE',
                    seed_faces: np.ndarray | None = None,
                    surface_tolerance_mm: float = 0.05) -> dict:
    """Estimate a signed normal without moving the query point or mesh.

    ``seed_faces`` optionally identifies the evaluated triangles hit by a ray
    (or a previously recorded seed). Otherwise the closest triangle is used.
    A radius-limited edge-connected patch cannot jump to nearby disconnected
    fragments. Edges with !=2 incident candidate faces, >50 degree dihedrals,
    and faces >60 degrees from the seed cannot be crossed. Three quadrature
    points per triangle approximate area-weighted Gaussian local PCA; samples
    outside the radius are discarded. Three Huber reweighting steps suppress
    local spikes. Rank/planarity failures raise ValueError; no silent fallback.

    Returns JSON-compatible diagnostics, including the normal and warnings.
    Thresholds are engineering defaults and do not establish anatomical validity.
    """
    vertices = np.asarray(vertices, dtype=float)
    triangles = np.asarray(triangles)
    point = np.asarray(point_mm, dtype=float)
    if (vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices)
            or not np.isfinite(vertices).all() or point.shape != (3,)
            or not np.isfinite(point).all()):
        raise ValueError('Expected finite vertices (N,3) and a point in world mm')
    if (triangles.ndim != 2 or triangles.shape[1] != 3 or not len(triangles)
            or not np.issubdtype(triangles.dtype, np.integer)
            or triangles.min() < 0 or triangles.max() >= len(vertices)):
        raise ValueError('Expected valid integer triangle indices')
    if (not np.isfinite(radius_mm) or radius_mm <= 0
            or not np.isfinite(surface_tolerance_mm) or surface_tolerance_mm <= 0):
        raise ValueError('Radius and surface tolerance must be positive finite mm')
    if mode not in ('LOCAL_PLANE', 'FACE'):
        raise ValueError('Unknown marker normal mode')

    # Broad-phase AABBs, one coordinate at a time: no full-mesh (M,3,3) copy.
    box_distance2 = np.zeros(len(triangles))
    for axis in range(3):
        coordinates = vertices[:, axis][triangles]-point[axis]
        delta = np.maximum(np.maximum(coordinates.min(axis=1), -coordinates.max(axis=1)), 0)
        box_distance2 += delta*delta
    ids = np.flatnonzero(box_distance2 <= max(radius_mm, surface_tolerance_mm)**2)
    tri = vertices[triangles[ids]]
    cross = np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0])
    area2 = np.linalg.norm(cross, axis=1)
    valid = area2 > 1e-12
    ids, tri, cross, area2 = ids[valid], tri[valid], cross[valid], area2[valid]
    if not len(ids):
        raise ValueError('No nondegenerate surface near the bone point')
    closest = _closest_points(tri, point)
    distances = np.linalg.norm(closest-point, axis=1)
    eligible = np.ones(len(ids), dtype=bool) if seed_faces is None else np.isin(ids, seed_faces)
    if not eligible.any():
        raise ValueError('Recorded/hit face is absent near the bone point; re-place the marker')
    seed = int(np.argmin(np.where(eligible, distances, np.inf)))
    if distances[seed] > surface_tolerance_mm:
        raise ValueError('Bone point is off the current surface; re-place it (no automatic snapping)')
    normals = cross/area2[:, None]
    reference = normals[seed]
    record = dict(method_version=METHOD_VERSION, mode=mode, radius_mm=float(radius_mm),
                  seed_triangle=int(ids[seed]), point_mm=point.tolist(),
                  surface_distance_mm=float(distances[seed]), warnings=[])
    if mode == 'FACE':
        return dict(record, normal=reference.tolist(), patch_faces=1, angle_to_face_deg=0.)

    nearby = distances <= radius_mm
    compatible = nearby & (normals @ reference >= .5)
    if not compatible[seed]:
        raise ValueError('Radius does not reach the bone surface')
    edge_faces = defaultdict(list)
    for index in np.flatnonzero(nearby):
        a, b, c = triangles[ids[index]]
        for u, v in ((a, b), (b, c), (c, a)):
            edge_faces[tuple(sorted((int(u), int(v))))].append(int(index))
    adjacent = defaultdict(list)
    barriers = []
    crease_cos = np.cos(np.deg2rad(50.))
    edges = np.array(list(edge_faces), dtype=int)
    starts, ends = vertices[edges[:, 0]], vertices[edges[:, 1]]
    deltas = ends-starts
    fractions = np.clip(np.einsum('ij,ij->i', point-starts, deltas)
                        / np.einsum('ij,ij->i', deltas, deltas), 0, 1)
    edge_distances = np.linalg.norm(starts+fractions[:, None]*deltas-point, axis=1)
    for (edge, faces), edge_distance in zip(edge_faces.items(), edge_distances):
        if (edge_distance <= radius_mm and len(faces) == 2 and all(compatible[faces])
                and np.dot(normals[faces[0]], normals[faces[1]]) >= crease_cos):
            adjacent[faces[0]].append(faces[1])
            adjacent[faces[1]].append(faces[0])
        else:
            barriers.append((float(edge_distance), faces))
    seen, queue = {seed}, deque([seed])
    while queue:
        for neighbor in adjacent[queue.popleft()]:
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    selected = np.array(sorted(seen), dtype=int)
    if len(selected) < 3:
        raise ValueError('Insufficient connected support; adjust radius or explicitly choose Face normal')

    # Symmetric order-2 triangle quadrature reduces triangulation-density bias.
    barycentric = np.array([[2/3, 1/6, 1/6], [1/6, 2/3, 1/6], [1/6, 1/6, 2/3]])
    samples = np.einsum('qi,fij->fqj', barycentric, tri[selected]).reshape(-1, 3)-point
    weights = np.repeat(area2[selected]/6, 3)
    radial2 = np.sum(samples*samples, axis=1)/radius_mm**2
    inside = radial2 <= 1.
    samples, weights = samples[inside], weights[inside]*np.exp(-2*radial2[inside])
    if len(samples) < 9 or weights.sum() <= 0:
        raise ValueError('Too few local surface samples; enlarge radius or explicitly choose Face normal')
    base_weights = weights.copy()
    for iteration in range(4):
        weights = weights/weights.sum()
        centroid = weights @ samples
        centered = samples-centroid
        covariance = (centered.T*weights) @ centered
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        if (not np.isfinite(eigenvalues).all() or eigenvalues[2] <= 1e-12
                or eigenvalues[1]/eigenvalues[2] < .02
                or eigenvalues[0]/eigenvalues[1] > .3):
            raise ValueError('Local surface is narrow or non-planar; inspect site and change radius/direction')
        normal = eigenvectors[:, 0]
        residual = np.abs(centered @ normal)
        if iteration < 3:
            scale = max(1.4826*float(np.median(residual)), .01*radius_mm)
            weights = base_weights*np.minimum(1., 1.5*scale/np.maximum(residual, 1e-15))
    if normal @ reference < 0:
        normal = -normal
    angle = float(np.rad2deg(np.arccos(np.clip(normal @ reference, -1., 1.))))
    if angle > 60:
        raise ValueError('Local normal differs >60 degrees from the hit face; inspect the surface')
    warnings = record['warnings']
    if angle > 25:
        warnings.append('Large change from face normal; review direction')
    # Only barriers close to the point count; the artificial radius rim does not.
    for edge_distance, faces in barriers:
        if not seen.intersection(faces):
            continue
        if edge_distance < .75*radius_mm:
            warnings.append('Boundary, crease or nonmanifold edge nearby; one-sided support needs review')
            break
    if eigenvalues[0]/eigenvalues[1] > .1:
        warnings.append('Curved/noisy patch; compare a smaller radius')
    return dict(record, normal=normal.tolist(), patch_faces=len(selected), samples=len(samples),
                angle_to_face_deg=angle, plane_rms_mm=float(np.sqrt(max(eigenvalues[0], 0))),
                eigenvalues_mm2=eigenvalues.tolist(), tangent_spread_ratio=float(eigenvalues[1]/eigenvalues[2]),
                crease_limit_deg=50., seed_cone_deg=60.)

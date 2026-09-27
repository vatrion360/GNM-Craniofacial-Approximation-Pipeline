"""Deterministic geometry diagnostics, distinct from anatomical validation.

Full mode checks nonadjacent exterior triangles for contacts, including coplanar
contacts. Shared-vertex pairs are excluded. Bone clearance is sampled and local;
it is not a watertight containment certificate for open skull fragments.
"""
import numpy as np
from .validation import finite_array, residual_metrics


def deformation_metrics(reference, deformed, triangles):
    a, b = reference[triangles], deformed[triangles]
    na = np.cross(a[:, 1]-a[:, 0], a[:, 2]-a[:, 0])
    nb = np.cross(b[:, 1]-b[:, 0], b[:, 2]-b[:, 0])
    aa, ab = np.linalg.norm(na, axis=1), np.linalg.norm(nb, axis=1)
    valid = aa > 1e-10
    collapsed = valid & (ab <= 1e-10)
    reversed_faces = valid & ~collapsed & (np.einsum('ij,ij->i', na, nb) <= 0)
    ratios = ab[valid]/aa[valid]
    ea, eb = np.linalg.norm(a-np.roll(a, 1, axis=1), axis=2), np.linalg.norm(b-np.roll(b, 1, axis=1), axis=2)
    edges = eb[ea > 1e-10]/ea[ea > 1e-10]
    return dict(reference_degenerate_faces=np.flatnonzero(~valid).tolist(),
        new_degenerate_faces=np.flatnonzero(collapsed).tolist(), normal_reversed_faces=np.flatnonzero(reversed_faces).tolist(),
        area_ratio_range=[float(ratios.min()), float(ratios.max())] if len(ratios) else None,
        edge_ratio_range=[float(edges.min()), float(edges.max())] if len(edges) else None,
        interpretation='Normal reversal is relative to the pose-aligned reference, not a volumetric Jacobian')


def triangles_contact(a, b, tolerance=1e-8):
    """Vectorized triangle separating-axis test, including coplanar overlaps."""
    origin = a[:, :1].copy()
    a, b = a-origin, b-origin
    ea, eb = np.roll(a, -1, axis=1)-a, np.roll(b, -1, axis=1)-b
    na, nb = np.cross(ea[:, 0], ea[:, 1]), np.cross(eb[:, 0], eb[:, 1])
    axes = np.concatenate([na[:, None], nb[:, None], np.cross(ea[:, :, None], eb[:, None, :]).reshape(-1, 9, 3),
        np.cross(na[:, None], ea), np.cross(nb[:, None], eb)], axis=1)
    lengths = np.linalg.norm(axes, axis=2)
    active = lengths > 1e-14
    axes /= np.maximum(lengths[..., None], 1e-300)
    pa, pb = np.einsum('nai,npi->nap', axes, a), np.einsum('nai,npi->nap', axes, b)
    separated = ((pa.max(axis=2) < pb.min(axis=2)-tolerance) | (pb.max(axis=2) < pa.min(axis=2)-tolerance)) & active
    return ~np.any(separated, axis=1)


def self_contacts(vertices, triangles, candidate_limit=2_000_000):
    """Complete broad-phase search with a fail-closed computational budget."""
    from scipy.spatial import cKDTree
    tri = vertices[triangles]
    if not len(tri):
        return dict(complete=True, pairs=[], candidate_pairs_tested=0)
    centers = tri.mean(axis=1)
    radii = np.linalg.norm(tri-centers[:, None], axis=2).max(axis=1)
    maximum = radii.max()
    lower, upper, tree = tri.min(axis=1), tri.max(axis=1), cKDTree(centers)
    pending, contacts, tested = [], [], 0
    def check(pairs):
        array = np.asarray(pairs, dtype=int)
        contacts.extend(array[triangles_contact(tri[array[:, 0]], tri[array[:, 1]])].tolist())
    for i, center in enumerate(centers):
        ids = np.asarray(tree.query_ball_point(center, radii[i]+maximum+1e-8), dtype=int)
        ids = ids[ids > i]
        if not len(ids):
            continue
        ids = ids[np.all(lower[ids] <= upper[i]+1e-8, axis=1) & np.all(upper[ids] >= lower[i]-1e-8, axis=1)]
        adjacent = np.any(triangles[ids, :, None] == triangles[i][None, None, :], axis=(1, 2))
        ids = ids[~adjacent]
        tested += len(ids)
        if tested > candidate_limit:
            return dict(complete=False, pairs=contacts, candidate_pairs_tested=tested, reason='candidate budget exceeded')
        pending.extend((i, int(j)) for j in ids)
        if len(pending) >= 4096:
            check(pending)
            pending = []
    if pending:
        check(pending)
    return dict(complete=True, pairs=contacts, candidate_pairs_tested=tested)


def sampled_bone_clearance(vertices, triangles, points, normals, budget=5000):
    """Exact closest surface for deterministic samples; signed by bone normals."""
    from scipy.spatial import cKDTree
    from trimesh.triangles import closest_point
    ids = np.linspace(0, len(points)-1, min(budget, len(points))).round().astype(int)
    tri = vertices[triangles]
    centers = tri.mean(axis=1)
    radius = np.linalg.norm(tri-centers[:, None], axis=2).max()
    tree = cKDTree(centers)
    upper, _ = cKDTree(vertices[np.unique(triangles)]).query(points[ids])
    clearance, distances = [], []
    for index, bound in zip(ids, upper):
        point = points[index]
        candidates = tree.query_ball_point(point, bound+radius+1e-8)
        closest = closest_point(tri[candidates], np.repeat(point[None], len(candidates), axis=0))
        lengths = np.linalg.norm(closest-point, axis=1)
        nearest = int(lengths.argmin())
        clearance.append(float((closest[nearest]-point) @ normals[index]))
        distances.append(float(lengths[nearest]))
    return dict(sample_indices=ids.tolist(), outward_clearance_mm=clearance,
        minimum_outward_clearance_mm=min(clearance), negative_clearance_count=int(np.sum(np.asarray(clearance) < -.1)),
        tolerance_mm=.1, unsigned_distance=residual_metrics(distances),
        interpretation='Sampled local outward clearance; not a closed-volume containment certificate')


def geometry_quality(reference, statistical, final, triangles, mode='basic', skin_mask=None,
                     skull_points=None, skull_normals=None):
    reference = finite_array(reference, 'reference')
    statistical = finite_array(statistical, 'statistical vertices', reference.shape)
    final = finite_array(final, 'final vertices', reference.shape)
    result = dict(mode=mode, statistical=deformation_metrics(reference, statistical, triangles),
                  final=deformation_metrics(reference, final, triangles), status='passed_basic_checks',
                  anatomical_accuracy_established=False)
    failed = any(result[s]['new_degenerate_faces'] or result[s]['normal_reversed_faces'] for s in ('statistical', 'final'))
    if mode == 'full':
        selected = np.flatnonzero(np.all(skin_mask[triangles], axis=1)) if skin_mask is not None else np.arange(len(triangles))
        if not len(selected):
            raise ValueError('Full QC requires exterior-surface triangles')
        ts = triangles[selected]
        result['contact_scope'] = 'skin_exterior triangles' if skin_mask is not None else 'all triangles'
        result['contact_face_indices'] = selected.tolist()
        baseline = self_contacts(reference, ts)
        result['baseline_contacts'] = baseline
        failed |= not baseline['complete']
        baseline_pairs = set(map(tuple, baseline['pairs']))
        same = np.array_equal(statistical, final)
        for stage, vertices in [('statistical', statistical), ('final', final)]:
            contacts = result['statistical']['contacts'] if same and stage == 'final' else self_contacts(vertices, ts)
            new = sorted(set(map(tuple, contacts['pairs']))-baseline_pairs)
            result[stage]['contacts'] = contacts
            result[stage]['new_contact_face_pairs'] = [[int(selected[i]), int(selected[j])] for i, j in new]
            failed |= bool(new) or not contacts['complete']
            if skull_points is not None and len(skull_points):
                clearance = (result['statistical']['bone_clearance'] if same and stage == 'final'
                    else sampled_bone_clearance(vertices, ts, skull_points, skull_normals))
                result[stage]['bone_clearance'] = clearance
                failed |= clearance['negative_clearance_count'] > 0
            else:
                result[stage]['bone_clearance'] = dict(status='not_assessed', reason='no observed bone supplied')
        result['status'] = 'passed_full_checks'
        result['scope_note'] = 'New defects relative to baseline; existing contacts and excluded adjacent faces still require review'
    if failed:
        result['status'] = 'needs_review'
    return result

"""Review-only bone registration. No case marker, skin surface or Blender state."""
import numpy as np

from .optimize import weighted_umeyama
from .tps import LinearPolyharmonic3D
from .validation import finite_array, validate_points


def _project(nearest, points):
    """nearest maps an N x 3 world-mm array onto the selected observed triangles."""
    hits = finite_array(nearest(points), 'closest fragment points', points.shape)
    return hits, np.linalg.norm(points-hits, axis=1)


def propose(reference, observed, samples, sites, nearest, *, gap_mm, anchor_radius_mm, anchor_limit_mm):
    """Anchored, distance-gated surface ICP then interpolation of anchor residuals.

    Sites are named, held-out reference points. Caller establishes homologous patch,
    anchor identities, units and nearest-triangle search; no unknown-site inference.
    """
    limits = finite_array([gap_mm, anchor_radius_mm, anchor_limit_mm], 'operator limits', (3,))
    if np.any(limits <= 0):
        raise ValueError('Set all three positive distances in mm for this fragment')
    a = validate_points(reference, 'reference anchors', minimum=4, rank=3)
    b = validate_points(observed, 'observed anchors', minimum=4, rank=3)
    if a.shape != b.shape or any(len(np.unique(p, axis=0)) != len(p) for p in (a, b)):
        raise ValueError('Need distinct, paired anchors on both fragments')
    if np.linalg.slogdet((a-a.mean(0)).T @ (b-b.mean(0)))[0] <= 0:
        raise ValueError('Anchor correspondence is reflected or singular; check sides')
    s = finite_array(samples, 'reference surface samples')
    if s.ndim != 2 or s.shape[1] != 3 or not len(s):
        raise ValueError('Expected reference surface samples with shape N x 3')
    if not sites:
        raise ValueError('No unplaced reviewed sites in this atlas patch')
    labels = sorted(sites)
    q = finite_array([sites[k] for k in labels], 'reference sites', (len(labels), 3))
    def apply(x, pose):
        scale, rotation, translation = pose
        return scale * (x @ rotation.T) + translation

    pose = weighted_umeyama(a, b, np.ones(len(a)))
    def assess(pose):
        aligned = apply(a, pose)
        anchor_err = np.linalg.norm(aligned-b, axis=1)
        hits, distances = _project(nearest, apply(s, pose))
        objective = np.mean(anchor_err**2) + np.mean(np.minimum(distances, gap_mm)**2)
        return anchor_err, hits, distances, objective
    errors, hits, distances, loss = assess(pose)
    if errors.max() > anchor_limit_mm:
        raise ValueError('Similarity anchor residual exceeds the configured limit; review anchor pairs')
    iterations = 0
    for _ in range(12):  # computation budget; no anatomical convergence threshold
        keep = distances <= gap_mm
        if not keep.any():
            break
        # Normalize by original sample count for a truncated squared-distance objective.
        weights = np.r_[np.ones(len(a))/len(a), np.ones(keep.sum())/len(s)]
        candidate = weighted_umeyama(np.vstack((a, s[keep])), np.vstack((b, hits[keep])), weights)
        e, h, d, new_loss = assess(candidate)
        if new_loss >= loss or e.max() > anchor_limit_mm:
            break
        pose, errors, hits, distances, loss = candidate, e, h, d, new_loss
        iterations += 1
    inliers = int(np.count_nonzero(distances <= gap_mm))
    if not inliers:
        raise ValueError('No reference surface samples supported by the observed patch')
    aligned = apply(a, pose)
    interp = LinearPolyharmonic3D(aligned, b-aligned)
    pred = apply(q, pose)
    pred += interp(pred)
    surface, gap = _project(nearest, pred)
    # Both source and target neighborhoods must have an anchor. A warp or snap
    # must not rescue an unsupported extrapolation from a distant reference site.
    src_radius = np.linalg.norm(q[:, None]-a, axis=2).min(axis=1)*pose[0]
    dst_radius = np.linalg.norm(surface[:, None]-b, axis=2).min(axis=1)
    rows = {}
    for i, label in enumerate(labels):
        distance = float(max(src_radius[i], dst_radius[i]))
        reason = ('outside local anchor support' if distance > anchor_radius_mm else
                  'no observed surface within limit' if gap[i] > gap_mm else '')
        rows[label] = dict(status='unsupported' if reason else 'needs_review', reason=reason,
            world_mm=None if reason else surface[i].tolist(), snap_mm=float(gap[i]),
            nearest_anchor_mm=distance, support_score=0. if reason else
            float(max(0., 1.-max(distance/anchor_radius_mm, gap[i]/gap_mm))))
    return dict(sites=rows, icp_iterations=iterations, sampled_reference_points=len(s),
        surface_inliers=inliers, similarity_scale=float(pose[0]), rotation=pose[1].tolist(),
        translation_mm=pose[2].tolist(), similarity_anchor_residuals_mm=errors.tolist(),
        spline=interp.diagnostics, limits_mm=dict(surface_gap=gap_mm, anchor_radius=anchor_radius_mm,
        similarity_anchor_residual=anchor_limit_mm), interpretation='Geometric support only; not a calibrated probability')


def held_out_errors(snapshot, manual):
    """Compare independent manual world-mm sites, keeping unsupported cases in the counts."""
    if set(manual) & set(snapshot.get('anchors', {})):
        raise ValueError('Do not score registration anchors as independent observations')
    distances = {}
    for label, xyz in manual.items():
        point = finite_array(xyz, 'manual '+label, (3,))
        row = snapshot['sites'].get(label)
        if row and row['status'] == 'needs_review':
            distances[label] = float(np.linalg.norm(finite_array(row['world_mm'], label, (3,))-point))
    return dict(manual_count=len(manual), compared_count=len(distances),
                unassessed=sorted(set(manual)-set(distances)), distances_mm=distances,
                median_mm=float(np.median(list(distances.values()))) if distances else None)


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description='Score held-out manual bone sites (same world-mm frame)')
    parser.add_argument('snapshot', type=Path, help='Saved proposal Text Editor JSON')
    parser.add_argument('manual', type=Path, help='JSON object mapping independent labels to [x, y, z] mm')
    args = parser.parse_args()
    try:
        record = json.loads(args.snapshot.read_text(encoding='utf8'))
        if record.get('schema') != 'gnm.bone-proposals.v1':
            raise ValueError('Expected a versioned GNM fragment proposal snapshot')
        result = held_out_errors(record, json.loads(args.manual.read_text(encoding='utf8')))
        print(json.dumps(result, indent=2, allow_nan=False))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        parser.exit(2, f'{exc}\n')

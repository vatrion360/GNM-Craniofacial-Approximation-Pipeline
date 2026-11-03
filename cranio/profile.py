"""Opt-in, fixed-pose identity refinement from reviewed segmented bone profiles.

No automatic completion, anatomical mapping, tissue value or direction inference.
The baseline shared identity fit is preserved whenever the acceptance gates fail.
"""
import argparse
import json

import numpy as np

from . import craniometry as cm
from .export import atomic_text
from .reference_frame import _source, EPS
from .validation import finite_array, validate_outputs


def empty_manifest():
    """Null scientific inputs must be configured and reviewed before fitting."""
    return dict(schema_version=1, model_sha256=None, case_id=None,
        source=None, mapping_reviewed=False, mandible_reviewed=False,
        plane=dict(origin_mm=None, normal_world=None, source=None, reviewed=False),
        plane_tolerance_mm=None, segments=[], gap_notes=[], samples=[],
        strength=None, delta_regularization=None, marker_preservation_weight=None,
        marker_displacement_limit_mm=None)


def _number(value, name, positive=True):
    if type(value) not in (int, float):
        raise ValueError(f'{name} must be explicitly configured')
    try:
        valid = np.isfinite(float(value)) and (value > 0 if positive else value >= 0)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f'{name} must be finite and {"positive" if positive else "nonnegative"}')
    return float(value)


def prepare(manifest, model, model_hash, metadata):
    """Validate topology, observed source hashes, plane, directions and depth SDs.

    Each segment follows mesh edges on self-mirrored GNM vertices. Inter-segment
    gaps require notes and are not interpolated. Anatomical endpoints are reviewed
    labels, not certified from a vertex number or a mirror index.
    """
    if not isinstance(metadata, dict):
        raise ValueError('Profile case metadata must be an object')
    if not isinstance(manifest, dict) or set(manifest) != set(empty_manifest()):
        raise ValueError('Profile manifest fields must match the blank template')
    if type(manifest['schema_version']) is not int or manifest['schema_version'] != 1:
        raise ValueError('Unsupported profile schema')
    if manifest['model_sha256'] != model_hash or not cm._sha(model_hash):
        raise ValueError('Profile model SHA-256 mismatch')
    if not isinstance(manifest['case_id'], str) or not manifest['case_id'] or manifest['case_id'] != metadata.get('case_id'):
        raise ValueError('Profile case_id must match the marker case')
    _source(manifest['source'])
    if manifest['mapping_reviewed'] is not True or manifest['mandible_reviewed'] is not True or metadata.get('mandible_articulation_reviewed') is not True:
        raise ValueError('Review profile mapping and mandibular articulation in both case and manifest')
    plane = manifest['plane']
    if not isinstance(plane, dict) or set(plane) != {'origin_mm', 'normal_world', 'source', 'reviewed'} or plane['reviewed'] is not True:
        raise ValueError('Explicit reviewed midsagittal plane required')
    _source(plane['source'])
    origin = finite_array(plane['origin_mm'], 'profile plane origin', (3,))
    normal = finite_array(plane['normal_world'], 'profile plane normal', (3,))
    length = np.linalg.norm(normal)
    if not np.isfinite(length) or length <= EPS:
        raise ValueError('Invalid profile plane normal')
    normal = normal/length
    tolerance = _number(manifest['plane_tolerance_mm'], 'plane_tolerance_mm')
    params = {key: _number(manifest[key], key, positive=key not in ('marker_preservation_weight', 'marker_displacement_limit_mm'))
              for key in ('strength', 'delta_regularization', 'marker_preservation_weight', 'marker_displacement_limit_mm')}
    segments, gaps = manifest['segments'], manifest['gap_notes']
    if not isinstance(segments, list) or not segments or any(not isinstance(s, list) or len(s) < 2 for s in segments):
        raise ValueError('Supply nonempty profile segments, each with at least two vertices')
    if not isinstance(gaps, list) or len(gaps) != len(segments)-1:
        raise ValueError('Document every inter-segment gap')
    for note in gaps:
        _source(note)
    ids = [v for segment in segments for v in segment]
    if any(type(v) is not int or not 0 <= v < model.vertex_count for v in ids) or len(set(ids)) != len(ids):
        raise ValueError('Invalid or duplicate profile vertex')
    if np.any(model.mirror_indices[ids] != ids):
        raise ValueError('Profile chain must use self-mirrored template vertices; review correspondence')
    edges = {tuple(sorted((int(a), int(b)))) for tri in model.triangles for a, b in zip(tri, np.roll(tri, -1))}
    if any(tuple(sorted((a, b))) not in edges for segment in segments for a, b in zip(segment, segment[1:])):
        raise ValueError('A profile segment crosses a non-edge; record a gap instead')
    rows = manifest['samples']
    if not isinstance(rows, list) or len(rows) != len(ids):
        raise ValueError('One reviewed bone sample per profile vertex required')
    source_doc = cm.empty_document()
    source_doc['bone_sources'] = metadata.get('bone_sources', [])
    cm.measure(source_doc)
    sources = {s['id']: s['geometry_sha256'] for s in source_doc['bone_sources']}
    targets, sigmas, labels = [], [], []
    for row in rows:
        fields = {'label', 'bone_xyz_mm', 'normal_world', 'source_id', 'source_geometry_sha256',
                  'status', 'reviewed', 'depth_mm', 'sd_mm', 'tissue_source', 'direction'}
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError('Invalid profile sample fields')
        _source(row['label']); _source(row['tissue_source'])
        if row['status'] != 'observed' or row['reviewed'] is not True:
            raise ValueError('Profile samples must be observed and reviewed; no missing-bone interpolation')
        _source(row['source_id'])
        digest = row['source_geometry_sha256']
        if not cm._sha(digest) or sources.get(row['source_id']) != digest:
            raise ValueError('Profile sample source geometry missing or stale')
        if row['direction'] != 'bone_normal':
            raise ValueError('Only explicitly reviewed bone_normal profile depths are supported')
        bone = finite_array(row['bone_xyz_mm'], 'profile bone point', (3,))
        direction = finite_array(row['normal_world'], 'reviewed bone normal', (3,))
        norm = np.linalg.norm(direction)
        if not np.isfinite(norm) or norm <= EPS:
            raise ValueError('Profile sample normal is zero/invalid')
        depth = _number(row['depth_mm'], 'depth_mm', positive=False)
        sd = _number(row['sd_mm'], 'sd_mm')
        target = bone + depth*direction/norm
        if max(abs((bone-origin)@normal), abs((target-origin)@normal)) > tolerance:
            raise ValueError('Profile bone/skin target outside the reviewed midsagittal tolerance')
        targets.append(target); sigmas.append(sd); labels.append(row['label'])
    if labels[0] != 'Glabella' or labels[-1] != 'Menton' or len(set(labels)) != len(labels):
        raise ValueError('Distinct labels and reviewed Glabella-to-Menton endpoint order required')
    return dict(indices=np.asarray(ids), targets=finite_array(targets, 'profile targets'),
        sigmas=np.asarray(sigmas), origin=origin, normal=normal, plane_tolerance_mm=tolerance,
        labels=labels, manifest=manifest, **params)


def refine(model, coefficients, scale, rotation, translation, marker_indices, marker_weights,
           prepared, *, clip_sigma, active=None):
    """One convex ridge delta solve at fixed pose, followed by explicit safeguards.

    Hard clipping bounds the candidate coefficients. Accept only if every profile
    residual is non-worsening, all chain vertices remain in the declared plane
    tolerance, and every marker displacement respects the declared limit.
    This is NOT a joint MAP fit or an empirical uncertainty/accuracy estimate.
    """
    c = finite_array(coefficients, 'baseline coefficients', (model.identity_dim,))
    rotation = finite_array(rotation, 'rotation', (3, 3))
    translation = finite_array(translation, 'translation', (3,))
    scale = _number(scale, 'scale'); clip_sigma = _number(clip_sigma, 'clip_sigma')
    if not np.allclose(rotation.T@rotation, np.eye(3), atol=1e-10, rtol=0) or np.linalg.det(rotation) <= 0:
        raise ValueError('Profile refinement requires a proper baseline rotation')
    if np.any(np.abs(c) > clip_sigma+EPS):
        raise ValueError('Baseline coefficients outside requested clip bounds')
    from .identity import validate_active_components
    active = np.arange(model.identity_dim) if active is None else validate_active_components(active, model.identity_dim)
    idx = prepared['indices']
    markers = np.asarray(marker_indices)
    if markers.ndim != 1 or markers.dtype.kind not in 'iu' or not len(markers) or np.any(markers < 0) or np.any(markers >= model.vertex_count):
        raise ValueError('Invalid marker indices for profile refinement')
    w = finite_array(marker_weights, 'profile marker weights', markers.shape)
    if np.any(w <= 0) or not np.isfinite(w.sum()):
        raise ValueError('Profile marker weights must be finite and positive')
    baseline = scale*(model.generate(c)@rotation.T)+translation
    finite_array(baseline, 'baseline profile mesh')
    normal, origin = prepared['normal'], prepared['origin']
    if np.any(np.abs((baseline[idx]-origin)@normal) > prepared['plane_tolerance_mm']):
        raise ValueError('Baseline profile chain outside declared plane tolerance; review pose/mapping')
    world_basis = scale*(model.basis[active]@rotation.T)
    jp = world_basis[:, idx].reshape(len(active), -1).T
    jm = world_basis[:, markers].reshape(len(active), -1).T
    wp = np.sqrt(prepared['strength']/len(idx))/np.repeat(prepared['sigmas'], 3)
    wm = np.sqrt(np.repeat(prepared['marker_preservation_weight']*w/w.sum(), 3))
    design = np.vstack((jp*wp[:, None], jm*wm[:, None], np.sqrt(prepared['delta_regularization'])*np.eye(len(active))))
    rhs = np.concatenate(((prepared['targets']-baseline[idx]).reshape(-1)*wp, np.zeros(len(markers)*3+len(active))))
    finite_array(design, 'profile design'); finite_array(rhs, 'profile rhs')
    delta, _, rank, singular = np.linalg.lstsq(design, rhs, rcond=None)
    if rank != len(active):
        raise ValueError('Numerically rank-deficient profile system; review parameter scaling and regularization')
    finite_array(delta, 'profile coefficient delta')
    finite_array(singular, 'profile singular values')
    candidate = c.copy()
    candidate[active] = np.clip(c[active]+delta, -clip_sigma, clip_sigma)
    world = scale*(model.generate(candidate)@rotation.T)+translation
    before = np.linalg.norm(baseline[idx]-prepared['targets'], axis=1)
    after = np.linalg.norm(world[idx]-prepared['targets'], axis=1)
    moved = np.linalg.norm(world[markers]-baseline[markers], axis=1)
    finite_array(after, 'profile candidate residual'); finite_array(moved, 'profile marker displacement')
    numerical = EPS*max(1., float(np.max(np.abs(baseline))), float(np.max(np.abs(prepared['targets']))))
    gates = dict(profile_nonworsening=bool(np.all(after <= before+numerical)),
        marker_displacement=bool(np.all(moved <= prepared['marker_displacement_limit_mm']+numerical)),
        plane_membership=bool(np.all(np.abs((world[idx]-origin)@normal) <= prepared['plane_tolerance_mm']+numerical)))
    accepted = all(gates.values())
    output = candidate if accepted else c.copy()
    final = after if accepted else before
    record = dict(status='accepted' if accepted else 'baseline_retained', pose_policy='frozen baseline similarity',
        acceptance_gates=gates, manifest=prepared['manifest'], baseline_coefficients=c.tolist(), candidate_coefficients=candidate.tolist(),
        final_coefficients=output.tolist(), active_indices=active.tolist(), rank=int(rank),
        singular_values=singular.tolist(), numerical_tolerance_mm=numerical,
        candidate_marker_max_displacement_mm=float(moved.max()),
        final_marker_max_displacement_mm=float(moved.max()) if accepted else 0.,
        points=[dict(label=label, vertex=int(v), target_world_mm=target.tolist(), sd_mm=float(sd),
                     before_mm=float(a), candidate_mm=float(b), final_mm=float(d))
                for label, v, target, sd, a, b, d in zip(prepared['labels'], idx, prepared['targets'], prepared['sigmas'], before, after, final)],
        interpretation='Conditional fixed-pose profile refinement; training constraints, not anatomical validation.')
    return output, record


def main(argv=None):
    parser = argparse.ArgumentParser(description='Write an unconfigured profile manifest (no scientific values guessed)')
    parser.add_argument('--template', required=True, help='New output JSON path')
    args = parser.parse_args(argv)
    try:
        validate_outputs([], [args.template])
        with atomic_text(args.template) as stream:
            json.dump(empty_manifest(), stream, indent=2, allow_nan=False)
        return 0
    except (ValueError, OSError) as exc:
        parser.exit(2, f'Profile: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())

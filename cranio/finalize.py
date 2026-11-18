"""Compute an independent neutral Blender result from current world-mm fit inputs."""
import numpy as np

from .config import PipelineConfig
from .geometry import build_protected_mask, build_scalp_mask, dense_correspondences
from .local_correction import prepare_local_correction
from .marker_audit import require_unique_landmarks
from .preview import fit_preview
from .quality import geometry_quality
from .regularization import adaptive_lambda
from .validation import finite_array, validate_points, residual_metrics


def finalize_snapshot(model, snap, settings, *, dense=None, prior=None):
    """Fresh statistical fit + bounded correction. Return stored coordinates and audit.

    Never uses a displayed mesh, cached coefficients or previously corrected surface.
    At least four included marker rows; a requested dense fit needs current source data.
    QC evaluates the actual float32 coordinates that will be stored by Blender.
    """
    labels, ids = list(snap['labels']), np.asarray(snap['verts'])
    n = len(labels)
    if n < 4:
        raise ValueError('Local finalization needs at least four included markers; ICP alone is unsupported')
    if ids.shape != (n,) or ids.dtype.kind not in 'iu' or np.any(ids < 0) or np.any(ids >= model.vertex_count):
        raise ValueError('Local finalization: invalid marker vertex indices')
    targets = validate_points(snap['targets'], 'marker targets', minimum=4)
    if targets.shape != (n, 3):
        raise ValueError('Marker targets and labels must have matching lengths')
    weights = finite_array(snap['weights'], 'marker confidence', (n,))
    if np.any(weights <= 0) or np.any(weights > 1):
        raise ValueError('Marker confidence must be in (0, 1]')
    require_unique_landmarks(labels, ids, targets)
    if bool(snap.get('dense')) != (dense is not None):
        raise ValueError('Dense setting and prepared bone inputs disagree')
    dense = None if dense is None else dict(dense)
    lam = ('auto' if settings['loo_auto'] else adaptive_lambda(
        n, settings['lambda_base'], settings['lambda_min'], settings['lambda_max']))
    c, scale, rot, trans, used, info, _ = fit_preview(model, snap, lam, settings, dense, prior)
    reference = scale*(model.mu @ rot.T)+trans
    world = scale*(model.generate(c) @ rot.T)+trans
    dense_args = {}
    if dense is not None:
        selected, locations, _, _ = dense_correspondences(world, dense)
        if not len(selected):
            raise ValueError('No accepted dense rows at final pose; inspect coverage and normals')
        dense_args = dict(dense_indices=selected, dense_targets=locations, dense_regions=dense['last_diagnostics']['regions'])
    defaults = PipelineConfig()
    plan = prepare_local_correction(world, ids, targets, weights,
        scalp_indices=build_scalp_mask(model.mu, model.vertex_groups, model.vertex_group_names),
        protected_indices=build_protected_mask(model.vertex_groups, model.vertex_group_names),
        face_cap_mm=defaults.face_cap_mm, scalp_cap_mm=defaults.max_correction_mm,
        protect_damping=defaults.protect_damping, seed=defaults.seed,
        scalp_centres=defaults.tps_scalp_centres, face_centres=defaults.tps_face_centres, **dense_args)
    final, _, _ = plan.apply(backend='numpy')
    stored = np.ascontiguousarray(final, dtype=np.float32)
    rounding = np.linalg.norm(stored.astype(float)-final, axis=1)
    if not np.all(np.isfinite(rounding)) or rounding.max() > .01:
        raise ValueError('Blender float32 storage would lose more than the 0.01 mm software parity tolerance')
    qc = geometry_quality(reference, world, stored, model.triangles)
    if not info.diagnostics['converged']:
        qc['status'] = 'needs_review'
    qc['solver_converged'] = info.diagnostics['converged']
    matrix = np.eye(4)
    matrix[:3, :3], matrix[:3, 3] = scale*rot, trans
    diagnostics = dict(schema_version=1, method='fresh-live-fit-local-numpy-v1', units='world mm',
        settings=dict(settings), labels=labels, targets_mm=targets.tolist(), identity_coefficients=c.tolist(),
        model_to_world=matrix.tolist(), lambda_used=float(used), solver=info.diagnostics,
        measurement_controls=snap.get('measurement_controls', []), measurement_weight=snap.get('measurement_weight', 0.),
        skipped_controls=snap.get('skipped_measurement_controls', []),
        preparation=plan.record(), centres_mm=plan.centers.tolist(), vectors_mm=plan.vectors.tolist(),
        statistical_marker_residuals_mm=np.linalg.norm(world[ids]-targets, axis=1).tolist(),
        final_marker_residuals_mm=np.linalg.norm(stored[ids]-targets, axis=1).tolist(),
        local_displacement=residual_metrics(np.linalg.norm(stored-world, axis=1)),
        max_storage_rounding_mm=float(rounding.max()), geometry_quality=qc,
        scope='Basic geometry checks and training residuals only. Bone clearance, self-contact and anatomical accuracy not assessed.')
    return stored, diagnostics

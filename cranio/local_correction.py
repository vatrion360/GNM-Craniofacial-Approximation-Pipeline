"""Shared NumPy preparation of the existing bounded local-correction inputs.

Consumes a frozen statistical mesh and already accepted dense correspondences.
Does not query a skull, infer missing anatomy, refit identity or apply SD weights.
All coordinates and lengths use one world-mm frame. Selection preserves the
legacy pipeline order: markers, sampled scalp rows, sampled other-region rows.
"""
import copy
from dataclasses import dataclass

import numpy as np

from .validation import finite_array, validate_points

# provenance: legacy_hardcoded — former pipeline.py dense/marker exclusion.
# Numerical separation heuristic, not an anatomical validity threshold.
MARKER_EXCLUSION_MM = 3.0


def _indices(value, size, name):
    ids = np.asarray(value)
    if (ids.ndim != 1 or (ids.size and ids.dtype.kind not in 'iu')
            or np.any(ids < 0) or np.any(ids >= size)
            or len(np.unique(ids)) != len(ids)):
        raise ValueError(f'{name}: require distinct in-range integer vertex indices')
    return ids.astype(np.int64, copy=True)


def _positive(value, name):
    if isinstance(value, (bool, np.bool_)) or not np.isscalar(value):
        raise ValueError(f'{name} must be a finite positive scalar')
    value = float(value)
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be a finite positive scalar')
    return value


def _near_markers(points, markers):
    """Bounded query batches; same strict >3 mm eligibility as legacy KDTree."""
    near = np.zeros(len(points), dtype=bool)
    if len(markers):
        for start in range(0, len(points), 256):
            with np.errstate(over='ignore', invalid='ignore'):
                distances = np.linalg.norm(points[start:start+256, None]-markers[None], axis=2)
            finite_array(distances, 'dense-to-marker distances')
            near[start:start+256] = distances.min(axis=1) <= MARKER_EXCLUSION_MM
    return near


@dataclass(frozen=True)
class PreparedCorrection:
    """Detached read-only arrays and selection audit for one frozen mesh.

    Obtain through prepare_local_correction. apply() always uses the captured
    statistical vertices, preventing accidental cumulative application.
    """
    vertices: np.ndarray
    centers: np.ndarray
    vectors: np.ndarray
    caps: np.ndarray
    protected: np.ndarray
    protect_damping: float
    _audit: dict

    def record(self):
        """Return a detached JSON-compatible preparation record (not QC)."""
        return copy.deepcopy(self._audit)

    def apply(self, *, backend='scipy'):
        """Apply the shared bounded solver; SciPy remains the offline default."""
        from .optimize import bounded_tps_correction
        return bounded_tps_correction(self.vertices, self.centers, self.vectors,
                                      self.caps, self.protected, self.protect_damping,
                                      backend=backend)


def prepare_local_correction(vertices, marker_indices, targets, confidence, *,
                             scalp_indices, protected_indices, face_cap_mm,
                             scalp_cap_mm, protect_damping, seed,
                             scalp_centres, face_centres, dense_indices=None,
                             dense_targets=None, dense_regions=None):
    """Prepare centres, residual vectors, regional caps and row provenance.

    Marker vectors = (target - statistical position) * confidence. These are
    displacement multipliers, NOT precision or IRLS weights. Dense vectors use
    the supplied target minus position without another weight. Caller performs
    inclusion, anatomical review and correspondence acceptance before this call.

    seed and region budgets are explicit; sampling uses legacy default_rng order.
    No unavailable region is synthesized. Exact coincident selected centres fail
    instead of silently choosing between conflicting observations. The bounded
    solver retains the additional numerical conditioning checks of its backend.
    """
    vertices = finite_array(vertices, 'statistical vertices').copy()
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices):
        raise ValueError('Statistical vertices must be a nonempty N by 3 array')
    n = len(vertices)
    markers = _indices(marker_indices, n, 'markers')
    scalp = _indices(scalp_indices, n, 'scalp')
    protected = _indices(protected_indices, n, 'protected')
    targets = finite_array(targets, 'marker targets', (len(markers), 3))
    confidence = finite_array(confidence, 'marker confidence', (len(markers),))
    if np.any(confidence < 0):
        raise ValueError('Marker confidence multipliers must be nonnegative')
    face_cap_mm = _positive(face_cap_mm, 'face cap')
    scalp_cap_mm = _positive(scalp_cap_mm, 'scalp cap')
    if (isinstance(protect_damping, (bool, np.bool_)) or not np.isscalar(protect_damping)
            or not np.isfinite(protect_damping) or not 0 <= protect_damping <= 1):
        raise ValueError('Protection damping must be finite in [0, 1]')
    for name, value in [('seed', seed), ('scalp_centres', scalp_centres), ('face_centres', face_centres)]:
        if type(value) is not int or value < 0:
            raise ValueError(f'{name} must be a nonnegative integer')
    provided = [x is not None for x in (dense_indices, dense_targets, dense_regions)]
    if any(provided) and not all(provided):
        raise ValueError('Dense indices, targets and regions must be supplied together')
    if all(provided):
        dense = _indices(dense_indices, n, 'dense')
        dense_targets = finite_array(dense_targets, 'dense targets', (len(dense), 3))
        regions = np.asarray(dense_regions, dtype=object)
        if (regions.shape != (len(dense),)
                or any(not isinstance(x, str) or not x.strip() for x in regions)):
            raise ValueError('Each dense row needs a nonempty region label')
    else:
        dense, dense_targets, regions = np.empty(0, dtype=np.int64), np.empty((0, 3)), np.empty(0, dtype=object)

    marker_positions = vertices[markers]
    near = _near_markers(vertices[dense], marker_positions)
    eligible = np.flatnonzero(~near)
    rng = np.random.default_rng(seed)
    chosen, counts = [], {}
    for name, cap, mask in [('scalp', scalp_centres, regions[eligible] == 'scalp'),
                             ('face', face_centres, regions[eligible] != 'scalp')]:
        candidates = np.flatnonzero(mask)
        selection = (np.sort(rng.choice(candidates, size=min(cap, len(candidates)), replace=False))
                     if len(candidates) else np.empty(0, dtype=np.int64))
        chosen.append(eligible[selection])
        counts[name] = len(selection)
    rows = np.concatenate(chosen)
    ids = np.concatenate((markers, dense[rows]))
    centers = vertices[ids].copy()
    with np.errstate(over='ignore', invalid='ignore'):
        vectors = np.vstack(((targets-marker_positions)*confidence[:, None],
                             dense_targets[rows]-vertices[dense[rows]]))
    finite_array(vectors, 'prescribed local vectors')
    if len(np.unique(centers, axis=0)) != len(centers):
        raise ValueError('Duplicate local correction centres; review coincident selected vertices')
    validate_points(centers, 'local correction centres', minimum=4, rank=3)
    caps = np.full(n, face_cap_mm)
    caps[scalp] = scalp_cap_mm
    audit = dict(schema_version=1, method='legacy-local-centres-v1', units='mm',
        coordinate_space='world', seed=seed, rng=type(rng.bit_generator).__name__,
        marker_vertex_indices=markers.tolist(), marker_confidence=confidence.tolist(),
        marker_weight_interpretation='Displacement multipliers, not SD precision or IRLS weights',
        dense_supplied=all(provided), dense_candidate_vertex_indices=dense.tolist(),
        dense_candidate_regions=regions.tolist(), dense_near_marker_rows=np.flatnonzero(near).tolist(),
        dense_selected_rows=rows.tolist(), centre_vertex_indices=ids.tolist(),
        centre_kinds=['marker']*len(markers)+['dense_scalp']*counts['scalp']+['dense_face']*counts['face'],
        counts=dict(markers=len(markers), scalp=counts['scalp'], face=counts['face'], total=len(ids)),
        scalp_centres_limit=scalp_centres, face_centres_limit=face_centres,
        marker_exclusion=dict(mm=MARKER_EXCLUSION_MM, rule='dense distance to every marker must be > mm',
                              provenance='legacy_hardcoded'),
        caps=dict(face_mm=face_cap_mm, scalp_mm=scalp_cap_mm, scalp_vertex_indices=scalp.tolist()),
        protection=dict(damping=float(protect_damping), vertex_indices=protected.tolist()),
        interpretation='Preparation of supplied constraints only; not anatomical validation or uncertainty')
    for array in (vertices, centers, vectors, caps, protected):
        array.setflags(write=False)
    return PreparedCorrection(vertices, centers, vectors, caps, protected, float(protect_damping), audit)

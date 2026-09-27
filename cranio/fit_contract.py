"""Shared NumPy contracts for preview and offline fitting."""
from dataclasses import dataclass, field
from typing import Any, NamedTuple
import numpy as np
from .validation import finite_array

DEFAULT_MAX_ITER = 30
DEFAULT_TOL = 1e-5
HUBER_K_MM = 10.0
DENSE_MAX_ROWS = 1500
DENSE_NOSE_WEIGHT = .7


def normalized_dense_weights(marker_weights, relative_weights, ratio=.5, markerless_mass=48.):
    """Fix dense total mass independently of row count; omit zero-strength rows."""
    w = finite_array(marker_weights, 'marker weights').reshape(-1)
    q = finite_array(relative_weights, 'dense relative weights').reshape(-1)
    if np.any(w <= 0) or np.any(q < 0) or not np.isfinite(ratio) or ratio < 0:
        raise ValueError('Invalid marker/dense weights')
    keep = q > 0 if ratio else np.zeros(len(q), bool)
    if not keep.any():
        return keep, np.empty(0)
    mass = ratio * (w.sum() if len(w) else markerless_mass)
    if not np.isfinite(mass) or mass <= 0:
        raise ValueError('Invalid dense weight mass')
    q = q[keep]/q[keep].max()
    return keep, mass*q/q.sum()


def balanced_indices(regions, budget):
    """Sample face/scalp deterministically, redistributing unused budget."""
    regions = np.asarray(regions)
    if budget < 1:
        raise ValueError('Dense row budget must be positive')
    if len(regions) <= budget:
        return np.arange(len(regions))
    scalp, face = np.flatnonzero(regions == 'scalp'), np.flatnonzero(regions != 'scalp')
    nf = min(len(face), budget//2)
    ns = min(len(scalp), budget-nf)
    nf = min(len(face), budget-ns)
    def pick(ids, count):
        return ids[np.linspace(0, len(ids)-1, count).round().astype(int)] if count else np.empty(0, int)
    return np.sort(np.concatenate([pick(scalp, ns), pick(face, nf)]))


@dataclass
class FitInfo:
    """Diagnostics with backward-compatible three-item tuple unpacking."""
    loo_table: list | None
    history: list
    dense_history: list
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __iter__(self):
        return iter((self.loo_table, self.history, self.dense_history))

    def __getitem__(self, item):
        return (self.loo_table, self.history, self.dense_history)[item]


class FitResult(NamedTuple):
    coefficients: np.ndarray
    scale: float
    rotation: np.ndarray
    translation: np.ndarray
    regularization: float
    info: FitInfo
    residuals_mm: np.ndarray

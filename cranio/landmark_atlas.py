"""Read-only placement cards and orthographic reference views. No fit dependencies."""
from dataclasses import dataclass

import numpy as np

from .landmarks import LANDMARK_INFO, PLACEMENT_HINTS, side_of
from .paper_reference import PAPER_ROWS, PAPER_DEFINITIONS, CAVEATS, CITATION, DOI


def card(label):
    """Separate paper bone-site definitions, project hints and unknowns."""
    if label not in LANDMARK_INFO:
        raise ValueError(f'No catalogue entry for {label!r}')
    paper = label in PAPER_DEFINITIONS
    definition = PAPER_DEFINITIONS.get(label)
    hint = PLACEMENT_HINTS.get(label)
    return dict(label=label, side={-1: 'right', 0: 'midline', 1: 'left'}[side_of(label)],
        status='needs_expert_review', definition=definition,
        definition_source=f'{CITATION}; Table 2, row {PAPER_ROWS[label]}; DOI {DOI}' if paper else None,
        placement_hint=hint if hint != definition else None, caution=CAVEATS.get(label))


# Camera position in local mesh axes; image-right cross image-up = toward viewer.
_AXES = {'+X': (1, 2, 0, 1), '-X': (1, 2, 0, -1),
         '+Y': (0, 2, 1, -1), '-Y': (0, 2, 1, 1),
         '+Z': (0, 1, 2, 1), '-Z': (0, 1, 2, -1)}
VIEWS = tuple(_AXES)


@dataclass(frozen=True)
class View:
    right: np.ndarray
    up: np.ndarray
    toward: np.ndarray
    eye: np.ndarray
    span: float
    size: int

    def ray_origin(self, x, y):
        return self.eye + self.span*((x+.5)/self.size-.5)*self.right + self.span*((y+.5)/self.size-.5)*self.up

    def project(self, point):
        delta = point-self.eye
        return self.size*(np.array([delta @ self.right, delta @ self.up])/self.span+.5)-.5


def make_view(vertices, axis, size):
    v = np.asarray(vertices, dtype=float)
    if (v.ndim != 2 or v.shape[1] != 3 or len(v) < 3 or not np.isfinite(v).all()
            or axis not in VIEWS or type(size) is not int or size < 2):
        raise ValueError('Invalid reference geometry, projection or image size')
    i, j, k, sign = _AXES[axis]
    right, up, toward = np.eye(3)[[i, j, k]]
    right *= sign
    toward *= 1 if axis.startswith('+') else -1
    low, high = v.min(axis=0), v.max(axis=0)
    extent = high-low
    span = 1.1*max(extent[i], extent[j])  # image border only
    if not np.isfinite(span) or span <= 0:
        raise ValueError('No visible extent on the selected axis')
    eye = (low+high)*.5 + toward*(extent[k]*.5+span)
    return View(right, up, toward, eye, span, size)

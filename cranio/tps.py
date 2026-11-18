"""NumPy-only 3-D linear polyharmonic displacement interpolation.

Implements the repository's existing K(r)=-r, affine polynomial, zero-smoothing
system. This is NOT the 2-D r**2 log(r) kernel called thin_plate_spline in SciPy.
The historical module name follows the pipeline's local-correction terminology.
No nearest-neighbor approximation, automatic smoothing or solver fallback.
"""
import copy

import numpy as np

from .validation import finite_array, validate_points


def _kernel(a, b):
    """Direct differences avoid squared-distance cancellation near a centre."""
    with np.errstate(over='ignore', invalid='ignore'):
        values = -np.linalg.norm(a[:, None, :]-b[None, :, :], axis=2)
    return finite_array(values, 'linear spline kernel')


class LinearPolyharmonic3D:
    """Interpolate C by 3 displacement vectors with an affine tail, float64.

    Coordinates and displacements use mm. An internal translation and uniform
    coordinate scaling condition the system without changing the zero-smoothed
    interpolant. The augmented system must retain full numerical rank using the
    standard size * machine-epsilon * largest-singular-value tolerance. This is
    an arithmetic criterion, not an anatomical separation threshold.
    """

    def __init__(self, centers, displacements):
        centers = validate_points(centers, 'local correction centres', minimum=4, rank=3).copy()
        values = finite_array(displacements, 'local displacements', centers.shape).copy()
        if len(np.unique(centers, axis=0)) != len(centers):
            raise ValueError('Duplicate local correction centres; review marker correspondences')
        with np.errstate(over='ignore', invalid='ignore'):
            origin = centers.mean(axis=0)
            centered = centers-origin
        finite_array(centered, 'centred spline coordinates')
        scale = float(np.max(np.abs(centered)))
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError('Invalid local spline coordinate scale')
        normalized = centered/scale
        polynomial = np.column_stack((np.ones(len(centers)), normalized))
        size = len(centers)+4
        system = np.zeros((size, size))
        system[:-4, :-4] = _kernel(normalized, normalized)
        system[:-4, -4:] = polynomial
        system[-4:, :-4] = polynomial.T
        rhs = np.zeros((size, 3))
        rhs[:-4] = values
        try:
            singular = np.linalg.svd(system, compute_uv=False)
            threshold = size*np.finfo(float).eps*singular[0]
            rank = int(np.count_nonzero(singular > threshold))
            if rank != size:
                raise ValueError('Local spline system is numerically rank deficient; review near-duplicate centres')
            coefficients = np.linalg.solve(system, rhs)
        except np.linalg.LinAlgError as exc:
            raise ValueError('Local spline factorization failed; no fallback or smoothing applied') from exc
        finite_array(coefficients, 'local spline coefficients')
        error = float(np.linalg.norm(system@coefficients-rhs, ord=np.inf))
        denominator = float(np.linalg.norm(system, ord=np.inf)*np.linalg.norm(coefficients, ord=np.inf)
                            + np.linalg.norm(rhs, ord=np.inf))
        backward = error/denominator if denominator else 0.
        if not np.isfinite(backward) or not np.isfinite(denominator):
            raise ValueError('Nonfinite local spline solve diagnostics')
        # Numerical acceptance only; does not bound interpolation/anatomical error.
        backward_limit = 64*size*np.finfo(float).eps
        if backward > backward_limit:
            raise ValueError('Local spline linear-system residual exceeds numerical tolerance')
        self._centers, self._origin, self._scale = normalized, origin, scale
        self._coefficients = coefficients
        for array in (self._centers, self._origin, self._coefficients):
            array.setflags(write=False)
        self._diagnostics = dict(backend='numpy', kernel='linear (-r)', degree=1, smoothing=0.,
            centre_count=len(centers), system_size=size, numerical_rank=rank,
            coordinate_origin_mm=origin.tolist(), coordinate_scale_mm=scale,
            condition_number=float(singular[0]/singular[-1]), rank_tolerance=float(threshold),
            relative_backward_error=backward, backward_error_limit=float(backward_limit),
            interpretation='Numerical solvability only; not anatomical accuracy or uncertainty')

    @property
    def diagnostics(self):
        """Detached numerical diagnostics; do not expose mutable solver state."""
        return copy.deepcopy(self._diagnostics)

    def __call__(self, points, *, chunk_size=2048):
        """Evaluate in bounded-size chunks; no mutation of supplied points."""
        if type(chunk_size) is not int or chunk_size < 1:
            raise ValueError('Spline evaluation chunk_size must be a positive integer')
        points = finite_array(points, 'local spline evaluation points')
        if points.ndim != 2 or points.shape[1] != 3:
            raise ValueError('Spline evaluation points must have shape N by 3')
        result = np.empty_like(points)
        for start in range(0, len(points), chunk_size):
            with np.errstate(over='ignore', invalid='ignore'):
                x = (points[start:start+chunk_size]-self._origin)/self._scale
            finite_array(x, 'normalized spline evaluation points')
            polynomial = np.column_stack((np.ones(len(x)), x))
            result[start:start+chunk_size] = _kernel(x, self._centers)@self._coefficients[:-4] + polynomial@self._coefficients[-4:]
        return finite_array(result, 'interpolated correction')

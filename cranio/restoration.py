"""Geometry for explicitly selected fragment restoration; no anatomy inference."""
import numpy as np

from .validation import finite_array, validate_points


def fit_reference_plane(points):
    points = validate_points(points, 'Plane references', minimum=3, rank=2)
    centre = points.mean(axis=0)
    _, singular, vt = np.linalg.svd(points - centre)
    # Nearly straight facial chains do not determine a stable sagittal plane.
    if singular[1] < max(0.1, singular[0] * 1e-3):
        raise ValueError('Plane references are nearly collinear; select broader preserved references or a manual plane')
    normal = vt[-1]
    rms = float(np.sqrt(np.mean(((points - centre) @ normal) ** 2)))
    return centre, normal, rms


def plane_values(centre, normal):
    centre = finite_array(centre, 'Plane origin', (3,))
    normal = finite_array(normal, 'Plane normal', (3,))
    length = np.linalg.norm(normal)
    if length <= 1e-12:
        raise ValueError('Plane normal is zero')
    return centre, normal / length


def reflect_points(points, centre, normal):
    centre, normal = plane_values(centre, normal)
    points = finite_array(points, 'Donor points')
    return points - 2.0 * ((points - centre) @ normal)[..., None] * normal


def donor_half(points, centre, normal, tolerance=0.1):
    """Reject mixed-side donors: a fragment group must describe ONE side.

    The sign is geometric, not an inferred anatomical left/right assignment.
    """
    centre, normal = plane_values(centre, normal)
    d = (finite_array(points, 'Donor points') - centre) @ normal
    if not len(d):
        raise ValueError('Donor region is empty')
    if np.any(d > tolerance) and np.any(d < -tolerance):
        raise ValueError('Donor spans both sides of the plane. Select a one-sided vertex group or separate the fragments; preserve the other anatomy')
    if not np.any(np.abs(d) > tolerance):
        raise ValueError('Donor lies on the midline. Use Keep preserved for central anatomy')
    return 1 if np.any(d > tolerance) else -1

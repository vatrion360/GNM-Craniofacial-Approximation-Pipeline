"""Input contracts shared by the CLI and Blender (NumPy only)."""
import hashlib
from pathlib import Path

import numpy as np


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite_array(value, name, shape=None):
    array = np.asarray(value, dtype=np.float64)
    if shape is not None and array.shape != shape:
        raise ValueError(f"{name}: expected shape {shape}, got {array.shape}")
    if not np.isfinite(array).all():
        raise ValueError(f"{name}: NaN and infinity are not permitted")
    return array


def validate_points(points, name="landmarks", minimum=3, rank=2):
    points = finite_array(points, name)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < minimum:
        raise ValueError(f"{name}: need at least {minimum} points with 3 coordinates")
    singular = np.linalg.svd(points - points.mean(axis=0), compute_uv=False)
    if singular[0] < 1e-10 or singular[rank - 1] <= singular[0] * 1e-7:
        raise ValueError(f"{name}: degenerate geometry (required spatial rank {rank})")
    return points


def validate_outputs(inputs, outputs, overwrite=False):
    inputs = {Path(p).expanduser().resolve() for p in inputs if p}
    resolved = [Path(p).expanduser().resolve() for p in outputs if p]
    if len(set(resolved)) != len(resolved):
        raise ValueError("Output paths must be distinct")
    for path in resolved:
        if path in inputs:
            raise ValueError(f"An output would overwrite an input: {path}")
        if path.exists() and not overwrite:
            raise ValueError(f"Output exists: {path}. Choose another output or use --overwrite")


def rmse(residuals):
    residuals = finite_array(residuals, "residuals")
    return float(np.sqrt(np.mean(residuals ** 2))) if residuals.size else 0.0


def residual_metrics(residuals):
    r = finite_array(residuals, "residuals")
    if not r.size:
        return {"count": 0}
    return {"count": int(r.size), "rmse_mm": rmse(r),
            "mean_mm": float(r.mean()), "median_mm": float(np.median(r)),
            "p95_mm": float(np.percentile(r, 95)), "max_mm": float(r.max())}

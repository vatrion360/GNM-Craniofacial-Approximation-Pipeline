"""Opt-in fixed-pose Gaussian diagnostic, not calibrated full-fit uncertainty.

The NumPy core distinguishes conditional posterior covariance from repeated-data
MAP-estimator covariance. Noise and prior covariance must be supplied explicitly.
See docs/LINEAR_UNCERTAINTY.md for the statistical contract and limitations.
"""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from .validation import finite_array


def _symmetric(value, size, name):
    matrix = finite_array(value, name, (size, size))
    magnitude = float(np.max(np.abs(matrix)))
    normalized = matrix / magnitude if magnitude else matrix
    if not np.allclose(normalized, normalized.T, rtol=0, atol=64*np.finfo(float).eps):
        raise ValueError(f'{name}: must be symmetric')
    return .5*matrix + .5*matrix.T


def _spd(value, size, name):
    matrix = _symmetric(value, size, name)
    try:
        factor = np.linalg.cholesky(matrix)
    except np.linalg.LinAlgError as exc:
        raise ValueError(f'{name}: must be positive definite; no jitter or missing SD is imputed') from exc
    return matrix, factor


@dataclass
class LinearGaussianResult:
    """Coefficient-space solution and whitened system for independent sampling."""
    mean: np.ndarray
    posterior_covariance: np.ndarray
    estimator_covariance: np.ndarray
    augmented_design: np.ndarray
    augmented_target: np.ndarray
    observation_count: int
    condition_number: float


def linear_gaussian(design, observations, observation_covariance, prior_mean,
                    prior_covariance) -> LinearGaussianResult:
    """Solve y=A beta+noise with explicit SPD C and Gaussian prior N(m,P).

    Uses Cholesky whitening and an augmented SVD; no normal-equation inversion.
    All pose, noise and prior parameters are conditioned on, not estimated here.
    """
    a = finite_array(design, 'design')
    if a.ndim != 2 or min(a.shape) < 1:
        raise ValueError('design must be a nonempty matrix')
    n, p = a.shape
    y = finite_array(observations, 'observations', (n,))
    m = finite_array(prior_mean, 'prior_mean', (p,))
    _, lc = _spd(observation_covariance, n, 'observation_covariance')
    _, lp = _spd(prior_covariance, p, 'prior_covariance')
    matrix = finite_array(np.vstack((np.linalg.solve(lc, a), np.linalg.solve(lp, np.eye(p)))),
                          'augmented design')
    target = finite_array(np.concatenate((np.linalg.solve(lc, y), np.linalg.solve(lp, m))),
                          'augmented target')
    u, singular, vt = np.linalg.svd(matrix, full_matrices=False)
    if singular[-1] <= np.finfo(float).eps*max(matrix.shape)*singular[0]:
        raise ValueError('Whitened augmented design is numerically rank deficient')
    factor = vt.T / singular
    mean = finite_array(factor @ (u.T @ target), 'conditional mean')
    covariance = finite_array(factor @ factor.T, 'posterior covariance')
    gain = factor @ u[:n].T
    estimator = finite_array(gain @ gain.T, 'estimator covariance')
    return LinearGaussianResult(mean, covariance, estimator, matrix, target, n,
                                float(singular[0]/singular[-1]))


def fixed_pose_design(model, indices, targets_mm, *, scale, rotation, translation_mm, active=None):
    """Return landmark design, residual target and full vertex Jacobian in world mm.

    Ordering is landmark-major xyz. Inactive identity coefficients remain zero.
    Scale/rotation/translation are explicit inputs; no alignment is performed.
    """
    from .identity import validate_active_components
    scale = float(scale)
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError('scale must be finite and positive')
    rotation = finite_array(rotation, 'rotation', (3, 3))
    if (not np.allclose(rotation.T @ rotation, np.eye(3), rtol=0, atol=1e-10)
            or not np.isclose(np.linalg.det(rotation), 1., rtol=0, atol=1e-10)):
        raise ValueError('rotation must be a proper orthogonal matrix (no reflection)')
    translation = finite_array(translation_mm, 'translation_mm', (3,))
    ids = np.asarray(indices)
    if (ids.ndim != 1 or not len(ids) or ids.dtype.kind not in 'iu'
            or np.any(ids < 0) or np.any(ids >= model.vertex_count)
            or len(np.unique(ids)) != len(ids)):
        raise ValueError('indices must be distinct in-range integers')
    targets = finite_array(targets_mm, 'targets_mm', (len(ids), 3))
    basis = model.basis if active is None else model.basis[validate_active_components(active, model.identity_dim)]
    jacobian = finite_array(scale*np.einsum('ab,ivb->vai', rotation, basis), 'world Jacobian')
    residual = finite_array(targets-(scale*(model.mu[ids] @ rotation.T)+translation), 'target residual')
    return jacobian[ids].reshape(3*len(ids), -1), residual.ravel(), jacobian


def propagate_covariance(jacobian, covariance) -> dict:
    """Propagate PSD coefficient covariance to coordinate SD and sqrt(trace), mm."""
    j = finite_array(jacobian, 'jacobian')
    if j.ndim != 3 or j.shape[1] != 3 or min(j.shape) < 1:
        raise ValueError('jacobian must have shape (vertices, 3, components)')
    c = _symmetric(covariance, j.shape[2], 'coefficient covariance')
    eigen, vectors = np.linalg.eigh(c)
    tolerance = 64*np.finfo(float).eps*len(eigen)*np.max(np.abs(eigen))
    if eigen[0] < -tolerance:
        raise ValueError('coefficient covariance must be positive semidefinite')
    factor = vectors*np.sqrt(np.maximum(eigen, 0))
    variance = np.empty(j.shape[:2])
    for start in range(0, len(j), 256):
        projected = j[start:start+256] @ factor
        variance[start:start+256] = np.sum(projected**2, axis=2)
    finite_array(variance, 'vertex variances')
    spread = finite_array(np.sqrt(variance.sum(axis=1)), 'vertex spread')
    return dict(sd_xyz_mm=np.sqrt(variance), spread_rms_mm=spread)


def _relative_error(observed, expected):
    denominator = float(np.linalg.norm(expected))
    error = float(np.linalg.norm(observed-expected))
    return error/denominator if denominator else (0. if error == 0 else None)


def covariance_crosscheck(result: LinearGaussianResult, draws=10000, seed=0) -> dict:
    """Independent augmented least-squares MC; sample covariance uses ddof=1.

    Perturbing both whitened data and prior targets samples the conditional
    posterior. Perturbing only data targets samples repeated-data MAP estimates.
    This is not nonlinear A2.1 refitting or random selection of demographic priors.
    """
    if isinstance(draws, bool) or not isinstance(draws, (int, np.integer)) or draws < 2:
        raise ValueError('draws must be an integer >= 2')
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    rng = np.random.Generator(np.random.PCG64(seed))
    noise = rng.normal(size=(len(result.augmented_target), draws))
    output = {}
    for name, expected in (('posterior', result.posterior_covariance), ('estimator', result.estimator_covariance)):
        if name == 'estimator':
            noise[result.observation_count:] = 0.
        samples = np.linalg.lstsq(result.augmented_design,
                                 result.augmented_target[:, None]+noise, rcond=None)[0]
        mean = samples.mean(axis=1)
        centered = samples-mean[:, None]
        empirical = finite_array(centered @ centered.T/(draws-1), 'MC covariance')
        output[name] = dict(mean=mean.tolist(), covariance=empirical.tolist(),
                            relative_covariance_error=_relative_error(empirical, expected),
                            mean_error_norm=float(np.linalg.norm(mean-result.mean)))
    return output


def _covariance_config(document, dimension, sd_key, matrix_key):
    if not isinstance(document, dict) or set(document) not in ({sd_key}, {matrix_key}):
        raise ValueError(f'Supply exactly one of {sd_key} or {matrix_key}')
    if sd_key in document:
        sd = finite_array(document[sd_key], sd_key, (dimension,))
        if np.any(sd <= 0):
            raise ValueError(f'{sd_key}: explicit strictly positive SD required')
        return _spd(np.diag(sd**2), dimension, matrix_key)[0]
    return _spd(document[matrix_key], dimension, matrix_key)[0]


def main(argv=None) -> int:
    """Explicit standalone diagnostic; existing fitting paths are untouched."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('input', 'npz', 'assumptions', 'output'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--draws', type=int, default=10000)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--identity-subspace', choices=('all', 'head'), default='all')
    args = parser.parse_args(argv)
    try:
        from . import __version__
        from .backend import GNMBackend
        from .export import atomic_text
        from .identity import active_components
        from .io_csv import read_marker_csv
        from .tissue import _json
        from .validation import sha256_file, validate_outputs, has_documented_tissue_source
        import platform
        paths = [args.input, args.npz, args.assumptions]
        validate_outputs(paths, [args.output])
        hashes = {p: sha256_file(p) for p in paths}
        assumptions = _json(Path(args.assumptions).read_text(encoding='utf-8-sig'))
        required = {'schema_version', 'model_sha256', 'units', 'coordinate_space', 'source', 'labels',
                    'pose', 'observation_covariance', 'prior_mean', 'prior_covariance'}
        if not isinstance(assumptions, dict) or set(assumptions) != required:
            raise ValueError('Assumptions must contain exactly the documented schema fields')
        if (type(assumptions['schema_version']) is not int or assumptions['schema_version'] != 1
                or assumptions['units'] != 'mm' or assumptions['coordinate_space'] != 'world'):
            raise ValueError('Expected assumptions schema_version 1, units mm and coordinate_space world')
        if assumptions['model_sha256'] != hashes[args.npz]:
            raise ValueError('Assumptions/model SHA-256 mismatch')
        if not has_documented_tissue_source(assumptions['source']):
            raise ValueError('A documented source for the assumptions is required')
        backend = GNMBackend(args.npz)
        model = backend.load()
        targets, skipped, metadata = read_marker_csv(args.input, backend.index_to_label, backend.landmark_vertex_map)
        if metadata.get('model_sha256') and metadata['model_sha256'] != hashes[args.npz]:
            raise ValueError('Marker/model SHA-256 mismatch')
        labels = [t.label for t in targets]
        if assumptions['labels'] != labels:
            raise ValueError('Assumption labels must match included CSV labels in exact order')
        pose = assumptions['pose']
        if not isinstance(pose, dict) or set(pose) != {'scale', 'rotation', 'translation_mm'}:
            raise ValueError('pose requires scale, rotation, translation_mm')
        active = active_components(model, args.identity_subspace)
        a, y, j = fixed_pose_design(model, [t.vertex for t in targets], [t.xyz for t in targets],
                                   active=active, **pose)
        c = _covariance_config(assumptions['observation_covariance'], len(y), 'sd_mm', 'matrix_mm2')
        p = _covariance_config(assumptions['prior_covariance'], a.shape[1], 'sd', 'matrix')
        result = linear_gaussian(a, y, c, assumptions['prior_mean'], p)
        mc = covariance_crosscheck(result, args.draws, args.seed)
        statistics = {}
        for name, covariance in (('posterior', result.posterior_covariance), ('estimator', result.estimator_covariance)):
            propagated = propagate_covariance(j, covariance)
            empirical = propagate_covariance(j, mc[name]['covariance'])
            statistics[name] = dict(coefficient_covariance=covariance.tolist(),
                **{key: value.tolist() for key, value in propagated.items()}, monte_carlo=mc[name],
                relative_vertex_sd_error=_relative_error(empirical['sd_xyz_mm'], propagated['sd_xyz_mm']))
        warnings = ['Conditional fixed-pose linear Gaussian diagnostic, not calibrated facial accuracy.',
                    'No pose uncertainty, Huber IRLS, clipping, LOO selection, dense constraints or TPS.',
                    'CSV confidence weights are recorded but not interpreted as measurement covariance.',
                    'Posterior covariance and repeated-data estimator covariance are different quantities.']
        if not metadata.get('model_sha256'):
            warnings.append('CSV model hash missing; correspondence compatibility not verified.')
        warnings.extend(metadata.get('landmark_audit', {}).get('warnings', []))
        report = dict(schema_version=1, method='conditional_linear_gaussian', calibration_status='uncalibrated',
            units='world_mm', assumptions=assumptions, input_hashes=hashes, marker_metadata=metadata,
            skipped=skipped, labels=labels, vertex_indices=[t.vertex for t in targets],
            csv_weights=[t.weight for t in targets], identity_subspace=args.identity_subspace,
            active_components=list(range(model.identity_dim)) if active is None else active.tolist(),
            mean_coefficients=result.mean.tolist(), augmented_condition_number=result.condition_number,
            draws=args.draws, seed=args.seed, rng='PCG64', statistics=statistics, warnings=warnings,
            implementation=dict(cranio=__version__, numpy=np.__version__, python=platform.python_version(),
                                source_sha256=sha256_file(__file__)))
        if any(sha256_file(p) != digest for p, digest in hashes.items()):
            raise ValueError('An input changed during analysis; refusing to publish')
        validate_outputs(paths, [args.output])
        with atomic_text(args.output) as stream:
            json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write('\n')
        print(args.output)
        return 0
    except (ValueError, OSError, OverflowError, TypeError, np.linalg.LinAlgError) as exc:
        print(f'Linear covariance diagnostic unavailable: {exc}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

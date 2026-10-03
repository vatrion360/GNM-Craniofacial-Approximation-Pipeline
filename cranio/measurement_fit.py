"""Reviewed skin-distance rows and scale update for the shared identity solver."""
import numpy as np
from .validation import finite_array


def prepare(controls, vertex_count, marker_weight_sum, strength):
    """Per-pair mass = strength * sum(marker weights) / N * influence / sigma².

    Sigma is an operator-supplied tolerance in world mm, not calibrated model
    uncertainty. N does not increase the adaptive-lambda marker count.
    """
    if not np.isfinite(strength) or strength < 0:
        raise ValueError('measurement_weight must be finite and nonnegative')
    pairs, targets, sigmas, influences = [], [], [], []
    for row in controls or []:
        ids = np.asarray(row['vertices'])
        if (ids.shape != (2,) or ids.dtype.kind not in 'iu' or np.any(ids < 0)
                or np.any(ids >= vertex_count) or ids[0] == ids[1]):
            raise ValueError('Invalid skin-distance vertices')
        pair = tuple(sorted(ids.tolist()))
        if pair in pairs:
            raise ValueError('Duplicate skin-distance pair')
        pairs.append(pair)
        values = finite_array([row['target_mm'], row['sigma_mm'], row['influence']], 'skin control', (3,))
        if np.any(values <= 0):
            raise ValueError('Skin target, tolerance and influence must be positive')
        targets.append(values[0]); sigmas.append(values[1]); influences.append(values[2])
    sigmas = np.asarray(sigmas)
    mass = strength * marker_weight_sum / max(1, len(pairs)) * np.asarray(influences) / sigmas**2
    finite_array(mass, 'skin-distance weights')
    return np.asarray(pairs, dtype=np.int64).reshape(-1, 2), np.asarray(targets), sigmas, mass


def differences(c, mu, basis, pairs):
    mean = mu[pairs[:, 0]]-mu[pairs[:, 1]]
    delta_basis = basis[:, pairs[:, 0], :]-basis[:, pairs[:, 1], :]
    delta = mean+np.einsum('i,ipk->pk', c, delta_basis)
    distance = np.linalg.norm(delta, axis=1)
    if np.any(distance < 1e-9):
        raise ValueError('Collapsed skin-distance endpoints; review correspondences')
    return mean, delta_basis, delta/distance[:, None], distance


def robust_weights(distance_model, scale, targets, sigmas, mass):
    residual = np.abs(scale*distance_model-targets)
    return mass*np.minimum(1., 2.5*sigmas/np.maximum(residual, 1e-12))


def linear_rows(c, mu, basis, prepared, scale, weights):
    """Gauss-Newton rows in model mm at fixed scale, rotation invariant."""
    pairs, targets, _, _ = prepared
    mean, delta_basis, unit, _ = differences(c, mu, basis, pairs)
    jacobian = np.einsum('ipk,pk->pi', delta_basis, unit)
    rhs = targets/scale-np.einsum('pk,pk->p', unit, mean)
    return jacobian*np.sqrt(weights)[:, None], rhs*np.sqrt(weights)


def update_scale(model_lm, targets_xyz, weights, rotation, distance_model, targets, pair_weights):
    """Closed-form joint marker/distance scale for a fixed proper rotation.

    Distances are invariant to rotation/translation, so marker Umeyama still
    supplies R. The scale must include pair rows on every pose update, including
    the final one, otherwise a final marker-only pose would undo the controls.
    """
    normalized = weights/weights.sum()
    mx = normalized @ model_lm
    my = normalized @ targets_xyz
    x, y = model_lm-mx, targets_xyz-my
    numerator = np.sum(weights[:, None]*(x @ rotation.T)*y)+np.dot(pair_weights*distance_model, targets)
    denominator = np.sum(weights[:, None]*x*x)+np.dot(pair_weights, distance_model**2)
    scale = float(numerator/denominator)
    if not np.isfinite(scale) or scale <= 1e-12:
        raise ValueError('Skin controls produced a degenerate scale')
    return scale, my-scale*(rotation @ mx)

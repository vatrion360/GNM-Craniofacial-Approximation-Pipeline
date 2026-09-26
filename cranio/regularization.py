"""Shared count-based ridge heuristic; not an empirically calibrated prior."""
import hashlib
import math

import numpy as np

REFERENCE_MARKERS = 48


def adaptive_lambda(n_used, base=1.0, minimum=0.3, maximum=1000.0):
    """Count only distinct, placed, included anatomical constraints.

    A fixed reference keeps the same fit independent of the selected UI set.
    Dense samples are not anatomical landmarks. Zero landmarks uses maximum
    regularization; it never masquerades as a complete set.
    """
    if int(n_used) != n_used or n_used < 0:
        raise ValueError('Landmark count must be a nonnegative integer')
    if not all(math.isfinite(x) and x > 0 for x in (base, minimum, maximum)):
        raise ValueError('Lambda settings must be finite and positive')
    if minimum > maximum:
        raise ValueError('Lambda minimum must not exceed maximum')
    return float(maximum if n_used == 0 else
                 min(max(base * REFERENCE_MARKERS / n_used, minimum), maximum))


def tuning_key(vertices, targets, weights, model_token):
    """Invalidate conditional-LOO cache when any actual constraint changes."""
    digest = hashlib.sha256(str(model_token).encode())
    for values, dtype in ((vertices, '<i8'), (targets, '<f8'), (weights, '<f8')):
        array = np.ascontiguousarray(values, dtype=dtype)
        digest.update(str(array.shape).encode())
        digest.update(array.tobytes())
    return digest.hexdigest()

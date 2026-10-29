"""Explicit fitting subspaces, resolved from model metadata rather than counts."""
import numpy as np


def active_components(model, subspace='all'):
    """Return head indices, or None for the unchanged complete-basis solve.

    Head mode requires the reviewed GNM v3 naming contract. Names, not arbitrary
    column position, identify components. Other/unnamed models remain usable in
    all mode; never assume that their first 170 components represent a head.
    """
    if subspace == 'all':
        return None
    if subspace != 'head':
        raise ValueError('identity_subspace must be all or head')
    names = getattr(model, 'identity_names', None)
    expected = ([f'head_{i:03d}' for i in range(170)] +
                [f'eyes_{i:03d}' for i in range(3)] +
                [f'teeth_{i:03d}' for i in range(80)])
    if (names is None or len(names) != model.identity_dim or len(names) != 253
            or set(names) != set(expected)):
        raise ValueError('Head-only fitting requires verified GNM v3 identity_names (170 head, 3 eyes, 80 teeth)')
    return np.array([i for i, name in enumerate(names) if name.startswith('head_')], dtype=np.int64)


def validate_active_components(indices, dimension):
    indices = np.asarray(indices)
    if (indices.ndim != 1 or not len(indices) or indices.dtype.kind not in 'iu'
            or np.any(indices < 0) or np.any(indices >= dimension)
            or len(np.unique(indices)) != len(indices)):
        raise ValueError('active_components must be distinct in-range integer component indices')
    return indices

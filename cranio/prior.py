"""Safe loading of optional experimental identity priors, without pickle."""
import numpy as np
from .validation import finite_array, sha256_file


def validate_justification(reason, *, required=False):
    """Validate operator intent without supplying a scientific rationale."""
    if reason is None:
        if required:
            raise ValueError('Prior comparison requires a documented prior justification')
        return
    if (not isinstance(reason, str) or not reason.strip()
            or reason.strip().casefold() in {'todo', 'unknown', 'unspecified', 'none', 'null'}
            or 'todo(verify-source)' in reason.casefold()):
        raise ValueError('prior-justification must document the operator rationale, not a placeholder')


def load_prior(path, identity_dim=253):
    with np.load(path, allow_pickle=False) as archive:
        if not {'mean', 'scale'} <= set(archive.files):
            raise ValueError('Prior archive requires mean and scale arrays')
        mean = finite_array(archive['mean'], 'prior mean', (identity_dim,)).copy()
        scale = finite_array(archive['scale'], 'prior scale', (identity_dim,)).copy()
        if np.any(scale <= 0):
            raise ValueError('Prior scale must be positive')
        count = int(archive['n_samples']) if 'n_samples' in archive else None
    return dict(mean=mean, scale=scale, sha256=sha256_file(path), path=str(path), n_samples=count)

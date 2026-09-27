"""NumPy adapter around the same identity objective used by the CLI."""
import numpy as np
from .fit_contract import DEFAULT_MAX_ITER, DEFAULT_TOL, normalized_dense_weights
from .geometry import dense_correspondences
from .optimize import fit_identity, LossConfig


def fit_preview(model, snapshot, regularization, settings, dense=None, prior=None):
    """Fit a snapshot; fewer than 3 markers use an explicitly markerless regime."""
    n = len(snapshot['labels'])
    idx, targets, weights = snapshot['verts'], snapshot['targets'], snapshot['weights']
    if n < 3:
        if dense is None:
            raise ValueError('Need three noncollinear markers or prepared bone surfaces')
        pose = snapshot.get('m_world', np.eye(4))
        initial = snapshot.get('initial_coefficients', np.zeros(model.identity_dim))
        world = model.generate(initial) @ pose[:3, :3].T + pose[:3, 3]
        di, dt, _, _ = dense_correspondences(world, dense)
        mask, dw = normalized_dense_weights(weights, dense['last_relative_weights'], dense['weight_ratio'])
        di, dt = di[mask], dt[mask]
        if len(di) < 10:
            raise ValueError('Too few valid dense surface constraints')
        idx, targets, weights = np.concatenate([idx, di]), np.concatenate([targets, dt]), np.concatenate([weights, dw])
        dense = None
    options = {}
    if prior is not None:
        options = dict(prior_mean=prior['mean'], prior_scale=prior['scale'], prior_weight=settings.get('prior_weight', 1.))
    return fit_identity(model.mu, model.basis, idx, targets, weights, lam=regularization,
        max_iter=int(settings.get('max_iter', DEFAULT_MAX_ITER)), tol=float(settings.get('tol', DEFAULT_TOL)),
        dense=dense, loss_cfg=LossConfig(clip_sigma=float(settings.get('clip_sigma', 3.))),
        pose_rows=n if n >= 3 else None, huber_rows=n, **options)

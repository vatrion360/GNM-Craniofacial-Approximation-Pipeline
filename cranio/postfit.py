"""Bounded presentation of a frozen fit using the reviewed GNM v3 asset.

This is not a fitting stage. Native additive bases and eye skinning are applied
to the final neutral surface, including its non-statistical residual. Head
identity and head/neck pose are not exposed. Geometry bounds are not anatomy.
"""
from dataclasses import dataclass
import numpy as np
from .backend.gnm_backend import OFFICIAL_V3_SHA256
from .validation import sha256_file


@dataclass
class PresentationAsset:
    mu: np.ndarray
    identity: np.ndarray
    expression: np.ndarray
    identity_names: list
    expression_names: list
    triangles: np.ndarray
    uvs: np.ndarray
    groups: np.ndarray
    group_names: list
    joints: np.ndarray
    joint_basis: np.ndarray
    joint_regressor: np.ndarray
    weights: np.ndarray
    parents: np.ndarray
    joint_names: list

    def mask(self, *names):
        return np.max(self.groups[[self.group_names.index(n) for n in names]], axis=0) > .5


def load_asset(path):
    """Load trusted numeric arrays without pickle, in canonical millimetres."""
    if sha256_file(path) != OFFICIAL_V3_SHA256:
        raise ValueError('Post-fit controls require the reviewed GNM Head v3 asset')
    with np.load(path, allow_pickle=False) as z:
        # This asset's corrective regressor is exactly zero; fail closed if changed.
        if np.any(z['pose_correctives_regressor']):
            raise ValueError('Unsupported nonzero pose correctives')
        asset = PresentationAsset(
            z['template_vertex_positions'].astype(float)*1000,
            z['vertex_identity_basis'].astype(float)*1000,
            z['expression_basis'].astype(float)*1000,
            z['identity_names'].tolist(), z['expression_names'].tolist(),
            z['triangles'].copy(), z['triangle_uvs'].copy(), z['vertex_groups'].copy(),
            z['vertex_group_names'].tolist(), z['template_joint_positions'].astype(float)*1000,
            z['joint_identity_basis'].astype(float)*1000, z['joint_regressor'].astype(float),
            z['skinning_weights'].astype(float), z['joint_parent_indices'].copy(), z['joint_names'].tolist())
    return asset


def check_topology(vertices, triangles, asset):
    """UV seams require exact face corners and vertex order, not just counts."""
    if np.asarray(vertices).shape != asset.mu.shape or not np.isfinite(vertices).all():
        raise ValueError('Expected finite vertices with the original GNM vertex order')
    if not np.array_equal(triangles, asset.triangles):
        raise ValueError('Topology/order differs from GNM; remeshed, decimated or reordered surfaces are unsupported')


def similarity_matrix(matrix):
    m = np.asarray(matrix, dtype=float)
    if m.shape != (4, 4) or not np.isfinite(m).all() or not np.allclose(m[3], [0, 0, 0, 1]):
        raise ValueError('Invalid model-to-world transform')
    scale = np.linalg.norm(m[:3, :3], axis=0).mean()
    if scale <= 1e-9 or np.linalg.det(m[:3, :3]) <= 0 or not np.allclose(
            m[:3, :3].T @ m[:3, :3], np.eye(3)*scale**2, rtol=1e-5, atol=1e-8):
        raise ValueError('Post-fit controls require a positive similarity transform; no shear or reflection')
    return m


def rotation(vector):
    """Rodrigues rotation for a three-component axis-angle vector in radians."""
    angle = np.linalg.norm(vector)
    if angle < 1e-14:
        return np.eye(3)
    x, y, z = vector/angle
    k = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) + np.sin(angle)*k + (1-np.cos(angle))*(k @ k)


def pose_eyes(vertices, joints, angles, asset):
    """GNM hierarchical LBS with head/neck fixed and eye rotations only."""
    transforms = []
    for i, parent in enumerate(asset.parents):
        local = np.eye(4)
        local[:3, :3] = rotation(angles[i])
        local[:3, 3] = joints[i] if i == 0 else joints[i]-joints[parent]
        transforms.append(local if i == 0 else transforms[parent] @ local)
    transforms = np.asarray(transforms)
    rs = transforms[:, :3, :3]
    ts = transforms[:, :3, 3] - np.einsum('jik,jk->ji', rs, joints)
    return (np.einsum('jv,jik,vk->vi', asset.weights, rs, vertices)
            + asset.weights.T @ ts)


def evaluate(asset, neutral_world, model_to_world, fitted_identity, expression,
             identity_delta, eye_angles, max_displacement_mm=3.):
    """Return bounded world-mm coordinates plus displacement diagnostics.

    All offsets are relative to a frozen neutral, never to the previous preview.
    Teeth deltas are masked to teeth/gums to suppress the asset's tiny leakage
    outside that component. Eye pivots follow the frozen fit's residual through
    the supplied joint regressor. A single attenuation factor bounds the combined
    displacement, avoiding independent clipping of individual controls.
    """
    neutral = np.asarray(neutral_world, dtype=float)
    check_topology(neutral, asset.triangles, asset)
    matrix = similarity_matrix(model_to_world)
    beta, expr, delta, angles = [np.asarray(a, dtype=float) for a in
        (fitted_identity, expression, identity_delta, eye_angles)]
    for a, shape in [(beta, (len(asset.identity_names),)), (delta, (len(asset.identity_names),)),
                     (expr, (len(asset.expression_names),)), (angles, (len(asset.parents), 3))]:
        if a.shape != shape or not np.isfinite(a).all():
            raise ValueError('Invalid presentation parameter shape or non-finite value')
    if not np.isfinite(max_displacement_mm) or not 0 <= max_displacement_mm <= 20:
        raise ValueError('Displacement limit must be in [0, 20] mm')
    editable = np.array([n.startswith(('teeth_', 'eyes_')) for n in asset.identity_names])
    if np.any(delta[~editable]) or np.any(angles[:2]):
        raise ValueError('Head identity and head/neck pose are locked after fitting')
    if np.any(abs(expr) > 3) or np.any(abs(delta) > 3) or np.any(abs(angles) > np.pi/6 + 1e-8):
        raise ValueError('Presentation controls exceed the engineering limits')
    # Native neutral is returned exactly; zero cap is also an exact neutral reset.
    if max_displacement_mm == 0 or not (np.any(expr) or np.any(delta) or np.any(angles)):
        return neutral.copy(), dict(requested_max_mm=0., applied_max_mm=0., attenuation=1.)
    canonical = (neutral-matrix[:3, 3]) @ np.linalg.inv(matrix[:3, :3]).T
    active = np.flatnonzero(expr)
    offset = np.einsum('i,ivk->vk', expr[active], asset.expression[active]) if len(active) else np.zeros_like(canonical)
    for prefix, mask in [('teeth_', asset.mask('teeth', 'gums')), ('eyes_', asset.mask('eyes'))]:
        ids = [i for i, n in enumerate(asset.identity_names) if n.startswith(prefix) and delta[i] != 0]
        if ids:
            offset[mask] += np.einsum('i,ivk->vk', delta[ids], asset.identity[ids])[mask]
    posed = canonical + offset
    if np.any(angles):
        statistical = asset.mu + np.einsum('i,ivk->vk', beta, asset.identity)
        joints = (asset.joints + np.einsum('i,ijk->jk', beta+delta, asset.joint_basis)
                  + asset.joint_regressor @ (canonical-statistical))
        posed = pose_eyes(posed, joints, angles, asset)
    displacement = (posed-canonical) @ matrix[:3, :3].T
    requested = float(np.linalg.norm(displacement, axis=1).max())
    alpha = min(1., max_displacement_mm/requested) if requested else 1.
    result = neutral + alpha*displacement
    if not np.isfinite(result).all():
        raise ValueError('Non-finite presentation geometry')
    return result, dict(requested_max_mm=requested, applied_max_mm=requested*alpha, attenuation=alpha)

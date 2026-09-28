"""Evaluated Blender surfaces. Called only on Blender's main thread."""
import hashlib
import numpy as np


def generated_surface(obj):
    """Generated faces/pegs/patches cannot be registered as observed bone."""
    return (any(obj.get(key) for key in ('gnm_generated', 'gnm_report', 'gnm_region_patch', 'gnm_reconstructed_via_mirroring'))
            or obj.name.startswith(('GNM_HEAD', 'GNM_Offline_', 'GNM_BAT_', 'GNM_LM_', 'GNM_GERASIMOV')))


def source_geometry(obj, depsgraph, flip_normals=False):
    """Return evaluated world-mm triangles, including modifiers and determinant parity."""
    if obj.type != 'MESH' or generated_surface(obj) or obj.mode != 'OBJECT':
        raise ValueError('Use preserved bone meshes in Object Mode')
    return evaluated_geometry(obj, depsgraph, flip_normals)[:4]


def evaluated_geometry(obj, depsgraph, flip_normals=False):
    """World surface plus evaluated polygon IDs, also usable on inferred patches.

    This does not authorize an object as observed bone; source_geometry retains
    that guard. Callers inspecting inferred surfaces must check their registry.
    """
    if obj.type != 'MESH' or obj.mode != 'OBJECT':
        raise ValueError('Use a mesh in Object Mode')
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        vertices = np.empty(len(mesh.vertices)*3, dtype=float)
        mesh.vertices.foreach_get('co', vertices)
        transform = np.asarray(evaluated.matrix_world, dtype=float)
        points = vertices.reshape(-1, 3) @ transform[:3, :3].T + transform[:3, 3]
        mesh.calc_loop_triangles()
        triangles = np.empty(len(mesh.loop_triangles)*3, dtype=np.int32)
        mesh.loop_triangles.foreach_get('vertices', triangles)
        triangles = triangles.reshape(-1, 3)
        polygons = np.empty(len(mesh.loop_triangles), dtype=np.int32)
        mesh.loop_triangles.foreach_get('polygon_index', polygons)
        if (np.linalg.det(transform[:3, :3]) < 0) != bool(flip_normals):
            triangles = triangles[:, ::-1].copy()
        if not len(points) or not len(triangles) or not np.isfinite(points).all():
            raise ValueError('Bone source has empty or invalid geometry')
        digest = hashlib.sha256(points.astype('<f8').tobytes()+triangles.astype('<i8').tobytes()).hexdigest()
        return points, triangles, digest, transform.tolist(), polygons
    finally:
        evaluated.to_mesh_clear()


def sample_surface(points, triangles, count, rng):
    """Area-weighted deterministic sampling, avoiding vertex density bias."""
    tri = points[triangles]
    normals = np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0])
    area2 = np.linalg.norm(normals, axis=1)
    if not np.isfinite(area2).all() or area2.sum() <= 0:
        raise ValueError('Bone source has no finite surface area')
    chosen = rng.choice(len(tri), count, p=area2/area2.sum())
    u, v = np.sqrt(rng.random(count)), rng.random(count)
    bary = np.stack([1-u, u*(1-v), u*v], axis=1)
    return np.einsum('ni,nij->nj', bary, tri[chosen]), normals[chosen]/area2[chosen, None]

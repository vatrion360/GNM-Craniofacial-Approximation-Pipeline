"""Optional Blender-only fragment geometry. Original objects are never edited."""
import hashlib

import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import numpy as np

from .restoration import donor_half


def check_source(obj):
    if obj is None or obj.type != 'MESH' or not len(obj.data.polygons):
        raise ValueError('Choose a mesh with faces for each region')
    if obj.get('gnm_region_patch'):
        raise ValueError('A generated patch cannot be used as preserved donor bone')
    if obj.mode != 'OBJECT':
        raise ValueError('Return to Object Mode before generating restoration patches')
    if any(mod.show_viewport for mod in obj.modifiers):
        raise ValueError(f'{obj.name}: apply visible modifiers on a working copy before defining regions')
    if abs(obj.matrix_world.to_3x3().determinant()) < 1e-12:
        raise ValueError(f'{obj.name}: singular object transform')


def protected_surface(objects):
    vertices, faces = [], []
    for obj in objects:
        check_source(obj)
        offset = len(vertices)
        vertices.extend(obj.matrix_world @ v.co for v in obj.data.vertices)
        faces.extend(tuple(offset + i for i in p.vertices) for p in obj.data.polygons)
    return BVHTree.FromPolygons(vertices, faces, all_triangles=False) if faces else None


def object_plane(obj):
    matrix = obj.matrix_world
    if abs(matrix.to_3x3().determinant()) < 1e-12:
        raise ValueError('Reference plane object has a singular transform')
    normal = matrix.to_3x3().inverted().transposed() @ Vector((0, 0, 1))
    return matrix.translation.copy(), normal.normalized(), 0.0


def build_patch(source, group_name, plane, protected, tolerance=0.1):
    """Mirror only the selected one-sided donor. Suppress fully covered faces.

    Nearest-surface filtering is deliberately conservative, not a Boolean union
    or an automatic watertight reconstruction. Partial intersections are counted
    and left for specialist review; preserved mesh is untouched.
    """
    check_source(source)
    centre, normal, rms = plane
    centre, normal = Vector(centre), Vector(normal).normalized()
    keep_indices = None
    if group_name:
        group = source.vertex_groups.get(group_name)
        if group is None:
            raise ValueError(f'{source.name}: vertex group {group_name!r} does not exist')
        keep_indices = {v.index for v in source.data.vertices
                        if any(g.group == group.index and g.weight > 0.5 for g in v.groups)}
    bm = bmesh.new()
    try:
        bm.from_mesh(source.data)
        bm.verts.ensure_lookup_table()
        if keep_indices is not None:
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in keep_indices], context='VERTS')
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='VERTS')
        if not bm.faces:
            raise ValueError(f'{source.name}: the donor group contains no complete faces')
        bmesh.ops.transform(bm, matrix=source.matrix_world, verts=list(bm.verts))
        if source.matrix_world.to_3x3().determinant() < 0:
            bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
        points = np.array([v.co[:] for v in bm.verts], dtype=np.float64)
        side = donor_half(points, centre, normal, tolerance)
        donor_digest = hashlib.sha256(points.tobytes())
        for face in bm.faces:
            donor_digest.update(np.array([v.index for v in face.verts], dtype='<i8').tobytes())
        # Trim only a numerical sliver at the seam, in this temporary mesh.
        bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
                              plane_co=centre, plane_no=normal * side,
                              clear_inner=True, clear_outer=False, dist=1e-6)
        for vertex in bm.verts:
            vertex.co -= 2 * (vertex.co - centre).dot(normal) * normal
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
        covered, partial = [], 0
        if protected is not None:
            for face in bm.faces:
                samples = [v.co for v in face.verts] + [face.calc_center_median()]
                hits = []
                for point in samples:
                    _, _, _, distance = protected.find_nearest(point)
                    hits.append(distance is not None and distance <= tolerance)
                if all(hits):
                    covered.append(face)
                elif any(hits):
                    partial += 1
        removed = len(covered)
        if covered:
            bmesh.ops.delete(bm, geom=covered, context='FACES')
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='VERTS')
        bm.verts.index_update()
        bm.normal_update()
        vertices = [v.co[:] for v in bm.verts]
        faces = [tuple(v.index for v in f.verts) for f in bm.faces]
        return vertices, faces, {
            'source': source.name, 'vertex_group': group_name,
            'donor_geometry_sha256_at_generation': donor_digest.hexdigest(),
            'plane_origin_mm': list(centre), 'plane_normal': list(normal),
            'plane_rms_mm': rms, 'geometric_donor_sign': side,
            'overlap_tolerance_mm': tolerance, 'covered_faces_removed': removed,
            'partial_contact_faces': partial, 'generated_faces': len(faces),
            'method': 'selected-region reflection; separate inferred patch; originals preserved',
        }
    finally:
        bm.free()

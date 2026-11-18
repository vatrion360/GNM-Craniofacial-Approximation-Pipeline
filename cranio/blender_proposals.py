"""Main-thread adapter for optional, read-only-on-case bone-site proposals."""
import hashlib
import json

import bpy
import numpy as np
from bpy.props import BoolProperty, FloatProperty, StringProperty
from mathutils.bvhtree import BVHTree

from . import blender_atlas, blender_sources, landmark_proposals

PATCH = 'ATLAS_PATCH:'
_api = None


def _groups(obj, names):
    wanted = {g.index: g.name for g in obj.vertex_groups if g.name in names}
    result = {name: [] for name in wanted.values()}
    for v in obj.data.vertices:
        for g in v.groups:
            if g.group in wanted and g.weight > 0:
                result[wanted[g.group]].append(v.index)
    return result


def _digest(*arrays):
    digest = hashlib.sha256()
    for array in arrays:
        digest.update(array.tobytes())
    return digest.hexdigest()


def _patch(points, triangles, group):
    mask = np.zeros(len(points), dtype=bool)
    mask[group] = True
    ids = np.flatnonzero(mask[triangles].all(axis=1))
    tri = triangles[ids]
    if not len(tri):
        raise ValueError('Both patch groups must contain complete triangles')
    faces = points[tri]
    area = np.linalg.norm(np.cross(faces[:,1]-faces[:,0], faces[:,2]-faces[:,0]), axis=1)
    if not np.isfinite(area).all() or np.any(area <= 0):
        raise ValueError('Patch contains degenerate triangles; review the selected surface')
    # Verify a single edge-connected sheet; sharing only a corner does not join fragments.
    edges = np.sort(np.concatenate((tri[:,[0,1]], tri[:,[1,2]], tri[:,[2,0]])), axis=1)
    order = np.lexsort((edges[:,1], edges[:,0]))
    edges = edges[order]
    equal = (edges[1:] == edges[:-1]).all(axis=1)
    if np.any(equal[1:] & equal[:-1]):
        raise ValueError('Nonmanifold patch; select one observed sheet')
    neighbours = [[] for _ in tri]
    for i in np.flatnonzero(equal):
        x, y = int(order[i] % len(tri)), int(order[i+1] % len(tri))
        neighbours[x].append(y)
        neighbours[y].append(x)
    seen = {0}
    stack = [0]
    while stack:
        for j in neighbours[stack.pop()]:
            if j not in seen:
                seen.add(j)
                stack.append(j)
    if len(seen) != len(tri):
        raise ValueError('Disconnected patch: register fragments separately')
    boundary = {tuple(edge) for edge in edges[~(np.r_[False,equal] | np.r_[equal,False])]}
    return ids, tri, area, boundary


def _tree(points, triangles):
    return BVHTree.FromPolygons(points.tolist(), triangles.tolist(), all_triangles=True)


def bvh_precision(points):
    return 8*np.finfo(np.float32).eps*max(1., float(np.max(np.abs(points))))


def open_edge(point, w, tri, boundary):
    tol = bvh_precision(w[tri])
    for i in range(3):
        j, k = sorted((tri[i], tri[(i+1)%3]))
        if (j,k) in boundary:
            edge, delta = w[k]-w[j], np.array(point)-w[j]
            if np.linalg.norm(delta-np.clip((delta@edge)/(edge@edge),0.,1.)*edge) <= tol:
                return True
    return False


def snapshot(context, *, review_inputs=False):
    scene = context.scene
    if not _api._is_mm_scene(scene):
        raise ValueError('Expected metric scene scale 0.001 (one world coordinate per mm)')
    _api._core_module('blender_articulation').require_review(scene, deep=True)
    limits = dict(gap_mm=scene.gnm_proposal_gap, anchor_radius_mm=scene.gnm_proposal_radius,
                  anchor_limit_mm=scene.gnm_proposal_anchor_limit)
    if min(limits.values()) <= 0:
        raise ValueError('Set all three positive review limits in mm')
    key = scene.gnm_proposal_patch.strip()
    if not key:
        raise ValueError('Enter the shared patch name')
    key = PATCH+key
    ref, source = blender_atlas.reference_object(scene)
    obj = context.active_object
    rows = [row for row in _api._bone_sources(scene) if row.source_object == obj]
    if len(rows) != 1 or not rows[0].uid or sum(r.uid == rows[0].uid for r in scene.gnm_bone_sources) != 1:
        raise ValueError('Activate one uniquely registered, enabled observed bone mesh')
    if obj.modifiers or obj.data.shape_keys or obj.data == ref.data:
        raise ValueError('Use independent, static target and reference mesh data')
    markers = {m.label: m for m in scene.gnm_markers}
    if len(markers) != len(scene.gnm_markers):
        raise ValueError('Duplicate marker labels; review the case list')
    prefix = blender_atlas.PREFIX
    rg = _groups(ref, {key} | {prefix+k for k in markers})
    tg = _groups(obj, {key})
    if key not in rg or key not in tg:
        raise ValueError('Assign the same named ATLAS_PATCH group on both bone meshes')
    v = np.empty((len(ref.data.vertices),3), np.float32)
    ref.data.vertices.foreach_get('co', v.ravel())
    ref.data.calc_loop_triangles()
    t = np.empty((len(ref.data.loop_triangles),3), np.int32)
    ref.data.loop_triangles.foreach_get('vertices', t.ravel())
    v = v.astype(float)
    if not np.isfinite(v).all():
        raise ValueError('Invalid atlas coordinates')
    _, tr, area, _ = _patch(v, t, rg[key])
    graph = context.evaluated_depsgraph_get()
    w, f, digest, _, polygons = blender_sources.evaluated_geometry(obj, graph, rows[0].flip_normals)
    ids, tf, _, boundary = _patch(w, f, tg[key])
    full = _tree(w, f)
    tree = _tree(w, tf)
    members, patch_ids = set(tr.ravel()), set(ids)
    anchors, sites, omitted, vids = {}, {}, {}, {}
    for label, m in sorted(markers.items()):
        indices = rg.get(prefix+label, [])
        if not indices or not members.intersection(indices):
            omitted[label] = 'not annotated in selected reference patch'
            continue
        if len(indices) != 1 or indices[0] in vids.values():
            raise ValueError('Ambiguous or duplicate reviewed reference vertex: '+label)
        vids[label] = indices[0]
        bone = m.bone_empty
        if bone is None:
            if m.target_empty is None:
                sites[label] = v[indices[0]]
            else:
                omitted[label] = 'incomplete existing marker; review manually'
            continue
        if 'gnm_bone_proposal_review' in bone:
            omitted[label] = 'proposal-assisted placement; not an independent registration anchor'
            continue
        if (m.bone_status != 'observed' or bone is None or scene.objects.get(bone.name) != bone
                or bone.get('gnm_bone_source_id') != rows[0].uid):
            omitted[label] = 'placed marker is not observed on selected source'
            continue
        if bone.get('gnm_source_sha256_at_placement') != digest:
            raise ValueError('Stale or missing observed-bone geometry signature: '+label)
        xyz = np.array(bone.evaluated_get(graph).matrix_world.translation)
        on_bone, _, ix, distance = full.find_nearest(xyz)
        if ix not in patch_ids:
            # At a shared edge/vertex BVH traversal may return the neighboring
            # excluded triangle first. Accept only the very same closest point.
            on_patch = tree.find_nearest(xyz)[0]
            eps = 8*np.finfo(np.float32).eps*max(1., float(np.max(np.abs(on_bone))))
            if np.linalg.norm(np.asarray(on_bone)-on_patch) > eps:
                omitted[label] = 'placed anchor outside observed patch'
                continue
        if distance > limits['gap_mm']:
            raise ValueError('Observed anchor too far from bone: '+label)
        anchors[label] = xyz.tolist()
    if len(anchors) < 4:
        raise ValueError('Need four or more paired, noncoplanar observed anchors in this fragment')
    binding = dict(schema='gnm.bone-proposals.v1', patch=key, atlas_source=source,
        reference_name=ref.name, reference_geometry_sha256=_digest(v.astype('<f8'),t.astype('<i8')),
        reference_patch_sha256=_digest(tr.astype('<i8')), reviewed_vertex_ids=vids,
        target_name=obj.name, target_id=rows[0].uid, target_geometry_sha256=digest,
        target_patch_sha256=_digest(tf.astype('<i8')), anchors=anchors,
        limits_mm=dict(surface_gap=limits['gap_mm'], anchor_radius=limits['anchor_radius_mm'],
                       similarity_anchor_residual=limits['anchor_limit_mm']))
    if review_inputs:
        return binding, (w, tf, tree, full, boundary, polygons[ids]), sites
    # Deterministic approximately area-stratified triangle centroids; computational budget only.
    cumulative = np.cumsum(area)
    count = min(256, len(tr))
    sampled = np.searchsorted(cumulative, (np.arange(count)+.5)/count*cumulative[-1])
    samples = v[tr[sampled]].mean(axis=1)
    def nearest(points):
        return np.array([tuple(tree.find_nearest(p)[0]) for p in points])
    result = landmark_proposals.propose([v[vids[k]] for k in anchors], list(anchors.values()),
        samples, sites, nearest, **limits)
    for label, row in result['sites'].items():
        if row['world_mm'] is None:
            continue
        point, _, face, _ = tree.find_nearest(row['world_mm'])
        if open_edge(point, w, tf[face], boundary):
            row.update(status='unsupported', world_mm=None, support_score=0., reason='on open patch boundary')
    for label, reason in omitted.items():
        result['sites'][label] = dict(status='not_assessed', reason=reason, world_mm=None, support_score=None)
    result.update(binding)
    return result


class GNM_OT_propose_landmarks(bpy.types.Operator):
    bl_idname = 'gnm.propose_landmarks'
    bl_label = 'Propose Landmarks (Review Only)'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            result = snapshot(context)
            encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
        except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        block = bpy.data.texts.new('GNM Landmark Proposals.json')
        block.write(encoded)
        block.use_fake_user = True
        _api._core_module('blender_proposal_review').initialize(context, result, block)
        n = sum(r['status']=='needs_review' for r in result['sites'].values())
        self.report({'INFO'}, f'{n} proposals; see Text Editor: {block.name}. No markers placed.')
        return {'FINISHED'}


def draw(layout, scene):
    layout.prop(scene, 'gnm_show_proposals', toggle=True)
    if not scene.gnm_show_proposals:
        return
    box = layout.box()
    box.label(text='Activate a registered observed fragment')
    box.prop(scene, 'gnm_atlas_skull')
    for name in ('patch','gap','radius','anchor_limit'):
        box.prop(scene, 'gnm_proposal_'+name)
    box.operator('gnm.propose_landmarks')
    _api._core_module('blender_proposal_review').draw(box, scene)


def register(api):
    global _api
    _api = api
    bpy.utils.register_class(GNM_OT_propose_landmarks)
    bpy.types.Scene.gnm_show_proposals = BoolProperty(name='Fragment landmark proposals', default=False)
    bpy.types.Scene.gnm_proposal_patch = StringProperty(name='Patch name (without prefix)')
    for name,label in [('gap','Maximum surface gap (mm)'),('radius','Local anchor radius (mm)'),
                       ('anchor_limit','Maximum anchor residual (mm)')]:
        setattr(bpy.types.Scene,'gnm_proposal_'+name, FloatProperty(name=label, min=0., default=0.))


def unregister():
    global _api
    for name in ('gnm_show_proposals','gnm_proposal_patch','gnm_proposal_gap','gnm_proposal_radius','gnm_proposal_anchor_limit'):
        delattr(bpy.types.Scene, name)
    bpy.utils.unregister_class(GNM_OT_propose_landmarks)
    _api = None

"""Main-thread rigid preview/apply/review. No inferred jaw joint or occlusion."""
import json
import uuid
import bpy
import numpy as np
from mathutils import Matrix
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from . import articulation as core
from .blender_sources import source_geometry, evaluated_geometry, generated_surface
from .blender_occlusion import check_surfaces
from .export import atomic_text
from .reference_frame import _source
from .validation import validate_outputs

_api = None


def _json(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _matrix(obj):
    return np.asarray(obj.matrix_world, dtype=float).tolist()


def _object(scene, name):
    obj = scene.objects.get(name)
    if obj is None:
        raise ValueError('Articulation object missing/renamed: '+name)
    return obj


def _static(obj):
    if obj.parent or obj.children or obj.constraints or obj.animation_data or (obj.type == 'MESH' and obj.modifiers):
        raise ValueError('Use independent static objects without parents/children, constraints, animation or modifiers: '+obj.name)
    if obj.mode != 'OBJECT':
        raise ValueError('Articulation requires Object Mode')


def _signature(scene, names, deep=False):
    result = {}
    for name in names:
        obj = _object(scene, name)
        _static(obj)
        row = dict(matrix=_matrix(obj))
        if obj.type == 'MESH' and deep:
            row['geometry_sha256'] = evaluated_geometry(obj, bpy.context.evaluated_depsgraph_get())[2]
        result[name] = row
    return result


def _source_rows(scene, ids):
    rows = [r for r in _api._bone_sources(scene) if r.uid in ids]
    if len(rows) != len(ids) or any(r.anatomy != 'MANDIBLE' for r in rows):
        raise ValueError('Mandibular source registry changed')
    return rows


def _references(scene):
    st = scene.gnm_articulation
    return {key: getattr(st, key).name if getattr(st, key) else None for key in
            ('upper_teeth', 'lower_teeth', 'condyle_left', 'fossa_left', 'condyle_right', 'fossa_right')}


def _validate_refs(scene):
    st = scene.gnm_articulation
    for key in ('upper_teeth', 'lower_teeth'):
        obj = getattr(st, key)
        if obj and (obj.type != 'MESH' or generated_surface(obj)):
            raise ValueError('Select observed dental meshes: '+key)
    for key in ('condyle_left', 'fossa_left', 'condyle_right', 'fossa_right'):
        obj = getattr(st, key)
        if obj and obj.type != 'EMPTY':
            raise ValueError('Condyle/fossa references must be point empties')
    names = [v for v in _references(scene).values() if v]
    if len(set(names)) != len(names):
        raise ValueError('Reference objects must be distinct')
    _signature(scene, names)


def _moving(scene, ids):
    objects = {r.source_object.name: r.source_object for r in _source_rows(scene, ids)}
    st = scene.gnm_articulation
    for obj in (st.lower_teeth, st.condyle_left, st.condyle_right):
        if obj:
            if obj.name not in scene.objects:
                raise ValueError('Reference outside this scene')
            objects[obj.name] = obj
    for m in scene.gnm_markers:
        if m.bone_empty and m.bone_empty.get('gnm_bone_source_id') in ids:
            for obj in (m.bone_empty, m.target_empty, m.peg_object):
                if obj:
                    objects[obj.name] = obj
    for p in scene.gnm_cranial_points:
        if p.source_id in ids and p.bone_empty:
            objects[p.bone_empty.name] = p.bone_empty
    for m in scene.gnm_markers:
        if m.bone_empty and m.bone_empty.get('gnm_bone_source_id') not in ids:
            if any(o and o.name in objects for o in (m.bone_empty, m.target_empty, m.peg_object)):
                raise ValueError('Marker objects shared with another source')
    for p in scene.gnm_cranial_points:
        if p.bone_empty and p.bone_empty.name in objects and p.source_id not in ids:
            raise ValueError('Bone reference shared with another source')
    for obj in (st.upper_teeth, st.fossa_left, st.fossa_right):
        if obj and obj.name in objects:
            raise ValueError('Cranial and mandibular references must be distinct')
    for obj in objects.values():
        _static(obj)
    return objects


def _placement_hashes(scene, before):
    hashes = {r['id']: r['geometry_sha256'] for r in before}
    for m in scene.gnm_markers:
        b = m.bone_empty
        if b and b.get('gnm_bone_source_id') in hashes:
            if b.get('gnm_source_sha256_at_placement') != hashes[b['gnm_bone_source_id']]:
                raise ValueError('Stale marker placement: '+m.label)
    for p in scene.gnm_cranial_points:
        if p.bone_empty and p.source_id in hashes and p.source_sha256 != hashes[p.source_id]:
            raise ValueError('Stale bone reference: '+p.code)


def begin(context):
    scene, st = context.scene, context.scene.gnm_articulation
    if st.pending:
        raise ValueError('Apply or cancel the preview first')
    if not _api._is_mm_scene(scene):
        raise ValueError('Articulation requires Metric scale 0.001')
    _validate_refs(scene)
    selected = list(context.selected_objects)
    rows = [r for r in _api._bone_sources(scene) if r.source_object in selected]
    if not rows or set(selected) != {r.source_object for r in rows} or any(r.anatomy != 'MANDIBLE' for r in rows):
        raise ValueError('Select only registered preserved MANDIBLE fragments')
    ids = [r.uid for r in rows]
    objects = _moving(scene, ids)
    before = [r for r in _api._source_manifest(scene, context.evaluated_depsgraph_get()) if r['id'] in ids]
    _placement_hashes(scene, before)
    snapshot = _signature(scene, objects, deep=True)
    token, created = uuid.uuid4().hex, []
    try:
        control = bpy.data.objects.new('GNM_Mandible_Control', None)
        scene.collection.objects.link(control); created.append(control)
        control['gnm_articulation_preview'] = token
        control.empty_display_type, control.empty_display_size = 'ARROWS', 5.  # visual only
        control.location, control.lock_scale = scene.cursor.location, (True, True, True)
        context.view_layer.update()
        for obj in objects.values():
            if obj.type != 'MESH':
                continue
            preview = obj.copy()
            preview.data = obj.data.copy()
            scene.collection.objects.link(preview); created.append(preview)
            preview.name = 'GNM_Mandible_Preview_'+obj.name
            preview['gnm_generated'], preview['gnm_articulation_preview'] = True, token
            preview.display_type, preview.hide_render, preview.hide_select = 'WIRE', True, True
            preview.parent = control
            preview.matrix_parent_inverse = control.matrix_world.inverted()
            preview.matrix_world = obj.matrix_world.copy()
            preview['gnm_preview_source'] = obj.name
        data = dict(token=token, ids=ids, snapshot=snapshot, source_before=before,
            references=_references(scene), control_initial=_matrix(control),
            old_aligned=bool(scene.gnm_settings.mandible_aligned), created=[o.name for o in created])
        st.pending, st.control = _json(data), control
        _api._stop_live()
        scene.gnm_settings.mandible_aligned = False
        for obj in context.selected_objects:
            obj.select_set(False)
        control.select_set(True); context.view_layer.objects.active = control
        for area in context.screen.areas if context.screen else []:
            if area.type == 'VIEW_3D':
                area.spaces.active.show_gizmo = True
                area.spaces.active.show_gizmo_object_translate = True
                area.spaces.active.show_gizmo_object_rotate = True
        st.status = 'Wireframe preview: G/R or handles; Apply moves originals and source-bound markers'
    except Exception:
        for obj in reversed(created):
            mesh = obj.data if obj.type == 'MESH' else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        st.pending, st.control = '', None
        raise


def _pending(scene):
    st = scene.gnm_articulation
    if not st.pending or st.control is None:
        raise ValueError('No intact preview; cancel and start again')
    data = json.loads(st.pending)
    if st.control.get('gnm_articulation_preview') != data['token'] or data['references'] != _references(scene):
        raise ValueError('Preview control/references changed; cancel and restart')
    objects = _moving(scene, data['ids'])
    if set(objects) != set(data['snapshot']) or _signature(scene, objects, deep=True) != data['snapshot']:
        raise ValueError('Originals changed during preview; cancel and restart')
    if st.control.parent or st.control.constraints or st.control.animation_data:
        raise ValueError('Control cannot be parented, animated or constrained')
    delta = core.rigid_delta(data['control_initial'], _matrix(st.control))
    dg = bpy.context.evaluated_depsgraph_get()
    for name in data['created']:
        preview = _object(scene, name)
        if preview == st.control:
            continue
        if preview.get('gnm_articulation_preview') != data['token'] or preview.parent != st.control:
            raise ValueError('Preview objects changed; cancel and restart')
        source = _object(scene, preview['gnm_preview_source'])
        p, t, _, _, _ = evaluated_geometry(source, dg)
        q, u, _, _, _ = evaluated_geometry(preview, dg)
        expected = p@delta[:3, :3].T+delta[:3, 3]
        tol = 64*np.finfo(np.float32).eps*max(1., float(np.abs(expected).max()))
        if q.shape != expected.shape or not np.array_equal(t, u) or not np.allclose(q, expected, atol=tol, rtol=0):
            raise ValueError('Preview geometry changed; cancel and restart')
    return data, delta


def _cleanup(scene, data):
    for name in reversed(data['created']):
        obj = scene.objects.get(name)
        if obj and obj.get('gnm_articulation_preview') == data['token']:
            mesh = obj.data if obj.type == 'MESH' else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
    scene.gnm_articulation.control, scene.gnm_articulation.pending = None, ''


def cancel(scene):
    st = scene.gnm_articulation
    if not st.pending:
        raise ValueError('No preview to cancel')
    data, unchanged = json.loads(st.pending), False
    try:
        unchanged = _signature(scene, data['snapshot'], deep=True) == data['snapshot']
    except ValueError:
        pass
    _cleanup(scene, data)
    scene.gnm_settings.mandible_aligned = data['old_aligned'] if unchanged else False
    st.status = 'Preview cancelled; tool did not move originals'


def apply(context):
    scene, st = context.scene, context.scene.gnm_articulation
    _source(st.assumption)
    data, delta = _pending(scene)
    objects = {n: _object(scene, n) for n in data['snapshot']}
    markers = [m for m in scene.gnm_markers if m.bone_empty and m.bone_empty.get('gnm_bone_source_id') in data['ids']]
    points = [p for p in scene.gnm_cranial_points if p.bone_empty and p.source_id in data['ids']]
    old_hashes = [m.bone_empty.get('gnm_source_sha256_at_placement') for m in markers]
    old_points = [(p.source_sha256, p.definition_reviewed) for p in points]
    old_history, old_record = st.history, st.record
    try:
        for name, obj in objects.items():
            obj.matrix_world = Matrix(delta.tolist()) @ Matrix(data['snapshot'][name]['matrix'])
        context.view_layer.update()
        after = [r for r in _api._source_manifest(scene, context.evaluated_depsgraph_get()) if r['id'] in data['ids']]
        hashes = {r['id']: r['geometry_sha256'] for r in after}
        for m in markers:
            m.bone_empty['gnm_source_sha256_at_placement'] = hashes[m.bone_empty['gnm_bone_source_id']]
        for p in points:
            p.source_sha256, p.definition_reviewed = hashes[p.source_id], False
        event = dict(schema_version=1, units='mm', coordinate_space='world', assumption=st.assumption,
            rigid_delta_world=delta.tolist(), before=data['snapshot'], after=_signature(scene, objects, deep=True),
            source_before=data['source_before'], source_after=after, references=data['references'],
            review_status='requires_review', interpretation='Operator-assumed rigid pose; no GNM jaw joint inferred')
        history = json.loads(st.history); history.append(event)
        st.history, st.record = _json(history), ''
        scene.gnm_settings.mandible_aligned = False
        _api._source_changed(None, context)
    except Exception:
        for name, obj in objects.items():
            obj.matrix_world = Matrix(data['snapshot'][name]['matrix'])
        for m, h in zip(markers, old_hashes):
            m.bone_empty['gnm_source_sha256_at_placement'] = h
        for p, (h, reviewed) in zip(points, old_points):
            p.source_sha256, p.definition_reviewed = h, reviewed
        st.history, st.record = old_history, old_record
        context.view_layer.update()
        raise
    _cleanup(scene, data)
    st.status = 'Applied; re-review moved bone definitions and record reviewed articulation before fitting'


def diagnostics(scene, preview=False):
    st = scene.gnm_articulation
    _validate_refs(scene)
    delta, pairs = _pending(scene)[1] if preview else np.eye(4), {}
    for side in ('left', 'right'):
        c, f = getattr(st, 'condyle_'+side), getattr(st, 'fossa_'+side)
        if c and f:
            moving = delta @ np.r_[np.asarray(c.matrix_world.translation), 1.]
            pairs[side] = [moving[:3].tolist(), list(f.matrix_world.translation)]
    result = dict(condyle_fossa=core.point_distances(pairs), dentition=dict(status='unavailable_missing_dental_meshes'),
                  scope='preview' if preview else 'current originals')
    if st.lower_teeth and st.upper_teeth:
        dg = bpy.context.evaluated_depsgraph_get()
        lp, lt, lh, _ = source_geometry(st.lower_teeth, dg)
        up, ut, uh, _ = source_geometry(st.upper_teeth, dg)
        result['dentition'] = check_surfaces((lp@delta[:3, :3].T+delta[:3, 3], lt), (up, ut),
            st.contact_tolerance_mm if st.contact_configured else None)
        result['dentition'].update(lower_source_sha256=lh, upper_source_sha256=uh)
    return result


def review(scene):
    st = scene.gnm_articulation
    if st.pending or st.history == '[]':
        raise ValueError('Apply a pose before recording review')
    _source(st.assumption)
    event = json.loads(st.history)[-1]
    if event['references'] != _references(scene) or _signature(scene, event['after'], deep=True) != event['after']:
        raise ValueError('Applied geometry/references changed; start a new articulation')
    result = diagnostics(scene)
    if result['dentition']['status'] == 'flags_present':
        try:
            _source(st.collision_override_reason)
        except ValueError as exc:
            raise ValueError('Collision flags require an explicit override reason after review') from exc
    names = sorted(set(event['after']) | {n for n in _references(scene).values() if n}
                   | {r.source_object.name for r in _api._bone_sources(scene)})
    st.record = _json(dict(schema_version=1, reviewed=True, assumption=st.assumption, diagnostics=result,
        references=_references(scene), registry=_registry(scene), current_signature=_signature(scene, names, deep=True),
        collision_override_reason=st.collision_override_reason if result['dentition']['status'] == 'flags_present' else None,
        contact_tolerance_mm=st.contact_tolerance_mm if st.contact_configured else None))
    history = json.loads(st.history)
    history[-1].setdefault('reviews', []).append(json.loads(st.record))
    history[-1]['review_status'] = 'reviewed'
    st.history = _json(history)
    scene.gnm_settings.mandible_aligned = True
    st.status = 'Pose review recorded; checks do not validate physiological occlusion'


def _registry(scene):
    return sorted((r.uid, r.source_object.name, r.anatomy) for r in _api._bone_sources(scene))


def require_review(scene, deep=False):
    st = scene.gnm_articulation
    if st.pending:
        raise ValueError('Apply/cancel preview and record review before fitting/export')
    if st.history == '[]':
        return
    if not st.record or not scene.gnm_settings.mandible_aligned:
        raise ValueError('Record reviewed mandibular pose before fitting/export')
    r = json.loads(st.record)
    if (r['registry'] != [list(x) for x in _registry(scene)]
            or r['references'] != _references(scene) or r['assumption'] != st.assumption
            or r['contact_tolerance_mm'] != (st.contact_tolerance_mm if st.contact_configured else None)):
        raise ValueError('Articulation assumptions/references changed; review again')
    expected = r['current_signature'] if deep else {n: dict(matrix=v['matrix']) for n, v in r['current_signature'].items()}
    if _signature(scene, expected, deep=deep) != expected:
        raise ValueError('Recorded mandibular pose/geometry is stale; re-articulate and review')
    _source_rows(scene, [s['id'] for s in json.loads(st.history)[-1]['source_after']])


def snapshot(scene, deep=True):
    st = scene.gnm_articulation
    if st.history == '[]' and not st.pending:
        return None
    try:
        require_review(scene, deep)
        status = 'reviewed_current'
    except ValueError as exc:
        status = str(exc)
    return dict(schema_version=1, units='mm', coordinate_space='world', case_id=scene.gnm_settings.case_id,
                status=status, history=json.loads(st.history), review=json.loads(st.record) if st.record else None,
                preview_pending=bool(st.pending))


class GNMArticulationSettings(PropertyGroup):
    control: PointerProperty(type=bpy.types.Object)
    lower_teeth: PointerProperty(name='Observed lower dentition', type=bpy.types.Object)
    upper_teeth: PointerProperty(name='Observed upper dentition', type=bpy.types.Object)
    condyle_left: PointerProperty(name='Left condyle point', type=bpy.types.Object)
    fossa_left: PointerProperty(name='Left fossa point', type=bpy.types.Object)
    condyle_right: PointerProperty(name='Right condyle point', type=bpy.types.Object)
    fossa_right: PointerProperty(name='Right fossa point', type=bpy.types.Object)
    assumption: StringProperty(name='Pose assumption / justification')
    collision_override_reason: StringProperty(name='Reason for accepting collision flags')
    contact_configured: BoolProperty(name='Explicit contact tolerance', default=False)
    contact_tolerance_mm: FloatProperty(name='Contact tolerance (mm)', default=0., min=0.)
    pending: StringProperty(default='')
    history: StringProperty(default='[]')
    record: StringProperty(default='')
    status: StringProperty(default='Not used; no automatic jaw position')
    output_path: StringProperty(name='Pose session JSON', subtype='FILE_PATH', default='//mandible_pose.json')


class GNM_OT_articulation(Operator):
    bl_idname = 'gnm.articulate_mandible'
    bl_label = 'Articulate Mandible'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=[(a, a.title(), '') for a in ('BEGIN', 'CHECK', 'APPLY', 'CANCEL', 'REVIEW', 'EXPORT')])

    def execute(self, context):
        scene, st = context.scene, context.scene.gnm_articulation
        try:
            if self.action == 'BEGIN':
                begin(context)
            elif self.action == 'APPLY':
                apply(context)
            elif self.action == 'CANCEL':
                cancel(scene)
            elif self.action == 'REVIEW':
                review(scene)
            elif self.action == 'CHECK':
                result = diagnostics(scene, preview=bool(st.pending))
                text = bpy.data.texts.get('GNM_Mandible_Checks') or bpy.data.texts.new('GNM_Mandible_Checks')
                text.clear(); text.write(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
                pairs = ', '.join(f"{s}: {r['distance_mm']:.3f} mm" if r['distance_mm'] is not None else s+': unavailable'
                                  for s, r in result['condyle_fossa'].items())
                st.status = pairs+'; teeth: '+result['dentition']['status']
            else:
                record = snapshot(scene)
                if record is None:
                    raise ValueError('No articulation record')
                sources = _api._source_manifest(scene, context.evaluated_depsgraph_get())
                inputs = [bpy.data.filepath, scene.gnm_settings.sursa_fisier, scene.gnm_settings.ultim_export_csv,
                          bpy.path.abspath(scene.gnm_live.npz_path), bpy.path.abspath(scene.gnm_live.json_path)]
                inputs += [s['acquisition_path'] for s in sources]
                inputs += [o.get('gnm_acquisition_path', '') for o in (st.lower_teeth, st.upper_teeth) if o]
                path = bpy.path.abspath(st.output_path)
                validate_outputs(inputs, [path])
                with atomic_text(path) as stream:
                    stream.write(_json(record)+'\n')
            return {'FINISHED'}
        except (ValueError, OSError, KeyError, TypeError, np.linalg.LinAlgError) as exc:
            st.status = str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class GNM_PT_articulation(Panel):
    bl_idname = 'GNM_PT_articulation'
    bl_label = 'Mandible Articulation (explicit assumption)'
    bl_space_type, bl_region_type, bl_category = 'VIEW_3D', 'UI', 'GNM Markers'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        st, layout = context.scene.gnm_articulation, self.layout
        layout.label(text='Select registered MANDIBLE fragments; cursor sets pivot')
        for prop in ('lower_teeth', 'upper_teeth', 'condyle_left', 'fossa_left', 'condyle_right', 'fossa_right'):
            layout.prop(st, prop)
        layout.operator('gnm.articulate_mandible', text='Articulate Mandible: Wireframe Preview').action = 'BEGIN'
        layout.prop(st, 'assumption')
        row = layout.row(align=True)
        for action in ('CHECK', 'APPLY', 'CANCEL'):
            row.operator('gnm.articulate_mandible', text=action.title()).action = action
        layout.prop(st, 'contact_configured')
        if st.contact_configured:
            layout.prop(st, 'contact_tolerance_mm')
        layout.prop(st, 'collision_override_reason')
        layout.operator('gnm.articulate_mandible', text='Record Reviewed Pose').action = 'REVIEW'
        layout.prop(st, 'output_path')
        layout.operator('gnm.articulate_mandible', text='Export Pose Session JSON').action = 'EXPORT'
        layout.label(text=st.status)
        layout.label(text='Checks run on demand; absent anatomy stays unavailable')


CLASSES = (GNMArticulationSettings, GNM_OT_articulation, GNM_PT_articulation)


def register(addon):
    global _api
    _api = addon
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gnm_articulation = PointerProperty(type=GNMArticulationSettings)


def unregister():
    del bpy.types.Scene.gnm_articulation
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

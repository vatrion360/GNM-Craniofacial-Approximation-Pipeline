"""Independent A/B picks for repeatability. No case marker, target, fit or ghost creation."""
import json
from pathlib import Path
import uuid

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy_extras import view3d_utils

from . import blender_sources, repeatability
from .export import atomic_text
from .validation import validate_outputs

_api = None


def _read(scene):
    return json.loads(scene.gnm_repeat_state) if scene.gnm_repeat_state else {'phase':'idle'}


def _save(scene, state):
    scene.gnm_repeat_state = json.dumps(state, allow_nan=False, sort_keys=True)


def _context(context):
    scene = context.scene
    if not _api._is_mm_scene(scene):
        raise ValueError('Repeat sessions require metric world coordinates (one Blender unit = one mm)')
    _api._core_module('blender_articulation').require_review(scene, deep=True)
    if not scene.gnm_settings.observer_id.strip():
        raise ValueError('Enter a pseudonymous observer ID before starting')
    if any(m.bone_empty or m.target_empty or m.peg_object for m in scene.gnm_markers):
        raise ValueError('Use a clean case copy without placed markers for unassisted repeat sessions')
    if scene.gnm_show_atlas or scene.gnm_show_proposals:
        raise ValueError('Close the placement atlas and proposals during unassisted repeats')
    labels = [m.label for m in scene.gnm_markers]
    if not labels or any(not k.strip() for k in labels) or len(set(labels)) != len(labels):
        raise ValueError('Initialize a unique nonempty marker list first')
    sources = _api._bone_sources(scene)
    if (not sources or any(not r.uid for r in sources) or len({r.uid for r in sources}) != len(sources)
            or len({r.source_object for r in sources}) != len(sources)):
        raise ValueError('Register uniquely identified preserved bone sources first')
    return labels,sources


def _binding(context, labels, rows):
    scene = context.scene
    graph = context.evaluated_depsgraph_get()
    return dict(case_id=_api._case_token(scene)[1], observer_id=scene.gnm_settings.observer_id,
        labels=labels, sources={r.uid:blender_sources.source_geometry(r.source_object,graph,r.flip_normals)[2]
                                for r in rows})


def _check(session, binding):
    for key,value in binding.items():
        if session[key] != value:
            raise ValueError('Repeat session changed: '+key+'; restore the original setup or start a new study')


def transition(context, action):
    scene = context.scene
    st = _read(scene)
    expected = {'START_A':'idle','FINISH_A':'A','START_B':'sealed_A','FINISH_B':'B'}
    if action not in expected or st['phase'] != expected[action]:
        raise ValueError('That action does not apply to the current session')
    binding = _binding(context,*_context(context))
    if action != 'START_A':
        _check(st['A'],binding)
    if action.startswith('START'):
        key = action[-1]
        st[key] = dict(binding,id=uuid.uuid4().hex,points={})
        st['phase'] = key
    else:
        key = st['phase']
        if not st[key]['points']:
            raise ValueError('Capture at least one bone site before closing this session')
        if key == 'B':
            repeatability.paired_report(st['A'],st['B'])
        st['phase'] = 'sealed_A' if key == 'A' else 'done'
    _save(scene,st)


def _active(scene):
    i = scene.gnm_marker_active_index
    if not 0 <= i < len(scene.gnm_markers):
        raise ValueError('Select a marker label')
    return scene.gnm_markers[i].label


def _pick_context(context):
    scene = context.scene
    st = _read(scene)
    key = st['phase']
    if key not in ('A','B'):
        raise ValueError('Start an A or B session before picking')
    labels, sources = _context(context)
    session = st[key]
    _check(session,dict(case_id=scene.gnm_settings.case_id, observer_id=scene.gnm_settings.observer_id,
                        labels=labels))
    if set(session['sources']) != {r.uid for r in sources}:
        raise ValueError('Enabled source registry changed')
    label = _active(scene)
    if label in session['points']:
        raise ValueError('Already measured in this session; select another label or Undo the pick')
    return st,session, sources,label


def pick_ray(context, origin, direction, expected):
    """Use a fresh view ray against the evaluated scene; never use fit/snapshot coordinates."""
    scene = context.scene
    st,session,sources,label = _pick_context(context)
    if (session['id'],label) != expected:
        raise ValueError('Session or label changed since starting this pick')
    dag = context.evaluated_depsgraph_get()
    hit, point, _, _, obj, _ = scene.ray_cast(dag,origin,direction)
    obj = getattr(obj,'original',obj)
    row = next((r for r in sources if r.source_object == obj),None)
    if not hit or row is None:
        raise ValueError('Click visible registered preserved bone; inferred and occluding objects are excluded')
    digest = blender_sources.source_geometry(obj,dag,row.flip_normals)[2]
    if digest != session['sources'][row.uid]:
        raise ValueError('Observed source geometry or world transform changed')
    session['points'][label] = dict(xyz_mm=list(point),source_id=row.uid)
    _save(scene,st)
    # No reference to A when choosing the next label in B.
    pending = next((i for i,k in enumerate(session['labels']) if k not in session['points']),None)
    if pending is not None:
        scene.gnm_marker_active_index = pending


class GNM_OT_repeat_session(bpy.types.Operator):
    bl_idname = 'gnm.repeat_session'
    bl_label = 'Repeat Placement Session'
    bl_options = {'UNDO'}
    action: EnumProperty(items=[(s,s.replace('_',' ').title(),'') for s in
                               ('START_A','FINISH_A','START_B','FINISH_B','RESET')])

    def invoke(self, context, event):
        if self.action in ('FINISH_A','FINISH_B','RESET'):
            return context.window_manager.invoke_confirm(self,event)
        return self.execute(context)

    def execute(self, context):
        try:
            if self.action == 'RESET':
                context.scene.gnm_repeat_state = ''
            else:
                transition(context,self.action)
                if self.action.startswith('START'):
                    context.scene.gnm_marker_active_index = 0
        except (ValueError,RuntimeError) as exc:
            self.report({'WARNING'},str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class GNM_OT_repeat_pick(bpy.types.Operator):
    bl_idname = 'gnm.repeat_pick'
    bl_label = 'Pick Selected Bone Site'
    bl_options = {'UNDO'}

    def invoke(self, context, event):
        try:
            _,s,_,label = _pick_context(context)
            if (not context.area or context.area.type != 'VIEW_3D' or context.space_data.region_quadviews):
                raise ValueError('Use a single 3D viewport for this pick')
            self.identity = s['id'],label
            self.area_id = context.area.as_pointer()
            self.scene_id = context.scene.as_pointer()
            context.window_manager.modal_handler_add(self)
            self.report({'INFO'},'Click visible bone for '+label+'; Esc cancels')
            return {'RUNNING_MODAL'}
        except (RuntimeError,ValueError) as exc:
            self.report({'WARNING'},str(exc))
            return {'CANCELLED'}

    def modal(self, context, event):
        if event.type in ('ESC','RIGHTMOUSE') or context.scene.as_pointer() != self.scene_id:
            return {'CANCELLED'}
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'PASS_THROUGH'}
        area = next((a for a in context.screen.areas if a.as_pointer()==self.area_id and a.type=='VIEW_3D'),None)
        if not area or area.spaces.active.region_quadviews:
            return {'CANCELLED'}
        region = next((r for r in area.regions if r.type=='WINDOW' and
                       r.x <= event.mouse_x < r.x+r.width and r.y <= event.mouse_y < r.y+r.height),None)
        if not region:
            return {'CANCELLED'}
        xy = (event.mouse_x-region.x,event.mouse_y-region.y)
        rv = area.spaces.active.region_3d
        try:
            pick_ray(context,view3d_utils.region_2d_to_origin_3d(region,rv,xy),
                     view3d_utils.region_2d_to_vector_3d(region,rv,xy),self.identity)
        except (ValueError,RuntimeError) as exc:
            self.report({'WARNING'},str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class GNM_OT_repeat_export(bpy.types.Operator):
    bl_idname = 'gnm.repeat_export'
    bl_label = 'Export Repeat Placement Report'
    filepath: StringProperty(subtype='FILE_PATH')

    def invoke(self,context,event):
        self.filepath = 'placement_error.json'
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self,context):
        try:
            st = _read(context.scene)
            if st['phase'] != 'done':
                raise ValueError('Finish both sessions first')
            result = repeatability.paired_report(st['A'],st['B'])
            path = Path(bpy.path.abspath(self.filepath))
            validate_outputs([], [path])
            with atomic_text(path) as stream:
                json.dump(result,stream,sort_keys=True,indent=2,allow_nan=False)
                stream.write('\n')
            self.report({'INFO'},f"Compared {result['compared']}/{result['requested']} sites")
        except (ValueError,RuntimeError,OSError) as exc:
            self.report({'WARNING'},str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


def draw(layout,scene):
    layout.prop(scene,'gnm_show_repeats',toggle=True)
    if not scene.gnm_show_repeats:
        return
    st = _read(scene)
    phase = st['phase']
    box = layout.box()
    box.prop(scene.gnm_settings,'observer_id')
    if phase in ('A','B'):
        box.label(text=f"Session {phase}: {len(st[phase]['points'])}/{len(st[phase]['labels'])} measured")
        box.operator('gnm.repeat_pick')
    if phase != 'done':
        action = dict(idle='START_A',A='FINISH_A',sealed_A='START_B',B='FINISH_B')[phase]
        box.operator('gnm.repeat_session',text=action.replace('_',' ').title()).action = action
    else:
        box.operator('gnm.repeat_export')
    if phase != 'idle':
        box.operator('gnm.repeat_session',text='Discard A/B Study').action = 'RESET'


_CLASSES = (GNM_OT_repeat_session,GNM_OT_repeat_pick,GNM_OT_repeat_export)


def register(api):
    global _api
    _api = api
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gnm_show_repeats = BoolProperty(name='Manual placement repeatability (A/B)',default=False)
    bpy.types.Scene.gnm_repeat_state = StringProperty(default='',options={'HIDDEN'})


def unregister():
    global _api
    del bpy.types.Scene.gnm_repeat_state
    del bpy.types.Scene.gnm_show_repeats
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    _api = None

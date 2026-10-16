"""Main-thread Blender presentation layer, independent of the live fit objects."""
import datetime
import hashlib
import json
import textwrap
from pathlib import Path
import bpy
import numpy as np
from bpy.props import (PointerProperty, CollectionProperty, StringProperty,
                       FloatProperty, FloatVectorProperty, IntProperty, EnumProperty)
from bpy.types import PropertyGroup, Operator, Panel, UIList
from mathutils import Matrix
from . import postfit
from .backend.gnm_backend import OFFICIAL_V3_SHA256

_addon = None
_cache = {}
PARTS = [('skin', 'Skin', ('skin',), (.65, .46, .36, 1)),
         ('teeth', 'Teeth / gums', ('upper_teeth_and_gums', 'lower_teeth_and_gums'), (.8, .75, .65, 1)),
         ('tongue', 'Tongue', ('tongue',), (.5, .15, .18, 1)),
         ('eye_interiors', 'Eye interiors', ('eye_interiors',), (.8, .8, .8, 1)),
         ('eye_exteriors', 'Eye exteriors', ('eye_exteriors',), (1, 1, 1, 1))]


def asset_for(path):
    path = str(Path(bpy.path.abspath(path)).expanduser().resolve())
    if path not in _cache:
        # Retain only the current trusted model. No disk I/O during panel draw.
        value = postfit.load_asset(path)
        _cache.clear()
        _cache[path] = value
    return _cache[path]


def coordinates(data):
    values = np.empty(len(data)*3, dtype=np.float32)
    data.foreach_get('co', values)
    return values.reshape(-1, 3)


def topology(mesh):
    totals = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get('loop_total', totals)
    if np.any(totals != 3):
        raise ValueError('Only the original GNM triangle topology is supported')
    values = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get('vertex_index', values)
    return values.reshape(-1, 3)


def digest(points):
    return hashlib.sha256(np.asarray(points, dtype='<f4').tobytes()).hexdigest()


def stamp_fit(obj, coefficients, model_to_local, model_hash, diagnostics=None):
    """Store the transform needed to transfer native controls to a final surface."""
    if model_hash != OFFICIAL_V3_SHA256:
        return
    obj['gnm_fit_state'] = json.dumps(dict(schema=1, model_sha256=model_hash,
        identity_coefficients=np.asarray(coefficients).tolist(),
        model_to_local=np.asarray(model_to_local).tolist(), diagnostics=diagnostics or {}), allow_nan=False)


def fit_state(source):
    raw = source.get('gnm_fit_state')
    if raw:
        return json.loads(raw)
    # Existing offline results already carry a report path. Preserve their TPS
    # surface, reading only the fitted identity and similarity from that report.
    if source.get('gnm_report'):
        report = json.loads(Path(bpy.path.abspath(source['gnm_report'])).read_text(encoding='utf-8'))
        if report.get('status') != 'completed':
            raise ValueError('Offline fit report is incomplete')
        t = report['transform']
        matrix = np.eye(4)
        matrix[:3, :3] = t['scale']*np.asarray(t['rotation'])
        matrix[:3, 3] = t['translation_mm']
        return dict(model_sha256=report['marker_metadata']['model_sha256'],
                    identity_coefficients=report['identity_coefficients'], model_to_local=matrix.tolist())
    raise ValueError('Choose a completed live/offline fit. Older live scenes need one refit to capture fit metadata')


def assign_uv(mesh, asset):
    """Per-loop assignment preserves GNM seams and intentionally overlapping eyes."""
    postfit.check_topology(coordinates(mesh.vertices), topology(mesh), asset)
    layer = mesh.uv_layers.get('GNM_UV') or mesh.uv_layers.new(name='GNM_UV')
    layer.data.foreach_set('uv', asset.uvs.astype(np.float32).ravel())
    mesh.uv_layers.active = layer
    layer.active_render = True


def materials(obj, asset):
    obj.data.materials.clear()
    indices = np.zeros(len(asset.triangles), dtype=np.int32)
    for i, (key, title, groups, color) in enumerate(PARTS):
        mat = bpy.data.materials.new('GNM Presentation '+title)
        mat.use_nodes = True
        mat.diffuse_color = color
        shader = mat.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value = color
        shader.inputs['Roughness'].default_value = .5
        if key == 'eye_exteriors':
            shader.inputs['Transmission Weight'].default_value = 1.
            shader.inputs['Roughness'].default_value = .03
        obj.data.materials.append(mat)
        mask = asset.mask(*groups)
        indices[np.all(mask[asset.triangles], axis=1)] = i
    obj.data.polygons.foreach_set('material_index', indices)


def freeze(context):
    scene = context.scene
    source = scene.gnm_postfit_source or context.active_object
    if source is None or source.type != 'MESH' or source.get('gnm_presentation'):
        raise ValueError('Select the fitted GNM surface as source')
    if not _addon._is_mm_scene(scene):
        raise ValueError('Use metric scene scale 0.001 for world-mm presentation')
    if source.modifiers or source.data.shape_keys or source.animation_data or source.constraints:
        raise ValueError('Freeze an unmodified fitted mesh; modifiers, shape keys, animation and constraints are unsupported')
    asset = asset_for(scene.gnm_live.npz_path)
    local = coordinates(source.data.vertices)
    postfit.check_topology(local, topology(source.data), asset)
    state = fit_state(source)
    if state['model_sha256'] != OFFICIAL_V3_SHA256:
        raise ValueError('Fit model checksum does not match the presentation asset')
    model_to_world = postfit.similarity_matrix(np.asarray(source.matrix_world) @ np.asarray(state['model_to_local']))
    beta = np.asarray(state['identity_coefficients'])
    if beta.shape != (253,) or not np.isfinite(beta).all():
        raise ValueError('Fit identity metadata is invalid')
    world_matrix = np.asarray(source.matrix_world)
    world = local @ world_matrix[:3, :3].T + world_matrix[:3, 3]
    obj = None
    mesh = source.data.copy()
    try:
        obj = bpy.data.objects.new(source.name+'_Presentation', mesh)
        scene.collection.objects.link(obj)
        obj.matrix_world = Matrix.Identity(4)
        mesh.vertices.foreach_set('co', world.astype(np.float32).ravel())
        mesh.update()
        obj['gnm_generated'], obj['gnm_presentation'] = True, True
        obj.shape_key_add(name='Basis')
        key = obj.shape_key_add(name='Postfit preview')
        key.value = 1.
        neutral = coordinates(obj.data.shape_keys.key_blocks['Basis'].data)
        obj['gnm_postfit_state'] = json.dumps(dict(schema=1, model_sha256=OFFICIAL_V3_SHA256,
            source_name=source.name, neutral_sha256=digest(neutral),
            frozen_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            identity_coefficients=beta.tolist(), model_to_world=model_to_world.tolist(),
            note='Presentation scenario; original neutral fit retained'), allow_nan=False)
        obj.gnm_presentation_settings.model_path = bpy.path.abspath(scene.gnm_live.npz_path)
        for i, name in enumerate(asset.expression_names):
            row = obj.gnm_postfit_controls.add()
            row.name, row.kind, row.index = name, 'EXPRESSION', i
        for i, name in enumerate(asset.identity_names):
            if name.startswith(('teeth_', 'eyes_')):
                row = obj.gnm_postfit_controls.add()
                row.name, row.kind, row.index = name, 'TEETH' if name.startswith('teeth_') else 'EYES', i
        assign_uv(mesh, asset)
        materials(obj, asset)
        _addon._stop_live()
        scene.gnm_postfit_source = source
        scene.gnm_postfit_object = obj
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        source.hide_set(True)
        source.hide_render = True
        obj.gnm_presentation_settings.status = 'Frozen neutral ready; controls apply only to this presentation copy'
        return obj
    except Exception:
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        raise


def checked_preview(scene):
    obj = scene.gnm_postfit_object
    if obj is None or not obj.get('gnm_presentation') or obj.name not in scene.objects:
        raise ValueError('Create or select a presentation copy first')
    if not _addon._is_mm_scene(scene) or not np.allclose(obj.matrix_world, np.eye(4), atol=1e-7):
        raise ValueError('Keep the presentation copy in its original world-mm transform')
    if obj.modifiers or obj.animation_data or obj.constraints or obj.parent or obj.data.users != 1:
        raise ValueError('Presentation requires an independent mesh without modifiers, parenting or animation')
    keys = obj.data.shape_keys
    if keys is None or keys.animation_data or len(keys.key_blocks) != 2:
        raise ValueError('Presentation shape keys were changed or animated')
    basis, preview = keys.key_blocks.get('Basis'), keys.key_blocks.get('Postfit preview')
    if basis is None or preview is None:
        raise ValueError('Presentation shape keys are missing')
    state = json.loads(obj['gnm_postfit_state'])
    neutral = coordinates(basis.data)
    if digest(neutral) != state['neutral_sha256']:
        raise ValueError('Frozen neutral changed; create a new presentation from the original fit')
    return obj, state, neutral, preview


def apply_preview(scene, reset=False):
    obj, state, neutral, key = checked_preview(scene)
    st = obj.gnm_presentation_settings
    asset = asset_for(st.model_path)
    postfit.check_topology(neutral, topology(obj.data), asset)
    expr, delta, angles = np.zeros(383), np.zeros(253), np.zeros((4, 3))
    if not reset:
        for row in obj.gnm_postfit_controls:
            (expr if row.kind == 'EXPRESSION' else delta)[row.index] = row.value
        angles[2], angles[3] = st.left_eye, st.right_eye
    output, stats = postfit.evaluate(asset, neutral, state['model_to_world'],
        state['identity_coefficients'], expr, delta, angles, st.max_mm)
    # All computation/validation succeeds before mutating the preview.
    key.data.foreach_set('co', output.astype(np.float32).ravel())
    key.relative_key = obj.data.shape_keys.key_blocks['Basis']
    key.vertex_group, key.mute, key.value = '', False, 1.
    obj.data.shape_keys.use_relative = True
    obj.data.update()
    if reset:
        for row in obj.gnm_postfit_controls:
            row.value = 0.
        st.left_eye = st.right_eye = (0., 0., 0.)
    state['last_preview'] = dict(expression=expr.tolist(), identity_delta=delta.tolist(),
        eye_axis_angle_radians=angles.tolist(), limit_mm=st.max_mm, **stats,
        applied_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    obj['gnm_postfit_state'] = json.dumps(state, allow_nan=False)
    st.status = f"Max shift {stats['applied_max_mm']:.3f} mm; combined multiplier {stats['attenuation']:.3f}. Inspect lips, teeth and eyelids."


class GNMPostfitControl(PropertyGroup):
    kind: StringProperty()
    index: IntProperty()
    value: FloatProperty(name='Offset', default=0., min=-3., max=3.)


class GNMPresentationSettings(PropertyGroup):
    model_path: StringProperty(subtype='FILE_PATH')
    active: IntProperty(default=0)
    category: EnumProperty(name='Controls', items=[('EXPRESSION', 'Expression / tongue / pupils', ''),
        ('TEETH', 'Teeth shape offsets', ''), ('EYES', 'Eye shape offsets', '')])
    max_mm: FloatProperty(name='Max combined shift (mm)', default=3., min=0., max=20.,
        description='Engineering displacement bound from frozen neutral, not an anatomical safety threshold')
    left_eye: FloatVectorProperty(name='Left eye axis-angle (rad)', size=3, min=-np.pi/6, max=np.pi/6)
    right_eye: FloatVectorProperty(name='Right eye axis-angle (rad)', size=3, min=-np.pi/6, max=np.pi/6)
    texture_part: EnumProperty(name='Texture region', items=[(p[0], p[1], '') for p in PARTS])
    status: StringProperty(default='Apply Preview to update the surface')


class GNM_UL_postfit(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.label(text=item.name)
        row.prop(item, 'value', text='')

    def filter_items(self, context, data, propname):
        category = data.gnm_presentation_settings.category
        flags = [self.bitflag_filter_item if row.kind == category and self.filter_name.lower() in row.name.lower() else 0
                 for row in getattr(data, propname)]
        return flags, []


class GNM_OT_postfit(Operator):
    bl_idname = 'gnm.postfit'
    bl_label = 'Post-fit Presentation'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=[('FREEZE', 'Create presentation copy', ''),
        ('APPLY', 'Apply Preview', ''), ('RESET', 'Reset to Frozen Neutral', '')])

    def execute(self, context):
        try:
            if self.action == 'FREEZE':
                freeze(context)
            else:
                apply_preview(context.scene, reset=self.action == 'RESET')
            return {'FINISHED'}
        except (ValueError, KeyError, OSError, RuntimeError, TypeError, IndexError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class GNM_OT_postfit_texture(Operator):
    bl_idname = 'gnm.postfit_texture'
    bl_label = 'Load GNM UV Texture'
    bl_options = {'REGISTER', 'UNDO'}
    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default='*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.exr', options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            obj, _, _, _ = checked_preview(context.scene)
            st = obj.gnm_presentation_settings
            index = [p[0] for p in PARTS].index(st.texture_part)
            if len(obj.data.materials) != len(PARTS):
                raise ValueError('Presentation material slots changed')
            image = bpy.data.images.load(bpy.path.abspath(self.filepath), check_existing=True)
            # Copy even a presentation material to avoid modifying another scenario.
            mat = obj.data.materials[index].copy()
            obj.data.materials[index] = mat
            nodes, links = mat.node_tree.nodes, mat.node_tree.links
            tex = nodes.get('GNM Color Texture') or nodes.new('ShaderNodeTexImage')
            tex.name, tex.image = 'GNM Color Texture', image
            uv = nodes.get('GNM UV Map') or nodes.new('ShaderNodeUVMap')
            uv.name, uv.uv_map = 'GNM UV Map', 'GNM_UV'
            links.new(uv.outputs['UV'], tex.inputs['Vector'])
            links.new(tex.outputs['Color'], nodes.get('Principled BSDF').inputs['Base Color'])
            st.status = 'Texture loaded on '+PARTS[index][1]+'; use Material Preview or Rendered mode'
            return {'FINISHED'}
        except (ValueError, KeyError, OSError, RuntimeError, TypeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class GNM_PT_postfit(Panel):
    bl_label = 'Post-fit Presentation / GNM UV'
    bl_idname = 'GNM_PT_postfit'
    bl_space_type, bl_region_type, bl_category = 'VIEW_3D', 'UI', 'GNM Markers'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout, scene = self.layout, context.scene
        layout.prop(scene, 'gnm_postfit_source', text='Fitted source')
        layout.operator('gnm.postfit', text='Create Presentation Copy', icon='DUPLICATE').action = 'FREEZE'
        layout.prop(scene, 'gnm_postfit_object', text='Presentation')
        obj = scene.gnm_postfit_object
        if obj is None or not obj.get('gnm_presentation'):
            return
        st = obj.gnm_presentation_settings
        layout.prop(st, 'model_path', text='Presentation model')
        layout.label(text='Original fit retained; head identity locked')
        layout.label(text='Native statistical components, not named emotions')
        layout.prop(st, 'category')
        layout.template_list('GNM_UL_postfit', '', obj, 'gnm_postfit_controls', st, 'active', rows=6)
        layout.prop(st, 'left_eye')
        layout.prop(st, 'right_eye')
        layout.prop(st, 'max_mm')
        layout.operator('gnm.postfit', text='Apply Preview', icon='CHECKMARK').action = 'APPLY'
        layout.operator('gnm.postfit', text='Reset to Frozen Neutral', icon='LOOP_BACK').action = 'RESET'
        layout.label(text='Controls take effect on Apply Preview')
        for line in textwrap.wrap(st.status, width=48):
            layout.label(text=line)
        layout.separator()
        layout.prop(st, 'texture_part')
        layout.operator('gnm.postfit_texture', icon='IMAGE_DATA')
        layout.label(text='Use a texture matching the GNM UV layout')


_classes = (GNMPostfitControl, GNMPresentationSettings, GNM_UL_postfit,
            GNM_OT_postfit, GNM_OT_postfit_texture, GNM_PT_postfit)


def register(addon):
    global _addon
    _addon = addon
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.gnm_postfit_controls = CollectionProperty(type=GNMPostfitControl)
    bpy.types.Object.gnm_presentation_settings = PointerProperty(type=GNMPresentationSettings)
    bpy.types.Scene.gnm_postfit_source = PointerProperty(type=bpy.types.Object)
    bpy.types.Scene.gnm_postfit_object = PointerProperty(type=bpy.types.Object)


def unregister():
    _cache.clear()
    del bpy.types.Scene.gnm_postfit_source
    del bpy.types.Scene.gnm_postfit_object
    del bpy.types.Object.gnm_postfit_controls
    del bpy.types.Object.gnm_presentation_settings
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)

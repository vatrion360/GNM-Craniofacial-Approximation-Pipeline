"""Blender-only craniometry UI. Numeric definitions and fit policy live in craniometry.

All geometry reads and RNA access occur on Blender's main thread. Exported
documents/snapshots contain plain JSON values. No scan is modified.
"""
import json
import os
import textwrap
import bpy
import numpy as np
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, PointerProperty, StringProperty)
from bpy.types import Operator, Panel, PropertyGroup, UIList
from bpy_extras import view3d_utils
from . import craniometry as core
from .export import atomic_text

_api = None
_draw_handle = None


def changed(self, context):
    if _api is not None and context and context.scene:
        # Bone-only measurements do not affect the face when controls are off.
        # A strength change, including switching to zero, still needs a refit.
        if isinstance(self, GNMCranialSettings) or context.scene.gnm_craniometry.weight > 0:
            _api._request_refit(context.scene)


class GNMCranialPoint(PropertyGroup):
    code: StringProperty()
    bone_empty: PointerProperty(type=bpy.types.Object)
    linked_marker: StringProperty()
    source_id: StringProperty()
    source_sha256: StringProperty()
    bone_status: EnumProperty(name='Bone status', items=[('observed', 'Observed', ''),
        ('reconstructed', 'Reconstructed / inferred', ''), ('unspecified', 'Unspecified', '')],
        default='unspecified', update=changed)
    definition_reviewed: BoolProperty(default=False)
    review_xyz: FloatVectorProperty(size=3)
    notes: StringProperty(name='Localization / construction notes', update=changed)
    skin_vertex: IntProperty(name='Reviewed GNM skin vertex', default=-1, min=-1, max=17820)
    skin_depth_mm: FloatProperty(name='Reviewed tissue depth (mm)', default=0., min=0.)
    tissue_source: StringProperty(name='Tissue source / method')


class GNMCranialBinding(PropertyGroup):
    measurement: StringProperty()
    enabled: BoolProperty(name='Use skin-distance control', default=False, update=changed)
    marker_a: StringProperty(name='Skin marker A', update=changed)
    marker_b: StringProperty(name='Skin marker B', update=changed)
    target_mode: EnumProperty(name='Skin target', items=[
        ('skin_markers', 'Distance between reviewed skin targets', 'Dependent on the existing marker observations'),
        ('reviewed_prediction', 'Documented skin-distance prediction', 'Enter a case-specific skin prediction and its method')],
        default='skin_markers', update=changed)
    target_mm: FloatProperty(name='Predicted skin distance (mm)', default=0., min=0., update=changed)
    sigma_mm: FloatProperty(name='Tolerance (mm)', default=2., min=.1, update=changed)
    influence: FloatProperty(name='Relative influence', default=1., min=.001, max=100., update=changed)
    method: StringProperty(name='Bone-to-skin method / reference', update=changed)
    mapping_reviewed: BoolProperty(name='Bone-to-skin mapping reviewed', default=False, update=changed)


class GNMCranialSettings(PropertyGroup):
    active_point: IntProperty(default=0)
    active_measurement: IntProperty(default=0)
    weight: FloatProperty(name='Skin-distance strength (0 = off)', default=0., min=0., max=100., update=changed)
    export_path: StringProperty(name='Craniometry JSON', subtype='FILE_PATH', default='//craniometry.json')
    overwrite: BoolProperty(name='Replace existing JSON', default=False)
    show_new_skin: BoolProperty(name='Create a custom skin control', default=False)
    status: StringProperty(default='Skin-distance controls disabled')
    last_fit: StringProperty(default='')


def initialize(scene):
    """Idempotently add registry entries without replacing existing case work."""
    for marker in scene.gnm_markers:
        marker.name = marker.label
    for code in core.POINTS:
        if not any(point.code == code for point in scene.gnm_cranial_points):
            point = scene.gnm_cranial_points.add()
            point.name = point.code = code
    for spec in core.MEASUREMENTS:
        if not any(row.measurement == spec.key for row in scene.gnm_cranial_bindings):
            row = scene.gnm_cranial_bindings.add()
            row.name = row.measurement = spec.key


def selected_point(scene):
    if not scene.gnm_cranial_points:
        raise ValueError('Initialize cranial measurements first')
    return scene.gnm_cranial_points[min(scene.gnm_craniometry.active_point, len(scene.gnm_cranial_points)-1)]


def _xyz(scene, point):
    obj = point.bone_empty
    return None if obj is None or obj.name not in scene.objects else list(obj.matrix_world.translation)


def _review_current(scene, point):
    xyz = _xyz(scene, point)
    return bool(xyz is not None and point.definition_reviewed and np.linalg.norm(np.asarray(xyz)-point.review_xyz) < 1e-4)


def document(scene, manifest=None, model_hash=None):
    """Current points plus preserved placement hashes; moved points lose review."""
    if not _api._is_mm_scene(scene):
        raise ValueError('Craniometry requires Metric scale 0.001 (1 coordinate = 1 mm)')
    _api._case_token(scene)
    doc = core.empty_document(scene.gnm_settings.case_id)
    doc.update(observer_id=scene.gnm_settings.observer_id, protocol_id=scene.gnm_settings.protocol_id)
    doc['bone_sources'] = manifest if manifest is not None else _api._source_manifest(scene, bpy.context.evaluated_depsgraph_get())
    if model_hash is None:
        path = bpy.path.abspath(scene.gnm_live.npz_path)
        model_hash = _api._core_module('validation').sha256_file(path) if os.path.isfile(path) else ''
    doc['model_sha256'] = model_hash
    for point in scene.gnm_cranial_points:
        xyz = _xyz(scene, point)
        status = point.bone_status if xyz is not None else 'missing'
        linked = _api._marker_item(scene, point.linked_marker)
        if linked and linked.bone_empty == point.bone_empty:
            status = 'reconstructed' if linked.bone_status in ('reconstructed', 'inferred') else linked.bone_status
            if xyz is None:
                status = 'missing'
        doc['points'].append(dict(code=point.code, xyz_mm=xyz, status=status,
            definition_reviewed=_review_current(scene, point), notes=point.notes,
            source_id=point.source_id, source_geometry_sha256=point.source_sha256))
    fields = ('measurement', 'enabled', 'marker_a', 'marker_b', 'target_mode', 'target_mm',
              'sigma_mm', 'influence', 'method', 'mapping_reviewed')
    doc['bindings'] = [{name: getattr(row, name) for name in fields} for row in scene.gnm_cranial_bindings]
    core.measure(doc)
    return doc


def _skin_marker_record(item):
    """Read only the endpoint metadata needed for the shared review check."""
    return dict(mapping_reviewed=item.mapping_reviewed, bone_status=item.bone_status,
                tissue_source=item.tissue_source)


def snapshot_controls(scene, labels, vertices, targets):
    """Use the same resolver as offline; only an opt-in fit reads source geometry."""
    strength = float(scene.gnm_craniometry.weight)
    if strength <= 0:
        scene.gnm_craniometry.status = 'Skin-distance controls disabled'
        return [], [], 0.
    live = _api._LIVE
    # Use the provenance of the loaded in-memory model, not a repeated 53 MB
    # disk read. Standalone snapshots/exports still hash the current file.
    model_hash = (live.model_hash if live.model is not None
                  and live.case_token == _api._case_token(scene) else None)
    doc = document(scene, model_hash=model_hash)
    records, bones = {}, {}
    for item in scene.gnm_markers:
        if not item.is_placed:
            continue
        records[item.label] = dict(_skin_marker_record(item),
            bone_source_id=item.bone_empty.get('gnm_bone_source_id', ''),
            bone_source_geometry_sha256=item.bone_empty.get('gnm_source_sha256_at_placement', ''))
        bones[item.label] = list(item.bone_empty.matrix_world.translation)
    controls, skipped = core.resolve_controls(doc, labels, vertices, targets, records, bones, doc['model_sha256'])
    scene.gnm_craniometry.status = f'{len(controls)} active skin controls; {len(skipped)} skipped (excluded/missing skin markers)'
    return controls, skipped, strength


def fingerprint(scene):
    if scene.gnm_craniometry.weight <= 0:
        return (0.,)
    return (float(scene.gnm_craniometry.weight),
        tuple((p.code, tuple(_xyz(scene, p) or ()), p.bone_status, p.definition_reviewed,
               tuple(p.review_xyz), p.source_id, p.source_sha256, p.notes) for p in scene.gnm_cranial_points),
        tuple((b.measurement, b.enabled, b.marker_a, b.marker_b, b.target_mode, b.target_mm,
               b.sigma_mm, b.influence, b.method, b.mapping_reviewed) for b in scene.gnm_cranial_bindings))


def _detach(point):
    obj = point.bone_empty
    point.bone_empty = None
    point.linked_marker = ''
    point.definition_reviewed = False
    # Never delete a borrowed bone marker, nor a point borrowed by a skin control.
    borrowed = obj is not None and any(m.bone_empty == obj for scene in bpy.data.scenes
                                      if hasattr(scene, 'gnm_markers') for m in scene.gnm_markers)
    if obj is not None and obj.get('gnm_craniometry_point') and not borrowed:
        bpy.data.objects.remove(obj, do_unlink=True)


def place_point(context, point, location, source_object):
    """Place bone-only reference, with no tissue peg and no automatic mirroring."""
    scene = context.scene
    if not _api._is_mm_scene(scene):
        raise ValueError('Craniometry requires Metric scale 0.001')
    original = getattr(source_object, 'original', source_object)
    source = next((s for s in _api._bone_sources(scene) if s.source_object == original), None)
    if source is None:
        # The picker can hit explicitly enabled inferred regions. Keep that distinction.
        if not original.get('gnm_region_patch'):
            raise ValueError('Select a registered bone surface or an enabled inferred patch')
        status, source_id, digest = 'reconstructed', '', ''
    else:
        _, _, digest, _ = _api._core_module('blender_sources').source_geometry(original,
            context.evaluated_depsgraph_get(), source.flip_normals)
        status, source_id = 'observed', source.uid
    _detach(point)
    obj = bpy.data.objects.new('GNM_CRANIAL_'+point.code, None)
    obj['gnm_craniometry_point'] = True
    obj['gnm_generated'] = True
    obj.empty_display_type, obj.empty_display_size = 'SPHERE', scene.gnm_settings.marker_size_mm
    obj.location = location
    obj.show_name = True
    scene.collection.objects.link(obj)
    point.bone_empty = obj
    point.source_id, point.source_sha256, point.bone_status = source_id, digest, status
    context.view_layer.update()
    changed(None, context)


class GNM_OT_craniometry(Operator):
    bl_idname = 'gnm.craniometry'
    bl_label = 'Cranial Measurements'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=[(x, x, '') for x in ('INIT', 'LINK', 'REVIEW', 'CLEAR', 'EXPORT', 'SKIN', 'SEGMENT')])

    def execute(self, context):
        scene = context.scene
        try:
            if self.action == 'INIT':
                initialize(scene)
            elif self.action == 'SEGMENT':
                toggle_segment()
            elif self.action == 'EXPORT':
                doc = document(scene)
                doc['measurements'] = core.measure(doc)
                path = bpy.path.abspath(scene.gnm_craniometry.export_path)
                if not path.lower().endswith('.json'):
                    raise ValueError('Choose a .json filename for craniometry')
                inputs = [bpy.data.filepath, bpy.path.abspath(scene.gnm_live.npz_path), scene.gnm_settings.sursa_fisier,
                          bpy.path.abspath(scene.gnm_live.json_path)]
                inputs += [source.get('acquisition_path', '') for source in doc['bone_sources']]
                _api._core_module('validation').validate_outputs(inputs,
                    [path], scene.gnm_craniometry.overwrite)
                with atomic_text(path) as stream:
                    json.dump(doc, stream, indent=2, ensure_ascii=False, allow_nan=False)
                self.report({'INFO'}, 'Exported 14 bone measurements: '+path)
            else:
                point = selected_point(scene)
                if self.action == 'CLEAR':
                    _detach(point)
                elif self.action == 'LINK':
                    if not scene.gnm_markers:
                        raise ValueError('Select an existing bone marker in the main panel')
                    item = scene.gnm_markers[min(scene.gnm_marker_active_index, len(scene.gnm_markers)-1)]
                    if item.bone_empty is None:
                        raise ValueError('Selected marker has no bone placement')
                    _detach(point)
                    point.bone_empty, point.linked_marker = item.bone_empty, item.label
                    point.source_id = item.bone_empty.get('gnm_bone_source_id', '')
                    point.source_sha256 = item.bone_empty.get('gnm_source_sha256_at_placement', '')
                    point.bone_status = 'reconstructed' if item.bone_status in ('inferred', 'reconstructed') else item.bone_status
                elif self.action == 'REVIEW':
                    xyz = _xyz(scene, point)
                    if xyz is None or point.bone_status == 'unspecified':
                        raise ValueError('Place the reference and record its bone status first')
                    if point.code == 'ns' and not point.notes.strip():
                        raise ValueError('Document the nasospinale construction / protocol variant')
                    # Review confirms anatomy at this position; it does not rewrite a stale source hash.
                    point.review_xyz, point.definition_reviewed = xyz, True
                elif self.action == 'SKIN':
                    create_skin_control(context, point)
                changed(None, context)
            return {'FINISHED'}
        except (ValueError, OSError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


def create_skin_control(context, point):
    """Explicit custom marker; no inherited vertex/depth is assigned to new anatomy."""
    scene = context.scene
    if point.code in ('ba', 'o') or not _review_current(scene, point) or point.bone_status != 'observed':
        raise ValueError('Custom skin controls need reviewed preserved external bone anatomy')
    if point.skin_vertex < 0 or point.skin_depth_mm <= 0 or not point.tissue_source.strip():
        raise ValueError('Supply a reviewed GNM vertex, positive tissue depth and its source')
    label = 'Cranio_'+point.code
    if _api._marker_item(scene, label) is not None:
        raise ValueError('This custom marker already exists; edit it in the main marker panel')
    source = next((s for s in _api._bone_sources(scene) if s.uid == point.source_id), None)
    if source is None:
        raise ValueError('The bone reference has no enabled registered source')
    # Normal estimation is completed before appending a marker, avoiding partial mutation on failure.
    normal = _api._core_module('blender_marker_normals').calculate(scene, source.source_object,
        point.bone_empty.matrix_world.translation, context.evaluated_depsgraph_get())
    if normal['source_geometry_sha256'] != point.source_sha256:
        raise ValueError('Bone source changed; re-place and review the reference')
    item = scene.gnm_markers.add()
    item.name = item.label = label
    item.use_for_fit = False
    item.use_for_plane = False
    item.gnm_vertex_override = point.skin_vertex
    item.gnm_index = _api._encode_index(point.skin_vertex, True)
    item.tissue_depth_mm, item.tissue_source = point.skin_depth_mm, point.tissue_source
    item.bone_status, item.bone_empty = 'observed', point.bone_empty
    item.bone_empty['gnm_bone_source_id'] = point.source_id
    item.bone_empty['gnm_source_sha256_at_placement'] = point.source_sha256
    target = bpy.data.objects.new('GNM_PIELE_'+label, None)
    target.empty_display_type, target.empty_display_size = 'SPHERE', scene.gnm_settings.marker_size_mm
    scene.collection.objects.link(target)
    target.location = np.asarray(_xyz(scene, point))+point.skin_depth_mm*np.asarray(normal['normal'])
    item.target_empty = target
    point.linked_marker = label
    scene.gnm_marker_active_index = len(scene.gnm_markers)-1
    context.view_layer.update()
    _api._core_module('blender_marker_normals').set_direction(item, normal['normal'], scene.gnm_settings.peg_thickness_mm)
    _api._core_module('blender_marker_normals').record_application(item, normal)


class GNM_OT_place_cranial_point(Operator):
    bl_idname = 'gnm.place_cranial_point'
    bl_label = 'Place Bone Reference'
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        if not _api._is_mm_scene(context.scene) or not context.scene.gnm_cranial_points:
            self.report({'ERROR'}, 'Initialize measurements and use Metric scale 0.001')
            return {'CANCELLED'}
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            return {'CANCELLED'}
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'PASS_THROUGH'}
        if context.region_data is None:
            return {'PASS_THROUGH'}
        coord = (event.mouse_region_x, event.mouse_region_y)
        origin = view3d_utils.region_2d_to_origin_3d(context.region, context.region_data, coord)
        direction = view3d_utils.region_2d_to_vector_3d(context.region, context.region_data, coord)
        hit, location, _, obj = _api._ray_cast_skull(context.scene, context.evaluated_depsgraph_get(),
            origin, direction, return_object=True)
        if not hit:
            return {'RUNNING_MODAL'}
        try:
            place_point(context, selected_point(context.scene), location, obj)
            return {'FINISHED'}
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


def clear_segment():
    global _draw_handle
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW')
        _draw_handle = None


def _draw_segment():
    import gpu
    from gpu_extras.batch import batch_for_shader
    scene = bpy.context.scene
    if not hasattr(scene, 'gnm_cranial_bindings') or not scene.gnm_cranial_bindings:
        return
    index = min(scene.gnm_craniometry.active_measurement, len(scene.gnm_cranial_bindings)-1)
    spec = core.BY_KEY[scene.gnm_cranial_bindings[index].measurement]
    points = {p.code: _xyz(scene, p) for p in scene.gnm_cranial_points}
    ends = [points.get(spec.a), points.get(spec.b)]
    if any(p is None for p in ends):
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float('color', (1., .65, .05, 1.))
    batch_for_shader(shader, 'LINES', {'pos': ends}).draw(shader)


def toggle_segment():
    global _draw_handle
    if _draw_handle is not None:
        clear_segment()
    else:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(_draw_segment, (), 'WINDOW', 'POST_VIEW')
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


class GNM_UL_cranial_points(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        layout.label(text=item.code+'  '+core.POINTS[item.code][0],
                     icon='CHECKMARK' if _review_current(context.scene, item) else 'QUESTION')
        layout.label(text='missing' if _xyz(context.scene, item) is None else item.bone_status)


class GNM_UL_cranial_measurements(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        spec = core.BY_KEY[item.measurement]
        points = {p.code: _xyz(context.scene, p) for p in context.scene.gnm_cranial_points}
        a, b = points.get(spec.a), points.get(spec.b)
        value = 'unavailable' if a is None or b is None else f'{np.linalg.norm(np.asarray(a)-b):.2f} mm'
        layout.label(text=spec.key)
        layout.label(text=value)
        layout.label(text='skin control' if item.enabled else '')


def draw_endpoint_review(layout, scene, binding):
    """Expose the actual marker fields; never hash files or build a fit snapshot."""
    box = layout.box()
    box.label(text='Endpoint marker review')
    for endpoint, label in (('A', binding.marker_a), ('B', binding.marker_b)):
        item = _api._marker_item(scene, label) if label else None
        if item is None:
            box.label(text=f'Select skin marker {endpoint}', icon='INFO')
            continue
        marker_box = box.box()
        marker_box.label(text=f'{endpoint}: {item.label}')
        if not item.is_placed:
            marker_box.label(text='Marker is not placed', icon='ERROR')
        if not item.use_for_fit:
            marker_box.label(text='Excluded from fit; this pair will be skipped', icon='INFO')
        marker_box.prop(item, 'bone_status')
        marker_box.prop(item, 'mapping_reviewed')
        marker_box.prop(item, 'tissue_source')
        for issue in core.skin_marker_issues(_skin_marker_record(item)):
            for line in textwrap.wrap(issue, width=48):
                marker_box.label(text=line, icon='ERROR')
    box.label(text='Reference position and pair review are separate')
    box.label(text='Source geometry and anchors are checked at fit')


class GNM_PT_craniometry(Panel):
    bl_label = 'Cranial Measurements (Table 3)'
    bl_idname = 'GNM_PT_craniometry'
    bl_space_type, bl_region_type, bl_category = 'VIEW_3D', 'UI', 'GNM Markers'

    def draw(self, context):
        scene, layout = context.scene, self.layout
        settings = scene.gnm_craniometry
        layout.operator('gnm.craniometry', text='Add 22 Bone References / 14 Measurements').action = 'INIT'
        if not _api._is_mm_scene(scene):
            layout.label(text='Set Metric scale 0.001 to measure in mm', icon='ERROR')
            return
        if not scene.gnm_cranial_points:
            return
        layout.template_list('GNM_UL_cranial_points', '', scene, 'gnm_cranial_points', settings, 'active_point', rows=5)
        point = selected_point(scene)
        for line in textwrap.wrap(core.POINTS[point.code][1], width=48):
            layout.label(text=line)
        row = layout.row(align=True)
        row.operator('gnm.place_cranial_point')
        row.operator('gnm.craniometry', text='Link Selected Marker').action = 'LINK'
        layout.prop(point, 'bone_status')
        layout.prop(point, 'notes')
        row = layout.row(align=True)
        row.operator('gnm.craniometry', text='Confirm Definition / Position').action = 'REVIEW'
        row.operator('gnm.craniometry', text='Clear').action = 'CLEAR'
        layout.prop(settings, 'show_new_skin')
        if settings.show_new_skin:
            box = layout.box()
            box.prop(point, 'skin_vertex'); box.prop(point, 'skin_depth_mm'); box.prop(point, 'tissue_source')
            box.operator('gnm.craniometry', text='Create Skin Marker (Excluded Until Reviewed)').action = 'SKIN'
        layout.separator()
        layout.template_list('GNM_UL_cranial_measurements', '', scene, 'gnm_cranial_bindings', settings, 'active_measurement', rows=7)
        if scene.gnm_cranial_bindings:
            binding = scene.gnm_cranial_bindings[min(settings.active_measurement, len(scene.gnm_cranial_bindings)-1)]
            spec = core.BY_KEY[binding.measurement]
            for line in textwrap.wrap(spec.name, width=48):
                layout.label(text=line)
            layout.operator('gnm.craniometry', text='Show / Hide Selected Chord').action = 'SEGMENT'
            if spec.skin_control_allowed:
                layout.prop(binding, 'enabled')
                if binding.enabled:
                    box = layout.box()
                    box.label(text='Skin target requires documented correspondence')
                    box.prop_search(binding, 'marker_a', scene, 'gnm_markers', text=spec.a+' skin marker')
                    box.prop_search(binding, 'marker_b', scene, 'gnm_markers', text=spec.b+' skin marker')
                    box.prop(binding, 'target_mode')
                    if binding.target_mode == 'reviewed_prediction':
                        box.prop(binding, 'target_mm')
                    box.prop(binding, 'sigma_mm'); box.prop(binding, 'influence')
                    box.prop(binding, 'method'); box.prop(binding, 'mapping_reviewed')
                    draw_endpoint_review(box, scene, binding)
            else:
                layout.label(text='Bone-only measurement; no skin control')
        layout.prop(settings, 'weight')
        layout.label(text='Fit uses observed, reviewed endpoints only')
        for line in textwrap.wrap(settings.status, width=48):
            layout.label(text=line)
        for line in textwrap.wrap(settings.last_fit, width=48):
            layout.label(text=line)
        layout.prop(settings, 'export_path'); layout.prop(settings, 'overwrite')
        layout.operator('gnm.craniometry', text='Export Measurements JSON').action = 'EXPORT'


CLASSES = (GNMCranialPoint, GNMCranialBinding, GNMCranialSettings, GNM_OT_craniometry,
           GNM_OT_place_cranial_point, GNM_UL_cranial_points, GNM_UL_cranial_measurements, GNM_PT_craniometry)


def register(addon):
    global _api
    _api = addon
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gnm_cranial_points = CollectionProperty(type=GNMCranialPoint)
    bpy.types.Scene.gnm_cranial_bindings = CollectionProperty(type=GNMCranialBinding)
    bpy.types.Scene.gnm_craniometry = PointerProperty(type=GNMCranialSettings)


def unregister():
    clear_segment()
    for name in ('gnm_craniometry', 'gnm_cranial_bindings', 'gnm_cranial_points'):
        delattr(bpy.types.Scene, name)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

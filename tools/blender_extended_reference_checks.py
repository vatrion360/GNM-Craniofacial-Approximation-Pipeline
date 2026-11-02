"""Actual Blender checks: optional references, definition review and marker reuse."""
import json
import os
from pathlib import Path

import bpy
from mathutils import Vector


def run_extended_reference_checks(addon, directory):
    previous = bpy.context.window.scene
    scene = bpy.data.scenes.new('Extended reference checks')
    bpy.context.window.scene = scene
    module = addon._core_module('blender_craniometry')
    core = addon._core_module('craniometry')
    def select(code):
        scene.gnm_craniometry.active_point = next(i for i, p in enumerate(scene.gnm_cranial_points) if p.code == code)
        return module.selected_point(scene)
    def rejected(action, text):
        try:
            result = bpy.ops.gnm.craniometry(action=action)
        except RuntimeError as exc:
            assert text in str(exc), str(exc)
        else:
            assert result == {'CANCELLED'}
    try:
        scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', .001
        assert bpy.ops.gnm.craniometry(action='INIT') == {'FINISHED'}
        original_rows = [p.code for p in scene.gnm_cranial_points]
        scene.gnm_cranial_points[0].notes = 'Synthetic existing case work'
        scene.gnm_cranial_points[0].skin_vertex = 7
        scene.gnm_cranial_points[0].skin_depth_mm = 3.25
        assert len(original_rows) == 22
        before_document = module.document(scene)
        assert bpy.ops.gnm.craniometry(action='INIT_EXTENDED') == {'FINISHED'}
        assert bpy.ops.gnm.craniometry(action='INIT_EXTENDED') == {'FINISHED'}
        assert len(scene.gnm_cranial_points) == 34 and len(scene.gnm_markers) == 0
        assert [p.code for p in scene.gnm_cranial_points][:22] == original_rows
        assert scene.gnm_cranial_points[0].skin_vertex == 7
        assert scene.gnm_cranial_points[0].skin_depth_mm == 3.25
        assert module.document(scene)['points'][:22] == before_document['points']
        assert len(scene.gnm_cranial_bindings) == 14
        mesh = bpy.data.meshes.new('Extended synthetic bone surface')
        mesh.from_pydata([(-20, -20, 0), (20, -20, 0), (0, 20, 0)], [], [(0, 1, 2)])
        surface = bpy.data.objects.new('Extended preserved bone', mesh)
        scene.collection.objects.link(surface)
        addon._register_bone_source(scene, surface)
        bpy.context.view_layer.update()
        point = select('po_R')
        assert not point.definition_text and not point.definition_source
        module.place_point(bpy.context, point, Vector((0, 0, 0)), surface)
        rejected('REVIEW', 'definition_text')
        point.definition_text = 'Synthetic test location; not an anatomical definition'
        rejected('REVIEW', 'definition_source')
        point.definition_source = 'Synthetic headless software test'
        assert bpy.ops.gnm.craniometry(action='REVIEW') == {'FINISHED'}
        assert module._review_current(scene, point)
        point.definition_source = 'Synthetic edited protocol'
        assert not point.definition_reviewed and not module._review_current(scene, point)
        assert bpy.ops.gnm.craniometry(action='REVIEW') == {'FINISHED'}
        # Reinitialization preserves case work, definition, review and object identity.
        old = point.bone_empty
        assert bpy.ops.gnm.craniometry(action='INIT_EXTENDED') == {'FINISHED'}
        assert point.bone_empty == old and point.definition_source == 'Synthetic edited protocol'
        assert module._review_current(scene, point)
        point.bone_empty.location.x += 1
        bpy.context.view_layer.update()
        assert not module._review_current(scene, point)
        point.bone_empty.location.x -= 1
        bpy.context.view_layer.update()
        rejected('SKIN', 'do not create')
        assert not scene.gnm_markers
        missing = select('po_L')
        assert missing.bone_empty is None
        restored = select('co_L')
        module.place_point(bpy.context, restored, Vector((3, 0, 0)), surface)
        restored.bone_status = 'reconstructed'
        # A known orbital-rim reference must not link an infraorbital-foramen marker.
        reference = select('or_R')
        marker = scene.gnm_markers.add()
        marker.name = marker.label = 'Infraorbitale_Dr'
        marker.gnm_vertex_override = 0
        marker.gnm_index = addon._encode_index(0, True)
        marker.bone_status = 'observed'
        marker.use_for_fit = False
        marker.tissue_depth_mm = 2.
        marker.tissue_source = 'Synthetic software test'
        for attr, xyz in [('bone_empty', (1, 2, 3)), ('target_empty', (1, 2, 5))]:
            obj = bpy.data.objects.new('Synthetic '+attr, None)
            scene.collection.objects.link(obj)
            obj.location = xyz
            setattr(marker, attr, obj)
        bpy.context.view_layer.update()
        rejected('LINK', 'catalogued existing marker')
        assert reference.bone_empty is None
        marker.name = marker.label = 'Suborbitale_Dr'
        assert bpy.ops.gnm.craniometry(action='LINK') == {'FINISHED'}
        assert reference.bone_empty == marker.bone_empty and not reference.definition_reviewed
        assert bpy.ops.gnm.craniometry(action='REVIEW') == {'FINISHED'}
        rejected('SKIN', 'do not create')
        assert len(scene.gnm_markers) == 1 and not marker.use_for_fit
        bone_name = marker.bone_empty.name
        assert bpy.ops.gnm.craniometry(action='CLEAR') == {'FINISHED'}
        assert marker.bone_empty.name == bone_name and bone_name in scene.objects
        document = module.document(scene)
        points, _ = core.validate_document(document)
        assert points['po_L']['status'] == 'missing' and points['co_L']['status'] == 'reconstructed'
        assert points['po_R']['definition_reviewed'] and not points['po_R']['fit_target']
        assert points['po_R']['xyz_mm'] == [0., 0., 0.]
        scene.gnm_craniometry.export_path = str(Path(directory)/'extended-references.json')
        assert bpy.ops.gnm.craniometry(action='EXPORT') == {'FINISHED'}
        saved = json.loads(Path(scene.gnm_craniometry.export_path).read_text())
        assert saved['points'] == document['points']
        if os.environ.get('GNM_MODEL_PATH'):
            scene.gnm_live.npz_path = os.environ['GNM_MODEL_PATH']
            path = Path(directory)/'extended-references-markers.csv'
            addon._export_markers(scene, str(path))
            targets, _, meta = addon._core_module('io_csv').read_marker_csv(path, {}, {})
            assert not targets  # single existing marker is excluded, new references add no targets
            points, _ = core.validate_document(meta['craniometry'])
            assert len(points) == 34 and points['po_R']['definition_source'] == 'Synthetic edited protocol'
        print('BLENDER_EXTENDED_REFERENCES_PASS: opt-in 34, unchanged 48 skin catalogue, definition gates, reuse, CSV/JSON')
    finally:
        addon._stop_live()
        bpy.context.window.scene = previous
        for obj in list(scene.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(scene)

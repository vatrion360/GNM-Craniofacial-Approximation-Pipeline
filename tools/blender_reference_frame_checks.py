"""Real RNA/ZIP checks; rendering stub tests cameras, not pixel appearance."""
import json
import os
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector, Matrix


def run_reference_frame_checks(addon, directory):
    previous = bpy.context.window.scene
    scene = bpy.data.scenes.new('Reference frame checks')
    bpy.context.window.scene = scene
    cm = addon._core_module('blender_craniometry')
    adapter = addon._core_module('blender_reference_frame')
    core = addon._core_module('reference_frame')
    original_render = addon._render_documentation_still
    try:
        scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', .001
        assert not scene.gnm_reference_frame.use_for_captures
        assert 'reference_frame' not in cm.document(scene)
        assert bpy.ops.gnm.craniometry(action='INIT_EXTENDED') == {'FINISHED'}
        mesh = bpy.data.meshes.new('Frame synthetic source')
        mesh.from_pydata([(-200, -200, 0), (200, -200, 0), (0, 200, 100)], [], [(0, 1, 2)])
        source = bpy.data.objects.new('Frame preserved bone', mesh)
        scene.collection.objects.link(source)
        addon._register_bone_source(scene, source)
        q = Matrix.Rotation(.7, 3, 'Y') @ Matrix.Rotation(.4, 3, 'X')
        shift = Vector((11, -23, 6))
        xyz = dict(po_R=(50, 0, 0), po_L=(-50, 0, 0), or_L=(-25, 60, 0),
                   n=(0, 60, 30), b=(0, 0, 80), op=(0, -65, 10))
        points = {}
        for code, position in xyz.items():
            index = next(i for i, p in enumerate(scene.gnm_cranial_points) if p.code == code)
            scene.gnm_craniometry.active_point = index
            point = cm.selected_point(scene)
            point.definition_text = 'Synthetic location only, not anatomical evidence'
            point.definition_source = 'Synthetic Blender integration check'
            cm.place_point(bpy.context, point, q@Vector(position)+shift, source)
            assert bpy.ops.gnm.craniometry(action='REVIEW') == {'FINISHED'}
            points[code] = point
        before = {o.name: np.array(o.matrix_world) for o in scene.objects}
        path = Path(directory)/'frame-config.json'
        config = dict(schema_version=1, orbitale='or_L', superior_code='b', midline_codes=['n', 'b', 'op'],
                      source='Synthetic integration protocol', placement_error=None)
        path.write_text(json.dumps(config), encoding='utf-8')
        scene.gnm_reference_frame.config_path = str(path)
        assert bpy.ops.gnm.reference_frame(action='COMPUTE') == {'FINISHED'}
        record = adapter.current_record(scene)
        np.testing.assert_allclose(record['geometry']['axes_world'], np.array(q), atol=2e-7)
        assert record['uncertainty']['status'] == 'not_assessed'
        if any(a.type == 'VIEW_3D' for a in bpy.context.screen.areas):
            assert bpy.ops.gnm.reference_frame(action='FRONT') == {'FINISHED'}
        for name, matrix in before.items():
            np.testing.assert_array_equal(np.array(scene.objects[name].matrix_world), matrix)
        # Every change must be caught without panel draw/hash side effects.
        point = points['n']
        point.bone_empty.location.x += 1
        bpy.context.view_layer.update()
        assert cm.document(scene)['reference_frame']['status'] == 'stale'
        try:
            adapter.current_record(scene)
        except ValueError:
            pass
        else:
            raise AssertionError('Moved reference must invalidate views/captures')
        point.bone_empty.location.x -= 1
        bpy.context.view_layer.update()
        assert adapter.current_record(scene)['status'] == 'current'
        config['source'] += ' changed'
        path.write_text(json.dumps(config), encoding='utf-8')
        assert cm.document(scene)['reference_frame']['status'] == 'stale'
        assert bpy.ops.gnm.reference_frame(action='COMPUTE') == {'FINISHED'}
        points['po_R'].definition_source += ' changed'
        assert cm.document(scene)['reference_frame']['status'] == 'stale'
        points['po_R'].definition_reviewed = True  # explicit test review; production uses operator
        assert bpy.ops.gnm.reference_frame(action='COMPUTE') == {'FINISHED'}
        mesh.vertices[0].co.x += 1
        mesh.update(); bpy.context.view_layer.update()
        assert cm.document(scene)['reference_frame']['status'] == 'stale'
        mesh.vertices[0].co.x -= 1
        mesh.update(); bpy.context.view_layer.update()
        assert adapter.current_record(scene)['status'] == 'current'
        scene.gnm_craniometry.export_path = str(Path(directory)/'frame-bones.json')
        assert bpy.ops.gnm.craniometry(action='EXPORT') == {'FINISHED'}
        saved = json.loads(Path(scene.gnm_craniometry.export_path).read_text())
        assert saved['reference_frame']['status'] == 'current'
        if os.environ.get('GNM_MODEL_PATH'):
            scene.gnm_live.npz_path = os.environ['GNM_MODEL_PATH']
            # Existing export requires a marker row, even if excluded.
            marker = scene.gnm_markers.add()
            marker.name = marker.label = 'SyntheticFrameMarker'
            marker.gnm_vertex_override = 0
            marker.gnm_index = addon._encode_index(0, True)
            marker.use_for_fit = False
            marker.bone_status = 'observed'
            marker.tissue_source = 'Synthetic software check'
            marker.tissue_depth_mm = 2.
            for attr, position in [('bone_empty', (1, 2, 3)), ('target_empty', (1, 2, 5))]:
                obj = bpy.data.objects.new('Frame '+attr, None)
                scene.collection.objects.link(obj); obj.location = position
                setattr(marker, attr, obj)
            bpy.context.view_layer.update()
            csv = Path(directory)/'frame-markers.csv'
            addon._export_markers(scene, str(csv))
            _, _, metadata = addon._core_module('io_csv').read_marker_csv(csv, {}, {})
            assert metadata['craniometry']['reference_frame'] == saved['reference_frame']
        # Actual capture operator; renderer is deliberately stubbed.
        bpy.context.view_layer.objects.active = source
        source.select_set(True)
        original_camera = scene.camera
        scene.gnm_reference_frame.use_for_captures = True
        cameras = []
        def render_stub():
            bpy.context.view_layer.update()
            cameras.append(np.array(scene.camera.rotation_quaternion.to_matrix()))
            assert scene.camera.get('gnm_reference_frame_json')
        addon._render_documentation_still = render_stub
        assert bpy.ops.gnm.capturi_standardizate(directory=directory) == {'FINISHED'}
        assert scene.camera == original_camera and len(cameras) == 3
        for name, matrix in before.items():
            np.testing.assert_array_equal(np.array(scene.objects[name].matrix_world), matrix)
        record = adapter.current_record(scene)
        for rotation, view in zip(cameras, ('front', '3quarter', 'profile')):
            np.testing.assert_allclose(rotation, core.camera_basis(record, view), atol=3e-7)
        points['po_R'].bone_status = 'reconstructed'
        try:
            result = bpy.ops.gnm.capturi_standardizate(directory=directory)
        except RuntimeError as exc:
            assert 'stale' in str(exc)
        else:
            assert result == {'CANCELLED'}
        assert len(cameras) == 3
        points['po_R'].bone_status = 'observed'
        def failing_render():
            raise RuntimeError('Synthetic render failure')
        addon._render_documentation_still = failing_render
        try:
            bpy.ops.gnm.capturi_standardizate(directory=directory)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Renderer failure must propagate')
        assert scene.camera == original_camera
        assert bpy.ops.gnm.reference_frame(action='CLEAR') == {'FINISHED'}
        assert 'reference_frame' not in cm.document(scene)
        assert not scene.gnm_reference_frame.use_for_captures
        print('BLENDER_REFERENCE_FRAME_PASS: geometry, review, stale sources/config, CSV/JSON, capture camera roll')
    finally:
        addon._render_documentation_still = original_render
        addon._stop_live()
        bpy.context.window.scene = previous
        for obj in list(scene.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(scene)

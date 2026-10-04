"""Actual RNA/geometry/export checks for the installed add-on, independent of UI mocks."""
import json
import os
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector


def run_craniometry_checks(addon, directory):
    previous = bpy.context.window.scene
    scene = bpy.data.scenes.new('Craniometry software checks')
    bpy.context.window.scene = scene
    module = addon._core_module('blender_craniometry')
    core = addon._core_module('craniometry')
    try:
        scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', .001
        scene.gnm_settings.normal_mode = 'FACE'
        assert bpy.ops.gnm.craniometry(action='INIT') == {'FINISHED'}
        assert bpy.ops.gnm.craniometry(action='INIT') == {'FINISHED'}
        assert len(scene.gnm_cranial_points) == 22 and len(scene.gnm_cranial_bindings) == 14
        assert all(row['bone_mm'] is None for row in core.measure(module.document(scene)))
        mesh = bpy.data.meshes.new('Synthetic preserved vault')
        mesh.from_pydata([(-80, -20, 0), (80, -20, 0), (80, 20, 0), (-80, 20, 0)], [], [(0, 1, 2), (0, 2, 3)])
        obj = bpy.data.objects.new('Preserved vault', mesh)
        scene.collection.objects.link(obj)
        source = addon._register_bone_source(scene, obj)
        source.anatomy = 'CRANIUM'
        bpy.context.view_layer.update()
        original = addon._source_manifest(scene, bpy.context.evaluated_depsgraph_get())
        points = {p.code: p for p in scene.gnm_cranial_points}
        for code, x, vertex in [('eu_R', 60., 0), ('eu_L', -60., 1)]:
            point = points[code]
            module.place_point(bpy.context, point, Vector((x, 0, 0)), obj)
            scene.gnm_craniometry.active_point = list(core.POINTS).index(code)
            assert bpy.ops.gnm.craniometry(action='REVIEW') == {'FINISHED'}
            assert module._review_current(scene, point)
            point.skin_vertex, point.skin_depth_mm = vertex, 5.
            point.tissue_source = 'Synthetic software fixture; not anatomical evidence'
            assert bpy.ops.gnm.craniometry(action='SKIN') == {'FINISHED'}
            marker = scene.gnm_markers[-1]
            assert not marker.use_for_fit and not marker.mapping_reviewed
            marker.mapping_reviewed = marker.use_for_fit = True
        bpy.context.view_layer.update()
        assert addon._source_manifest(scene, bpy.context.evaluated_depsgraph_get()) == original
        rows = {r['measurement']: r for r in core.measure(module.document(scene))}
        assert rows['eu-eu']['bone_mm'] == 120. and rows['eu-eu']['definition_reviewed']
        assert rows['ba-b']['status'] == 'missing'
        # Moving the point invalidates anatomical review even if geometry has not changed.
        point = points['eu_R']
        point.bone_empty.location.x += 1
        bpy.context.view_layer.update()
        assert not module._review_current(scene, point)
        point.bone_empty.location.x -= 1
        bpy.context.view_layer.update()
        assert module._review_current(scene, point)
        if os.environ.get('GNM_MODEL_PATH'):
            scene.gnm_live.npz_path = os.environ['GNM_MODEL_PATH']
            binding = next(b for b in scene.gnm_cranial_bindings if b.measurement == 'eu-eu')
            binding.marker_a, binding.marker_b = 'Cranio_eu_R', 'Cranio_eu_L'
            binding.method = 'Synthetic paired skin-marker control'
            binding.mapping_reviewed, binding.enabled = True, True
            scene.gnm_craniometry.weight = .5
            before = addon._fingerprint(scene)
            snap = addon._build_snapshot(scene)
            assert len(snap['measurement_controls']) == 1 and snap['measurement_weight'] == .5
            binding.sigma_mm = 3.
            assert addon._fingerprint(scene) != before
            path = Path(directory)/'cranial-markers.csv'
            addon._export_markers(scene, str(path))
            targets, _, meta = addon._core_module('io_csv').read_marker_csv(path, {}, {})
            controls, _ = core.resolve_controls(meta['craniometry'], [t.label for t in targets],
                [t.vertex for t in targets], [t.xyz for t in targets], meta['marker_records'],
                meta['bone_positions_mm'], meta['model_sha256'])
            assert controls == addon._build_snapshot(scene)['measurement_controls']
            # An excluded endpoint must remove only its dependent control.
            scene.gnm_markers[1].use_for_fit = False
            snap = addon._build_snapshot(scene)
            assert not snap['measurement_controls'] and len(snap['skipped_measurement_controls']) == 1
            scene.gnm_markers[1].use_for_fit = True
            # Neither a reconstructed endpoint nor stale source geometry is accepted as observed.
            scene.gnm_markers[1].bone_status = 'reconstructed'
            try:
                addon._build_snapshot(scene)
            except ValueError as exc:
                assert 'observed bone' in str(exc)
            else:
                raise AssertionError('Accepted an inferred measurement control')
            scene.gnm_markers[1].bone_status = 'observed'
            obj.location.z += .5
            bpy.context.view_layer.update()
            try:
                addon._build_snapshot(scene)
            except ValueError as exc:
                assert 'current' in str(exc)
            else:
                raise AssertionError('Accepted a stale measurement control')
            obj.location.z -= .5
            bpy.context.view_layer.update()
        scene.gnm_craniometry.export_path = str(Path(directory)/'craniometry.json')
        assert bpy.ops.gnm.craniometry(action='EXPORT') == {'FINISHED'}
        exported = json.loads(Path(scene.gnm_craniometry.export_path).read_text())
        assert len(exported['measurements']) == 14
        assert core.measure(exported)[4]['bone_mm'] == 120.
        # Clear a borrowed reference without deleting the marker it points to.
        point = points['eu_R']
        name = point.bone_empty.name
        scene.gnm_craniometry.active_point = list(core.POINTS).index('eu_R')
        assert bpy.ops.gnm.craniometry(action='CLEAR') == {'FINISHED'}
        assert name in bpy.data.objects and scene.gnm_markers[0].bone_empty.name == name
        assert point.bone_empty is None
        # Units and display helper lifetime are explicit.
        scene.unit_settings.scale_length = 1.
        try:
            module.document(scene)
        except ValueError as exc:
            assert '0.001' in str(exc)
        else:
            raise AssertionError('Accepted metre coordinates as mm')
        module.toggle_segment()
        assert module._draw_handle is not None
        addon._gnm_live_on_load_post(None)
        assert module._draw_handle is None
        print('BLENDER_CRANIOMETRY_PASS: 22 points, 14 chords, controls, units, missing/inferred/stale, CSV parity')
    finally:
        addon._stop_live()
        module.clear_segment()
        bpy.context.window.scene = previous
        for obj in list(scene.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(scene)

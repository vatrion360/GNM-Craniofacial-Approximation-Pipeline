"""Actual Blender regressions for marker placement, preview and reorientation."""
import json
import os
from pathlib import Path
import tempfile
import bpy
import numpy as np
from mathutils import Matrix, Vector


def run_normal_checks(addon):
    previous = bpy.context.window.scene
    scene = bpy.data.scenes.new('Marker normal checks')
    bpy.context.window.scene = scene
    scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', .001
    module = addon._core_module('blender_marker_normals')
    try:
        coordinates = np.linspace(-5, 5, 41)
        x, y = np.meshgrid(coordinates, coordinates)
        z = .055*np.sin(9*x)*np.cos(8*y)
        vertices = np.column_stack((x.ravel(), y.ravel(), z.ravel()))
        faces = []
        for row in range(40):
            for col in range(40):
                a = row*41+col
                faces.extend(((a, a+1, a+42), (a, a+42, a+41)))
        mesh = bpy.data.meshes.new('Noisy observed bone')
        mesh.from_pydata(vertices.tolist(), [], faces)
        obj = bpy.data.objects.new('Observed test fragment', mesh)
        scene.collection.objects.link(obj)
        source = addon._register_bone_source(scene, obj)
        source.normals_reviewed = True
        bpy.context.view_layer.update()
        original = addon._source_manifest(scene, bpy.context.evaluated_depsgraph_get())
        points, triangles, digest, _ = addon._core_module('blender_sources').source_geometry(
            obj, bpy.context.evaluated_depsgraph_get())
        seed = int(np.argmin(np.linalg.norm(points[triangles].mean(axis=1)-[.2, .05, 0], axis=1)))
        point = Vector(points[triangles[seed]].mean(axis=0))
        marker = scene.gnm_markers.add()
        marker.label, marker.tissue_depth_mm = 'Nasion', 6.
        record = addon._place_marker_at(bpy.context, marker, point, obj, seed)
        bpy.context.view_layer.update()
        np.testing.assert_allclose(marker.bone_empty.matrix_world.translation, point, atol=1e-7)
        assert np.linalg.norm(record['normal'][:2]) < .02
        assert marker.bone_empty['gnm_source_sha256_at_placement'] == digest
        assert abs((marker.target_empty.matrix_world.translation-point).length-6.) < 1e-5
        np.testing.assert_allclose(marker.peg_object.matrix_world @ Vector((0, 0, -.5)), point, atol=1e-6)
        np.testing.assert_allclose(marker.peg_object.matrix_world @ Vector((0, 0, .5)),
                                   marker.target_empty.matrix_world.translation, atol=1e-6)
        module.set_direction(marker, [1, 0, 1], .5)
        bpy.context.view_layer.update()
        assert not module.export_record(marker)['matches_current_marker']
        before = marker.target_empty.matrix_world.copy()
        assert bpy.ops.gnm.marker_normal(action='PREVIEW') == {'FINISHED'}
        bpy.context.view_layer.update()
        np.testing.assert_array_equal(marker.target_empty.matrix_world, before)
        helpers = [o for o in scene.objects if o.get('gnm_marker_normal_preview')]
        assert len(helpers) == 2
        assert all(addon._core_module('blender_sources').generated_surface(o) for o in helpers)
        assert bpy.ops.gnm.marker_normal(action='APPLY') == {'FINISHED'}
        bpy.context.view_layer.update()
        assert module.export_record(marker)['matches_current_marker']
        assert not any(o.get('gnm_marker_normal_preview') for o in scene.objects)
        assert addon._source_manifest(scene, bpy.context.evaluated_depsgraph_get()) == original
        assert marker.bone_status == 'observed' and marker.use_for_fit
        if os.environ.get('GNM_MODEL_PATH'):
            scene.gnm_live.npz_path = os.environ['GNM_MODEL_PATH']
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'normal-markers.csv'
                addon._export_markers(scene, str(path))
                _, _, meta = addon._core_module('io_csv').read_marker_csv(path, {}, {})
                provenance = meta['marker_orientation']['Nasion']
                assert provenance['matches_current_marker']
                assert provenance['applied_estimate']['source_geometry_sha256'] == digest
        # Zero depth still remembers the direction for the next depth edit.
        marker.tissue_depth_mm = 0.
        bpy.context.view_layer.update()
        np.testing.assert_allclose(marker.target_empty.matrix_world.translation, point, atol=1e-7)
        marker.tissue_depth_mm = 7.
        bpy.context.view_layer.update()
        assert abs((marker.target_empty.matrix_world.translation-point).length-7.) < 1e-5
        scene.gnm_settings.normal_mode = 'FACE'
        assert bpy.ops.gnm.marker_normal(action='APPLY') == {'FINISHED'}
        bpy.context.view_layer.update()
        record = json.loads(marker.bone_empty['gnm_normal_record'])
        assert record['mode'] == 'FACE' and np.linalg.norm(record['normal'][:2]) > .08
        # World normals must include negative determinant and nonuniform scale.
        rotation = Matrix.Rotation(.4, 4, 'Y')
        obj.matrix_world = Matrix.Translation((20, 5, 4)) @ rotation @ Matrix.Diagonal((-2., 1.5, .7, 1.))
        bpy.context.view_layer.update()
        new_point = obj.matrix_world @ point
        record = addon._place_marker_at(bpy.context, marker, new_point, obj, seed)
        expected = (obj.matrix_world.to_3x3().inverted().transposed() @ Vector(
            addon._core_module('surface_normals').estimate_normal(points, triangles, point,
                mode='FACE', seed_faces=[seed])['normal'])).normalized()
        np.testing.assert_allclose(record['normal'], expected, atol=1e-6)
        source.flip_normals = True
        bpy.context.view_layer.update()
        record = addon._place_marker_at(bpy.context, marker, new_point, obj, seed)
        np.testing.assert_allclose(record['normal'], -expected, atol=1e-6)
        # A changed source cannot silently reuse the original point/seed.
        obj.location.x += 1.
        bpy.context.view_layer.update()
        before = marker.target_empty.matrix_world.copy()
        try:
            bpy.ops.gnm.marker_normal(action='APPLY')
        except RuntimeError as exc:
            assert 'Source changed' in str(exc)
        else:
            raise AssertionError('Accepted stale marker source geometry')
        np.testing.assert_array_equal(marker.target_empty.matrix_world, before)
        # Source vertex coordinates are never smoothed or changed by orientation.
        actual = np.empty(len(mesh.vertices)*3)
        mesh.vertices.foreach_get('co', actual)
        np.testing.assert_array_equal(actual.reshape(-1, 3), vertices.astype(np.float32).astype(float))
        # Modifier-aware ray placement uses the evaluated surface and polygon ID.
        obj.matrix_world = Matrix.Identity(4)
        source.flip_normals = False
        modifier = obj.modifiers.new('Evaluated thickness', 'SOLIDIFY')
        modifier.thickness = .5
        bpy.context.view_layer.update()
        hit = addon._ray_cast_skull(scene, bpy.context.evaluated_depsgraph_get(),
            Vector((.18, .06, 10.)), Vector((0, 0, -1)), return_face=True)
        assert hit[0] and hit[3] == obj
        addon._place_marker_at(bpy.context, marker, hit[1], hit[3], hit[4])
        # Inferred bone remains inferred/excluded after normal placement and reorientation.
        inferred = bpy.data.objects.new('Test inferred patch', mesh.copy())
        scene.collection.objects.link(inferred)
        region = scene.gnm_restoration_regions.add()
        region.uid, region.enabled, region.result_object = 'normal-test-inferred', True, inferred
        inferred['gnm_region_patch'] = region.uid
        inferred['gnm_reconstructed_via_mirroring'] = True
        bpy.context.view_layer.update()
        scene.gnm_settings.normal_mode = 'LOCAL_PLANE'
        addon._place_marker_at(bpy.context, marker, point, inferred, seed)
        assert marker.bone_status == 'reconstructed'
        assert not marker.use_for_fit and not marker.use_for_plane
        assert bpy.ops.gnm.marker_normal(action='APPLY') == {'FINISHED'}
        assert not marker.use_for_fit and not marker.use_for_plane
        # An unsuccessful new placement preserves all existing marker objects.
        names = [o.name for o in (marker.bone_empty, marker.target_empty, marker.peg_object)]
        scene.gnm_settings.normal_radius_mm = .25
        try:
            addon._place_marker_at(bpy.context, marker, point+Vector((0, 0, 2)), inferred)
        except ValueError:
            pass
        else:
            raise AssertionError('Accepted off-surface placement')
        assert names == [o.name for o in (marker.bone_empty, marker.target_empty, marker.peg_object)]
        # File-load/unregister cleanup must remove disposable preview objects.
        scene.gnm_settings.normal_radius_mm = 3.
        assert bpy.ops.gnm.marker_normal(action='PREVIEW') == {'FINISHED'}
        addon._gnm_live_on_load_post(None)
        assert not any(o.get('gnm_marker_normal_preview') for o in scene.objects)
        print('GNM NORMAL CHECKS PASSED: placement, preview, reorientation, depth, parity, provenance')
    finally:
        module.clear_preview(scene)
        addon._stop_live()
        bpy.context.window.scene = previous
        for obj in list(scene.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(scene)

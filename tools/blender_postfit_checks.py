"""Installed Blender checks for final-surface preservation, UVs and presentation."""
import json
import os
from pathlib import Path
import tempfile
import bpy
import numpy as np
from mathutils import Matrix


def run_postfit_checks(addon):
    module = addon._core_module('blender_postfit')
    previous = bpy.context.window.scene
    scene = bpy.data.scenes.new('Postfit presentation checks')
    bpy.context.window.scene = scene
    scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', .001
    scene.gnm_live.npz_path = os.environ['GNM_MODEL_PATH']
    asset = module.asset_for(scene.gnm_live.npz_path)
    try:
        beta = np.zeros(253); beta[3] = .2
        local = asset.mu + beta[3]*asset.identity[3]
        local[:, 2] += .2*np.sin(np.arange(len(local)))  # a non-statistical final correction
        mesh = bpy.data.meshes.new('Final fitted mesh')
        mesh.from_pydata(local, [], asset.triangles)
        source = bpy.data.objects.new('Final fitted source', mesh)
        scene.collection.objects.link(source)
        source.matrix_world = Matrix.Translation((4, 5, 6)) @ Matrix.Rotation(.3, 4, 'X') @ Matrix.Scale(1.2, 4)
        bpy.context.view_layer.update()
        before = module.coordinates(mesh.vertices).copy()
        world_matrix = np.asarray(source.matrix_world)
        expected = (before @ world_matrix[:3, :3].T + world_matrix[:3, 3]).astype(np.float32)
        module.stamp_fit(source, beta, np.eye(4), module.OFFICIAL_V3_SHA256)
        scene.gnm_postfit_source = source
        assert bpy.ops.gnm.postfit(action='FREEZE') == {'FINISHED'}
        obj = scene.gnm_postfit_object
        assert obj != source and obj.data != mesh
        assert len(obj.gnm_postfit_controls) == 466
        assert len(obj.data.materials) == 5 and len(mesh.materials) == 0
        assert source.hide_render
        keys = obj.data.shape_keys.key_blocks
        np.testing.assert_array_equal(module.coordinates(keys['Basis'].data), expected)
        uv = np.empty(asset.uvs.size, np.float32)
        obj.data.uv_layers['GNM_UV'].data.foreach_get('uv', uv)
        np.testing.assert_array_equal(uv.reshape(asset.uvs.shape), asset.uvs)
        control = next(r for r in obj.gnm_postfit_controls if r.name == 'lower_face_region_000')
        control.value = 1.
        obj.gnm_presentation_settings.max_mm = .5
        obj.gnm_presentation_settings.left_eye = (.03, 0., .01)
        assert bpy.ops.gnm.postfit(action='APPLY') == {'FINISHED'}
        altered = module.coordinates(keys['Postfit preview'].data).copy()
        assert np.max(np.linalg.norm(altered-expected, axis=1)) <= .5001
        assert np.max(abs(altered-expected)) > .001
        assert bpy.ops.gnm.postfit(action='APPLY') == {'FINISHED'}
        np.testing.assert_array_equal(module.coordinates(keys['Postfit preview'].data), altered)
        np.testing.assert_array_equal(module.coordinates(mesh.vertices), before)
        np.testing.assert_array_equal(source.matrix_world, world_matrix)
        assert bpy.ops.gnm.postfit(action='RESET') == {'FINISHED'}
        np.testing.assert_array_equal(module.coordinates(keys['Postfit preview'].data), expected)
        assert not any(r.value for r in obj.gnm_postfit_controls)
        assert not any(obj.gnm_presentation_settings.left_eye)
        # Corrupted neutral cannot be silently accepted as the fitted result.
        keys['Basis'].data[0].co.x += 1
        try:
            module.apply_preview(scene)
        except ValueError as exc:
            assert 'Frozen neutral changed' in str(exc)
        else:
            raise AssertionError('Accepted edited neutral basis')
        keys['Basis'].data.foreach_set('co', expected.ravel())
        with tempfile.TemporaryDirectory() as directory:
            # Load an actual local test texture on a separate presentation material.
            image = bpy.data.images.new('Synthetic UV color', width=4, height=4)
            path = str(Path(directory)/'color.png')
            image.filepath_raw, image.file_format = path, 'PNG'
            image.save()
            assert bpy.ops.gnm.postfit_texture(filepath=path) == {'FINISHED'}
            assert obj.data.materials[0].node_tree.nodes['GNM UV Map'].uv_map == 'GNM_UV'
            assert len(source.data.materials) == 0
            blend = str(Path(directory)/'postfit.blend')
            bpy.data.libraries.write(blend, {scene})
            with bpy.data.libraries.load(blend) as (src, dst):
                dst.scenes = src.scenes
            restored = dst.scenes[0]
            bpy.context.window.scene = restored
            module._cache.clear()
            module.apply_preview(restored, reset=True)
            other = restored.gnm_postfit_object
            np.testing.assert_array_equal(module.coordinates(other.data.shape_keys.key_blocks['Basis'].data), expected)
            bpy.context.window.scene = scene
            bpy.data.scenes.remove(restored)
            # Legacy offline result: world-space final mesh plus existing report.
            report = dict(status='completed', marker_metadata={'model_sha256':module.OFFICIAL_V3_SHA256},
                identity_coefficients=beta.tolist(), transform=dict(scale=1.2,
                    rotation=(world_matrix[:3, :3]/1.2).tolist(), translation_mm=[4,5,6]))
            report_path = Path(directory)/'face_report.json'
            report_path.write_text(json.dumps(report))
            offline_mesh = mesh.copy()
            offline_mesh.vertices.foreach_set('co', expected.ravel())
            offline = bpy.data.objects.new('Offline final with TPS', offline_mesh)
            scene.collection.objects.link(offline)
            offline['gnm_report'] = str(report_path)
            scene.gnm_postfit_source = offline
            module.freeze(bpy.context)
            offline_preview = scene.gnm_postfit_object
            np.testing.assert_array_equal(module.coordinates(offline_preview.data.shape_keys.key_blocks['Basis'].data), expected)
        print('BLENDER_POSTFIT_PRESENTATION_PASS: final residual, native UV, cap, reset, persistence, texture, offline report')
    finally:
        bpy.context.window.scene = previous
        bpy.data.scenes.remove(scene)

"""Installed-ZIP checks for bulk depth edits on actual Blender RNA/objects."""
import json
import os
from pathlib import Path
import tempfile
import bpy
import numpy as np
from mathutils import Vector


def run_depth_checks(addon):
    previous = bpy.context.window.scene
    scene = bpy.data.scenes.new('Depth adjustment checks')
    bpy.context.window.scene = scene
    scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', .001
    module = addon._core_module('blender_marker_depths')
    normals = addon._core_module('blender_marker_normals')
    refit = addon._request_refit
    requests = []
    addon._request_refit = lambda s: requests.append(s.name)
    try:
        for label, depth in [('Nasion', 10.), ('Rhinion', 5.), ('Glabella', 8.)]:
            item = scene.gnm_markers.add()
            item.name = item.label = label
            item.tissue_depth_mm = depth
            item.tissue_source = 'synthetic fixture'
            item.bone_status, item.mapping_reviewed = 'observed', True
        item = scene.gnm_markers[0]
        item.adjust_depth_selected = scene.gnm_markers[1].adjust_depth_selected = True
        scene.gnm_markers[1].use_for_fit = False
        for attr in ['bone_empty', 'target_empty', 'peg_object']:
            obj = bpy.data.objects.new(attr, None)
            scene.collection.objects.link(obj)
            setattr(item, attr, obj)
        item.bone_empty.location = (2, 3, 4)
        bpy.context.view_layer.update()
        normals.set_direction(item, (.6, 0, .8), .5)
        bpy.context.view_layer.update()
        bone = item.bone_empty.matrix_world.copy()
        settings = scene.gnm_settings
        settings.depth_adjust_percent, settings.depth_adjust_mode = 20., 'INCREASE'
        requests.clear()
        assert bpy.ops.gnm.adjust_marker_depths() == {'FINISHED'}
        bpy.context.view_layer.update()
        assert [m.tissue_depth_mm for m in scene.gnm_markers] == [12., 6., 8.]
        assert requests == [scene.name]
        np.testing.assert_array_equal(item.bone_empty.matrix_world, bone)
        np.testing.assert_allclose(item.target_empty.matrix_world.translation, [9.2, 3, 13.6], atol=2e-6)
        np.testing.assert_allclose(item.peg_object.matrix_world @ Vector((0, 0, -.5)), [2, 3, 4], atol=2e-6)
        np.testing.assert_allclose(item.peg_object.matrix_world @ Vector((0, 0, .5)),
                                   item.target_empty.matrix_world.translation, atol=2e-6)
        assert item.mapping_reviewed and item.bone_status == 'observed'
        assert not scene.gnm_markers[1].use_for_fit
        assert scene.gnm_markers[2].tissue_source == 'synthetic fixture'
        assert module.history(item)[0]['before_mm'] == 10.
        assert module.history(item)[0]['after_mm'] == 12.
        assert item.tissue_source == 'manual-percentage; base source: synthetic fixture'
        assert module.apply_adjustment(addon, bpy.context, 25., 'DECREASE') == 2
        bpy.context.view_layer.update()
        assert [m.tissue_depth_mm for m in scene.gnm_markers] == [9., 4.5, 8.]
        assert len(module.history(item)) == 2
        # No-op edits do not append audit entries or request a refit.
        requests.clear()
        assert module.apply_adjustment(addon, bpy.context, 0., 'INCREASE') == 0
        assert not requests and len(module.history(item)) == 2
        before = [(m.tissue_depth_mm, m.tissue_source, m.depth_adjustment_history) for m in scene.gnm_markers]
        def rejected(percent, mode, text):
            try:
                module.apply_adjustment(addon, bpy.context, percent, mode)
            except ValueError as exc:
                assert text in str(exc), str(exc)
            else:
                raise AssertionError('Invalid bulk edit accepted')
            assert before == [(m.tissue_depth_mm, m.tissue_source, m.depth_adjustment_history) for m in scene.gnm_markers]
        rejected(101., 'DECREASE', '100%')
        # A failure in a later row must not partially edit the first row.
        scene.gnm_markers[1].bone_empty = item.bone_empty
        rejected(20., 'INCREASE', 'incomplete placement')
        scene.gnm_markers[1].bone_empty = None
        item.target_empty.parent = item.bone_empty
        rejected(20., 'INCREASE', 'parents')
        item.target_empty.parent = None
        bpy.context.view_layer.update()
        # Inject a geometry-adapter failure after it has modified the target.
        target = item.target_empty.matrix_world.copy()
        peg = item.peg_object.matrix_world.copy()
        original = normals.set_direction
        def fail(*args):
            original(*args)
            raise ValueError('injected geometry failure')
        normals.set_direction = fail
        try:
            rejected(20., 'INCREASE', 'injected')
        finally:
            normals.set_direction = original
        bpy.context.view_layer.update()
        np.testing.assert_allclose(item.target_empty.matrix_world, target, atol=2e-6)
        np.testing.assert_allclose(item.peg_object.matrix_world, peg, atol=2e-6)
        assert not addon._MARKER_DEPTH_BATCH
        # Zero depth must retain a usable direction for a later direct edit.
        assert module.apply_adjustment(addon, bpy.context, 100., 'DECREASE') == 2
        bpy.context.view_layer.update()
        np.testing.assert_allclose(item.target_empty.matrix_world.translation, [2, 3, 4], atol=2e-6)
        item.tissue_depth_mm = 7.
        bpy.context.view_layer.update()
        np.testing.assert_allclose(item.target_empty.matrix_world.translation, [6.2, 3, 9.6], atol=2e-6)
        assert bpy.ops.gnm.select_depth_markers(select=True) == {'FINISHED'}
        assert all(m.adjust_depth_selected for m in scene.gnm_markers)
        assert bpy.ops.gnm.select_depth_markers(select=False) == {'FINISHED'}
        assert not any(m.adjust_depth_selected for m in scene.gnm_markers)
        assert not bpy.ops.gnm.adjust_marker_depths.poll()
        # Persist RNA audit data and selection through an actual blend library.
        item.adjust_depth_selected = True
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'depths.blend')
            bpy.data.libraries.write(path, {scene})
            with bpy.data.libraries.load(path) as (source, destination):
                destination.scenes = source.scenes
            restored = destination.scenes[0]
            assert restored.gnm_markers[0].depth_adjustment_history == item.depth_adjustment_history
            assert restored.gnm_markers[0].adjust_depth_selected
            assert restored.gnm_markers[0].tissue_depth_mm == 7.
            bpy.data.scenes.remove(restored)
            if os.environ.get('GNM_MODEL_PATH'):
                scene.gnm_live.npz_path = os.environ['GNM_MODEL_PATH']
                addon._export_markers(scene, str(Path(directory) / 'markers.csv'))
                text = (Path(directory) / 'markers.csv').read_text()
                assert 'marker_depth_adjustments' in text and 'manual_percentage' in text
                assert json.loads(item.depth_adjustment_history)[-1]['after_mm'] == 0.
        print('BLENDER_MARKER_DEPTH_ADJUSTMENT_PASS')
    finally:
        addon._request_refit = refit
        bpy.context.window.scene = previous
        bpy.data.scenes.remove(scene)


def run_depth_undo_checks(addon):
    """Check a Blender undo/redo boundary, reacquiring RNA after undo invalidates it."""
    previous_name = bpy.context.window.scene.name
    scene = bpy.data.scenes.new('Depth Undo')
    name = scene.name
    bpy.context.window.scene = scene
    item = scene.gnm_markers.add()
    item.label, item.tissue_depth_mm = 'Nasion', 10.
    item.adjust_depth_selected = True
    scene.gnm_settings.depth_adjust_percent = 20.
    bpy.ops.ed.undo_push(message='Before depth adjustment')
    assert bpy.ops.gnm.adjust_marker_depths() == {'FINISHED'}
    bpy.ops.ed.undo_push(message='After depth adjustment')
    assert bpy.ops.ed.undo() == {'FINISHED'}
    scene = bpy.data.scenes[name]
    assert scene.gnm_markers[0].tissue_depth_mm == 10.
    assert scene.gnm_markers[0].depth_adjustment_history == '[]'
    assert bpy.ops.ed.redo() == {'FINISHED'}
    scene = bpy.data.scenes[name]
    assert scene.gnm_markers[0].tissue_depth_mm == 12.
    assert len(addon._core_module('blender_marker_depths').history(scene.gnm_markers[0])) == 1
    bpy.context.window.scene = bpy.data.scenes[previous_name]
    bpy.data.scenes.remove(scene)
    print('BLENDER_MARKER_DEPTH_UNDO_PASS')

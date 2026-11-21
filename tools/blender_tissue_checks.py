"""Actual RNA/geometry, audit persistence and failure rollback for table application."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import bpy
import numpy as np


def make_scene(addon, name):
    scene = bpy.data.scenes.new(name)
    bpy.context.window.scene = scene
    scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', .001
    for i, label in enumerate(('Nasion', 'Rhinion')):
        item = scene.gnm_markers.add()
        item.name = item.label = label
        item.tissue_depth_mm, item.tissue_source = 10., 'individual measurement'
        item.mapping_reviewed, item.bone_status = True, 'observed'
        for attr in ('bone_empty', 'target_empty', 'peg_object'):
            obj = bpy.data.objects.new(label+attr, None)
            scene.collection.objects.link(obj)
            setattr(item, attr, obj)
        item.bone_empty.location = (20*i, 3, 4)
        bpy.context.view_layer.update()
        addon._core_module('blender_marker_normals').set_direction(item, (.6, 0, .8), .5)
    bpy.context.view_layer.update()
    scene.gnm_markers[0].adjust_depth_selected = True
    return scene


def run_tissue_checks(addon):
    previous = bpy.context.window.scene
    scene = make_scene(addon, 'Tissue checks')
    module = addon._core_module('blender_tissue')
    tissue = addon._core_module('tissue')
    normals = addon._core_module('blender_marker_normals')
    original_refit, requests = addon._request_refit, []
    addon._request_refit = lambda scene: requests.append(scene.name)
    try:
        item = scene.gnm_markers[0]
        settings = scene.gnm_settings
        assert settings.tissue_table == 'NONE' and not settings.tissue_axis_existing
        original_target = np.array(item.target_empty.matrix_world.translation)
        settings.tissue_table = 'legacy_hardcoded'
        assert item.tissue_depth_mm == 10. and not settings.tissue_axis_existing
        try:
            module.apply_selected_table(addon, bpy.context, 'legacy_hardcoded')
        except ValueError:
            pass
        else:
            raise AssertionError('Missing axis acknowledgement accepted')
        np.testing.assert_array_equal(item.target_empty.matrix_world.translation, original_target)
        # An unselected marker sharing a target must not be moved implicitly.
        other = scene.gnm_markers[1]
        owned = other.target_empty
        other.target_empty = item.target_empty
        try:
            module.apply_selected_table(addon, bpy.context, 'legacy_hardcoded', True)
        except ValueError as exc:
            assert 'shared target' in str(exc)
        else:
            raise AssertionError('Shared target accepted')
        other.target_empty = owned
        assert item.tissue_depth_mm == 10.
        # Missing selected table row must preserve every previously planned row.
        scene.gnm_markers[1].adjust_depth_selected = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'table.json'
            doc = tissue.empty_table('synthetic')
            doc['citation'] = 'Synthetic fixture only'
            doc['landmarks']['Nasion'] = dict(central_mm=4.)
            tissue.write_table(path, doc)
            try:
                module.apply_selected_table(addon, bpy.context, path, True)
            except ValueError as exc:
                assert 'Rhinion' in str(exc)
            else:
                raise AssertionError('Missing row accepted')
            assert item.tissue_depth_mm == 10. and item.depth_adjustment_history == '[]'
            scene.gnm_markers[1].adjust_depth_selected = False
            settings.tissue_table = 'FILE'
            settings.tissue_table_path = str(path)
            settings.tissue_axis_existing = True
            requests.clear()
            assert bpy.ops.gnm.apply_tissue_table() == {'FINISHED'}
            bpy.context.view_layer.update()
            assert requests == [scene.name]
            assert item.tissue_depth_mm == 4. and scene.gnm_markers[1].tissue_depth_mm == 10.
            np.testing.assert_allclose(item.bone_empty.matrix_world.translation, [0, 3, 4])
            np.testing.assert_allclose(item.target_empty.matrix_world.translation, [2.4, 3, 7.2], atol=2e-6)
            history = json.loads(item.depth_adjustment_history)
            assert history[-1]['method'] == 'explicit_tissue_table'
            assert history[-1]['application']['table']['sha256'] == tissue.load_table(path).sha256
            assert history[-1]['previous_tissue_source'] == 'individual measurement'
            assert item.mapping_reviewed and item.bone_status == 'observed'
            # Inject a failure after geometry mutation and verify exact state rollback.
            before = (item.tissue_depth_mm, item.tissue_source, item.depth_adjustment_history)
            target_matrix = item.target_empty.matrix_world.copy()
            original_direction = normals.set_direction
            def fail(*args):
                original_direction(*args)
                raise ValueError('injected')
            normals.set_direction = fail
            try:
                try:
                    module.apply_selected_table(addon, bpy.context, 'legacy_hardcoded', True)
                except ValueError as exc:
                    assert 'injected' in str(exc)
                else:
                    raise AssertionError('Failed mutation accepted')
            finally:
                normals.set_direction = original_direction
            bpy.context.view_layer.update()
            assert before == (item.tissue_depth_mm, item.tissue_source, item.depth_adjustment_history)
            np.testing.assert_allclose(item.target_empty.matrix_world, target_matrix, atol=2e-6)
            assert not addon._MARKER_DEPTH_BATCH
            blend = str(Path(directory)/'tissue.blend')
            bpy.data.libraries.write(blend, {scene})
            with bpy.data.libraries.load(blend) as (source, destination):
                destination.scenes = source.scenes
            restored = destination.scenes[0]
            assert restored.gnm_markers[0].depth_adjustment_history == item.depth_adjustment_history
            bpy.data.scenes.remove(restored)
            if os.environ.get('GNM_MODEL_PATH'):
                scene.gnm_live.npz_path = os.environ['GNM_MODEL_PATH']
                addon._export_markers(scene, str(Path(directory)/'case.csv'))
                _, _, metadata = addon._core_module('io_csv').read_marker_csv(Path(directory)/'case.csv', {}, {})
                assert metadata['marker_depth_adjustments']['Nasion'][-1]['method'] == 'explicit_tissue_table'
                assert metadata['marker_records']['Nasion']['tissue_depth_mm'] == 4.
        print('BLENDER_TISSUE_APPLICATION_PASS')
    finally:
        addon._request_refit = original_refit
        bpy.context.window.scene = previous
        bpy.data.scenes.remove(scene)


def run_offline_weighting_checks(addon, scene, directory, baseline_folder, baseline_report):
    settings = scene.gnm_settings
    assert not settings.offline_depth_weighting
    assert baseline_report['config']['depth_weighting'] == 'none'
    assert 'tissue_table' not in baseline_report['inputs']
    assert not (baseline_folder / 'weighting_table.json').exists()
    tissue = addon._core_module('tissue')
    adapter = addon._core_module('blender_tissue')
    source = Path(directory) / 'țesut sintetic.json'
    old_selection = settings.tissue_table, settings.tissue_table_path
    try:
        settings.tissue_table, settings.tissue_table_path = 'FILE', str(source)
        assert adapter.offline_weight_table(settings) is None
        settings.offline_depth_weighting = True
        source.write_text('{}', encoding='utf-8')
        existing = set(Path(settings.case_directory).iterdir())
        for selection, path in [('NONE', ''), ('FILE', ''), ('FILE', str(source))]:
            settings.tissue_table, settings.tissue_table_path = selection, path
            try:
                assert bpy.ops.gnm.run_offline() == {'CANCELLED'}
            except RuntimeError:
                pass
            assert settings.offline_status.startswith('Cannot start:')
            assert addon._OFFLINE['process'] is None
            assert set(Path(settings.case_directory).iterdir()) == existing

        settings.tissue_table = 'legacy_hardcoded'
        assert adapter.offline_weight_table(settings) == tissue.table_path('legacy_hardcoded').read_bytes()
        settings.tissue_table = 'FILE'
        doc = tissue.empty_table('synthetic')
        doc['citation'] = 'Synthetic software check only'
        doc['landmarks']['Nasion'] = dict(central_mm=40., sd_mm=2.)
        raw = json.dumps(doc, indent=1).encode('utf-8-sig')
        source.write_bytes(raw)
        assert bpy.ops.gnm.run_offline() == {'FINISHED'}
        folder = Path(addon._OFFLINE['folder'])
        source.write_text('{}', encoding='utf-8')  # Child must use its archived copy.
        deadline = time.monotonic() + 180
        while addon._OFFLINE['process'] is not None and time.monotonic() < deadline:
            addon._offline_poll()
            time.sleep(.05)
        assert settings.offline_status.startswith('Completed;'), settings.offline_status
        assert '1/47 retained markers' in settings.offline_status
        snapshot = folder / 'weighting_table.json'
        assert snapshot.read_bytes() == raw
        report = json.loads((folder / 'face_report.json').read_text(encoding='utf-8'))
        assert report['config']['depth_weighting'] == 'sd'
        assert snapshot.samefile(report['inputs']['tissue_table']['path'])
        assert report['inputs']['tissue_table']['sha256'] == hashlib.sha256(raw).hexdigest()
        metadata = report['marker_metadata']
        assert metadata['tissue_application']['replaced_labels'] == []
        assert metadata['marker_records'] == baseline_report['marker_metadata']['marker_records']
        assert metadata['bone_positions_mm'] == baseline_report['marker_metadata']['bone_positions_mm']
        rows = metadata['depth_weighting']['landmarks']
        assert 'Vertex_VarfCap' not in rows
        assert rows['Nasion']['effective_weight'] == rows['Nasion']['base_weight'] / 4
        assert rows['Rhinion']['effective_weight'] == rows['Rhinion']['base_weight']
        assert rows['Rhinion']['fallback'] == 'missing table row'
        assert any(obj.get('gnm_report') == str(folder / 'face_report.json') for obj in scene.objects)
        print('BLENDER_OFFLINE_TISSUE_WEIGHTING_PASS')
    finally:
        addon._stop_offline()
        settings.offline_depth_weighting = False
        settings.tissue_table, settings.tissue_table_path = old_selection


def run_tissue_undo_checks(addon):
    previous = bpy.context.window.scene.name
    scene = make_scene(addon, 'Tissue undo')
    name = scene.name
    scene.gnm_settings.tissue_table = 'legacy_hardcoded'
    scene.gnm_settings.tissue_axis_existing = True
    bpy.ops.ed.undo_push(message='Before tissue application')
    assert bpy.ops.gnm.apply_tissue_table() == {'FINISHED'}
    bpy.ops.ed.undo_push(message='After tissue application')
    assert bpy.ops.ed.undo() == {'FINISHED'}
    scene = bpy.data.scenes[name]
    assert scene.gnm_markers[0].tissue_depth_mm == 10. and scene.gnm_markers[0].depth_adjustment_history == '[]'
    assert bpy.ops.ed.redo() == {'FINISHED'}
    scene = bpy.data.scenes[name]
    assert scene.gnm_markers[0].tissue_depth_mm == 6.
    assert scene.gnm_markers[0].tissue_source == 'legacy-unvalidated'
    bpy.context.window.scene = bpy.data.scenes[previous]
    bpy.data.scenes.remove(scene)
    print('BLENDER_TISSUE_UNDO_PASS')

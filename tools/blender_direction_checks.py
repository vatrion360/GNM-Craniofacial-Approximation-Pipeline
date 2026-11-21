"""Actual Blender source-direction transaction; synthetic geometry and depths only."""
import json
import os
from pathlib import Path
import tempfile
import bpy
import numpy as np
from blender_tissue_checks import make_scene


def run_direction_checks(addon):
    previous = bpy.context.window.scene.name
    scene = make_scene(addon, 'Source directions')
    name = scene.name
    tissue = addon._core_module('tissue')
    adapter = addon._core_module('blender_tissue')
    normals = addon._core_module('blender_marker_normals')
    with tempfile.TemporaryDirectory() as directory:
        table_path, path = Path(directory)/'table.json', Path(directory)/'directions.json'
        table = tissue.empty_table('synthetic_direction')
        table['landmarks']['Nasion'] = dict(central_mm=4., measurement_direction='vertical')
        tissue.write_table(table_path, table)
        try:
            settings = scene.gnm_settings
            assert settings.tissue_axis_mode == 'EXISTING' and not settings.tissue_source_reviewed
            settings.tissue_table, settings.tissue_table_path = 'FILE', str(table_path)
            settings.tissue_axis_mode, settings.tissue_directions_path = 'SOURCE', str(path)
            item = scene.gnm_markers[0]
            before_target = np.array(item.target_empty.matrix_world.translation)
            scene.gnm_markers[1].adjust_depth_selected = True
            try:
                assert bpy.ops.gnm.create_direction_template() == {'CANCELLED'}
            except RuntimeError as exc:
                assert 'Rhinion: absent from tissue table' in str(exc)
            assert not path.exists() and item.depth_adjustment_history == '[]'
            scene.gnm_markers[1].adjust_depth_selected = False
            assert bpy.ops.gnm.create_direction_template() == {'FINISHED'}
            raw = path.read_bytes()
            manifest = json.loads(raw)
            assert set(manifest['landmarks']) == {'Nasion'}
            row = manifest['landmarks']['Nasion']
            assert row['bone_xyz_mm'] == list(item.bone_empty.matrix_world.translation)
            assert row['axis_world'] is None and row['reviewed'] is False
            assert row['measurement_direction'] == 'vertical'
            assert row['bone_source_geometry_sha256'] is None
            assert manifest['table_sha256s'] == [tissue.load_table(table_path).sha256]
            assert manifest['frame']['vertical_world'] is None and not manifest['frame']['reviewed']
            assert not settings.tissue_source_reviewed and item.depth_adjustment_history == '[]'
            if os.environ.get('GNM_MODEL_PATH'):
                scene.gnm_live.npz_path = os.environ['GNM_MODEL_PATH']
                csv = Path(directory)/'template-input.csv'
                addon._export_markers(scene, str(csv))
                cli = addon._core_module('tissue_directions')
                assert manifest == cli.make_template(csv, tissue.load_table(table_path), ['Nasion'])
            try:
                assert bpy.ops.gnm.create_direction_template() == {'CANCELLED'}
            except RuntimeError as exc:
                assert 'already exists' in str(exc)
            assert path.read_bytes() == raw
            # Even an acknowledged template has no reviewed source direction.
            settings.tissue_source_reviewed = True
            try:
                assert bpy.ops.gnm.apply_tissue_table() == {'CANCELLED'}
            except RuntimeError as exc:
                assert 'reviewed=true' in str(exc)
            assert item.depth_adjustment_history == '[]'
            np.testing.assert_array_equal(item.target_empty.matrix_world.translation, before_target)
            settings.tissue_source_reviewed = False
            manifest['frame'].update(vertical_world=[1.,0.,0.], reviewed=True,
                                     definition='Synthetic case vertical, not scene Z')
            row.update(axis_world=[1.,0.,0.], reviewed=True, definition='Synthetic test direction')
            path.write_text(json.dumps(manifest), encoding='utf-8')
            try:
                adapter.apply_selected_table(addon, bpy.context, table_path, direction_source=path)
            except ValueError as exc:
                assert 'Review' in str(exc)
            else:
                raise AssertionError('Unacknowledged source directions accepted')
            np.testing.assert_array_equal(item.target_empty.matrix_world.translation, before_target)
            settings.tissue_source_reviewed = True
            bpy.ops.ed.undo_push(message='Before source directions')
            assert bpy.ops.gnm.apply_tissue_table() == {'FINISHED'}
            bpy.context.view_layer.update()
            np.testing.assert_allclose(item.target_empty.matrix_world.translation, [4.,3.,4.], atol=2e-6)
            np.testing.assert_array_equal(item.bone_empty.matrix_world.translation, [0.,3.,4.])
            assert scene.gnm_markers[1].tissue_depth_mm == 10.
            record = json.loads(item.depth_adjustment_history)[-1]
            assert record['application']['source_direction_enforced']
            assert record['replacement']['source_direction']['measurement_direction'] == 'vertical'
            bpy.ops.ed.undo_push(message='After source directions')
            assert bpy.ops.ed.undo() == {'FINISHED'}
            scene = bpy.data.scenes[name]
            item = scene.gnm_markers[0]
            assert item.tissue_depth_mm == 10. and item.depth_adjustment_history == '[]'
            np.testing.assert_allclose(item.target_empty.matrix_world.translation, before_target, atol=2e-6)
            assert bpy.ops.ed.redo() == {'FINISHED'}
            scene = bpy.data.scenes[name]
            item = scene.gnm_markers[0]
            np.testing.assert_allclose(item.target_empty.matrix_world.translation, [4.,3.,4.], atol=2e-6)
            # Geometry failure after mutation must restore direction, transforms and audit.
            before = (item.tissue_depth_mm, item.tissue_source, item.depth_adjustment_history,
                      list(item.bone_empty['gnm_normal']))
            matrices = [obj.matrix_world.copy() for obj in (item.bone_empty,item.target_empty,item.peg_object)]
            manifest['landmarks']['Nasion']['axis_world'] = [-1.,0.,0.]
            path.write_text(json.dumps(manifest))
            original = normals.set_direction
            def fail(*args):
                original(*args)
                raise ValueError('injected direction failure')
            normals.set_direction = fail
            try:
                try:
                    adapter.apply_selected_table(addon, bpy.context, table_path,
                                                 direction_source=path, source_acknowledged=True)
                except ValueError as exc:
                    assert 'injected direction failure' in str(exc)
                else:
                    raise AssertionError('Direction failure did not roll back')
            finally:
                normals.set_direction = original
            bpy.context.view_layer.update()
            assert before == (item.tissue_depth_mm,item.tissue_source,item.depth_adjustment_history,list(item.bone_empty['gnm_normal']))
            for obj,matrix in zip((item.bone_empty,item.target_empty,item.peg_object),matrices):
                np.testing.assert_allclose(obj.matrix_world,matrix,atol=2e-6)
            assert not addon._MARKER_DEPTH_BATCH
            if os.environ.get('GNM_MODEL_PATH'):
                scene.gnm_live.npz_path = os.environ['GNM_MODEL_PATH']
                csv = Path(directory)/'case.csv'
                addon._export_markers(scene, str(csv))
                _, _, meta = addon._core_module('io_csv').read_marker_csv(csv, {}, {})
                assert meta['marker_depth_adjustments']['Nasion'][-1]['application']['source_direction_enforced']
                assert meta['marker_records']['Nasion']['target_xyz_mm'] == [4.,3.,4.]
            # Zero current depth must use the manifest, not an old endpoint axis.
            item.tissue_depth_mm = 0.
            bpy.context.view_layer.update()
            assert adapter.apply_selected_table(addon,bpy.context,table_path,
                direction_source=path,source_acknowledged=True) == 1
            bpy.context.view_layer.update()
            np.testing.assert_allclose(item.target_empty.matrix_world.translation, [-4.,3.,4.], atol=2e-6)
            # With a registered source hash, changed evaluated geometry must fail.
            mesh = bpy.data.meshes.new('Direction test surface')
            mesh.from_pydata([(0,0,0),(10,0,0),(0,10,0)], [], [(0,1,2)])
            obj = bpy.data.objects.new('Direction test bone', mesh)
            scene.collection.objects.link(obj)
            row = scene.gnm_bone_sources.add()
            row.uid, row.enabled, row.source_object = 'direction_source', True, obj
            bpy.context.view_layer.update()
            digest = addon._core_module('blender_sources').evaluated_geometry(obj, bpy.context.evaluated_depsgraph_get())[2]
            item.bone_empty['gnm_bone_source_id'] = row.uid
            item.bone_empty['gnm_source_sha256_at_placement'] = digest
            manifest['landmarks']['Nasion']['bone_source_geometry_sha256'] = digest
            path.write_text(json.dumps(manifest))
            assert adapter.apply_selected_table(addon,bpy.context,table_path,
                direction_source=path,source_acknowledged=True) == 1
            output = Path(directory)/'repere-revizuite.json'
            settings = scene.gnm_settings  # Undo/Redo replaced the original RNA.
            settings.tissue_directions_path = str(output)
            item.use_for_fit = False
            assert bpy.ops.gnm.create_direction_template() == {'FINISHED'}
            template_row = json.loads(output.read_bytes())['landmarks']['Nasion']
            assert template_row['bone_source_geometry_sha256'] == digest
            assert not item.use_for_fit and template_row['axis_world'] is None
            output.unlink()
            scene.unit_settings.scale_length = 1.
            try:
                assert bpy.ops.gnm.create_direction_template() == {'CANCELLED'}
            except RuntimeError as exc:
                assert 'scale 0.001' in str(exc)
            assert not output.exists()
            scene.unit_settings.scale_length = .001
            before = np.array(item.target_empty.matrix_world.translation)
            obj.location.x = 1.
            bpy.context.view_layer.update()
            try:
                adapter.apply_selected_table(addon,bpy.context,table_path,
                    direction_source=path,source_acknowledged=True)
            except ValueError as exc:
                assert 'source changed' in str(exc)
            else:
                raise AssertionError('Changed source geometry accepted')
            np.testing.assert_array_equal(item.target_empty.matrix_world.translation, before)
            try:
                assert bpy.ops.gnm.create_direction_template() == {'CANCELLED'}
            except RuntimeError as exc:
                assert 'source changed' in str(exc)
            assert not output.exists()
            print('BLENDER_DIRECTION_TEMPLATE_PASS')
            print('BLENDER_TISSUE_SOURCE_DIRECTIONS_PASS')
        finally:
            bpy.context.window.scene = bpy.data.scenes[previous]
            bpy.data.scenes.remove(bpy.data.scenes[name])

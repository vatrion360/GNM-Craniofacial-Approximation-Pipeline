"""Run in Blender 4.2+: blender --background --factory-startup --python-exit-code 1 --python tools/blender_smoke.py.

Tests the actual ZIP namespace, registration, tissue updates, v3 export and
cleanup. Set GNM_MODEL_PATH to also exercise model loading and marker export.
Set GNM_EXTERNAL_PYTHON to test the external fitting/import/cancellation path.
This is an engineering smoke check, not a visual/anatomical validation.
"""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import zipfile

import bpy

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tools'))
from blender_fragment_checks import run_fragment_checks, run_lambda_checks

archive = root / 'dist' / 'gnm_cranio-5.0.0rc3.zip'
with tempfile.TemporaryDirectory() as directory:
    with zipfile.ZipFile(archive) as z:
        z.extractall(directory)
    sys.path.insert(0, directory)
    addon = importlib.import_module('gnm_cranio')
    for _ in range(2):
        addon.register()
        assert hasattr(bpy.context.scene, 'gnm_markers')
        addon.unregister()
        assert not hasattr(bpy.types.Scene, 'gnm_markers')
    addon.register()
    try:
        run_fragment_checks(addon)
        scene = bpy.context.scene
        scene.unit_settings.system = 'METRIC'
        scene.unit_settings.scale_length = .001
        scene.gnm_settings.marker_set = 'LEGACY_27'
        assert bpy.ops.gnm.init_markers() == {'FINISHED'}
        assert len(scene.gnm_markers) == 27
        item = scene.gnm_markers[0]
        for attr, position in [('bone_empty', (0, 0, 0)), ('target_empty', (0, 0, 6))]:
            obj = bpy.data.objects.new(attr, None)
            scene.collection.objects.link(obj)
            obj.location = position
            setattr(item, attr, obj)
        bpy.context.view_layer.update()
        item.tissue_depth_mm = 8
        bpy.context.view_layer.update()
        assert abs(item.target_empty.matrix_world.translation.z - 8) < 1e-5
        item.gnm_vertex_override = 12310
        bone_name = item.bone_empty.name
        scene.gnm_settings.marker_set = 'EXTENDED_48'
        assert bpy.ops.gnm.init_markers() == {'FINISHED'}
        assert len(scene.gnm_markers) == 48
        item = scene.gnm_markers[0]
        assert item.bone_empty.name == bone_name and item.tissue_depth_mm == 8
        assert item.gnm_vertex_override == 12310
        assert bpy.ops.gnm.init_markers() == {'FINISHED'}
        assert len(scene.gnm_markers) == 48
        paper_scene = bpy.data.scenes.new('Paper 32')
        paper_scene.gnm_settings.marker_set = 'PAPER_32'
        with bpy.context.temp_override(scene=paper_scene):
            assert bpy.ops.gnm.init_markers() == {'FINISHED'}
        assert len(paper_scene.gnm_markers) == 32
        paper = addon._core_module('paper_reference')
        for marker in paper_scene.gnm_markers:
            assert marker.tissue_depth_mm == paper.PAPER_DEPTHS[marker.label]
            assert paper.DOI in marker.tissue_source
        if os.environ.get('GNM_MODEL_PATH'):
            scene.gnm_live.npz_path = os.environ['GNM_MODEL_PATH']
            model = addon._load_gnm_model(scene.gnm_live.npz_path)
            assert model.vertex_count == 17821
            item.gnm_vertex_override = 12310
            path = Path(directory) / 'test.csv'
            addon._export_markers(scene, str(path))
            backend = addon._core_module('backend').GNMBackend(scene.gnm_live.npz_path)
            targets, _, meta = addon._core_module('io_csv').read_marker_csv(path, backend.index_to_label,
                                                                          backend.landmark_vertex_map)
            assert targets[0].vertex == 12310
            assert meta['bone_positions_mm']['Nasion'] == [0, 0, 0]
            assert bpy.ops.gnm.apply_paper_tissues() == {'FINISHED'}
            bpy.context.view_layer.update()
            assert item.tissue_depth_mm == 7
            assert abs(item.target_empty.matrix_world.translation.z - 7) < 1e-5
            if os.environ.get('GNM_EXTERNAL_PYTHON'):
                # Synthetic mean targets test software plumbing, not anatomy.
                for marker in scene.gnm_markers:
                    marker.gnm_vertex_override = -1
                    marker.mapping_reviewed = True
                    marker.bone_status = 'observed'
                    target = model.mu[addon._resolve_vertex(marker)]
                    bone = target.copy()
                    bone[2] -= marker.tissue_depth_mm
                    for attr, position in [('bone_empty', bone), ('target_empty', target)]:
                        obj = getattr(marker, attr)
                        if obj is None:
                            obj = bpy.data.objects.new(marker.label + attr, None)
                            scene.collection.objects.link(obj)
                            setattr(marker, attr, obj)
                        obj.location = position.tolist()
                    marker.tissue_source = 'synthetic model mean; software test only'
                bpy.context.view_layer.update()
                run_lambda_checks(addon, scene, model)
                settings = scene.gnm_settings
                settings.case_directory = str(Path(directory) / 'caz sintetic șță')
                # The formerly accepted .py selection must fail before a case
                # directory/process is created, with a useful Windows remedy.
                settings.python_executable = str(root / 'gnm_reconstruct.py')
                try:
                    assert bpy.ops.gnm.run_offline() == {'CANCELLED'}
                except RuntimeError as exc:
                    assert 'not a Python executable' in str(exc)
                assert addon._OFFLINE['process'] is None
                assert not Path(settings.case_directory).exists()
                assert 'Scripts/python.exe' in settings.offline_status
                print('BLENDER_BAD_INTERPRETER_PREVENTED')
                settings.python_executable = os.environ['GNM_EXTERNAL_PYTHON']
                assert bpy.ops.gnm.check_python() == {'FINISHED'}
                assert 'numpy/scipy/trimesh OK' in settings.python_status
                for marker in scene.gnm_markers:
                    if marker.label == 'Vertex_VarfCap':
                        marker.use_for_fit = False
                assert len(addon._build_snapshot(scene)['labels']) == 47
                assert bpy.ops.gnm.run_offline() == {'FINISHED'}
                assert bpy.app.timers.is_registered(addon._offline_poll)
                folder = Path(addon._OFFLINE['folder'])
                deadline = time.monotonic() + 180
                while addon._OFFLINE['process'] is not None and time.monotonic() < deadline:
                    addon._offline_poll()
                    time.sleep(.05)
                if not settings.offline_status.startswith('Completed;'):
                    print((folder / 'run.log').read_text(encoding='utf-8'))
                    raise AssertionError(settings.offline_status)
                report = json.loads((folder / 'face_report.json').read_text(encoding='utf-8'))
                assert report['metrics']['final_fit']['rmse_mm'] < .01
                assert len(report['landmarks']) == 47
                assert abs(report['lambda'] - 48 / 47) < 1e-8
                assert not report['marker_metadata']['marker_records']['Vertex_VarfCap']['use_for_fit']
                imported = [obj for obj in scene.objects if obj.get('gnm_report') == str(folder / 'face_report.json')]
                assert len(imported) == 1 and len(imported[0].data.vertices) == model.vertex_count
                # Direct polling in this headless script does not unregister a
                # timer returning None, unlike Blender's event loop.
                if bpy.app.timers.is_registered(addon._offline_poll):
                    bpy.app.timers.unregister(addon._offline_poll)
                assert bpy.ops.gnm.run_offline() == {'FINISHED'}
                process = addon._OFFLINE['process']
                assert bpy.ops.gnm.cancel_offline() == {'FINISHED'}
                assert process.poll() is not None
                assert not bpy.app.timers.is_registered(addon._offline_poll)
                print('BLENDER_EXTERNAL_FIT_IMPORT_CANCEL_PASS')
            else:
                print('EXTERNAL FIT NOT TESTED: set GNM_EXTERNAL_PYTHON')
        else:
            print('MODEL LOAD/EXPORT NOT TESTED: set GNM_MODEL_PATH')
    finally:
        addon.unregister()
    assert not bpy.app.timers.is_registered(addon._offline_poll)
    assert not bpy.app.timers.is_registered(addon._live_timer_tick)
print('BLENDER_SMOKE_PASS')

"""Exercise the installed addon operator, actual CLI comparator, rollback and Undo."""
import json
import os
from pathlib import Path
import subprocess

import bpy
import numpy as np


def run_finalize_checks(addon, directory):
    previous = bpy.context.scene.name
    scene = bpy.data.scenes.new('Finalize synthetic fit')
    name = scene.name
    bpy.context.window.scene = scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = .001
    scene.gnm_live.npz_path = os.environ['GNM_MODEL_PATH']
    assert bpy.ops.gnm.load_live_model() == {'FINISHED'}
    model = addon._LIVE.model
    source = scene.objects[addon._case_name(addon.GNM_MESH_NAME, scene)]
    coords = addon._core_module('blender_postfit').coordinates
    original = coords(source.data.vertices)
    rng = np.random.default_rng(94)
    for label, vid in addon._label_to_vertex_map().items():
        row = scene.gnm_markers.add()
        row.label, row.gnm_vertex_override, row.mapping_reviewed = label, vid, True
        row.tissue_source = 'Synthetic integration fixture'
        xyz = model.mu[vid] + rng.normal(size=3)
        for key, point in [('target_empty', xyz), ('bone_empty', xyz-[0,0,row.tissue_depth_mm])]:
            obj = bpy.data.objects.new(label+key, None)
            scene.collection.objects.link(obj)
            obj.location = point
            setattr(row, key, obj)
    scene.gnm_settings.mandible_aligned = True
    bpy.context.view_layer.update()
    api = addon._core_module('blender_finalize')
    csv, face = Path(directory)/'finalize.csv', Path(directory)/'finalize-cli.obj'
    addon._export_markers(scene, csv)
    options = addon._core_module('external_python').process_options()
    cli = Path(addon.__file__).with_name('gnm_reconstruct.py')
    process = subprocess.run([os.environ['GNM_EXTERNAL_PYTHON'], str(cli), '--input', str(csv), '--npz',
        os.environ['GNM_MODEL_PATH'], '--output', str(face), '--regularization', 'adaptive','--local-correction'],
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120, **options)
    assert process.returncode == 0, process.stdout+process.stderr
    expected = np.array([line.split()[1:] for line in face.read_text().splitlines() if line.startswith('v ')], float)
    bpy.ops.ed.undo_push(message='Before GNM local finalize')
    assert bpy.ops.gnm.finalize_local() == {'FINISHED'}
    obj, = [o for o in scene.objects if o.get('gnm_local_finalize_record')]
    result_name = obj.name
    record = json.loads(obj['gnm_local_finalize_record'])
    actual = coords(obj.data.vertices)
    max_mm = np.linalg.norm(actual-expected, axis=1).max()
    assert max_mm <= .01, max_mm
    assert record['local_displacement']['max_mm'] > .01 and not obj.get('gnm_report')
    np.testing.assert_array_equal(coords(source.data.vertices), original)
    assert obj.data != source.data and record['model_sha256'] == addon._LIVE.model_hash
    assert np.array_equal(obj.matrix_world, np.eye(4))
    assert json.loads(obj['gnm_fit_state'])['model_to_local'] == record['model_to_world']
    # Invalid/stale placement and failure after a private mesh/object are allocated.
    marker = scene.gnm_markers[0]
    marker.bone_empty['gnm_bone_source_id'] = 'stale-source'
    counts = (len(bpy.data.objects), len(bpy.data.meshes))
    try:
        api.create(bpy.context, addon)
    except ValueError as exc:
        assert 'bound bone source' in str(exc)
    else:
        raise AssertionError('Accepted missing bound source')
    del marker.bone_empty['gnm_bone_source_id']
    bad = dict(record, invalid_value=float('nan'))
    try:
        api._publish(bpy.context, source, actual, bad)
    except ValueError:
        pass
    else:
        raise AssertionError('Published invalid provenance')
    assert counts == (len(bpy.data.objects), len(bpy.data.meshes))
    bpy.ops.ed.undo_push(message='After GNM local finalize')
    assert bpy.ops.ed.undo() == {'FINISHED'}
    assert result_name not in bpy.data.scenes[name].objects
    assert bpy.ops.ed.redo() == {'FINISHED'}
    restored = bpy.data.scenes[name].objects[result_name]
    np.testing.assert_array_equal(coords(restored.data.vertices), actual)
    assert restored['gnm_local_finalize_record'] == obj_record(record)
    bpy.context.window.scene = bpy.data.scenes[previous]
    bpy.data.scenes.remove(bpy.data.scenes[name])
    print(f'BLENDER_LOCAL_FINALIZE_PASS: vertices={len(actual)} max_cli_mm={max_mm:.12g}; rollback and undo/redo')


def obj_record(record):
    return json.dumps(record, allow_nan=False, separators=(',', ':'))

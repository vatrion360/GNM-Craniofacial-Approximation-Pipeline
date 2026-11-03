"""Actual Blender feature reference/export integration; synthetic geometry only."""
import json
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector


def run_feature_checks(addon, directory):
    previous = bpy.context.window.scene
    scene = bpy.data.scenes.new('Feature checks')
    bpy.context.window.scene = scene
    core = addon._core_module('features')
    cm = addon._core_module('blender_craniometry')
    try:
        scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', .001
        assert bpy.ops.gnm.craniometry(action='INIT') == {'FINISHED'}
        assert len(scene.gnm_cranial_points) == 22
        assert bpy.ops.gnm.craniometry(action='INIT_EXTENDED') == {'FINISHED'}
        assert len(scene.gnm_cranial_points) == 34
        assert bpy.ops.gnm.craniometry(action='INIT_FEATURES') == {'FINISHED'}
        assert bpy.ops.gnm.craniometry(action='INIT_FEATURES') == {'FINISHED'}
        assert len(scene.gnm_cranial_points) == 38 and not scene.gnm_markers
        assert len(scene.gnm_cranial_bindings) == 14
        mesh = bpy.data.meshes.new('Synthetic feature bone')
        mesh.from_pydata([(-100, -100, 0), (100, -100, 0), (0, 100, 0)], [], [(0, 1, 2)])
        obj = bpy.data.objects.new('Feature preserved bone', mesh)
        scene.collection.objects.link(obj)
        addon._register_bone_source(scene, obj)
        for code, xyz in dict(ba=(0, 0, 0), pr=(0, 0, 60), n=(0, 80, 0), go_R=(40, 0, 0), go_L=(-40, 0, 0)).items():
            scene.gnm_craniometry.active_point = next(i for i, p in enumerate(scene.gnm_cranial_points) if p.code == code)
            point = cm.selected_point(scene)
            cm.place_point(bpy.context, point, Vector(xyz), obj)
            assert bpy.ops.gnm.craniometry(action='REVIEW') == {'FINISHED'}
        points = {p.code: p for p in scene.gnm_cranial_points}
        before = {o.name: np.array(o.matrix_world) for o in scene.objects}
        config = core.empty_config()
        config['features']['gnathic_ratio'] = dict(reviewed=True, source='Synthetic ratio protocol',
            definition=dict(kind='ratio', points=['ba', 'pr', 'ba', 'n'], space='3d'))
        config['features']['bigonial_breadth'] = dict(reviewed=True, source='Synthetic width protocol',
            definition=dict(kind='distance', points=['go_R', 'go_L'], space='3d'))
        config['mandible_pose'] = dict(reviewed=True, source='Synthetic mandibular assembly')
        settings = scene.gnm_features
        cfg = Path(directory)/'feature-protocol.json'
        settings.config_path = str(cfg)
        assert bpy.ops.gnm.cranial_features(action='TEMPLATE') == {'FINISHED'}
        assert json.loads(cfg.read_text()) == core.empty_config()
        cfg.write_text(json.dumps(config), encoding='utf-8')
        settings.output_path = str(Path(directory)/'skull_features.json')
        try:
            result = bpy.ops.gnm.cranial_features(action='EXPORT')
        except RuntimeError as exc:
            assert 'mandibular articulation' in str(exc)
        else:
            assert result == {'CANCELLED'}
        assert not Path(settings.output_path).exists()
        scene.gnm_settings.mandible_aligned = True
        assert bpy.ops.gnm.cranial_features(action='EXPORT') == {'FINISHED'}
        result = json.loads(Path(settings.output_path).read_text())
        assert result['features']['gnathic_ratio']['value'] == .75
        assert result['features']['bigonial_breadth']['value'] == 80
        assert result['features']['anb_angle']['status'] == 'not_configured'
        assert result['features']['bigonial_breadth']['classification']['status'] == 'no_thresholds_configured'
        saved = Path(settings.output_path).read_bytes()
        try:
            result = bpy.ops.gnm.cranial_features(action='EXPORT')
        except RuntimeError as exc:
            assert 'Output exists' in str(exc)
        else:
            assert result == {'CANCELLED'}
        assert Path(settings.output_path).read_bytes() == saved
        points['go_L'].bone_status = 'reconstructed'
        settings.output_path = str(Path(directory)/'partial-skull-features.json')
        assert bpy.ops.gnm.cranial_features(action='EXPORT') == {'FINISHED'}
        result = json.loads(Path(settings.output_path).read_text())
        assert result['features']['gnathic_ratio']['value'] == .75
        assert result['features']['bigonial_breadth']['status'] == 'unavailable'
        points['pr'].bone_empty.location.z += 1
        bpy.context.view_layer.update()
        settings.output_path = str(Path(directory)/'moved-feature.json')
        assert bpy.ops.gnm.cranial_features(action='EXPORT') == {'FINISHED'}
        result = json.loads(Path(settings.output_path).read_text())
        assert result['features']['gnathic_ratio']['status'] == 'unavailable'
        points['pr'].bone_empty.location.z -= 1
        bpy.context.view_layer.update()
        for name, matrix in before.items():
            np.testing.assert_array_equal(np.array(scene.objects[name].matrix_world), matrix)
        assert not scene.gnm_markers
        assert 'GNM_Cranial_Features' in bpy.data.texts
        doc = cm.document(scene)
        rows = {p['code']: p for p in doc['points']}
        assert rows['pr']['fit_target'] is False and rows['pr']['existing_marker'] == 'Prosthion_BuzaSup'
        print('BLENDER_FEATURES_PASS: 22/34/38 opt-in, review, pose gate, partial anatomy, safe export, unchanged geometry')
    finally:
        addon._stop_live()
        bpy.context.window.scene = previous
        for obj in list(scene.objects): bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(scene)

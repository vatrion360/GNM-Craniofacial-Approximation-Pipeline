"""Exercise real ray hits and both measurement sessions in the installed addon."""
import json
from pathlib import Path
import tempfile

import bpy
from mathutils import Vector


def run_repeatability_checks(addon):
    api = addon._core_module('blender_repeatability')
    old = bpy.context.scene
    case = bpy.data.scenes.new('Repeat fixture')
    bpy.context.window.scene = case
    mesh = bpy.data.meshes.new('Synthetic bone')
    mesh.from_pydata([(0,0,0),(10,0,0),(0,10,0)],[],[(0,1,2)])
    mesh.update()
    bone = bpy.data.objects.new('Observed repeat triangle',mesh)
    case.collection.objects.link(bone)
    try:
        case.unit_settings.system = 'METRIC'
        case.unit_settings.scale_length = .001
        for label in ('Nasion','Glabella','Menton'):
            case.gnm_markers.add().label = label
        assert not case.gnm_show_repeats and not case.gnm_repeat_state
        case.gnm_settings.observer_id = 'fixture-observer'
        src = addon._register_bone_source(case,bone)
        bpy.context.view_layer.update()
        def action(k):
            return bpy.ops.gnm.repeat_session(action=k)
        def pick(x,y):
            _,session,_,label = api._pick_context(bpy.context)
            api.pick_ray(bpy.context,Vector((x,y,10)),Vector((0,0,-1)),(session['id'],label))
        assert action('START_A')=={'FINISHED'}
        assert action('FINISH_A')=={'CANCELLED'}
        state_before = case.gnm_repeat_state
        try:
            pick(25,25)
        except ValueError as exc:
            assert 'visible registered' in str(exc)
        else:
            raise AssertionError('Missed ray unexpectedly recorded')
        assert case.gnm_repeat_state==state_before
        pick(1,1)
        pick(2,2)
        # A miss and a pose change never publish a completed session.
        bone.location.x = 1.
        bpy.context.view_layer.update()
        assert action('FINISH_A')=={'CANCELLED'}
        bone.location.x = 0.
        bpy.context.view_layer.update()
        assert action('FINISH_A')=={'FINISHED'}
        case.gnm_settings.observer_id = 'other'
        assert action('START_B')=={'CANCELLED'}
        case.gnm_settings.observer_id = 'fixture-observer'
        assert action('START_B')=={'FINISHED'}
        assert api._read(case)['B']['points']=={} and case.gnm_marker_active_index==0
        pick(4,5)
        assert action('FINISH_B')=={'FINISHED'}
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'placement_error.json'
            assert bpy.ops.gnm.repeat_export(filepath=str(path))=={'FINISHED'}
            old_data = path.read_bytes()
            assert bpy.ops.gnm.repeat_export(filepath=str(path))=={'CANCELLED'} and old_data==path.read_bytes()
            r=json.loads(old_data)
            assert r['compared']==1 and r['requested']==3
            assert abs(r['landmarks']['Nasion']['distance_mm']-5.)<1e-5
            assert r['landmarks']['Glabella']['status']=='missing_B'
            assert r['landmarks']['Menton']['status']=='missing_both'
            assert r['sessions']['A']['points']['Nasion']['source_id']==src.uid
        assert len(case.objects)==1 and all(not m.bone_empty and not m.target_empty for m in case.gnm_markers)
        assert action('RESET')=={'FINISHED'} and not case.gnm_repeat_state
        print('BLENDER_PAIRED_REPEATABILITY_PASS: two independent ray captures, 5 mm known distance, changed-pose/observer refusal, no fit markers')
    finally:
        bpy.context.window.scene=old
        bpy.data.scenes.remove(case)
        bpy.data.objects.remove(bone,do_unlink=True)
        bpy.data.meshes.remove(mesh)

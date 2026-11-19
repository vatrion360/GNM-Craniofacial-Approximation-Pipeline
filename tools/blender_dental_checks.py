"""Installed add-on checks for original-bone capture and explicit saved-file actions."""
import json
from pathlib import Path

import bpy


def run_dental_pick(addon):
    old = bpy.context.scene
    scene = bpy.data.scenes.new('C2 dental pick fixture')
    bpy.context.window.scene = scene
    block = None
    mesh = bpy.data.meshes.new('C2 preserved triangle')
    obj = bpy.data.objects.new('C2 upper fragment', mesh)
    try:
        scene.unit_settings.system,scene.unit_settings.scale_length='METRIC',.001
        scene.gnm_settings.case_id='C2-synthetic'
        mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
        mesh.update()
        obj.location=(10,20,30)
        scene.collection.objects.link(obj)
        row=addon._register_bone_source(scene,obj)
        bpy.context.view_layer.objects.active=obj
        bpy.context.view_layer.update()
        for v in mesh.vertices: v.select=v.index==1
        op=bpy.ops.gnm.dental_consistency
        assert not scene.gnm_record.show_dental
        assert op(action='PICK')=={'CANCELLED'}
        assert bpy.ops.gnm.surface_origin(action='ORIGINAL')=={'FINISHED'}
        assert op(action='PICK')=={'FINISHED'}
        block=bpy.data.texts[scene.gnm_record.dental_status.split(': ',1)[1]]
        pick=json.loads(block.as_string())
        assert pick['case_id']=='C2-synthetic' and pick['source_id']==row.uid
        assert pick['xyz_mm']==[11,20,30] and len(pick['geometry_sha256'])==64
        print('BLENDER_DENTAL_PICK_PASS')
    finally:
        bpy.context.window.scene=old
        if block: bpy.data.texts.remove(block)
        bpy.data.scenes.remove(scene)
        bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.meshes.remove(mesh)


def run_saved_dental(scene, directory, source_folder):
    s=scene.gnm_record
    block=None
    old=(s.report_path,s.artifacts_path,s.dental_sites,s.dental_output,s.dental_status)
    try:
        s.report_path=str(Path(source_folder)/'face_report.json')
        s.artifacts_path=str(source_folder)
        s.dental_sites=str(Path(directory)/'dental-sites.json')
        s.dental_output=str(Path(directory)/'dental-report.json')
        op=bpy.ops.gnm.dental_consistency
        assert op(action='TEMPLATE')=={'FINISHED'}
        assert op(action='COMPARE')=={'FINISHED'}
        block=bpy.data.texts[s.dental_status.split('Text Editor: ',1)[1]]
        assert 'Measured 0/12 sites.' in block.as_string()
        r=json.loads(Path(s.dental_output).read_text())
        assert r['summary']['final']['measured']==0 and r['summary']['final']['mean_tooth_distance_mm'] is None
        assert op(action='COMPARE')=={'CANCELLED'}
        print('BLENDER_DENTAL_SAVED_FIT_PASS')
    finally:
        if block: bpy.data.texts.remove(block)
        s.report_path,s.artifacts_path,s.dental_sites,s.dental_output,s.dental_status=old

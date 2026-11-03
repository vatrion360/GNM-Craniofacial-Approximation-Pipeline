"""Actual Blender scenario export on synthetic coordinates; no scene mutation."""
import json
from pathlib import Path
import bpy
import numpy as np


def run_sensitivity_checks(addon,directory):
    previous=bpy.context.window.scene
    scene=bpy.data.scenes.new('Sensitivity test')
    bpy.context.window.scene=scene
    cm=addon._core_module('blender_craniometry')
    core=addon._core_module('sensitivity')
    try:
        scene.unit_settings.system,scene.unit_settings.scale_length='METRIC',.001
        scene.gnm_settings.case_id='synthetic-blender-sensitivity'
        scene.gnm_settings.mandible_aligned=True
        cm.initialize(scene,features=True)
        mesh=bpy.data.meshes.new('Synthetic mandible')
        mesh.from_pydata([(0,0,0),(100,0,0),(0,100,0)],[],[(0,1,2)])
        obj=bpy.data.objects.new('Observed test mandible',mesh)
        scene.collection.objects.link(obj)
        source=addon._register_bone_source(scene,obj)
        source.anatomy='MANDIBLE'
        digest=addon._source_manifest(scene,bpy.context.evaluated_depsgraph_get())[0]['geometry_sha256']
        for code,xyz in [('go_R',(40,0,0)),('go_L',(-40,0,0))]:
            point=next(p for p in scene.gnm_cranial_points if p.code==code)
            empty=bpy.data.objects.new(code,None)
            scene.collection.objects.link(empty);empty.location=xyz
            point.bone_empty,point.source_id,point.source_sha256=empty,source.uid,digest
            point.bone_status,point.review_xyz='observed',xyz
            point.definition_text,point.definition_source='Synthetic reference','Synthetic protocol'
            point.definition_reviewed=True
        bpy.context.view_layer.update()
        config=core.empty_config()
        config.update(case_id=scene.gnm_settings.case_id,reviewed=True,source='Synthetic scenario',
            moving_sources=[dict(id=source.uid,geometry_sha256=digest)],pivot_mm=[0,0,0],axes_world=np.eye(3).tolist(),
            translation_mm=[[-1,1],[0,0],[0,0]],rotation_deg=[[0,0]]*3,samples=2,seed=46)
        fc=config['feature_config']
        fc['mandible_pose']=dict(reviewed=True,source='Synthetic baseline assumption')
        fc['features']['bigonial_breadth']=dict(reviewed=True,source='Synthetic chord',
            definition=dict(kind='distance',points=['go_R','go_L'],space='3d'))
        st=scene.gnm_sensitivity
        st.config_path=str(Path(directory)/'sensitivity_config.json')
        st.output_path=str(Path(directory)/'sensitivity.json')
        assert bpy.ops.gnm.pose_sensitivity(action='TEMPLATE')=={'FINISHED'}
        assert json.loads(Path(st.config_path).read_text())==core.empty_config()
        Path(st.config_path).write_text(json.dumps(config),encoding='utf-8')
        before={o.name:np.asarray(o.matrix_world).copy() for o in scene.objects}
        before_doc=cm.document(scene,include_frame=False)
        assert bpy.ops.gnm.pose_sensitivity(action='EXPORT')=={'FINISHED'}
        result=json.loads(Path(st.output_path).read_text())
        assert result['features']['bigonial_breadth']['sampled_range']==[80.,80.]
        assert len(result['poses'])==5
        assert result['features']['bigonial_breadth']['classification']['status']=='no_thresholds_configured'
        for obj in scene.objects:
            np.testing.assert_array_equal(np.asarray(obj.matrix_world),before[obj.name])
        assert cm.document(scene,include_frame=False)==before_doc
        assert 'GNM_Pose_Sensitivity' in bpy.data.texts
        saved=Path(st.output_path).read_bytes()
        try:
            bpy.ops.gnm.pose_sensitivity(action='EXPORT')
        except RuntimeError as exc:
            assert 'Output exists' in str(exc)
        else:
            raise AssertionError('Existing output overwritten')
        assert Path(st.output_path).read_bytes()==saved
        scene.gnm_settings.mandible_aligned=False
        st.output_path=str(Path(directory)/'unreviewed-sensitivity.json')
        try:
            bpy.ops.gnm.pose_sensitivity(action='EXPORT')
        except RuntimeError as exc:
            assert 'baseline mandibular articulation' in str(exc)
        else:
            raise AssertionError('Unreviewed baseline accepted')
        assert not Path(st.output_path).exists()
        print('BLENDER_SENSITIVITY_PASS: template, ranges, missing thresholds, review gate, unchanged scene, safe export')
    finally:
        addon._gnm_live_on_load_post(None)
        bpy.context.window.scene=previous
        for obj in list(scene.objects):
            bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.scenes.remove(scene)

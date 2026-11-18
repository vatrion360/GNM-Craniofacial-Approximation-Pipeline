"""Installed-ZIP exercise: scenario preview, effective live/CSV rows and restoration."""
import json
import os
from pathlib import Path
import tempfile

import bpy


def run_scenario_checks(addon):
    old=bpy.context.scene
    scene=bpy.data.scenes.new('Guided fixture')
    bpy.context.window.scene=scene
    objects=[]
    mesh=bpy.data.meshes.new('Guided triangle')
    try:
        scene.unit_settings.system='METRIC'
        scene.unit_settings.scale_length=.001
        scene.gnm_settings.case_id='synthetic-guided'
        scene.gnm_settings.mandible_aligned=True
        mesh.from_pydata([(0,0,0),(10,0,0),(0,10,0)],[],[(0,1,2)])
        bone=bpy.data.objects.new('Preserved fixture',mesh)
        objects.append(bone)
        scene.collection.objects.link(bone)
        source=addon._register_bone_source(scene,bone)
        bpy.context.view_layer.update()
        digest=addon._core_module('blender_sources').source_geometry(bone,bpy.context.evaluated_depsgraph_get())[2]
        labels=['Nasion','Rhinion','Glabella','Gonion_St','Gonion_Dr','Menton']
        for i,label in enumerate(labels):
            m=scene.gnm_markers.add()
            m.label=label
            m.gnm_vertex_override=800+i
            m.bone_status='observed' if label!='Gonion_Dr' else 'inferred'
            m.use_for_fit=label!='Menton'
            m.fit_weight=.75
            for key,z in [('bone_empty',0),('target_empty',m.tissue_depth_mm)]:
                o=bpy.data.objects.new(label+key,None)
                objects.append(o)
                scene.collection.objects.link(o)
                o.location=(i,i*i,z)
                setattr(m,key,o)
            m.bone_empty['gnm_bone_source_id']=source.uid
            m.bone_empty['gnm_source_sha256_at_placement']=digest
        bpy.context.view_layer.update()
        def action(k):
            return bpy.ops.gnm.guided_case(action=k)
        def fit():
            snap=addon._build_snapshot(scene)
            return dict(zip(snap['labels'],snap['weights']))
        original=fit()
        assert not scene.gnm_show_guide and not scene.gnm_guide_active and len(original)==5
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            if os.environ.get('GNM_MODEL_PATH'):
                scene.gnm_live.npz_path=os.environ['GNM_MODEL_PATH']
                addon._export_markers(scene,folder/'before.csv')
            for key in ('complete','partial','no_mandible','deformed'):
                scene.gnm_guide_choice=key
                scene.gnm_guide_note='Synthetic preserved regions'
                assert action('APPLY')=={'CANCELLED'}
                assert action('PREVIEW')=={'FINISHED'} and fit()==original
                assert action('APPLY')=={'FINISHED'}
                used=fit()
                assert ('Gonion_St' in used)==(key!='no_mandible')
                assert 'Gonion_Dr' not in used and 'Menton' not in used
                assert action('CLEAR')=={'FINISHED'} and fit()==original
            path=folder/'custom.json'
            custom=dict(case_id=scene.gnm_settings.case_id,scenario='partial',weights={'Gonion_St':.25},
                        exclude=['Rhinion'],source='synthetic placement protocol',required_policy_ids=['region'])
            path.write_text(json.dumps(custom))
            scene.gnm_guide_choice='partial'
            scene.gnm_guide_file=str(path)
            assert action('PREVIEW')=={'FINISHED'}
            custom['weights']['Gonion_St']=.5
            path.write_text(json.dumps(custom))
            assert action('APPLY')=={'CANCELLED'} and fit()==original
            assert action('PREVIEW')=={'FINISHED'} and action('APPLY')=={'FINISHED'}
            path.unlink()  # live fit/export must use frozen rules, not re-open a case-supplied path
            used=fit()
            assert used['Gonion_St']==.5 and 'Rhinion' not in used
            assert all(m.fit_weight==.75 for m in scene.gnm_markers)
            if os.environ.get('GNM_MODEL_PATH'):
                addon._export_markers(scene,folder/'guided.csv')
                targets,_,metadata=addon._core_module('io_csv').read_marker_csv(folder/'guided.csv',{},{})
                assert {t.label:t.weight for t in targets}==used
                assert metadata['guided_scenario']['custom']==custom
                assert metadata['marker_records']['Gonion_St']['csv_base_weight']==.5
            assert action('CLEAR')=={'FINISHED'}
            if os.environ.get('GNM_MODEL_PATH'):
                addon._export_markers(scene,folder/'after.csv')
                assert (folder/'after.csv').read_bytes()==(folder/'before.csv').read_bytes()
        print('BLENDER_GUIDED_SCENARIOS_PASS: four profiles, mixed sides, frozen rules, live/CSV parity and clear restores defaults')
    finally:
        bpy.context.window.scene=old
        bpy.data.scenes.remove(scene)
        for o in objects:
            bpy.data.objects.remove(o,do_unlink=True)
        bpy.data.meshes.remove(mesh)

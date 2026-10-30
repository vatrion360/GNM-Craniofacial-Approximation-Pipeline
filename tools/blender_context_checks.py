"""Real RNA/CSV posture and estimator reporting; synthetic values only."""
import json
import os
from pathlib import Path
import tempfile
import bpy
import numpy as np
from blender_tissue_checks import make_scene


def run_context_checks(addon):
    previous=bpy.context.window.scene
    scene=make_scene(addon,'Tissue posture checks')
    tissue=addon._core_module('tissue')
    try:
        settings=scene.gnm_settings
        assert settings.acquisition_posture==''
        original=np.array(scene.gnm_markers[0].target_empty.matrix_world.translation)
        settings.acquisition_posture='supine'
        np.testing.assert_array_equal(scene.gnm_markers[0].target_empty.matrix_world.translation,original)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'table.json'
            doc=tissue.empty_table('synthetic_context')
            doc['posture']='upright'
            doc['landmarks']['Nasion']=dict(central_mm=4.,estimator='75-shormax')
            tissue.write_table(path,doc)
            settings.tissue_table='FILE'
            settings.tissue_table_path=str(path)
            settings.tissue_axis_existing=True
            assert bpy.ops.gnm.apply_tissue_table()=={'FINISHED'}
            bpy.context.view_layer.update()
            assert 'posture mismatch' in settings.tissue_status and '75-shormax: 1' in settings.tissue_status
            item=scene.gnm_markers[0]
            assert item.tissue_depth_mm==4.
            record=json.loads(item.depth_adjustment_history)[-1]['application']['context']
            assert record['table_posture']=='upright'
            assert record['case_posture']['value']=='supine'
            assert record['posture_comparison']=='different_labels'
            before=np.array(item.target_empty.matrix_world.translation)
            settings.acquisition_posture='upright'
            np.testing.assert_array_equal(item.target_empty.matrix_world.translation,before)
            # Application history records the old posture honestly; editing case metadata
            # cannot rewrite a past application. A new application records the new posture.
            assert json.loads(item.depth_adjustment_history)[-1]['application']['context']==record
            assert bpy.ops.gnm.apply_tissue_table()=={'FINISHED'}
            assert 'matching_labels' in settings.tissue_status
            np.testing.assert_allclose(item.target_empty.matrix_world.translation,before,atol=2e-6)
            if os.environ.get('GNM_MODEL_PATH'):
                scene.gnm_live.npz_path=os.environ['GNM_MODEL_PATH']
                csv=Path(directory)/'case.csv'
                addon._export_markers(scene,str(csv))
                _,_,meta=addon._core_module('io_csv').read_marker_csv(csv,{}, {})
                assert meta['acquisition_posture']=='upright'
                assert meta['marker_depth_adjustments']['Nasion'][-1]['application']['context']['posture_comparison']=='matching_labels'
            blend=Path(directory)/'posture.blend'
            bpy.data.libraries.write(str(blend),{scene})
            with bpy.data.libraries.load(str(blend)) as (source,destination):
                destination.scenes=source.scenes
            restored=destination.scenes[0]
            assert restored.gnm_settings.acquisition_posture=='upright'
            bpy.data.scenes.remove(restored)
        print('BLENDER_TISSUE_CONTEXT_PASS')
    finally:
        bpy.context.window.scene=previous
        bpy.data.scenes.remove(scene)

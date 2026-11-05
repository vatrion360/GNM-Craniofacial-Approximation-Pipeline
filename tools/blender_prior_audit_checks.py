"""Real Blender/external CLI integration with a synthetic, non-demographic prior."""
import json
from pathlib import Path
import time
import bpy
import numpy as np


def run_prior_audit_checks(addon, scene, model, directory):
    st, settings = scene.gnm_live, scene.gnm_settings
    fields=('prior_dir','prior_sex','prior_ethnicity','prior_justification')
    saved={key:getattr(st,key) for key in fields}
    initial_objects=set(scene.objects)
    targets=np.array([tuple(m.target_empty.matrix_world.translation) for m in scene.gnm_markers if m.is_placed])
    prior_dir=Path(directory)/'synthetic priors'
    prior_dir.mkdir()
    prior_path=prior_dir/'prior_FEMALE_WHITE.npz'
    np.savez(prior_path,mean=np.zeros(model.identity_dim),scale=np.ones(model.identity_dim))
    def wait():
        deadline=time.monotonic()+180
        while addon._OFFLINE['process'] is not None and time.monotonic()<deadline:
            addon._offline_poll()
            time.sleep(.05)
        assert addon._OFFLINE['process'] is None
        if bpy.app.timers.is_registered(addon._offline_poll):
            bpy.app.timers.unregister(addon._offline_poll)
    def rejected():
        before=set(Path(settings.case_directory).iterdir())
        try:
            assert bpy.ops.gnm.run_offline(prior_compare=True)=={'CANCELLED'}
        except RuntimeError:
            pass
        assert addon._OFFLINE['process'] is None
        assert set(Path(settings.case_directory).iterdir())==before
    try:
        assert st.prior_justification==''
        st.prior_sex='NONE'
        rejected()
        assert 'Select an explicit' in settings.offline_status
        st.prior_dir=str(prior_dir)
        st.prior_sex='FEMALE'
        st.prior_ethnicity='WHITE'
        rejected()
        assert 'justification' in settings.offline_status
        st.prior_justification='Scenariu sintetic — fără validare anatomică'
        bpy.context.view_layer.update()
        np.testing.assert_array_equal([tuple(m.target_empty.matrix_world.translation) for m in scene.gnm_markers if m.is_placed],targets)
        assert bpy.ops.gnm.run_offline(prior_compare=True)=={'FINISHED'}
        folder=Path(addon._OFFLINE['folder'])
        wait()
        assert settings.offline_status.startswith('Comparison completed;'),settings.offline_status
        bundle=folder/'face_prior_compare'
        summary=json.loads((bundle/'summary.json').read_text(encoding='utf-8'))
        assert summary['justification']==st.prior_justification
        assert summary['prior']['identity_subspace']=='head'
        assert summary['color_scale_max_mm']==0
        assert prior_path.read_bytes()==(folder/'selected_prior.npz').read_bytes()
        imported=[o for o in scene.objects if o.get('gnm_prior_comparison')==str(bundle/'summary.json')]
        assert len(imported)==2
        by_id={o['gnm_prior_scenario']:o for o in imported}
        assert by_id['neutral'].hide_viewport and by_id['neutral'].hide_render
        assert not by_id['prior'].hide_viewport and not by_id['prior'].hide_render
        for name,obj in by_id.items():
            report=json.loads(Path(obj['gnm_report']).read_text(encoding='utf-8'))
            assert bool(report['config']['prior'])==(name=='prior')
            assert len(obj.data.vertices)==model.vertex_count
            assert not any(report['identity_coefficients'][170:])
        assert initial_objects <= set(scene.objects)
        # A corrupted completed bundle must create no partial objects.
        (bundle/'prior/face.obj').write_text('bad',encoding='utf-8')
        before=set(scene.objects)
        try:
            addon._core_module('blender_prior_audit').import_comparison(scene,bundle)
        except ValueError:
            pass
        else:
            raise AssertionError('Corrupt bundle accepted')
        assert set(scene.objects)==before
        # Operator mode must not leak into the next ordinary fit.
        assert bpy.ops.gnm.run_offline()=={'FINISHED'}
        ordinary=Path(addon._OFFLINE['folder'])
        assert not addon._OFFLINE['prior_compare']
        wait()
        assert settings.offline_status.startswith('Completed;')
        report=json.loads((ordinary/'face_report.json').read_text(encoding='utf-8'))
        assert report['config']['prior_justification']==st.prior_justification
        assert not report['config']['prior_compare']
        # Saved scenes retain the operator's rationale, without fit callbacks.
        path=Path(directory)/'prior-rationale.blend'
        bpy.data.libraries.write(str(path),{scene})
        with bpy.data.libraries.load(str(path)) as (_,destination):
            destination.scenes=[scene.name]
        restored=destination.scenes[0]
        assert restored.gnm_live.prior_justification==st.prior_justification
        bpy.data.scenes.remove(restored)
        assert bpy.ops.gnm.run_offline(prior_compare=True)=={'FINISHED'}
        cancelled=Path(addon._OFFLINE['folder'])
        assert bpy.ops.gnm.cancel_offline()=={'FINISHED'}
        assert not (cancelled/'face_prior_compare'/'summary.json').exists()
        np.testing.assert_array_equal([tuple(m.target_empty.matrix_world.translation) for m in scene.gnm_markers if m.is_placed],targets)
        print('BLENDER_PRIOR_AUDIT_PASS')
    finally:
        addon._stop_offline()
        st.prior_sex='NONE'
        for key,value in saved.items():
            setattr(st,key,value)

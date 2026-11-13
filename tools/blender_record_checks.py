"""Actual ZIP/external record export, source immutability and lifecycle checks."""
import json
import hashlib
from pathlib import Path
import time

import bpy
import numpy as np


def run_record_checks(addon, scene, directory, source_folder, fitted):
    module = addon._core_module('blender_record')
    settings = scene.gnm_record
    original_active = bpy.context.view_layer.objects.active
    before_objects = set(scene.objects)
    vertices = np.array([tuple(v.co) for v in fitted.data.vertices])
    targets = np.array([tuple(m.target_empty.matrix_world.translation) for m in scene.gnm_markers if m.is_placed])
    before = {p: p.read_bytes() for p in Path(source_folder).iterdir() if p.is_file()}
    parent = Path(directory)/'registre șță & literal'
    limits = Path(directory)/'limite șță.json'
    limits.write_text(json.dumps(dict(schema_version=1, revision='synthetic-blender', approved=True,
        ro='Text sintetic — fără validare anatomică.', en='Synthetic text, not anatomical validation.'),
        ensure_ascii=False), encoding='utf-8')

    # Synthetic complete-only domain and a partial case exercise the banner;
    # this is a software fixture, not a declaration about the model-mean skull.
    domain_core = addon._core_module('validity_domain')
    raw_report = (Path(source_folder)/'face_report.json').read_bytes()
    report = json.loads(raw_report)
    domain = domain_core.empty_domain()
    domain.update(id='synthetic-blender-domain', revision='test-1', reviewed=True,
        model_sha256=report['inputs']['model']['sha256'], run_signatures=[domain_core.run_signature(report)],
        evidence=dict(reference='Synthetic software fixture, not CT evidence', sha256='a'*64, n_subjects=3),
        conditions={'skull_completeness': dict(definition='Synthetic completeness category',
                    allowed_values=['complete'], source='Synthetic fixture definition')})
    observations = domain_core.case_template(hashlib.sha256(raw_report).hexdigest(), domain)
    observations['observations']['skull_completeness'] = dict(value='partial', source='Synthetic test observation', reviewed=True)
    domain_path, observations_path = Path(directory)/'domain.json', Path(directory)/'domain-case.json'
    domain_path.write_text(json.dumps(domain), encoding='utf-8')
    observations_path.write_text(json.dumps(observations), encoding='utf-8')

    check_core = addon._core_module('check_policy')
    check_policy = check_core.empty_policy()
    check_policy.update(id='synthetic-count-policy', revision='test-1', reviewed=True, rules=[
        dict(id='synthetic-region', kind='marker_count', region='synthetic missing region',
             labels=['not-in-this-synthetic-fit'], minimum=1, on_fail='block',
             source='Synthetic software fixture, not anatomical evidence')])
    check_path = Path(directory)/'check-policy.json'
    check_path.write_text(json.dumps(check_policy), encoding='utf-8')

    def wait():
        deadline = time.monotonic()+90
        while module._JOB['process'] is not None and time.monotonic() < deadline:
            module.poll_job()
            time.sleep(.05)
        assert module._JOB['process'] is None
        if bpy.app.timers.is_registered(module.poll_job):
            bpy.app.timers.unregister(module.poll_job)

    def reject():
        try:
            assert bpy.ops.gnm.export_approximation_record() == {'CANCELLED'}
        except RuntimeError:
            pass
        assert module._JOB['process'] is None
        assert not parent.exists()

    try:
        assert settings.uncertainty_scenario == 'NONE'
        assert settings.report_path == settings.result_path == ''
        bpy.context.view_layer.objects.active = fitted
        assert bpy.ops.gnm.record_use_active() == {'FINISHED'}
        assert settings.report_path == fitted['gnm_report']
        settings.output_parent = str(parent)
        settings.limitations_path = str(limits)
        assert settings.validity_domain_path == settings.domain_case_path == ''
        settings.validity_domain_path = str(domain_path)
        settings.domain_case_path = str(observations_path)
        assert settings.check_policy_path == settings.check_override == ''
        settings.check_policy_path = str(check_path)
        settings.check_override = 'Synthetic diagnostic investigation; not approval'
        settings.uncertainty_scenario = 'off'
        reject()
        assert 'both an uncertainty JSON' in settings.status
        settings.uncertainty_scenario = 'NONE'
        python = scene.gnm_settings.python_executable
        scene.gnm_settings.python_executable = str(Path(addon.__file__).parent/'gnm_reconstruct.py')
        reject()
        assert 'not a Python executable' in settings.status
        scene.gnm_settings.python_executable = python
        assert bpy.ops.gnm.export_approximation_record() == {'FINISHED'}
        assert bpy.app.timers.is_registered(module.poll_job)
        assert not module.GNM_OT_record_export.poll(bpy.context)
        run_folder = Path(module._JOB['folder'])
        # The submitted request is independent of later edits to UI fields.
        saved_path = settings.report_path
        settings.report_path = str(Path(directory)/'not-the-submitted-report.json')
        wait()
        assert settings.status.startswith('Recorded;'), (settings.status, (run_folder/'run.log').read_text(encoding='utf-8'))
        settings.report_path = saved_path
        result = json.loads(Path(settings.result_path).read_text(encoding='utf-8'))
        assert result['status'] == 'diagnostic_only'
        assert result['assessments']['check_policy']['status'] == 'block'
        assert result['assessments']['check_policy']['gate']['status'] == 'overridden'
        assert 'CHECK POLICY: BLOCK' in settings.status
        assert '[CHECKS] CHECK POLICY: BLOCK' in bpy.data.texts[settings.result_text].as_string()
        print('BLENDER_EXPLICIT_CHECK_POLICY_PASS')
        assert result['assessments']['validity_domain']['status'] == 'outside_declared_domain'
        assert 'OUTSIDE DECLARED DOMAIN' in settings.status
        assert '[DOMAIN] OUTSIDE DECLARED DOMAIN' in bpy.data.texts[settings.result_text].as_string()
        print('BLENDER_DECLARED_VALIDITY_DOMAIN_BANNER_PASS')
        assert result['limitations']['document']['revision'] == 'synthetic-blender'
        assert 'fără validare' in bpy.data.texts[settings.result_text].as_string()
        first_text = settings.result_text
        assert before_objects == set(scene.objects)
        np.testing.assert_array_equal(vertices, [tuple(v.co) for v in fitted.data.vertices])
        np.testing.assert_array_equal(targets, [tuple(m.target_empty.matrix_world.translation) for m in scene.gnm_markers if m.is_placed])
        assert all(p.read_bytes() == data for p, data in before.items())
        # The same saved-fit job lifecycle supports explicit mesh-export modes.
        assert settings.export_mode == 'NONE'
        try:
            assert bpy.ops.gnm.export_approximation_record(bundle=True) == {'CANCELLED'}
        except RuntimeError:
            pass
        assert module._JOB['process'] is None
        old_reason = settings.check_override
        settings.check_override = ''
        settings.export_mode = 'scientific'
        assert bpy.ops.gnm.export_approximation_record(bundle=True) == {'FINISHED'}
        # UI edits cannot replace the submitted mode.
        settings.export_mode = 'illustrative'
        wait()
        blocked = json.loads(Path(settings.result_path).read_text(encoding='utf-8'))
        assert blocked['status'] == 'blocked' and blocked['mode'] == 'scientific'
        assert settings.status.startswith('SCIENTIFIC EXPORT BLOCKED')
        assert not (Path(settings.result_path).parent/'face.obj').exists()
        assert 'No face mesh was exported' in bpy.data.texts[settings.result_text].as_string()
        settings.export_mode = 'scientific'
        settings.check_override = old_reason
        assert bpy.ops.gnm.export_approximation_record(bundle=True) == {'FINISHED'}
        wait()
        decision = json.loads(Path(settings.result_path).read_text(encoding='utf-8'))
        assert decision['status'] == 'completed' and decision['check_gate']['status'] == 'overridden'
        assert settings.status.startswith('SCIENTIFIC EXPORT WITH RECORDED OVERRIDE')
        bundle = Path(settings.result_path).parent
        assert 'map_' not in (bundle/'face.mtl').read_text(encoding='utf-8')
        source_rows = [line for line in (Path(source_folder)/'face.obj').read_text(encoding='utf-8').splitlines()
                       if line.startswith(('v ', 'f '))]
        exported_rows = [line for line in (bundle/'face.obj').read_text(encoding='utf-8').splitlines()
                         if line.startswith(('v ', 'f '))]
        assert source_rows == exported_rows
        settings.export_mode = 'illustrative'
        settings.check_override = ''
        assert bpy.ops.gnm.export_approximation_record(bundle=True) == {'FINISHED'}
        wait()
        illustrative = json.loads(Path(settings.result_path).read_text(encoding='utf-8'))
        assert illustrative['mode'] == 'illustrative' and illustrative['status'] == 'completed'
        assert illustrative['check_gate']['proceed'] is False
        assert 'ILLUSTRATIVE' in bpy.data.texts[settings.result_text].as_string()
        assert before_objects == set(scene.objects)
        np.testing.assert_array_equal(vertices, [tuple(v.co) for v in fitted.data.vertices])
        np.testing.assert_array_equal(targets, [tuple(m.target_empty.matrix_world.translation) for m in scene.gnm_markers if m.is_placed])
        assert all(p.read_bytes() == data for p, data in before.items())
        assert bpy.ops.gnm.export_approximation_record(bundle=True) == {'FINISHED'}
        process = module._JOB['process']
        assert bpy.ops.gnm.cancel_record_export() == {'FINISHED'}
        assert process.poll() is not None
        settings.export_mode = 'NONE'
        settings.check_override = old_reason
        print('BLENDER_GATED_SAVED_FIT_EXPORT_PASS')
        # Explicit B4 diagnostics use only report/artifacts, not optional policy,
        # prior, ensemble or presentation settings. They never authorize export.
        assert bpy.ops.gnm.export_approximation_record(diagnostics=True) == {'FINISHED'}
        assert not module.GNM_OT_record_export.poll(bpy.context)
        diagnostic_folder = Path(module._JOB['folder'])
        settings.report_path = str(Path(directory)/'not-submitted-diagnostic-report.json')
        wait()
        assert settings.status.startswith('Consistency: '), (settings.status,
            (diagnostic_folder/'run.log').read_text(encoding='utf-8'))
        settings.report_path = saved_path
        diagnostic = json.loads((Path(settings.result_path).parent/'consistency.json').read_text(encoding='utf-8'))
        assert diagnostic['status'] in ('block', 'not_assessed')
        assert diagnostic['correction_applied'] is False
        assert diagnostic['stages']['final']['serialized_mesh_angles']['triangle_count'] == len(fitted.data.polygons)
        assert 'NOT ASSESSED:' in bpy.data.texts[settings.result_text].as_string()
        assert before_objects == set(scene.objects)
        np.testing.assert_array_equal(vertices, [tuple(v.co) for v in fitted.data.vertices])
        np.testing.assert_array_equal(targets, [tuple(m.target_empty.matrix_world.translation) for m in scene.gnm_markers if m.is_placed])
        assert all(p.read_bytes() == data for p, data in before.items())
        assert bpy.ops.gnm.export_approximation_record(diagnostics=True) == {'FINISHED'}
        process = module._JOB['process']
        assert bpy.ops.gnm.cancel_record_export() == {'FINISHED'}
        assert process.poll() is not None and not bpy.app.timers.is_registered(module.poll_job)
        print('BLENDER_SAVED_FIT_CONSISTENCY_PASS')
        # Worker rejection never creates another displayed report or mesh.
        face = Path(source_folder)/'face.obj'
        original = face.read_bytes()
        try:
            face.write_bytes(original+b'corrupt')
            assert bpy.ops.gnm.export_approximation_record() == {'FINISHED'}
            wait()
            assert settings.status.startswith('Failed ('), settings.status
            assert settings.result_path == settings.result_text == ''
            assert first_text in bpy.data.texts
        finally:
            face.write_bytes(original)
        assert bpy.ops.gnm.export_approximation_record() == {'FINISHED'}
        process = module._JOB['process']
        assert bpy.ops.gnm.cancel_record_export() == {'FINISHED'}
        assert process.poll() is not None
        assert not bpy.app.timers.is_registered(module.poll_job)
        assert settings.status.startswith('Stopped;')
        # A deleted scene must not deliver its result to a replacement of the same name.
        owner = bpy.data.scenes.new('Record temporary owner')
        name = owner.name
        owner.gnm_record.report_path = saved_path
        owner.gnm_record.output_parent = str(parent)
        owner.gnm_settings.python_executable = python
        bpy.context.window.scene = owner
        assert bpy.ops.gnm.export_approximation_record() == {'FINISHED'}
        process = module._JOB['process']
        bpy.context.window.scene = scene
        bpy.data.scenes.remove(owner)
        replacement = bpy.data.scenes.new(name)
        replacement_status = replacement.gnm_record.status
        module.poll_job()
        assert process.poll() is not None and module._JOB['process'] is None
        assert replacement.gnm_record.status == replacement_status
        assert not bpy.app.timers.is_registered(module.poll_job)
        bpy.data.scenes.remove(replacement)
        assert before_objects == set(scene.objects)
        print('BLENDER_APPROXIMATION_RECORD_EXPORT_CANCEL_LIFECYCLE_PASS')
    finally:
        module.stop()
        bpy.context.window.scene = scene
        bpy.context.view_layer.objects.active = original_active

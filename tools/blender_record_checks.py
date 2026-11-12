"""Actual ZIP/external record export, source immutability and lifecycle checks."""
import json
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
        assert result['status'] == 'recorded_not_validated'
        assert result['limitations']['document']['revision'] == 'synthetic-blender'
        assert 'fără validare' in bpy.data.texts[settings.result_text].as_string()
        first_text = settings.result_text
        assert before_objects == set(scene.objects)
        np.testing.assert_array_equal(vertices, [tuple(v.co) for v in fitted.data.vertices])
        np.testing.assert_array_equal(targets, [tuple(m.target_empty.matrix_world.translation) for m in scene.gnm_markers if m.is_placed])
        assert all(p.read_bytes() == data for p, data in before.items())
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

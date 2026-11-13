"""Actual installed-ZIP render, metric bar and parent-scene isolation checks."""
import json
from pathlib import Path
import shutil
import time

import bpy
import numpy as np


def run_capture_checks(addon, scene, directory, source_folder, fitted):
    core = addon._core_module('capture_plan')
    rf, cm = addon._core_module('reference_frame'), addon._core_module('craniometry')
    record = addon._core_module('record')
    exporter = addon._core_module('review_export')
    module = addon._core_module('blender_record')
    settings = scene.gnm_record
    fields = ('report_path', 'capture_bundle_path', 'output_parent', 'capture_resolution',
              'capture_bar_mm', 'capture_samples')
    original_settings = {key: getattr(settings, key) for key in fields}
    before_objects = set(scene.objects)
    vertices = np.array([tuple(v.co) for v in fitted.data.vertices])
    targets = np.array([tuple(m.target_empty.matrix_world.translation) for m in scene.gnm_markers if m.is_placed])
    before_camera = scene.camera
    before_render = (scene.render.engine, scene.render.resolution_x, scene.render.resolution_y, scene.render.filepath)
    before_sources = {p: p.read_bytes() for p in Path(source_folder).iterdir() if p.is_file()}
    fixture = Path(directory)/'capture fixture șță'
    shutil.copytree(source_folder, fixture)
    report_path = fixture/'face_report.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    # Synthetic observed references exercise software only, not anatomical truth.
    lines, _ = exporter.geometry_lines((fixture/'face.obj').read_bytes())
    positions = np.array([[float(v) for v in row.split()[1:]] for row in lines if row.startswith('v ')])
    centre = (positions.min(axis=0)+positions.max(axis=0))/2
    offsets = dict(po_R=[50, 0, 0], po_L=[-50, 0, 0], or_L=[-25, 60, 0],
                   n=[0, 60, 30], b=[0, 0, 80], op=[0, -65, 10])
    doc = cm.empty_document('Synthetic capture references, not anatomical evidence')
    doc['bone_sources'] = [dict(id='fixture', geometry_sha256='a'*64)]
    doc['points'] = [dict(code=code, xyz_mm=(centre+xyz).tolist(), status='observed',
        definition_reviewed=True, source_id='fixture', source_geometry_sha256='a'*64,
        definition_text='Synthetic definition', definition_source='Synthetic software fixture')
        for code, xyz in offsets.items()]
    config = dict(schema_version=1, orbitale='or_L', superior_code='b', midline_codes=['n', 'b', 'op'],
                  source='Synthetic software fixture', placement_error=None)
    doc['reference_frame'] = rf.compute_frame(doc, config)
    report['marker_metadata']['craniometry'] = doc
    report_path.write_bytes(record.canonical_bytes(report))
    policy = Path(directory)/'capture-policy.json'
    policy.write_text(json.dumps(addon._core_module('check_policy').empty_policy()), encoding='utf-8')
    bundle = Path(directory)/'capture-bundle'
    exporter.export_bundle(report_path, bundle, mode='scientific', check_policy_path=policy,
                           check_override='Synthetic capture smoke only; not scientific approval')
    _, _, _, pinned = core.load_inputs(report_path, bundle)
    try:
        settings.report_path = str(report_path)
        settings.capture_bundle_path = str(bundle/'export_decision.json')
        settings.output_parent = str(Path(directory)/'captures șță & literal')
        settings.capture_resolution, settings.capture_bar_mm, settings.capture_samples = 256, 50., 2
        assert bpy.ops.gnm.capture_saved_bundle() == {'FINISHED'}
        folder = Path(module._JOB['folder'])
        assert bpy.app.timers.is_registered(module.poll_job)
        assert not module.GNM_OT_capture_bundle.poll(bpy.context)
        # Later UI edits cannot replace the submitted capture request.
        settings.capture_bar_mm = 51.
        deadline = time.monotonic()+180
        while module._JOB['process'] is not None and time.monotonic() < deadline:
            module.poll_job()
            time.sleep(.05)
        log = (folder/'run.log').read_text(encoding='utf-8', errors='replace')
        assert module._JOB['process'] is None, log
        if bpy.app.timers.is_registered(module.poll_job):
            bpy.app.timers.unregister(module.poll_job)
        assert settings.status.startswith('Captures completed;'), (settings.status, log)
        manifest = json.loads(Path(settings.result_path).read_text(encoding='utf-8'))
        assert manifest['bar_mm'] == 50.
        assert manifest['export_mode'] == 'scientific'
        assert manifest['check_gate']['status'] == 'overridden'
        assert manifest['renderer']['textures'] is False
        assert 'OVERRIDE' in bpy.data.texts[settings.result_text].as_string()
        for view in manifest['views']:
            path = Path(settings.result_path).parent/(view['name']+'.png')
            image = bpy.data.images.load(str(path), check_existing=False)
            try:
                assert tuple(image.size) == (256, 256)
                pixels = np.empty(256*256*4, dtype=np.float32)
                image.pixels.foreach_get(pixels)
                rgb = pixels.reshape(256, 256, 4)[:, :, :3]
                assert np.isfinite(rgb).all() and np.ptp(rgb) > .5
                np.testing.assert_allclose(rgb[:, :, 0], rgb[:, :, 1], atol=.01)
                np.testing.assert_allclose(rgb[:, :, 1], rgb[:, :, 2], atol=.01)
                assert np.count_nonzero(rgb[48:208, 48:208].mean(axis=2) < .95) > 100
                # Blender pixel buffers start at the bottom. Sample inside the
                # actual bar quad, away from the footer text and facial surface.
                row = int((.5-.42+.004)*256)
                start = .1*256
                end = start+view['bar_length_pixels']
                lo, hi = max(0, int(start)-3), min(256, int(end)+4)
                dark = np.flatnonzero(rgb[row, lo:hi].mean(axis=1) < .3)+lo
                assert len(dark) > 0, (view['name'], rgb[row, lo:hi])
                assert abs((dark[-1]-dark[0]+1)-view['bar_length_pixels']) <= 3, (view, dark)
                assert abs(dark[0]-start) <= 2
            finally:
                bpy.data.images.remove(image)
        core.assert_unchanged(pinned)
        assert before_objects == set(scene.objects)
        assert before_camera == scene.camera
        assert before_render == (scene.render.engine, scene.render.resolution_x, scene.render.resolution_y, scene.render.filepath)
        np.testing.assert_array_equal(vertices, [tuple(v.co) for v in fitted.data.vertices])
        np.testing.assert_array_equal(targets, [tuple(m.target_empty.matrix_world.translation) for m in scene.gnm_markers if m.is_placed])
        assert all(p.read_bytes() == data for p, data in before_sources.items())
        assert bpy.ops.gnm.capture_saved_bundle() == {'FINISHED'}
        process = module._JOB['process']
        assert bpy.ops.gnm.cancel_record_export() == {'FINISHED'}
        assert process.poll() is not None
        assert not bpy.app.timers.is_registered(module.poll_job)
        print('BLENDER_STANDARDIZED_CAPTURE_RENDER_PASS')
    finally:
        module.stop()
        for key, value in original_settings.items():
            setattr(settings, key, value)

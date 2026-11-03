"""Real Blender option wiring/external import, synthetic constraints only."""
import json
from pathlib import Path
import time

import bpy
import numpy as np


def run_profile_options(addon, directory):
    previous = bpy.context.window.scene
    scene = bpy.data.scenes.new('Profile option checks')
    bpy.context.window.scene = scene
    try:
        settings = scene.gnm_settings
        assert settings.profile_enabled is False
        assert addon._profile_offline_arguments(scene) == []
        settings.profile_enabled = True
        try:
            addon._profile_offline_arguments(scene)
        except ValueError as exc:
            assert 'Select' in str(exc)
        else:
            raise AssertionError('Missing profile path accepted')
        path = Path(directory)/'blank-profile.json'
        path.write_text(json.dumps(addon._core_module('profile').empty_manifest()))
        settings.profile_path = str(path)
        assert addon._profile_offline_arguments(scene) == ['--profile-constraint', str(path)]
        for prop in ('offline_dense', 'local_correction'):
            setattr(settings, prop, True)
            try:
                addon._profile_offline_arguments(scene)
            except ValueError as exc:
                assert 'marker-only' in str(exc)
            else:
                raise AssertionError('Unsupported loss accepted')
            setattr(settings, prop, False)
        settings.profile_enabled = False
        settings.profile_path = '//missing.json'
        assert addon._profile_offline_arguments(scene) == []
        print('BLENDER_PROFILE_OPTIONS_PASS')
    finally:
        bpy.context.window.scene = previous
        bpy.data.scenes.remove(scene)


def run_profile_external(addon, scene, model, directory, baseline_report):
    settings = scene.gnm_settings
    old_case = settings.case_id
    path = Path(directory)/'synthetic-profile.json'
    mesh = bpy.data.meshes.new('Synthetic profile bone')
    # Endpoint IDs from the repository's reviewed map; neighbours here test only
    # segmented topology plumbing, not a supplied anatomical correspondence.
    endpoints = [12337, 12346]
    segments = []
    used = set(endpoints)
    for i, endpoint in enumerate(endpoints):
        neighbours = sorted({int(v) for tri in model.triangles if endpoint in tri for v in tri
                             if int(v) not in used and model.mirror_indices[v] == v})
        assert neighbours
        neighbour = neighbours[0]
        used.add(neighbour)
        segments.append([endpoint, neighbour] if i == 0 else [neighbour, endpoint])
    ids = [v for segment in segments for v in segment]
    transform = baseline_report['transform']
    world = transform['scale']*(model.generate(np.asarray(baseline_report['identity_coefficients']))@
                               np.asarray(transform['rotation']).T)+transform['translation_mm']
    vertices = world[ids]
    mesh.from_pydata(vertices.tolist(), [], [(0, 1, 2), (1, 2, 3)])
    obj = bpy.data.objects.new('Synthetic profile sample surface', mesh)
    scene.collection.objects.link(obj)
    try:
        settings.case_id = 'synthetic-profile'
        source_row = addon._register_bone_source(scene, obj)
        bpy.context.view_layer.update()
        source = next(s for s in addon._source_manifest(scene, bpy.context.evaluated_depsgraph_get())
                      if s['id'] == source_row.uid)
        manifest = addon._core_module('profile').empty_manifest()
        manifest.update(model_sha256=baseline_report['inputs']['model']['sha256'],
            case_id=settings.case_id, source='Synthetic same-model smoke test; not anatomical data',
            mapping_reviewed=True, mandible_reviewed=True,
            plane=dict(origin_mm=[0, 0, 0], normal_world=[1, 0, 0], source='Synthetic wide plane band', reviewed=True),
            plane_tolerance_mm=1000., segments=segments, gap_notes=['Synthetic unsampled interval; no interpolation'],
            strength=1., delta_regularization=1., marker_preservation_weight=1., marker_displacement_limit_mm=1.)
        manifest['samples'] = [dict(label=label, bone_xyz_mm=xyz.tolist(), normal_world=[0, 0, 1],
            source_id=source['id'], source_geometry_sha256=source['geometry_sha256'], status='observed',
            reviewed=True, depth_mm=0., sd_mm=1., tissue_source='Synthetic zero offset', direction='bone_normal')
            for label, xyz in zip(['Glabella', 'SyntheticUpper', 'SyntheticLower', 'Menton'], vertices)]
        path.write_text(json.dumps(manifest), encoding='utf-8')
        settings.profile_path, settings.profile_enabled = str(path), True
        assert bpy.ops.gnm.run_offline() == {'FINISHED'}
        folder = Path(addon._OFFLINE['folder'])
        deadline = time.monotonic()+180
        while addon._OFFLINE['process'] is not None and time.monotonic() < deadline:
            addon._offline_poll()
            time.sleep(.05)
        if not settings.offline_status.startswith('Completed;'):
            print((folder/'run.log').read_text(encoding='utf-8'))
            raise AssertionError(settings.offline_status)
        report = json.loads((folder/'face_report.json').read_text(encoding='utf-8'))
        record = report['marker_metadata']['profile_constraint']
        assert record['manifest'] == manifest
        assert record['status'] == 'accepted'
        assert all(p['final_mm'] <= p['before_mm']+record['numerical_tolerance_mm'] for p in record['points'])
        assert len(record['active_indices']) == 170
        assert not any(record['final_coefficients'][170:])
        assert (folder/'profile_constraint.json').read_bytes() == path.read_bytes()
        assert any(o.get('gnm_report') == str(folder/'face_report.json') for o in scene.objects)
        print('BLENDER_PROFILE_EXTERNAL_PASS: copied manifest, fixed-pose refinement, report and imported mesh')
    finally:
        if addon._OFFLINE.get('process') is not None:
            addon._stop_offline()
        if bpy.app.timers.is_registered(addon._offline_poll):
            bpy.app.timers.unregister(addon._offline_poll)
        settings.profile_enabled, settings.profile_path, settings.case_id = False, '', old_case
        for i in reversed(range(len(scene.gnm_bone_sources))):
            if scene.gnm_bone_sources[i].source_object == obj:
                scene.gnm_bone_sources.remove(i)
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)

"""Optional reproducible headless benchmark, not a timing gate or a CT study.

GNM_MODEL_PATH is required. GNM_BENCHMARK_REPO optionally selects a baseline
checkout; GNM_BENCHMARK_OUTPUT optionally writes the JSON report. Run with
Blender --background --factory-startup --python-exit-code 1 --python <this file>.
"""
import importlib
import json
import os
from pathlib import Path
import platform
import sys
import time
import bpy
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_performance_checks import HeadlessLayout

root = Path(os.environ.get('GNM_BENCHMARK_REPO', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(root))
addon = importlib.import_module('addon_v13')
addon.register()
try:
    scene = bpy.context.scene
    scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', .001
    scene.gnm_settings.mandible_aligned = True
    scene.gnm_live.npz_path = os.environ['GNM_MODEL_PATH']
    bpy.ops.gnm.init_markers()
    start = time.perf_counter()
    bpy.ops.gnm.load_live_model()
    load_seconds = time.perf_counter()-start
    model = addon._LIVE.model
    rng = np.random.default_rng(43)
    shape = model.generate(rng.normal(0, .6, model.identity_dim))
    for marker in scene.gnm_markers:
        target = shape[addon._resolve_vertex(marker)]+rng.normal(0, 1, 3)
        for attr, xyz in [('bone_empty', target-[0, 0, marker.tissue_depth_mm]), ('target_empty', target)]:
            obj = bpy.data.objects.new(marker.label+attr, None)
            scene.collection.objects.link(obj)
            obj.location = xyz.tolist()
            setattr(marker, attr, obj)
    # Half a million triangles exercise full evaluated-source hashing. This
    # plane is only a geometry-cost fixture, not an anatomical cranium.
    n = 501
    x, y = np.meshgrid(np.linspace(-100., 100., n), np.linspace(-100., 100., n))
    points = np.column_stack((x.ravel(), y.ravel(), np.zeros(n*n)))
    base = (np.arange(n-1)[:, None]*n+np.arange(n-1)).ravel()
    triangles = np.concatenate((np.column_stack((base, base+1, base+n)),
                               np.column_stack((base+1, base+n+1, base+n))))
    mesh = bpy.data.meshes.new('Synthetic surface cost fixture')
    mesh.vertices.add(len(points)); mesh.vertices.foreach_set('co', points.ravel())
    mesh.loops.add(triangles.size); mesh.loops.foreach_set('vertex_index', triangles.ravel())
    mesh.polygons.add(len(triangles))
    mesh.polygons.foreach_set('loop_start', np.arange(len(triangles))*3)
    mesh.polygons.foreach_set('loop_total', np.full(len(triangles), 3))
    mesh.update()
    obj = bpy.data.objects.new(mesh.name, mesh)
    scene.collection.objects.link(obj)
    addon._register_bone_source(scene, obj).anatomy = 'CRANIUM'
    addon._core_module('blender_craniometry').initialize(scene)
    scene.gnm_craniometry.weight = .5
    bpy.context.view_layer.update()
    addon._LIVE.scene_name = scene.name
    counts = dict(source_manifests=0, model_file_hashes=0)
    original_manifest = addon._source_manifest
    validation = addon._core_module('validation')
    original_hash = validation.sha256_file
    def manifest(*args, **kwargs):
        counts['source_manifests'] += 1
        return original_manifest(*args, **kwargs)
    def digest(*args, **kwargs):
        counts['model_file_hashes'] += 1
        return original_hash(*args, **kwargs)
    addon._source_manifest, validation.sha256_file = manifest, digest
    report = dict(addon_version=list(addon.bl_info['version']), blender=bpy.app.version_string,
        numpy=np.__version__, platform=platform.platform(), model_sha256=addon._LIVE.model_hash,
        fixture=dict(seed=43, skin_markers=48, cranial_references=22, source_triangles=len(triangles),
                     skin_distance_strength=.5, enabled_distance_bindings=0, dense=False),
        load_seconds=load_seconds, stages={})
    for name, operation in [('panel_draw', lambda: addon._draw_live_section(HeadlessLayout(), bpy.context)),
                            ('refit_request', lambda: addon._request_refit(scene))]:
        addon._LIVE.enabled = name == 'refit_request'
        counts.update(source_manifests=0, model_file_hashes=0)
        times = []
        for _ in range(20):
            start = time.perf_counter(); operation(); times.append(time.perf_counter()-start)
        report['stages'][name] = dict(repeats=20, median_ms=float(np.median(times)*1000), **counts)
    addon._LIVE.enabled = False
    snap = addon._build_snapshot(scene)
    for loo in (False, True):
        addon._LIVE.cfg['loo_auto'] = loo
        start = time.perf_counter(); result = addon._compute_fit(snap)
        report['stages']['fit_loo' if loo else 'fit_adaptive'] = dict(seconds=time.perf_counter()-start,
            rms_mm=result['rms'], lam=result['lam'], iterations=result['solver']['iterations'],
            coefficients=result['c'].tolist(), scale=result['scale'], rotation=result['rot'].tolist(),
            translation=result['trans'].tolist())
    output = json.dumps(report, indent=2)
    if os.environ.get('GNM_BENCHMARK_OUTPUT'):
        Path(os.environ['GNM_BENCHMARK_OUTPUT']).write_text(output+'\n', encoding='utf-8')
    print(output)
finally:
    addon.unregister()

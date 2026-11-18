"""Main-thread adapter: explicit refit from current inputs, publish one independent mesh."""
import json
from pathlib import Path

import bpy
import numpy as np

from . import blender_postfit, finalize
from .backend.gnm_backend import OFFICIAL_V3_SHA256
from .mapping import read_reviewed_map
from .prior import load_prior
from .validation import sha256_file


def _markers(scene, addon, sources):
    by_id = {row['id']: row for row in sources}
    patches = {}
    records = []
    for item in scene.gnm_markers:
        included = item.is_placed and addon._marker_terms(scene,item)[0]
        vertex = addon._resolve_vertex(item)
        row = dict(label=item.label, included=bool(included), vertex=vertex,
                   placed=bool(item.is_placed), mapping_reviewed=bool(item.mapping_reviewed),
                   mapping_source='manual' if item.gnm_vertex_override >= 0 else 'model/map',
                   bone_status=item.bone_status, tissue_source=item.tissue_source)
        if included:
            if any(scene.objects.get(o.name) != o for o in (item.bone_empty, item.target_empty)):
                raise ValueError(f'{item.label}: marker object is outside the current case scene')
            if vertex is None:
                raise ValueError(f'{item.label}: included marker is unmapped; review or explicitly exclude')
            bone, target = (np.asarray(o.matrix_world.translation, dtype=float)
                            for o in (item.bone_empty, item.target_empty))
            if not np.isclose(np.linalg.norm(target-bone), item.tissue_depth_mm, rtol=0, atol=.05):
                raise ValueError(f'{item.label}: bone-to-target distance differs from recorded depth')
            source = item.bone_empty.get('gnm_bone_source_id', '')
            digest = item.bone_empty.get('gnm_source_sha256_at_placement', '')
            current = by_id.get(source, {}).get('geometry_sha256')
            if source and current is None and item.bone_status in ('inferred', 'reconstructed'):
                if source not in patches:
                    patch = next((r.result_object for r in scene.gnm_restoration_regions if r.enabled
                        and r.uid == source and r.result_object and scene.objects.get(r.result_object.name) == r.result_object
                        and r.result_object.get('gnm_region_patch') == source
                        and r.result_object.get('gnm_reconstructed_via_mirroring')), None)
                    if patch is not None:
                        patches[source] = addon._core_module('blender_sources').evaluated_geometry(
                            patch, bpy.context.evaluated_depsgraph_get())[2]
                current = patches.get(source)
            if (source or digest) and (not digest or digest != current):
                raise ValueError(f'{item.label}: bound bone source missing or changed; review or re-place marker')
            row.update(bone_mm=bone.tolist(), tissue_depth_mm=float(item.tissue_depth_mm),
                       bone_source_id=source or None, bone_geometry_sha256=digest or None)
        records.append(row)
    return records


def _publish(context, source, vertices, record):
    """No existing scene objects changed. Remove both private datablocks on failure."""
    mesh = source.data.copy()
    obj = None
    try:
        mesh.vertices.foreach_set('co', vertices.ravel())
        mesh.update()
        stored = blender_postfit.coordinates(mesh.vertices)
        if not np.array_equal(vertices, stored):
            raise ValueError('Final vertex coordinates changed during Blender storage')
        record['stored_coordinates_sha256'] = blender_postfit.digest(stored)
        obj = bpy.data.objects.new(source.name+'_Finalized', mesh)
        obj['gnm_generated'] = True
        obj['gnm_local_finalize_record'] = json.dumps(record, allow_nan=False, separators=(',', ':'))
        blender_postfit.stamp_fit(obj, record['identity_coefficients'], record['model_to_world'],
            record['model_sha256'], {'status': record['geometry_quality']['status'], 'source': 'gnm_local_finalize_record'})
        context.scene.collection.objects.link(obj)
        # Include the result in the local view(s) that show the original GNM object.
        for area in context.screen.areas if context.screen else ():
            space = area.spaces.active
            if area.type == 'VIEW_3D' and space.local_view and source.local_view_get(space):
                obj.local_view_set(space, True)
        return obj
    except Exception:
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        raise


def create(context, addon):
    scene, live = context.scene, addon._LIVE
    st = scene.gnm_live
    if context.mode != 'OBJECT' or not addon._is_mm_scene(scene):
        raise ValueError('Use Object Mode and metric scene scale 0.001 (world mm)')
    if live.model is None or live.case_token != addon._case_token(scene):
        raise ValueError('Load the GNM model and map for this case')
    context.view_layer.update()
    model = live.model
    source = scene.objects.get(addon._case_name(addon.GNM_MESH_NAME, scene))
    if (source is None or source.type != 'MESH' or not source.get('gnm_generated') or source.data.shape_keys
            or source.data.animation_data or source.modifiers or len(source.data.vertices) != model.vertex_count
            or not np.array_equal(blender_postfit.topology(source.data), model.triangles)):
        raise ValueError('Load the native GNM model; altered topology, shape keys and modifiers are unsupported')
    if live.model_hash != OFFICIAL_V3_SHA256 or sha256_file(bpy.path.abspath(st.npz_path)) != live.model_hash:
        raise ValueError('Selected GNM model differs from the loaded official model; reload it')
    map_hash = None
    mapped = {}
    if st.json_path:
        path = bpy.path.abspath(st.json_path)
        mapped = read_reviewed_map(path, live.model_hash, model.vertex_count)
        map_hash = sha256_file(path)
    if mapped != live.reviewed_map:
        raise ValueError('Selected landmark map changed; reload Model & Map before finalizing')
    addon._core_module('blender_articulation').require_review(scene, deep=True)
    sources = addon._source_manifest(scene, context.evaluated_depsgraph_get())
    markers = _markers(scene, addon, sources)
    snap = addon._build_snapshot(scene)
    settings = {k: getattr(st, k) for k in ('identity_subspace','loo_auto','lambda_base','lambda_min',
                'lambda_max','clip_sigma','dense_strength','dense_nose_weight','dense_max_rows','prior_weight')}
    dense = None
    if snap['dense']:
        used = [row for row in sources if row['use_dense']]
        if not used or used != live.skull['sources'] or not all(row['normals_reviewed'] for row in used):
            raise ValueError('Dense source geometry or review changed; prepare registered bones again')
        if not scene.gnm_settings.mandible_aligned and any(row['anatomy'] in ('MANDIBLE','MIXED') for row in used):
            raise ValueError('Review mandibular articulation before dense finalization')
        dense = addon._live_dense_config(max_rows=st.dense_max_rows)
        dense.update(weight_ratio=.5*st.dense_strength, nose_weight=st.dense_nose_weight)
    prior = None
    if st.prior_sex != 'NONE' and st.prior_ethnicity != 'NONE':
        path = Path(bpy.path.abspath(st.prior_dir))/f'prior_{st.prior_sex}_{st.prior_ethnicity}.npz'
        prior = load_prior(path, model.identity_dim)
    vertices, record = finalize.finalize_snapshot(model, snap, settings, dense=dense, prior=prior)
    record.update(case_id=scene.gnm_settings.case_id, model_sha256=live.model_hash, map_sha256=map_hash,
        prior_sha256=prior['sha256'] if prior else None, source_object=source.name,
        blender_version=bpy.app.version_string, addon_version=list(addon.bl_info['version']),
        markers=markers, bone_sources=sources, mandible_aligned=bool(scene.gnm_settings.mandible_aligned),
        mandible_pose=addon._core_module('blender_articulation').snapshot(scene),
        dense_enabled=bool(snap['dense']), dense_scalp_only=bool(st.dense_scalp_only),
        bone_sampling_seed=live.skull['seed'] if dense is not None else None)
    record.update(addon._core_module('blender_scenarios').metadata(scene))
    return _publish(context, source, vertices, record), record

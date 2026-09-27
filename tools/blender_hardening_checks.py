"""Regression checks requiring the actual Blender API and ZIP namespace."""
from pathlib import Path
import json
from types import SimpleNamespace
import bpy
from mathutils import Vector
import numpy as np


def run_source_checks(addon, directory):
    previous = bpy.context.window.scene
    scene = bpy.data.scenes.new('Observed fragment ensemble')
    bpy.context.window.scene = scene
    scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', .001
    def triangle(name, x, z=0):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([(x, 0, z), (x+1, 0, z), (x, 1, z)], [], [(0, 1, 2)])
        obj = bpy.data.objects.new(name, mesh)
        scene.collection.objects.link(obj)
        return obj
    try:
        addon._bind_case(scene)
        objects = [triangle('Right cranium', -10), triangle('Nasal bone', 0), triangle('Left mandible', 10)]
        for obj, anatomy in zip(objects, ('CRANIUM', 'NASAL', 'MANDIBLE')):
            row = addon._register_bone_source(scene, obj)
            row.anatomy, row.normals_reviewed = anatomy, True
        try:
            bpy.ops.gnm.prepare_skull()
        except RuntimeError as exc:
            assert 'articulation' in str(exc)
        else:
            raise AssertionError('Unarticulated mandible accepted for dense fit')
        scene.gnm_settings.mandible_aligned = True
        bpy.context.view_layer.update()
        assert bpy.ops.gnm.prepare_skull() == {'FINISHED'}
        assert len(addon._LIVE.skull['sources']) == 3
        assert addon._LIVE.skull['points'][:, 0].min() < -9 and addon._LIVE.skull['points'][:, 0].max() > 10
        original = addon._LIVE.skull['points'].copy()
        assert bpy.ops.gnm.prepare_skull() == {'FINISHED'}
        np.testing.assert_array_equal(original, addon._LIVE.skull['points'])
        generated = triangle('GNM_Offline_face', 0, 5)
        try:
            addon._register_bone_source(scene, generated)
        except ValueError:
            pass
        else:
            raise AssertionError('Generated face accepted as bone')
        bpy.context.view_layer.update()
        hit = addon._ray_cast_skull(scene, bpy.context.evaluated_depsgraph_get(), Vector((.2, .2, 10)), Vector((0, 0, -1)), return_object=True)
        assert hit[0] and hit[3] == objects[1], hit
        marker = scene.gnm_markers.add()
        marker.label = 'Nasion'
        marker.bone_empty = bpy.data.objects.new('Bone marker', None)
        scene.collection.objects.link(marker.bone_empty)
        addon._record_marker_surface(marker, objects[1])
        assert marker.bone_empty.get('gnm_source_sha256_at_placement')
        # Evaluated geometry includes modifiers, and movement invalidates sampling.
        before = addon._source_manifest(scene, bpy.context.evaluated_depsgraph_get())[0]['geometry_sha256']
        objects[0].modifiers.new('Observed surface modifier', 'SOLIDIFY').thickness = .2
        bpy.context.view_layer.update()
        after = addon._source_manifest(scene, bpy.context.evaluated_depsgraph_get())[0]['geometry_sha256']
        assert before != after
        try:
            addon._assert_prepared_current(scene, bpy.context.evaluated_depsgraph_get())
        except ValueError:
            pass
        else:
            raise AssertionError('Prepared geometry survived modifier change')
        assert addon._LIVE.skull is None
        assert bpy.ops.gnm.prepare_skull() == {'FINISHED'}
        objects[0].location.x += 2
        bpy.context.view_layer.update()
        try:
            addon._assert_prepared_current(scene, bpy.context.evaluated_depsgraph_get())
        except ValueError:
            pass
        assert addon._LIVE.skull is None
        addon._LIVE.prior, addon._LIVE.last_c = {'mean': np.zeros(1)}, np.ones(1)
        addon._gnm_live_on_load_post(None)
        assert addon._LIVE.model is None and addon._LIVE.prior is None and addon._LIVE.last_c is None
        # Import keeps separately named objects in a common calibrated frame.
        source = Path(directory)/'fragments.obj'
        source.write_text('o right\nv -1 0 0\nv 0 0 0\nv -1 1 0\nf 1 2 3\no nasal\nv 2 0 0\nv 3 0 0\nv 2 1 0\nf 4 5 6\n')
        before_objects = set(scene.objects)
        assert bpy.ops.gnm.import_setup(filepath=str(source), source_units='cm') == {'FINISHED'}
        imported = [o for o in scene.objects if o not in before_objects]
        assert len(imported) == 2
        all_points = np.array([o.matrix_world@v.co for o in imported for v in o.data.vertices])
        assert abs(np.ptp(all_points[:, 0])-40) < 1e-5
        assert all(o.get('gnm_acquisition_sha256') and len(o.get('gnm_acquisition_to_world')) == 16 for o in imported)
        assert addon._nasal_rms(['Nasion', 'Rhinion'], [3, 4]) == np.sqrt(12.5)
        print('BLENDER_OBSERVED_SOURCES_TRANSFORMS_PROVENANCE_PASS')
    finally:
        addon._gnm_live_on_load_post(None)
        bpy.context.window.scene = previous


def run_map_checks(addon, scene, model, directory):
    addon._bind_case(scene)
    addon._LIVE.model = model
    addon._LIVE.model_hash = addon._core_module('validation').sha256_file(scene.gnm_live.npz_path)
    first = scene.gnm_markers[0]
    previous_path = scene.gnm_live.json_path
    scene.gnm_live.json_path = str(Path(directory)/'reviewed-map.json')
    saved = [(m, m.gnm_vertex_override, m.mapping_reviewed) for m in scene.gnm_markers]
    try:
        for m in scene.gnm_markers:
            m.mapping_reviewed = False
        first.gnm_vertex_override = 100
        assert bpy.ops.gnm.export_landmark_json() == {'FINISHED'}
        first.gnm_vertex_override = -1
        assert addon._resolve_vertex(first) == 100
        doc = json.loads(Path(scene.gnm_live.json_path).read_text())
        assert doc['model_sha256'] == addon._LIVE.model_hash
        assert addon._core_module('mapping').reviewed_vertices(doc, addon._LIVE.model_hash, model.vertex_count)[first.label] == 100
        # Another scene must clear priors, coefficients and reviewed maps.
        other = bpy.data.scenes.new('Other numerical case')
        addon._bind_case(other)
        assert addon._LIVE.model is None and not addon._LIVE.reviewed_map
        addon._bind_case(scene)
        addon._LIVE.model = model
    finally:
        scene.gnm_live.json_path = previous_path
        addon._LIVE.reviewed_map = {}
        for m, override, reviewed in saved:
            m.gnm_vertex_override, m.mapping_reviewed = override, reviewed
    print('BLENDER_REVIEWED_MAP_CASE_ISOLATION_PASS')


def run_icp_score_check(addon):
    """A lower geometric cost must not outrank a better coverage-adjusted score."""
    previous_model, previous_skull, previous_dense = addon._LIVE.model, addon._LIVE.skull, addon._LIVE.dense_set
    previous_rows, previous_fit = addon._dense_rows, addon._CRANIO['weighted_umeyama']
    points = np.random.default_rng(2).normal(size=(100, 3))
    calls = []
    def rows(world, *args, **kwargs):
        index = len(calls)
        calls.append(index)
        # yaw0: cost 2 / coverage .5 = 4; yaw90: 3 / 1 = 3 (winner).
        cost, kept = [(2., 50), (3., 100), (9., 100), (8., 100), (3., 100)][min(index, 4)]
        return np.arange(kept), points[:kept], kept, cost, {}
    try:
        addon._LIVE.model = SimpleNamespace(mu=points)
        addon._LIVE.skull = dict(points=points)
        addon._LIVE.dense_set = (np.arange(100), None, None, None)
        addon._dense_rows = rows
        addon._CRANIO['weighted_umeyama'] = lambda *args: (1., np.eye(3), np.zeros(3))
        assert addon._multi_start_icp(n_coarse=1, n_refine=1)[5] == 'yaw90'
    finally:
        addon._LIVE.model, addon._LIVE.skull, addon._LIVE.dense_set = previous_model, previous_skull, previous_dense
        addon._dense_rows, addon._CRANIO['weighted_umeyama'] = previous_rows, previous_fit
    print('BLENDER_ICP_COVERAGE_SCORE_PASS')

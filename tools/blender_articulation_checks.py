"""Synthetic geometry tested with actual Blender, not anatomical validation."""
import json
import os
from pathlib import Path
import bpy
import numpy as np

V = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]], float)
T = np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
              [1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]], int)


def error(call, text):
    try: call()
    except (ValueError, RuntimeError) as exc: assert text in str(exc), str(exc)
    else: raise AssertionError('Expected error '+text)


def run_articulation_checks(addon, directory):
    previous = bpy.context.window.scene
    scene = bpy.data.scenes.new('Articulation test')
    bpy.context.window.scene = scene
    core = addon._core_module('blender_articulation')
    qc = addon._core_module('blender_occlusion')
    cm = addon._core_module('blender_craniometry')
    def mesh(name, offset=(0,0,0)):
        data = bpy.data.meshes.new(name); data.from_pydata((V+offset).tolist(), [], T.tolist())
        obj = bpy.data.objects.new(name, data); scene.collection.objects.link(obj)
        return obj
    def empty(name, pos):
        obj = bpy.data.objects.new(name, None); scene.collection.objects.link(obj); obj.location = pos
        return obj
    def select(*objects):
        for o in scene.objects: o.select_set(False)
        for o in objects: o.select_set(True)
        bpy.context.view_layer.objects.active = objects[0]
    try:
        scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', .001
        st = scene.gnm_articulation
        assert core.snapshot(scene) is None and not st.contact_configured
        core.require_review(scene)
        skull, jaw, fragment = mesh('Cranium',(0,0,20)), mesh('Left mandibular fragment'), mesh('Right fragment',(5,0,0))
        upper, lower = mesh('Upper teeth',(0,0,10)), mesh('Lower teeth')
        addon._register_bone_source(scene, skull).anatomy = 'CRANIUM'
        sources = [addon._register_bone_source(scene, obj) for obj in (jaw, fragment)]
        for r in sources: r.anatomy = 'MANDIBLE'
        st.lower_teeth, st.upper_teeth = lower, upper
        st.condyle_left, st.fossa_left = empty('Condyle',(0,0,0)), empty('Fossa',(0,0,10))
        st.assumption = 'Synthetic software pose, no anatomical recommendation'
        cm.initialize(scene)
        point = next(p for p in scene.gnm_cranial_points if p.code == 'n')
        point.bone_empty = empty('Synthetic source-bound point',(0,1,0))
        point.source_id, point.bone_status = sources[0].uid, 'observed'
        point.definition_reviewed, point.review_xyz = True, (0,1,0)
        marker = scene.gnm_markers.add(); marker.label = 'Pogonion'
        marker.bone_empty, marker.target_empty = empty('Bone marker',(0,0,0)), empty('Skin target',(0,0,2))
        marker.peg_object = mesh('GNM_BAT_fixture')
        marker.tissue_depth_mm, marker.tissue_source = 2., 'Synthetic offset'
        marker.mapping_reviewed, marker.bone_status = True, 'observed'
        marker.bone_empty['gnm_bone_source_id'] = sources[0].uid
        bpy.context.view_layer.update()
        digest = next(r for r in addon._source_manifest(scene,bpy.context.evaluated_depsgraph_get()) if r['id']==sources[0].uid)['geometry_sha256']
        marker.bone_empty['gnm_source_sha256_at_placement'], point.source_sha256 = digest, digest
        originals = list(scene.objects)
        before = {o.name: core._matrix(o) for o in originals}
        scene.gnm_settings.mandible_aligned = True
        select(skull); error(lambda: core.begin(bpy.context), 'MANDIBLE')
        select(jaw,fragment); assert bpy.ops.gnm.articulate_mandible(action='BEGIN') == {'FINISHED'}
        assert not scene.gnm_settings.mandible_aligned
        error(lambda: core.require_review(scene), 'preview')
        st.control.location.z += 3; bpy.context.view_layer.update()
        assert all(core._matrix(o)==before[o.name] for o in originals)
        check = core.diagnostics(scene,preview=True)
        assert check['condyle_fossa']['left']['distance_mm'] == 7
        assert check['condyle_fossa']['right']['status'] == 'unavailable'
        assert bpy.ops.gnm.articulate_mandible(action='CANCEL') == {'FINISHED'}
        assert scene.gnm_settings.mandible_aligned
        assert not any(o.get('gnm_articulation_preview') for o in scene.objects)
        marker.bone_empty['gnm_source_sha256_at_placement'] = 'c'*64
        select(jaw,fragment); error(lambda: core.begin(bpy.context), 'Stale marker')
        marker.bone_empty['gnm_source_sha256_at_placement'] = digest
        core.begin(bpy.context); st.control.scale.x = 2; bpy.context.view_layer.update()
        error(lambda: core.apply(bpy.context), 'rigid')
        assert core._matrix(jaw)==before[jaw.name]
        st.control.scale.x = 1; st.control.location.z += 3; bpy.context.view_layer.update()
        core.apply(bpy.context)
        error(lambda: core.require_review(scene), 'reviewed mandibular')
        for o in (jaw,fragment,lower,marker.bone_empty,marker.target_empty,marker.peg_object,point.bone_empty,st.condyle_left):
            expected = np.asarray(before[o.name]); expected[2,3] += 3
            np.testing.assert_allclose(np.asarray(o.matrix_world),expected,atol=1e-6,rtol=0)
        assert core._matrix(skull)==before[skull.name] and core._matrix(upper)==before[upper.name]
        assert abs((marker.target_empty.matrix_world.translation-marker.bone_empty.matrix_world.translation).length-2)<1e-6
        assert not point.definition_reviewed and point.source_sha256 != digest
        assert marker.bone_empty['gnm_source_sha256_at_placement']==point.source_sha256
        assert bpy.ops.gnm.articulate_mandible(action='REVIEW') == {'FINISHED'}
        record = core.snapshot(scene)
        assert record['status']=='reviewed_current' and len(record['history'])==1
        assert record['history'][0]['rigid_delta_world'][2][3]==3
        assert cm.document(scene)['mandible_pose']==record
        assert bpy.ops.gnm.session_report()=={'FINISHED'}
        assert 'Mandibular articulation (operator assumption)' in bpy.data.texts['GNM_Session_Report'].as_string()
        st.output_path=str(Path(directory)/'mandible-session.json')
        assert bpy.ops.gnm.articulate_mandible(action='EXPORT')=={'FINISHED'}
        assert json.loads(Path(st.output_path).read_text())==record
        error(lambda: bpy.ops.gnm.articulate_mandible(action='EXPORT'),'Output exists')
        # Intentional overlap needs a reason; it cannot become an automatic clear.
        upper.location.z = -6.5; bpy.context.view_layer.update()
        error(lambda: core.review(scene), 'Collision flags')
        st.collision_override_reason = 'Synthetic overlap accepted to test explicit override recording'
        core.review(scene)
        assert core.snapshot(scene)['review']['collision_override_reason'] == st.collision_override_reason
        upper.location.z = 0.; bpy.context.view_layer.update()
        core.review(scene)
        record = core.snapshot(scene)
        saved = st.history
        addon.unregister(); addon.register()
        st=scene.gnm_articulation
        assert st.history==saved
        core.require_review(scene,deep=True)
        if os.environ.get('GNM_MODEL_PATH'):
            scene.gnm_live.npz_path=os.environ['GNM_MODEL_PATH']
            path=Path(directory)/'articulated.csv'; addon._export_markers(scene,str(path))
            backend=addon._core_module('backend').GNMBackend(scene.gnm_live.npz_path)
            _,_,meta=addon._core_module('io_csv').read_marker_csv(path,backend.index_to_label,backend.landmark_vertex_map)
            assert meta['mandible_pose']==record
        jaw.location.x+=1; bpy.context.view_layer.update()
        error(lambda: core.require_review(scene),'stale')
        jaw.location.x-=1; bpy.context.view_layer.update()
        jaw.data.vertices[0].co.x+=.25; bpy.context.view_layer.update()
        error(lambda: core.require_review(scene,deep=True),'stale')
        jaw.data.vertices[0].co.x-=.25; bpy.context.view_layer.update()
        select(jaw,fragment); core.begin(bpy.context)
        jaw.location.x+=.5; bpy.context.view_layer.update()
        error(lambda: core.apply(bpy.context),'changed during preview')
        core.cancel(scene); assert jaw.location.x==.5 and not scene.gnm_settings.mandible_aligned
        jaw.location.x-=.5; bpy.context.view_layer.update()
        select(jaw,fragment); core.begin(bpy.context); st.control.location.y+=1; bpy.context.view_layer.update()
        original=addon._source_manifest
        def fail(*args): raise ValueError('Synthetic post-move failure')
        addon._source_manifest=fail
        before_apply=core._matrix(jaw)
        try: error(lambda: core.apply(bpy.context),'Synthetic post-move')
        finally: addon._source_manifest=original
        assert core._matrix(jaw)==before_apply and st.history==saved
        core.cancel(scene)
        separated=qc.check_surfaces((V,T),(V+[0,0,5],T))
        assert separated['intersection_triangle_pairs']==0 and separated['lower_in_upper']['inside_vertices']==0
        overlap=qc.check_surfaces((V,T),(V+.5,T),.1)
        assert overlap['intersection_triangle_pairs']>0 and overlap['lower_in_upper']['inside_vertices']>0
        nested=qc.check_surfaces((V*.25,T),(V,T))
        assert nested['intersection_triangle_pairs']==0 and nested['lower_in_upper']['inside_vertices']==8
        assert nested['status']=='flags_present'
        opened=qc.check_surfaces((V*.25,T),(V,T[:-2]))
        assert opened['lower_in_upper']['status']=='unavailable_open_surface'
        print('BLENDER_ARTICULATION_PASS: fragments, cancel/apply, record, stale gates, rollback, BVH overlap/containment')
    finally:
        addon._gnm_live_on_load_post(None)
        bpy.context.window.scene=previous
        for o in list(scene.objects): bpy.data.objects.remove(o,do_unlink=True)
        bpy.data.scenes.remove(scene)


def run_articulation_undo(addon):
    previous = bpy.context.window.scene.name
    scene = bpy.data.scenes.new('Articulation undo test')
    name = scene.name
    bpy.context.window.scene = scene
    scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', .001
    mesh = bpy.data.meshes.new('Undo jaw'); mesh.from_pydata(V.tolist(),[],T.tolist())
    obj = bpy.data.objects.new('Undo jaw',mesh); scene.collection.objects.link(obj)
    object_name = obj.name
    addon._register_bone_source(scene,obj).anatomy = 'MANDIBLE'
    for other in scene.objects: other.select_set(False)
    obj.select_set(True); bpy.context.view_layer.objects.active=obj
    scene.gnm_articulation.assumption='Synthetic Undo/Redo test'
    assert bpy.ops.gnm.articulate_mandible(action='BEGIN')=={'FINISHED'}
    scene.gnm_articulation.control.location.z+=3
    bpy.context.view_layer.update()
    bpy.ops.ed.undo_push(message='Before articulation')
    assert bpy.ops.gnm.articulate_mandible(action='APPLY')=={'FINISHED'}
    bpy.ops.ed.undo_push(message='After articulation')
    assert bpy.ops.ed.undo()=={'FINISHED'}
    scene=bpy.data.scenes[name]
    assert scene.gnm_articulation.history=='[]' and scene.gnm_articulation.pending
    assert scene.objects[object_name].matrix_world.translation.z==0
    assert bpy.ops.ed.redo()=={'FINISHED'}
    scene=bpy.data.scenes[name]
    assert len(json.loads(scene.gnm_articulation.history))==1 and not scene.gnm_articulation.pending
    assert scene.objects[object_name].matrix_world.translation.z==3
    bpy.context.window.scene=bpy.data.scenes[previous]
    for o in list(scene.objects): bpy.data.objects.remove(o,do_unlink=True)
    bpy.data.scenes.remove(scene)
    print('BLENDER_ARTICULATION_UNDO_PASS')

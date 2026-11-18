"""Installed add-on: confirm/adjust a complete synthetic queue vs ordinary manual CSV."""
import csv
import json
import os
from pathlib import Path
import tempfile

import bpy
from mathutils import Vector


def run_queue_checks(addon):
    old = bpy.context.scene
    case = bpy.data.scenes.new('Queue case')
    atlas = bpy.data.scenes.new('Queue atlas')
    bpy.context.window.scene = case
    case.unit_settings.system = 'METRIC'
    case.unit_settings.scale_length = .001
    case.gnm_settings.normal_mode = 'FACE'  # coarse synthetic tetrahedron
    before = {kind: set(getattr(bpy.data,kind)) for kind in ('objects','meshes','texts')}
    coords = [(0,0,0),(12,0,0),(0,12,0),(0,0,12),(3,3,0),(4,0,3)]
    tris = [(0,4,1),(1,4,2),(2,4,0),(0,1,5),(1,3,5),(3,0,5),(2,3,0),(1,2,3)]
    labels = ['Menton','Bregma','Pogonion','Rhinion','Nasion','Glabella']
    try:
        objs = []
        for sc in (atlas,case):
            mesh = bpy.data.meshes.new('Queue fixture')
            mesh.from_pydata(coords, [], tris)
            mesh.update()
            obj = bpy.data.objects.new(sc.name+' bone',mesh)
            sc.collection.objects.link(obj)
            objs.append(obj)
            obj.vertex_groups.new(name='ATLAS_PATCH:observed').add(list(range(6)),1.,'REPLACE')
        ref,obj = objs
        ref['gnm_atlas_source'] = 'Software test, not anatomy'
        case.gnm_atlas_skull = ref
        src = addon._register_bone_source(case,obj)
        bpy.context.view_layer.objects.active = obj
        bpy.context.view_layer.update()
        digest = addon._core_module('blender_sources').source_geometry(obj,bpy.context.evaluated_depsgraph_get())[2]
        for i,label in enumerate(labels):
            ref.vertex_groups.new(name='ATLAS_REVIEWED:'+label).add([i],1.,'REPLACE')
            m = case.gnm_markers.add()
            m.label = label
            if i < 4:
                bone = bpy.data.objects.new('reviewed anchor',None)
                case.collection.objects.link(bone)
                bone.location = coords[i]
                m.bone_empty, m.bone_status = bone, 'observed'
                bone['gnm_bone_source_id'] = src.uid
                bone['gnm_source_sha256_at_placement'] = digest
            else:
                # Explicit synthetic model correspondence, not anatomical evidence.
                m.gnm_vertex_override = 100+i
        bpy.context.view_layer.update()
        case.gnm_proposal_patch = 'observed'
        case.gnm_proposal_gap, case.gnm_proposal_anchor_limit, case.gnm_proposal_radius = .1, .2, 20.
        run = bpy.ops.gnm.propose_landmarks
        act = bpy.ops.gnm.review_proposal
        assert run() == {'FINISHED'}
        q = case.gnm_proposal_queue
        assert len(q.rows) == 2 and q.rows[0].score <= q.rows[1].score
        raw = q.text.as_string()
        q.text.write('edited')
        assert act(action='CONFIRM') == {'CANCELLED'}
        q.text.from_string(raw)
        case.gnm_proposal_radius = 21.
        assert act(action='CONFIRM') == {'CANCELLED'}
        case.gnm_proposal_radius = 20.
        bone = case.gnm_markers[0].bone_empty
        bone.location = (.05,0,0)
        bpy.context.view_layer.update()
        assert act(action='LOCATE') == {'CANCELLED'}
        bone.location = coords[0]
        bpy.context.view_layer.update()
        assert act(action='SKIP') == {'FINISHED'}
        assert sum(r.decision == 'rejected' for r in q.rows) == 1
        assert not any(m.is_placed for m in case.gnm_markers)
        assert run() == {'FINISHED'}
        ids = {r.label:i for i,r in enumerate(q.rows)}
        q.index = ids['Glabella']
        assert act(action='LOCATE') == {'FINISHED'}
        assert (case.cursor.location-Vector(coords[5])).length < 1e-5
        case.cursor.location = (40,40,40)
        assert act(action='ADJUST') == {'CANCELLED'} and not case.gnm_markers[5].is_placed
        case.cursor.location = (5,0,3)
        assert act(action='ADJUST') == {'FINISHED'}
        assert q.rows[q.index].label == 'Nasion'
        # An occupied or partial row must never be silently replaced.
        case.gnm_markers[4].target_empty = bone
        assert act(action='CONFIRM') == {'CANCELLED'} and case.gnm_markers[4].target_empty == bone
        case.gnm_markers[4].target_empty = None
        assert act(action='CONFIRM') == {'FINISHED'}
        assert act(action='CONFIRM') == {'CANCELLED'} and {r.decision for r in q.rows} == {'confirmed','adjusted'}
        assert len([m for m in case.gnm_markers if m.is_placed]) == 2
        poses = {'Glabella':(5,0,3), 'Nasion':coords[4]}
        for m in list(case.gnm_markers)[4:]:
            assert (m.bone_empty.location-Vector(poses[m.label])).length < 1e-5
            assert not m.mapping_reviewed and m.bone_status == 'observed'
        if os.environ.get('GNM_MODEL_PATH'):
            case.gnm_live.npz_path = os.environ['GNM_MODEL_PATH']
            def exported(path):
                addon._export_markers(case, str(path))
                with path.open(encoding='utf8', newline='') as f:
                    assert f.readline().strip() == '# gnm-marker-csv v3'
                    meta = json.loads(f.readline()[1:])
                    return list(csv.DictReader(f)), meta
            with tempfile.TemporaryDirectory() as tmp:
                rows, meta = exported(Path(tmp)/'reviewed.csv')
                decisions = meta['proposal_reviews_at_placement']
                assert decisions['Glabella']['decision'] == 'adjusted'
                assert decisions['Nasion']['snapshot_sha256'] == q.digest
                assert (Vector(decisions['Glabella']['accepted_world_mm'])-Vector((5,0,3))).length < 1e-5
                assert decisions['Glabella']['proposed_world_mm'] != decisions['Glabella']['accepted_world_mm']
                # Repeat with actual normal manual placement path and the same polygon.
                for m in list(case.gnm_markers)[4:]:
                    seed = json.loads(m.bone_empty['gnm_normal_record'])['seed_triangle']
                    addon._place_marker_at(bpy.context,m,Vector(decisions[m.label]['accepted_world_mm']),obj,seed)
                manual, meta = exported(Path(tmp)/'manual.csv')
                assert 'proposal_reviews_at_placement' not in meta and manual == rows
        print('BLENDER_PROPOSAL_QUEUE_PASS: inspect, reject, confirm, adjust, stale/occupied guards and manual CSV parity')
    finally:
        bpy.context.window.scene = old
        bpy.data.scenes.remove(case)
        bpy.data.scenes.remove(atlas)
        for kind in ('objects','meshes','texts'):
            collection = getattr(bpy.data,kind)
            for obj in set(collection)-before[kind]:
                collection.remove(obj,do_unlink=True)

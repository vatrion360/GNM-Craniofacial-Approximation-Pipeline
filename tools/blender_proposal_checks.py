"""Installed-ZIP integration; separate reference and preserved observed patch."""
import json

import bpy
import numpy as np


def run_proposal_checks(addon):
    api = addon._core_module('blender_proposals')
    old = bpy.context.scene
    case, atlas = [bpy.data.scenes.new(n) for n in ('Proposal case', 'Proposal atlas')]
    bpy.context.window.scene = case
    case.unit_settings.system = 'METRIC'
    case.unit_settings.scale_length = .001
    coords = [(0,0,0),(6,0,0),(0,8,0),(0,0,10),(2,2,0),(20,0,0)]
    tris = [(0,1,4),(1,2,4),(2,0,4),(0,3,1),(2,3,0),(1,3,2),(1,5,2)]
    objects, meshes, blocks = [], [], []
    try:
        for sc,n in [(atlas,'reference'),(case,'observed')]:
            m = bpy.data.meshes.new(n)
            m.from_pydata(coords, [], tris)
            m.update()
            obj = bpy.data.objects.new(n, m)
            sc.collection.objects.link(obj)
            objects.append(obj)
            meshes.append(m)
            obj.vertex_groups.new(name='ATLAS_PATCH:specimen patch').add(list(range(5)),1.,'REPLACE')
        ref, obj = objects
        ref['gnm_atlas_source'] = 'Synthetic reviewed annotations'
        case.gnm_atlas_skull = ref
        source = addon._register_bone_source(case, obj)
        obj.location = (15,21,2)
        bpy.context.view_layer.objects.active = obj
        bpy.context.view_layer.update()
        digest = api.blender_sources.source_geometry(obj, bpy.context.evaluated_depsgraph_get())[2]
        labels = ['Nasion','Glabella','Menton','Bregma','Midphiltrum','Posterior']
        for i,label in enumerate(labels):
            ref.vertex_groups.new(name='ATLAS_REVIEWED:'+label).add([i],1.,'REPLACE')
            m = case.gnm_markers.add()
            m.label = label
            if i < 4:
                bone = bpy.data.objects.new('anchor-'+label, None)
                objects.append(bone)
                case.collection.objects.link(bone)
                bone.location = np.array(coords[i])+obj.location
                m.bone_empty, m.bone_status = bone, 'observed'
                bone['gnm_bone_source_id'] = source.uid
                bone['gnm_source_sha256_at_placement'] = digest
        bpy.context.view_layer.update()
        case.gnm_proposal_patch = 'specimen patch'
        assert not case.gnm_show_proposals and bpy.ops.gnm.propose_landmarks() == {'CANCELLED'}
        case.gnm_proposal_radius, case.gnm_proposal_gap, case.gnm_proposal_anchor_limit = 15., .1, .1
        old_blocks = set(bpy.data.texts)
        assert bpy.ops.gnm.propose_landmarks() == {'FINISHED'}
        blocks.extend(set(bpy.data.texts)-old_blocks)
        assert len(blocks) == 1
        r = json.loads(blocks[0].as_string())
        assert list(r['sites']['Midphiltrum']['world_mm']) == [17.,23.,2.]
        assert r['sites']['Posterior']['world_mm'] is None and len(r['anchors']) == 4
        assert not case.gnm_markers[4].is_placed and len(case.objects) == 5
        # Create an open cut through the unplaced vertex; reject boundary contact.
        for m in meshes:
            import bmesh
            bm = bmesh.new()
            bm.from_mesh(m)
            bm.faces.ensure_lookup_table()
            bmesh.ops.delete(bm, geom=[bm.faces[0]], context='FACES_ONLY')
            bm.to_mesh(m)
            bm.free()
            m.update()
        bpy.context.view_layer.update()
        assert bpy.ops.gnm.propose_landmarks() == {'CANCELLED'}  # stale source signature
        digest = api.blender_sources.source_geometry(obj, bpy.context.evaluated_depsgraph_get())[2]
        for m in list(case.gnm_markers)[:4]:
            m.bone_empty['gnm_source_sha256_at_placement'] = digest
        row = api.snapshot(bpy.context)['sites']['Midphiltrum']
        assert row['world_mm'] is None and row['reason'] == 'on open patch boundary'
        assert len(bpy.data.texts) == len(old_blocks)+1 and not case.gnm_markers[4].is_placed
        triangles = np.array([[0,1,2],[3,4,5]])
        try:
            api._patch(np.array(coords), triangles, list(range(6)))
        except ValueError as exc:
            assert 'Disconnected' in str(exc)
        else:
            raise AssertionError('Disjoint patches must not share a registration')
        print('BLENDER_FRAGMENT_PROPOSALS_PASS: held-out site, absent patch, open boundary, stale source, unchanged markers')
    finally:
        bpy.context.window.scene = old
        for text in blocks:
            bpy.data.texts.remove(text)
        for obj in objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        for m in meshes:
            bpy.data.meshes.remove(m)
        bpy.data.scenes.remove(case)
        bpy.data.scenes.remove(atlas)

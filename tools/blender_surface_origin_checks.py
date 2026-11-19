"""Installed add-on: genuine original/mirrored/donor faces, native picks and case weights."""
import json
import os
from pathlib import Path
import tempfile

import bpy
from mathutils import Vector


def run_surface_origin_checks(addon):
    old=bpy.context.scene
    case=bpy.data.scenes.new('Surface origin fixture')
    external=bpy.data.scenes.new('External donor only')
    bpy.context.window.scene=case
    before={k:set(getattr(bpy.data,k)) for k in ('objects','meshes')}
    def triangle(sc,label,x):
        mesh=bpy.data.meshes.new(label)
        mesh.from_pydata([(x,0,0),(x,4,0),(x,0,4)],[],[(0,1,2)])
        mesh.update()
        obj=bpy.data.objects.new(label,mesh)
        sc.collection.objects.link(obj)
        return obj
    try:
        case.unit_settings.system='METRIC'
        case.unit_settings.scale_length=.001
        external.unit_settings.system='METRIC'
        external.unit_settings.scale_length=.001
        case.gnm_settings.case_id='B5-case'
        case.gnm_settings.normal_mode='FACE'
        case.gnm_settings.mandible_aligned=True
        src=triangle(case,'Observed',-4)
        ext=triangle(external,'Borrowed zygomatic fragment',12)
        source=addon._register_bone_source(case,src)
        source.normals_reviewed=True
        bpy.context.view_layer.objects.active=src
        bpy.context.view_layer.update()
        action=bpy.ops.gnm.surface_origin
        assert not case.gnm_tag_mirrors and not case.gnm_origin_policy
        assert action(action='ORIGINAL')=={'FINISHED'}
        assert bpy.ops.gnm.region_add()=={'FINISHED'}
        reg=case.gnm_restoration_regions[0]
        reg.action='MIRROR'
        plane=bpy.data.objects.new('Reference plane',None)
        case.collection.objects.link(plane)
        from math import pi
        plane.rotation_euler.y=pi/2
        reg.plane_object=plane
        case.gnm_tag_mirrors=True
        bpy.context.view_layer.update()
        assert bpy.ops.gnm.mirror_reconstruct()=={'FINISHED'}
        mirror=reg.result_object
        case.gnm_origin_donor=ext
        case.gnm_origin_donor_note='Synthetic external region; aligned in test coordinates'
        assert action(action='DONOR')=={'FINISHED'}
        donor=case.gnm_restoration_regions[-1].result_object
        assert not donor.get('gnm_reconstructed_via_mirroring')
        assert case.objects.get(ext.name) is None and ext.data.attributes.get('gnm_bone_origin') is None
        bpy.context.view_layer.update()
        srcs=addon._core_module('blender_sources')
        for i,(obj,name) in enumerate(zip((src,mirror,donor),('Nasion','Glabella','Rhinion')),1):
            assert obj.data.attributes['gnm_bone_origin'].domain=='FACE'
            assert obj.data.attributes['gnm_bone_origin'].data[0].value==i
            if i>1:
                try:
                    addon._register_bone_source(case,obj)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Repair registered as observed bone')
            m=case.gnm_markers.add()
            m.label,m.fit_weight,m.gnm_vertex_override=name,.8,900+i
            pt=sum((obj.matrix_world@v.co for v in obj.data.vertices),Vector())/3
            addon._place_marker_at(bpy.context,m,pt,obj,0)
            assert m.bone_status==('observed' if i==1 else 'reconstructed')
            if i>1:
                assert not m.use_for_fit and not m.use_for_plane
                m.use_for_fit=True
        bpy.context.view_layer.update()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            f=root/'factors.json'
            p=dict(schema='gnm.origin-factors.v1',case_id='B5-case',status='calibrate',source='Synthetic factors',
                   mirrored=dict(weight_factor=.5,placement_sd_factor=2),donor=dict(weight_factor=.25,placement_sd_factor=3))
            f.write_text(json.dumps(p))
            case.gnm_origin_file=str(f)
            assert action(action='LOAD')=={'FINISHED'}
            f.unlink()
            snap=addon._build_snapshot(case)
            weights=dict(zip(snap['labels'],snap['weights']))
            assert abs(weights['Glabella']/weights['Nasion']-.5)<1e-7
            assert abs(weights['Rhinion']/weights['Nasion']-.25)<1e-7
            if os.environ.get('GNM_MODEL_PATH'):
                case.gnm_live.npz_path=os.environ['GNM_MODEL_PATH']
                addon._export_markers(case,root/'markers.csv')
                t,_,meta=addon._core_module('io_csv').read_marker_csv(root/'markers.csv',{},{})
                assert {v.label:v.weight for v in t}==weights
                assert meta['marker_records']['Glabella']['face_origin']['origin']=='mirrored'
                assert meta['marker_records']['Rhinion']['face_origin']['origin']=='donor'
            donor.data.vertices[0].co.x+=1
            bpy.context.view_layer.update()
            try:
                addon._build_snapshot(case)
            except ValueError as exc:
                assert 'stale' in str(exc)
            else:
                raise AssertionError('Accepted a changed donor patch')
            assert action(action='CLEAR')=={'FINISHED'} and not case.gnm_origin_policy
            assert srcs.generated_surface(donor)
        print('BLENDER_FACE_ORIGIN_PASS: original, mirror and distinct donor faces, reviewed weight factors, CSV and stale-source refusal')
    finally:
        bpy.context.window.scene=old
        bpy.data.scenes.remove(case)
        bpy.data.scenes.remove(external)
        for k in ('objects','meshes'):
            coll=getattr(bpy.data,k)
            for v in set(coll)-before[k]:
                coll.remove(v,do_unlink=True)

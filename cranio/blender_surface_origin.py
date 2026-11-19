"""Explicit static-face stamping, donor copies and placement receipt checks (main thread)."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
import uuid

import bpy
from bpy.props import BoolProperty, EnumProperty, PointerProperty, StringProperty
import numpy as np

from . import surface_origin as core
from .tissue import _json

_api=None


def tag(mesh,kind):
    attr=mesh.attributes.get(core.ATTRIBUTE)
    if attr is not None:
        raise ValueError('Face origin already exists; do not relabel an existing classification')
    attr=mesh.attributes.new(core.ATTRIBUTE,'INT','FACE')
    attr.data.foreach_set('value',np.full(len(mesh.polygons),core.CODES[kind],np.int32))
    mesh['gnm_origin_kind']=kind


def check(mesh,obj):
    attr=mesh.attributes.get(core.ATTRIBUTE)
    kind=mesh.get('gnm_origin_kind')
    if attr is None and kind is None:
        return None
    expected=('mirrored' if obj.get('gnm_reconstructed_via_mirroring') else
              'donor' if obj.get('gnm_external_donor') else 'original')
    if (attr is None or attr.domain!='FACE' or attr.data_type!='INT' or kind!=expected or
            obj.modifiers or obj.data.shape_keys):
        raise ValueError('Inconsistent face provenance; use distinct static fragments without modifiers or shape keys')
    codes=np.empty(len(mesh.polygons),np.int32)
    attr.data.foreach_get('value',codes)
    if (codes!=core.CODES[kind]).any():
        raise ValueError('Mixed/unknown face origins: split and review the fragment before use')
    return kind


def lineage(obj):
    return core.digest(obj.get('gnm_restoration_metadata','registered original'))


@lru_cache(maxsize=32)
def _decode(raw):
    return core.policy(_json(raw))


def terms(scene,item,enabled,weight,why):
    raw=scene.gnm_origin_policy
    if not raw or not enabled:
        return enabled,weight,why
    policy=_decode(raw)
    bone=item.bone_empty
    if policy['case_id']!=scene.gnm_settings.case_id or not bone or core.RECEIPT not in bone:
        return False,weight,'missing face provenance or wrong policy case'
    receipt=json.loads(bone[core.RECEIPT])
    kind=receipt['origin']
    if (item.bone_status!=('observed' if kind=='original' else 'reconstructed')
            or list(bone.matrix_world.translation)!=receipt['point_mm']):
        return False,weight,'stale face provenance; re-place'
    if kind=='original':
        return enabled,weight,why
    f=policy[kind]['weight_factor']
    return (False,weight,'no configured provenance weight') if f is None else (True,weight*f,kind+' weight factor')


def metadata(scene,manifest):
    raw=scene.gnm_origin_policy
    result={}
    if not raw and not any(m.is_placed and core.RECEIPT in m.bone_empty for m in scene.gnm_markers):
        return result
    if raw:
        p=_decode(raw)
        if p['case_id']!=scene.gnm_settings.case_id:
            raise ValueError('Face-origin policy belongs to a different case')
        result['face_origin_policy']=p
    from .blender_sources import evaluated_geometry,source_geometry
    original={r['id']:r['geometry_sha256'] for r in manifest or []}
    flips={r.uid:r.flip_normals for r in scene.gnm_bone_sources if r.enabled}
    sources={r.uid:r.source_object for r in scene.gnm_bone_sources if r.enabled}
    patches={r.uid:r.result_object for r in scene.gnm_restoration_regions if r.enabled and r.result_object}
    if (len(sources)!=sum(r.enabled for r in scene.gnm_bone_sources)
            or len(patches)!=sum(1 for r in scene.gnm_restoration_regions if r.enabled and r.result_object)
            or set(sources)&set(patches)):
        raise ValueError('Face provenance requires distinct source and region IDs')
    cache={}
    records={}
    base={}
    for m in scene.gnm_markers:
        b=m.bone_empty
        if not m.is_placed or core.RECEIPT not in b:
            continue
        r=json.loads(b[core.RECEIPT])
        core.validate_receipt(r,dict(bone_source_id=b.get('gnm_bone_source_id'),
            bone_source_geometry_sha256=b.get('gnm_source_sha256_at_placement'),
            bone_xyz_mm=list(b.matrix_world.translation),bone_status=m.bone_status))
        uid=r['source_id']
        obj=(sources if r['origin']=='original' else patches).get(uid)
        if (not obj or scene.objects.get(obj.name)!=obj or
                (r['origin']!='original' and obj.get('gnm_region_patch')!=uid)):
            raise ValueError(m.label+': bound face source unavailable')
        if uid not in cache:
            if r['origin']=='original':
                h=original.get(uid) if manifest is not None else source_geometry(obj,bpy.context.evaluated_depsgraph_get(),flips[uid])[2]
            else:
                h=evaluated_geometry(obj,bpy.context.evaluated_depsgraph_get())[2]
            cache[uid]=(h,check(obj.data,obj),lineage(obj))
        if cache[uid]!=(r['geometry_sha256'],r['origin'],r['lineage_sha256']) or r['polygon']>=len(obj.data.polygons):
            raise ValueError(m.label+': stale face provenance; re-place on the current fragment')
        records[m.label]=r
        if raw and _api._marker_terms(scene,m)[0]:
            base[m.label]=_api._marker_terms(scene,m,origin_factors=False)[1]
    if raw:
        result['face_origin_base_weights']=base
    if records:
        result['face_origins']=records
    return result


def donor(context):
    scene=context.scene
    src=scene.gnm_origin_donor
    note=scene.gnm_origin_donor_note.strip()
    if (not src or scene.objects.get(src.name) or src.mode!='OBJECT' or src.type!='MESH'
            or src.modifiers or src.data.shape_keys or src.animation_data or src.constraints or src.parent
            or src.data.animation_data or not core._str(note) or not _api._is_mm_scene(scene)
            or any(o.type=='MESH' and o.data==src.data for o in scene.objects)):
        raise ValueError('Choose an independent static aligned donor outside the case and document its source; use world mm')
    from .blender_sources import generated_surface
    if not src.users_scene or any(not _api._is_mm_scene(s) for s in src.users_scene):
        raise ValueError('Use a separate donor scene with the same metric scale, 0.001')
    if src.data.attributes.get(core.ATTRIBUTE) or generated_surface(src):
        raise ValueError('Supply the reviewed external donor region, not a generated patch')
    transform=np.array(src.matrix_world,dtype=float)
    if not np.isfinite(transform).all() or abs(np.linalg.det(transform[:3,:3]))<1e-12:
        raise ValueError('Invalid donor transform')
    src.data.calc_loop_triangles()
    points=np.array([tuple(v.co) for v in src.data.vertices],dtype=float)
    tris=np.array([tuple(t.vertices) for t in src.data.loop_triangles],dtype=np.int32)
    if not len(points) or not len(tris) or not np.isfinite(points).all():
        raise ValueError('Donor mesh needs finite vertices and faces')
    world=points@transform[:3,:3].T+transform[:3,3]
    if np.linalg.det(transform[:3,:3])<0:
        tris=tris[:,::-1]
    uid=uuid.uuid4().hex
    audit=dict(origin='donor',method='explicit copy of aligned external donor region; no registration or mirroring',
               donor_object=src.name,source_note=note,source_to_case_matrix=transform.tolist(),
               copied_geometry_sha256=hashlib.sha256(world.astype('<f8').tobytes()+tris.astype('<i8').tobytes()).hexdigest())
    mesh=bpy.data.meshes.new('GNM_Donor_'+src.name)
    obj=row=None
    try:
        mesh.from_pydata(world.tolist(),[],tris.tolist())
        mesh.update()
        tag(mesh,'donor')
        obj=bpy.data.objects.new('GNM_Donor_'+src.name,mesh)
        obj['gnm_region_patch']=uid
        obj['gnm_external_donor']=True
        obj['gnm_restoration_metadata']=json.dumps(audit,allow_nan=False,sort_keys=True)
        scene.collection.objects.link(obj)
        row=scene.gnm_restoration_regions.add()
        row.uid,row.name,row.result_object,row.action,row.notes=uid,src.name,obj,'DONOR',note
        row.donor_reference=src
        scene.gnm_restoration_active_index=len(scene.gnm_restoration_regions)-1
    except Exception:
        if row is not None:
            scene.gnm_restoration_regions.remove(len(scene.gnm_restoration_regions)-1)
        if obj is not None:
            bpy.data.objects.remove(obj,do_unlink=True)
        if not mesh.users:
            bpy.data.meshes.remove(mesh)
        raise


class GNM_OT_surface_origin(bpy.types.Operator):
    bl_idname='gnm.surface_origin'
    bl_label='Fragment Face Provenance'
    bl_options={'UNDO'}
    action: EnumProperty(items=[(s,s.title(),'') for s in ('ORIGINAL','DONOR','LOAD','CLEAR')])

    def execute(self,context):
        scene=context.scene
        try:
            if self.action=='ORIGINAL':
                obj=context.active_object
                if (not obj or not any(r.source_object==obj for r in _api._bone_sources(scene))
                        or obj.mode!='OBJECT' or obj.modifiers or obj.data.shape_keys or obj.data.users!=1
                        or obj.data.library or obj.data.get('gnm_origin_kind') or not len(obj.data.polygons)):
                    raise ValueError('Activate a registered single-user static mesh of verified original bone only')
                tag(obj.data,'original')
            elif self.action=='DONOR':
                donor(context)
            else:
                raw=''
                if self.action=='LOAD':
                    p=core.policy(_json(Path(bpy.path.abspath(scene.gnm_origin_file)).read_text(encoding='utf-8-sig')))
                    if p['case_id']!=_api._case_token(scene)[1]:
                        raise ValueError('Policy case ID mismatch')
                    raw=json.dumps(p,sort_keys=True)
                scene.gnm_origin_policy=raw
                if _api._LIVE.case_token==_api._case_token(scene):
                    _api._LIVE.geometry_epoch+=1
                    _api._request_refit(scene)
        except (ValueError,RuntimeError,OSError) as exc:
            self.report({'WARNING'},str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


def draw(box,scene):
    box.prop(scene,'gnm_show_face_origin')
    if not scene.gnm_show_face_origin:
        return
    box.operator('gnm.surface_origin',text='Mark All Faces of Active Preserved Bone as Original').action='ORIGINAL'
    box.prop(scene,'gnm_tag_mirrors')
    box.prop(scene,'gnm_origin_donor')
    box.prop(scene,'gnm_origin_donor_note')
    box.operator('gnm.surface_origin',text='Copy Aligned External Donor Region').action='DONOR'
    box.prop(scene,'gnm_origin_file')
    box.operator('gnm.surface_origin',text='Load Case Factors').action='LOAD'
    if scene.gnm_origin_policy:
        box.label(text='Face-origin factors active (uncalibrated)')
        box.operator('gnm.surface_origin',text='Disable Factors').action='CLEAR'


def register(api):
    global _api
    _api=api
    bpy.utils.register_class(GNM_OT_surface_origin)
    sc=bpy.types.Scene
    sc.gnm_show_face_origin=BoolProperty(name='Face provenance and donor regions',default=False)
    sc.gnm_tag_mirrors=BoolProperty(name='Tag faces on generated mirror patches',default=False)
    sc.gnm_origin_donor=PointerProperty(type=bpy.types.Object,name='Aligned external donor region',
        poll=lambda self,obj:obj.type=='MESH' and self.objects.get(obj.name) is None)
    sc.gnm_origin_donor_note=StringProperty(name='Donor source / alignment note')
    sc.gnm_origin_file=StringProperty(name='Case sensitivity factors',subtype='FILE_PATH')
    sc.gnm_origin_policy=StringProperty(default='',options={'HIDDEN'})


def unregister():
    global _api
    for name in ('gnm_show_face_origin','gnm_tag_mirrors','gnm_origin_donor','gnm_origin_donor_note','gnm_origin_file','gnm_origin_policy'):
        delattr(bpy.types.Scene,name)
    bpy.utils.unregister_class(GNM_OT_surface_origin)
    _decode.cache_clear()
    _api=None

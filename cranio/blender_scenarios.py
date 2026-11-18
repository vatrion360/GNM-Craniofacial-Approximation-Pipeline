"""Main-thread scenario preview and explicit activation. No marker RNA edits."""
import json
from functools import lru_cache
from pathlib import Path
import textwrap

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from . import scenarios
from .tissue import _json

_api=None


@lru_cache(maxsize=32)
def _decode(raw):
    return scenarios.validate(_json(raw))


def active(scene):
    raw=scene.gnm_guide_active
    if not raw:
        return None
    spec=_decode(raw)
    if spec['case_id']!=scene.gnm_settings.case_id:
        raise ValueError('Guided scenario belongs to a different case; clear it or reapply')
    return spec


def metadata(scene):
    spec=active(scene)
    return {'guided_scenario':spec} if spec is not None else {}


def _draft(scene):
    custom=None
    if scene.gnm_guide_file:
        custom=_json(Path(bpy.path.abspath(scene.gnm_guide_file)).read_text(encoding='utf-8-sig'))
        if not isinstance(custom,dict):
            raise ValueError('Expected a scenario customization object')
    spec=scenarios.configure(scene.gnm_guide_choice,_api._case_token(scene)[1],scene.gnm_guide_note,custom)
    if custom:
        unknown=(set(custom['weights'])|set(custom['exclude']))-{m.label for m in scene.gnm_markers}
        if unknown:
            raise ValueError('Customization labels missing from current list: '+', '.join(sorted(unknown)))
    return json.dumps(spec,sort_keys=True,allow_nan=False)


def _invalidate(scene):
    live=_api._LIVE
    if live.case_token==_api._case_token(scene):
        live.geometry_epoch+=1
        _api._request_refit(scene)


class GNM_OT_guided_case(bpy.types.Operator):
    bl_idname='gnm.guided_case'
    bl_label='Guided Skull Scenario'
    bl_options={'UNDO'}
    action: EnumProperty(items=[(k,k.title(),'') for k in ('PREVIEW','APPLY','CLEAR')])

    def execute(self,context):
        scene=context.scene
        try:
            if self.action=='CLEAR':
                scene.gnm_guide_active=scene.gnm_guide_preview=''
                _invalidate(scene)
            else:
                raw=_draft(scene)
                if self.action=='PREVIEW':
                    scene.gnm_guide_preview=raw
                elif raw!=scene.gnm_guide_preview:
                    raise ValueError('Preview the current choices before applying them')
                else:
                    scene.gnm_guide_active=raw
                    _invalidate(scene)
        except (ValueError,OSError,RuntimeError) as exc:
            self.report({'WARNING'},str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


def draw(layout,scene):
    layout.prop(scene,'gnm_show_guide',toggle=True)
    if scene.gnm_guide_active:
        try:
            layout.label(text='Active marker scenario: '+active(scene)['scenario'])
        except ValueError:
            layout.label(text='Stale scenario; clear or reapply',icon='ERROR')
    if not scene.gnm_show_guide:
        return
    box=layout.box()
    box.prop(scene,'gnm_guide_choice')
    profile=scenarios.catalog()[0]['profiles'][scene.gnm_guide_choice]
    for line in textwrap.wrap(profile['prompt'],width=48):
        box.label(text=line)
    box.prop(scene,'gnm_guide_note')
    box.prop(scene,'gnm_guide_file')
    box.operator('gnm.guided_case',text='Preview Marker Rules').action='PREVIEW'
    if scene.gnm_guide_preview:
        try:
            spec=_decode(scene.gnm_guide_preview)
        except ValueError:
            box.operator('gnm.guided_case',text='Clear Stale Guide').action='CLEAR'
            return
        profile=scenarios.catalog()[0]['profiles'][spec['scenario']]
        custom=spec['custom'] or {}
        box.label(text='Preview: '+profile['title'])
        box.label(text='Weights: '+str(custom.get('weights') or 'existing marker weights'))
        box.label(text='Case exclusions: '+', '.join(custom.get('exclude',[])))
        if profile['exclude_mandible']:
            box.label(text='Mandibular catalogue sites excluded')
        box.label(text='Only manually enabled, observed markers are eligible')
        for name in profile['required_checks']+custom.get('required_policy_ids',[]):
            box.label(text='Required: '+name)
        box.operator('gnm.guided_case',text='Apply Previewed Rules').action='APPLY'
    if scene.gnm_guide_active or scene.gnm_guide_preview:
        box.operator('gnm.guided_case',text='Clear Guide / Restore Manual Rules').action='CLEAR'


def register(api):
    global _api
    _api=api
    profiles=scenarios.catalog()[0]['profiles']
    bpy.utils.register_class(GNM_OT_guided_case)
    bpy.types.Scene.gnm_show_guide=BoolProperty(name='Guided skull scenario',default=False)
    bpy.types.Scene.gnm_guide_choice=EnumProperty(name='Scenario to preview',items=[
        (k,p['title'],p['prompt']) for k,p in profiles.items()],default='complete')
    bpy.types.Scene.gnm_guide_file=StringProperty(name='Case marker rules (optional)',subtype='FILE_PATH')
    bpy.types.Scene.gnm_guide_note=StringProperty(name='Preservation / review note')
    for k in ('gnm_guide_preview','gnm_guide_active'):
        setattr(bpy.types.Scene,k,StringProperty(default='',options={'HIDDEN'}))


def unregister():
    global _api
    for k in ('gnm_show_guide','gnm_guide_choice','gnm_guide_file','gnm_guide_note','gnm_guide_preview','gnm_guide_active'):
        delattr(bpy.types.Scene,k)
    bpy.utils.unregister_class(GNM_OT_guided_case)
    _decode.cache_clear()
    _api=None

"""Main-thread Blender adapter for explicit reference frames; no fit changes."""
import json
from pathlib import Path

import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Matrix, Vector

from . import reference_frame as core
from .validation import sha256_file

_api = None


def attach_snapshot(scene, document):
    """Preserve an old frame as stale metadata; never silently use it for views."""
    settings = scene.gnm_reference_frame
    if not settings.record:
        return
    record = {}
    try:
        record = json.loads(settings.record)
        if not isinstance(record, dict):
            record = {}
            raise ValueError('Invalid stored reference frame')
        path = bpy.path.abspath(settings.config_path)
        config = json.loads(Path(path).read_text(encoding='utf-8'))
        if sha256_file(path) != record.get('config_sha256'):
            raise ValueError('Reference-frame configuration changed')
        if core.input_signature(document, config) != record.get('input_signature'):
            raise ValueError('Reference observations or review changed')
        core.camera_basis(record, 'front')
    except (ValueError, TypeError, KeyError, OSError) as exc:
        record.update(status='stale', stale_reason=str(exc))
    document['reference_frame'] = record


def current_record(scene):
    document = _api._core_module('blender_craniometry').document(scene)
    record = document.get('reference_frame', {})
    if record.get('status') != 'current':
        raise ValueError('Reference frame missing/stale: recompute after reviewing references and configuration')
    return record


def compute(scene):
    settings = scene.gnm_reference_frame
    path = bpy.path.abspath(settings.config_path)
    digest = sha256_file(path)
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    document = _api._core_module('blender_craniometry').document(scene, include_frame=False)
    record = core.compute_frame(document, config)
    if sha256_file(path) != digest:
        raise ValueError('Configuration changed during computation')
    record['config_sha256'] = digest
    record['implementation_sha256'] = sha256_file(core.__file__)
    settings.record = json.dumps(record, sort_keys=True, allow_nan=False)
    settings.status = f"Last computation: midline RMS {record['geometry']['midsagittal']['residual_rms_mm']:.3f} mm (not accuracy)"
    return record


class GNMReferenceFrameSettings(PropertyGroup):
    config_path: StringProperty(name='Frame configuration JSON', subtype='FILE_PATH', default='//reference_frame_config.json')
    record: StringProperty(default='')
    status: StringProperty(default='No reference frame computed')
    use_for_captures: BoolProperty(name='Use reviewed frame for standardized captures', default=False)


class GNM_OT_reference_frame(Operator):
    bl_idname = 'gnm.reference_frame'
    bl_label = 'Anatomical Reference Frame'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=[(s, s, '') for s in ('TEMPLATE', 'COMPUTE', 'CLEAR', 'FRONT', 'PROFILE', 'LEFT', 'THREE_QUARTER')])

    def execute(self, context):
        settings = context.scene.gnm_reference_frame
        try:
            if self.action == 'TEMPLATE':
                path = bpy.path.abspath(settings.config_path)
                # CLI output refusal is shared; catch SystemExit only for its error path.
                core.main(['template', '--output', path])
                settings.status = 'Template saved; configure and review before computing'
            elif self.action == 'COMPUTE':
                compute(context.scene)
            elif self.action == 'CLEAR':
                settings.record, settings.status, settings.use_for_captures = '', 'Frame cleared', False
            else:
                record = current_record(context.scene)
                view = '3quarter' if self.action == 'THREE_QUARTER' else self.action.lower()
                rotation = Matrix(core.camera_basis(record, view).tolist()).to_quaternion()
                areas = [a for a in context.screen.areas if a.type == 'VIEW_3D'] if context.screen else []
                if not areas:
                    raise ValueError('No 3D viewport available')
                for area in areas:
                    region = area.spaces.active.region_3d
                    region.view_rotation = rotation
                    region.view_location = Vector(record['geometry']['origin_mm'])
                    region.view_perspective = 'ORTHO'
                    area.tag_redraw()
            return {'FINISHED'}
        except (ValueError, TypeError, KeyError, OSError, SystemExit, np.linalg.LinAlgError) as exc:
            settings.status = str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class GNM_PT_reference_frame(Panel):
    bl_idname = 'GNM_PT_reference_frame'
    bl_label = 'Anatomical Reference Frame (opt-in)'
    bl_space_type, bl_region_type, bl_category = 'VIEW_3D', 'UI', 'GNM Markers'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout, settings = self.layout, context.scene.gnm_reference_frame
        layout.prop(settings, 'config_path')
        row = layout.row(align=True)
        row.operator('gnm.reference_frame', text='Write Blank Template').action = 'TEMPLATE'
        row.operator('gnm.reference_frame', text='Compute Reviewed Frame').action = 'COMPUTE'
        layout.label(text='Observed Porion L/R + selected Orbitale required')
        layout.label(text='Independent cranial midline; no mandibular references')
        layout.label(text=settings.status)
        layout.label(text='Current status checked on use/export')
        row = layout.row(align=True)
        for action, label in [('FRONT', 'Front'), ('THREE_QUARTER', '3/4'), ('PROFILE', 'Right'), ('LEFT', 'Left')]:
            row.operator('gnm.reference_frame', text=label).action = action
        layout.prop(settings, 'use_for_captures')
        layout.operator('gnm.reference_frame', text='Clear Frame').action = 'CLEAR'


CLASSES = (GNMReferenceFrameSettings, GNM_OT_reference_frame, GNM_PT_reference_frame)


def register(addon):
    global _api
    _api = addon
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gnm_reference_frame = PointerProperty(type=GNMReferenceFrameSettings)


def unregister():
    del bpy.types.Scene.gnm_reference_frame
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

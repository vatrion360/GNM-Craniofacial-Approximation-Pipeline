"""Explicit feature export on Blender's main thread; no redraw fitting/hashing."""
import json
from pathlib import Path

import bpy
import numpy as np
from bpy.props import EnumProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

from . import features as core
from .export import atomic_text
from .validation import sha256_file, validate_outputs

_api = None


class GNMFeatureSettings(PropertyGroup):
    config_path: StringProperty(name='Feature protocol JSON', subtype='FILE_PATH', default='//feature_config.json')
    output_path: StringProperty(name='Feature results JSON', subtype='FILE_PATH', default='//skull_features.json')
    status: StringProperty(default='Not run; explicit protocol required')


class GNM_OT_features(Operator):
    bl_idname = 'gnm.cranial_features'
    bl_label = 'Cranial Feature Measurements'
    action: EnumProperty(items=[('TEMPLATE', 'Write blank protocol', ''), ('EXPORT', 'Compute and export', '')])

    def execute(self, context):
        scene, settings = context.scene, context.scene.gnm_features
        try:
            path = bpy.path.abspath(settings.config_path)
            if self.action == 'TEMPLATE':
                core.main(['template', '--output', path])
                settings.status = 'Blank protocol saved; configure definitions and sources'
                return {'FINISHED'}
            digest = sha256_file(path)
            config = json.loads(Path(path).read_text(encoding='utf-8'))
            core.validate_config(config)
            if (config['mandible_pose'] or {}).get('reviewed') and not scene.gnm_settings.mandible_aligned:
                raise ValueError('Confirm mandibular articulation in the scene before using a reviewed mandibular protocol')
            document = _api._core_module('blender_craniometry').document(scene, include_frame=False)
            result = core.compute_features(document, config)
            if sha256_file(path) != digest:
                raise ValueError('Feature protocol changed during computation')
            result.update(config_sha256=digest, input_sha256=core.definition_hash(document),
                          input_hash_method='canonical_json_sha256', implementation_sha256=sha256_file(core.__file__))
            output = bpy.path.abspath(settings.output_path)
            inputs = [path, bpy.data.filepath, bpy.path.abspath(scene.gnm_live.npz_path),
                      bpy.path.abspath(scene.gnm_live.json_path), scene.gnm_settings.sursa_fisier]
            inputs += [s.get('acquisition_path', '') for s in document['bone_sources']]
            validate_outputs(inputs, [output])
            with atomic_text(output) as stream:
                stream.write(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False)+'\n')
            count = sum(row['status'] == 'measured' for row in result['features'].values())
            settings.status = f'Last export: {count}/{len(result["features"])} measured; inspect per-feature status'
            text = bpy.data.texts.get('GNM_Cranial_Features') or bpy.data.texts.new('GNM_Cranial_Features')
            text.clear()
            text.write(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
            return {'FINISHED'}
        except (ValueError, TypeError, KeyError, OSError, OverflowError, SystemExit, np.linalg.LinAlgError) as exc:
            settings.status = str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class GNM_PT_features(Panel):
    bl_idname = 'GNM_PT_features'
    bl_label = 'Cranial Features (explicit protocol)'
    bl_space_type, bl_region_type, bl_category = 'VIEW_3D', 'UI', 'GNM Markers'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        settings, layout = context.scene.gnm_features, self.layout
        layout.operator('gnm.craniometry', text='Add Bone Feature References').action = 'INIT_FEATURES'
        layout.prop(settings, 'config_path')
        layout.operator('gnm.cranial_features', text='Write Blank Protocol').action = 'TEMPLATE'
        layout.prop(settings, 'output_path')
        layout.operator('gnm.cranial_features', text='Compute / Export Reviewed Features').action = 'EXPORT'
        layout.label(text=settings.status)
        layout.label(text='Explicit export; last results are not a live measurement')
        layout.label(text='Missing anatomy stays unavailable; no diagnostic inference')


CLASSES = (GNMFeatureSettings, GNM_OT_features, GNM_PT_features)


def register(addon):
    global _api
    _api = addon
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gnm_features = PointerProperty(type=GNMFeatureSettings)


def unregister():
    del bpy.types.Scene.gnm_features
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

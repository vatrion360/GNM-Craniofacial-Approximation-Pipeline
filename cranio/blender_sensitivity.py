"""Explicit pose-sensitivity export; never moves scene objects or fits a face."""
import json
from pathlib import Path
import bpy
import numpy as np
from bpy.props import EnumProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from . import sensitivity as core
from .features import definition_hash
from .export import atomic_text
from .validation import sha256_file, validate_outputs

_api = None


class GNMSensitivitySettings(PropertyGroup):
    config_path: StringProperty(name='Pose scenarios JSON',subtype='FILE_PATH',default='//sensitivity_config.json')
    output_path: StringProperty(name='Sensitivity results JSON',subtype='FILE_PATH',default='//pose_sensitivity.json')
    status: StringProperty(default='Not run; no implicit pose ranges')


class GNM_OT_sensitivity(Operator):
    bl_idname='gnm.pose_sensitivity'
    bl_label='Mandibular Pose Sensitivity'
    action: EnumProperty(items=[('TEMPLATE','Write blank configuration',''),('EXPORT','Compute and export','')])

    def execute(self,context):
        scene,st=context.scene,context.scene.gnm_sensitivity
        try:
            path=bpy.path.abspath(st.config_path)
            if self.action=='TEMPLATE':
                core.main(['template','--output',path])
                st.status='Blank configuration saved; supply reviewed ranges, sources and feature definitions'
                return {'FINISHED'}
            if not scene.gnm_settings.mandible_aligned:
                raise ValueError('Review baseline mandibular articulation before sensitivity analysis')
            _api._core_module('blender_articulation').require_review(scene,deep=True)
            digest=sha256_file(path)
            config=json.loads(Path(path).read_text(encoding='utf-8'))
            document=_api._core_module('blender_craniometry').document(scene,include_frame=False)
            output=bpy.path.abspath(st.output_path)
            inputs=[path,bpy.data.filepath,scene.gnm_settings.sursa_fisier,scene.gnm_settings.ultim_export_csv,
                    bpy.path.abspath(scene.gnm_live.npz_path),bpy.path.abspath(scene.gnm_live.json_path)]
            inputs += [s.get('acquisition_path','') for s in document['bone_sources']]
            validate_outputs(inputs,[output])
            result=core.compute(document,config)
            if sha256_file(path)!=digest:
                raise ValueError('Sensitivity configuration changed during computation')
            result.update(input_sha256=definition_hash(document),input_hash_method='canonical_json_sha256',
                          config_sha256=digest,implementation_sha256=sha256_file(core.__file__))
            with atomic_text(output) as stream:
                stream.write(core.rf._json(result)+'\n')
            text=bpy.data.texts.get('GNM_Pose_Sensitivity') or bpy.data.texts.new('GNM_Pose_Sensitivity')
            text.clear(); text.write(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
            st.status=f"Exported {len(result['poses'])} hypothetical poses; original geometry unchanged"
            return {'FINISHED'}
        except (ValueError,TypeError,KeyError,OSError,OverflowError,SystemExit,np.linalg.LinAlgError) as exc:
            st.status=str(exc)
            self.report({'ERROR'},str(exc))
            return {'CANCELLED'}


class GNM_PT_sensitivity(Panel):
    bl_idname='GNM_PT_sensitivity'
    bl_label='Mandibular Pose Sensitivity (opt-in)'
    bl_space_type,bl_region_type,bl_category='VIEW_3D','UI','GNM Markers'
    bl_options={'DEFAULT_CLOSED'}

    def draw(self,context):
        st,layout=context.scene.gnm_sensitivity,self.layout
        layout.prop(st,'config_path')
        layout.operator('gnm.pose_sensitivity',text='Write Blank Configuration').action='TEMPLATE'
        layout.prop(st,'output_path')
        layout.operator('gnm.pose_sensitivity',text='Compute / Export Pose Scenarios').action='EXPORT'
        layout.label(text=st.status)
        layout.label(text='Sampled ranges; not confidence or accuracy')
        layout.label(text='Landmarks, features and profile targets; no face refit')


CLASSES=(GNMSensitivitySettings,GNM_OT_sensitivity,GNM_PT_sensitivity)


def register(addon):
    global _api
    _api=addon
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gnm_sensitivity=PointerProperty(type=GNMSensitivitySettings)


def unregister():
    del bpy.types.Scene.gnm_sensitivity
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

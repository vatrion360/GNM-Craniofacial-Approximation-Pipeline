"""Main-thread operations on demand; panel redraw never reads geometry or files."""
from pathlib import Path
import zipfile

import bpy
from bpy.props import EnumProperty



def pick(context, api):
    from .blender_sources import source_geometry
    from .blender_surface_origin import check
    scene, obj = context.scene, context.active_object
    if not obj or obj.type != 'MESH' or obj.mode != 'OBJECT' or not api._is_mm_scene(scene):
        raise ValueError('Use Object Mode in the mm case scene after selecting one preserved tooth vertex')
    rows = [r for r in api._bone_sources(scene) if r.source_object == obj]
    if (len(rows) != 1 or not rows[0].uid or not scene.gnm_settings.case_id or obj.modifiers or obj.data.shape_keys
            or check(obj.data,obj) != 'original'):
        raise ValueError('Select a static registered preserved fragment stamped as original, in the current case')
    ids = [v.index for v in obj.data.vertices if v.select]
    if len(ids) != 1:
        raise ValueError('Select exactly one dental vertex in Edit Mode then return to Object Mode')
    points, _, digest, _ = source_geometry(obj,context.evaluated_depsgraph_get(),rows[0].flip_normals)
    return dict(case_id=scene.gnm_settings.case_id, source_id=rows[0].uid,
                geometry_sha256=digest, xyz_mm=points[ids[0]].tolist())


class GNM_OT_dental_consistency(bpy.types.Operator):
    bl_idname = 'gnm.dental_consistency'
    bl_label = 'Dental Fit Consistency'
    action: EnumProperty(items=[(s,s.title(),'') for s in ('TEMPLATE','PICK','COMPARE')])

    def execute(self, context):
        from . import dental_consistency as dental
        from .blender_record import _api
        scene, settings = context.scene, context.scene.gnm_record
        def path(s):
            if not s.strip():
                raise ValueError('Select the required input and output paths')
            return bpy.path.abspath(s)
        try:
            if self.action == 'PICK':
                observation = pick(context, _api)
                block = bpy.data.texts.new('GNM_Observed_Tooth_Point')
                block.write(dental.canonical_bytes(observation).decode())
                message = 'Observed point in Text Editor: '+block.name
            elif self.action == 'TEMPLATE':
                dental.run(path(settings.report_path),path(settings.dental_sites))
                message = 'Created dental sites template: '+Path(settings.dental_sites).name
            else:
                result = dental.run(path(settings.report_path),path(settings.dental_output),
                                    model=path(scene.gnm_live.npz_path),sites=path(settings.dental_sites),
                                    artifacts=path(settings.artifacts_path) if settings.artifacts_path.strip() else None)
                block = bpy.data.texts.new('GNM_Dental_Comparison')
                block.write(dental.result_text(result))
                summary = result['summary']['final']
                message = f"Measured {summary['measured']} of {summary['total']} dental sites. Text Editor: "+block.name
            settings.dental_status = message
            self.report({'INFO'}, message)
            return {'FINISHED'}
        except (OSError, ValueError, KeyError, OverflowError, zipfile.BadZipFile) as exc:
            settings.dental_status = 'Cannot complete dental comparison step: '+str(exc)
            self.report({'WARNING'}, settings.dental_status)
            return {'CANCELLED'}


def draw(column, settings):
    column.prop(settings,'show_dental')
    if not settings.show_dental:
        return
    box = column.box()
    box.prop(settings,'dental_sites')
    box.operator('gnm.dental_consistency',text='Write New Dental Sites Template').action='TEMPLATE'
    box.operator('gnm.dental_consistency',text='Read Selected Preserved Tooth Point').action='PICK'
    box.prop(settings,'dental_output')
    box.operator('gnm.dental_consistency',text='Compare Saved Dental Positions').action='COMPARE'
    if settings.dental_status:
        import textwrap
        for line in textwrap.wrap(settings.dental_status,48):
            box.label(text=line)

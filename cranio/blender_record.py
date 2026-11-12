"""Explicit asynchronous approximation-record export; Blender main-thread UI only."""
import datetime
from pathlib import Path
import textwrap
import uuid

import bpy
from bpy.props import EnumProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

from . import record_job

_api = None
_JOB = dict(process=None, log=None, scene=None, folder=None, request=None)


class GNMRecordSettings(PropertyGroup):
    report_path: StringProperty(name='Saved fit report JSON', subtype='FILE_PATH')
    output_parent: StringProperty(name='Output parent folder', subtype='DIR_PATH',
        description='A new record subfolder is created here; empty uses the source report folder')
    artifacts_path: StringProperty(name='Moved artifacts folder (optional)', subtype='DIR_PATH')
    limitations_path: StringProperty(name='Approved RO/EN limitations (optional)', subtype='FILE_PATH')
    uncertainty_path: StringProperty(name='Existing A2.1 ensemble (optional)', subtype='FILE_PATH')
    validity_domain_path: StringProperty(name='Declared validation domain (optional)', subtype='FILE_PATH')
    domain_case_path: StringProperty(name='Bound domain observations (optional)', subtype='FILE_PATH')
    uncertainty_scenario: EnumProperty(name='Ensemble prior scenario', items=[
        ('NONE', 'Not selected', 'No implicit prior scenario'),
        ('off', 'Prior off', 'Explicit neutral ensemble scenario'),
        ('on', 'Prior on', 'Explicit matching prior ensemble scenario')], default='NONE')
    status: StringProperty(default='Not exported; select a saved offline fit report', options={'SKIP_SAVE'})
    result_path: StringProperty(name='Last completed record', subtype='FILE_PATH', options={'SKIP_SAVE'})
    result_text: StringProperty(name='Report text block', options={'SKIP_SAVE'})


def _scene():
    """A deleted/replaced scene must never receive another scene's completion."""
    scene = _JOB.get('scene')
    try:
        if scene is not None and bpy.data.scenes.get(scene.name) == scene:
            return scene
    except ReferenceError:
        pass
    return None


def stop():
    """Bounded process cleanup on cancel, file load and unregister; retain files."""
    process = _JOB.get('process')
    try:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except Exception:
                process.kill()
                process.wait(timeout=2)
    finally:
        if _JOB.get('log') is not None:
            _JOB['log'].close()
        _JOB.update(process=None, log=None, scene=None, folder=None, request=None)
        if bpy.app.timers.is_registered(poll_job):
            bpy.app.timers.unregister(poll_job)


def poll_job():
    process = _JOB.get('process')
    if process is None:
        return None
    scene = _scene()
    if scene is None:
        stop()
        return None
    code = process.poll()
    if code is None:
        return .5
    folder, request = Path(_JOB['folder']), _JOB['request']
    _JOB['log'].close()
    _JOB.update(process=None, log=None, scene=None, folder=None, request=None)
    settings = scene.gnm_record
    if code != 0:
        settings.status = f'Failed ({code}); inspect {folder / "run.log"}'
        return None
    try:
        record, page = record_job.read_result(folder/'record', request)
        # New text blocks preserve previous reports. No scene mesh is changed.
        text = bpy.data.texts.new('GNM_Approximation_Record_'+folder.name)
        text.write(page)
        settings.result_path = str(folder/'record'/'approximation_record.json')
        settings.result_text = text.name
        domain = record['assessments']['validity_domain']
        banner = ('; '+domain['banner']) if domain['status'] != 'not_assessed' else ''
        settings.status = 'Recorded; '+record['status']+banner+'; '+settings.result_path
    except (ValueError, OSError, TypeError, KeyError) as exc:
        settings.status = 'Result not displayed: '+str(exc)+'; inspect '+str(folder/'run.log')
    return None


class GNM_OT_record_use_active(Operator):
    bl_idname = 'gnm.record_use_active'
    bl_label = 'Use Active Fit Report'

    @classmethod
    def poll(cls, context):
        return _JOB['process'] is None and context.active_object is not None

    def execute(self, context):
        settings = context.scene.gnm_record
        path = context.active_object.get('gnm_report')
        if not isinstance(path, str) or not path.strip():
            settings.status = 'Active object has no saved offline run report; select a report JSON explicitly'
            self.report({'WARNING'}, settings.status)
            return {'CANCELLED'}
        settings.report_path = path
        settings.status = 'Selected saved fit report; current scene edits are not included'
        return {'FINISHED'}


class GNM_OT_record_export(Operator):
    bl_idname = 'gnm.export_approximation_record'
    bl_label = 'Export Approximation Record'

    @classmethod
    def poll(cls, context):
        return (_JOB['process'] is None and _api._OFFLINE.get('process') is None
                and bool(context.scene.gnm_record.report_path.strip()))

    def execute(self, context):
        scene, settings = context.scene, context.scene.gnm_record
        try:
            def path(value):
                return bpy.path.abspath(value) if value.strip() else None
            request = record_job.prepare_request(path(settings.report_path),
                artifacts=path(settings.artifacts_path), limitations=path(settings.limitations_path),
                uncertainty=path(settings.uncertainty_path),
                scenario=None if settings.uncertainty_scenario == 'NONE' else settings.uncertainty_scenario,
                validity_domain=path(settings.validity_domain_path), domain_case=path(settings.domain_case_path))
            info = _api._check_external_python(scene)
            parent = Path(path(settings.output_parent) or Path(request['report_path']).parent)
            folder = parent/('record_'+datetime.datetime.now().strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:8])
            folder.mkdir(parents=True, exist_ok=False)
            log = (folder/'run.log').open('w', encoding='utf-8')
            try:
                process = record_job.start_record(info, Path(_api.__file__).resolve().parent,
                                                  request, folder/'record', log)
            except Exception:
                log.close()
                raise
            _JOB.update(process=process, log=log, scene=scene, folder=str(folder), request=request)
            settings.result_path = ''
            settings.result_text = ''
            settings.status = 'Exporting saved fit record; '+str(folder)
            try:
                bpy.app.timers.register(poll_job, first_interval=.5)
            except Exception:
                stop()
                raise
            return {'FINISHED'}
        except (ValueError, OSError, TypeError, ImportError, RuntimeError) as exc:
            settings.status = 'Cannot export: '+str(exc)
            self.report({'ERROR'}, settings.status)
            return {'CANCELLED'}


class GNM_OT_record_cancel(Operator):
    bl_idname = 'gnm.cancel_record_export'
    bl_label = 'Cancel Record Export'

    @classmethod
    def poll(cls, context):
        return _JOB['process'] is not None

    def execute(self, context):
        scene, folder = _scene(), _JOB['folder']
        stop()
        if scene is not None:
            scene.gnm_record.status = 'Stopped; files retained for inspection: '+str(folder)
        return {'FINISHED'}


class GNM_PT_record(Panel):
    bl_idname = 'GNM_PT_record'
    bl_label = 'Approximation Record (saved fit)'
    bl_space_type, bl_region_type, bl_category = 'VIEW_3D', 'UI', 'GNM Markers'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        settings, layout = context.scene.gnm_record, self.layout
        column = layout.column()
        column.enabled = _JOB['process'] is None
        column.operator('gnm.record_use_active')
        for name in ('report_path', 'output_parent', 'artifacts_path', 'limitations_path', 'uncertainty_path',
                     'validity_domain_path', 'domain_case_path'):
            column.prop(settings, name)
        if settings.uncertainty_path or settings.uncertainty_scenario != 'NONE':
            column.prop(settings, 'uncertainty_scenario')
        column.label(text='Uses the external Python selected in Offline fit')
        column.operator('gnm.export_approximation_record')
        layout.operator('gnm.cancel_record_export')
        for line in textwrap.wrap(settings.status, 48):
            layout.label(text=line)
        if settings.result_path:
            row = layout.column()
            row.enabled = False
            row.prop(settings, 'result_path')
            row.prop(settings, 'result_text')
        layout.label(text='Saved fit files only; current scene edits are not recorded')
        layout.label(text='Integrity and provenance are not scientific validation')


CLASSES = (GNMRecordSettings, GNM_OT_record_use_active, GNM_OT_record_export, GNM_OT_record_cancel, GNM_PT_record)


def register(addon):
    global _api
    _api = addon
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gnm_record = PointerProperty(type=GNMRecordSettings)


def unregister():
    global _api
    stop()
    del bpy.types.Scene.gnm_record
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    _api = None

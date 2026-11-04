"""Main-thread, explicit anatomical-rule inspection; redraw never reads a mesh.

Displayed measurements are historical snapshots, not continuously validated QC.
Only the bundled rule registry is used. No formula or threshold is supplied here.
"""
import hashlib
import json
from pathlib import Path
import textwrap

import bpy
import numpy as np
from bpy.props import EnumProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

from .rules import comparison as core
from .rules import load_registry
from .rules.engine import readiness
from .tissue import _json
from .export import atomic_text
from .validation import finite_array, sha256_file, validate_outputs

_api = None


def _clear_measurement(settings, context):
    settings.result_json = ''
    settings.status = 'Inputs changed; compute a new snapshot'


class GNMRuleSettings(PropertyGroup):
    source: PointerProperty(name='Neutral fitted mesh', type=bpy.types.Object,
                            update=_clear_measurement)
    mapping_path: StringProperty(name='Reviewed feature map', subtype='FILE_PATH',
                                 default='//feature_map.json', update=_clear_measurement)
    output_path: StringProperty(name='Feature snapshot JSON', subtype='FILE_PATH',
                                default='//feature_snapshot.json')
    catalogue_json: StringProperty(options={'HIDDEN'}, default='')
    result_json: StringProperty(options={'HIDDEN'}, default='')
    status: StringProperty(default='Not run; no anatomical predictions enabled')


def _protected_inputs(scene, settings):
    paths = [bpy.data.filepath, bpy.path.abspath(scene.gnm_live.npz_path),
             bpy.path.abspath(scene.gnm_live.json_path), scene.gnm_settings.sursa_fisier,
             scene.gnm_settings.ultim_export_csv, bpy.path.abspath(settings.mapping_path)]
    source = settings.source
    if source is not None and source.get('gnm_report'):
        paths.append(bpy.path.abspath(source['gnm_report']))
    return paths


def _snapshot(context, registry):
    """Read a completed neutral native mesh; reject evaluated/edited alternatives."""
    scene, settings = context.scene, context.scene.gnm_rule_checks
    source = settings.source
    if source is None or source.type != 'MESH' or source.name not in scene.objects:
        raise ValueError('Select a neutral fitted mesh in this scene')
    if not _api._is_mm_scene(scene):
        raise ValueError('Use metric scene scale 0.001 for world-mm measurements')
    if source.get('gnm_presentation'):
        raise ValueError('Select the original neutral fit, not a presentation copy')
    if (source.mode != 'OBJECT' or source.modifiers or source.data.shape_keys
            or source.animation_data or source.constraints or source.parent or source.data.animation_data):
        raise ValueError('Use an Object-mode neutral mesh without modifiers, shape keys, animation, constraints or parent')
    paths = dict(model=Path(bpy.path.abspath(scene.gnm_live.npz_path)),
                 mapping=Path(bpy.path.abspath(settings.mapping_path)))
    if source.get('gnm_report') and not source.get('gnm_fit_state'):
        paths['fit_report'] = Path(bpy.path.abspath(source['gnm_report']))
    hashes = {key: sha256_file(path) for key, path in paths.items()}
    postfit = _api._core_module('blender_postfit')
    state = postfit.fit_state(source)
    if not isinstance(state, dict) or state.get('model_sha256') != hashes['model']:
        raise ValueError('Fit metadata does not match the selected model')
    count, model_triangles = core._model(paths['model'])
    if len(source.data.vertices) != count:
        raise ValueError('Native model vertex count required')
    matrix = finite_array(np.asarray(source.matrix_world), 'world matrix', (4, 4))
    local = postfit.coordinates(source.data.vertices).astype(float)
    vertices = finite_array(local @ matrix[:3, :3].T + matrix[:3, 3], 'world-mm vertices')
    triangles = postfit.topology(source.data)
    mapping = _json(paths['mapping'].read_text(encoding='utf-8-sig'))
    report = core.measure_and_compare(vertices, triangles, model_triangles, hashes['model'],
                                     mapping, registry=registry)
    if hashes != {key: sha256_file(path) for key, path in paths.items()}:
        raise ValueError('Input changed during measurement')
    geometry = hashlib.sha256(np.asarray(vertices, dtype='<f8').tobytes()
                              + np.asarray(triangles, dtype='<i8').tobytes()).hexdigest()
    report.update(input_sha256=hashes, implementation_sha256=sha256_file(core.__file__),
                  blender_adapter_sha256=sha256_file(__file__),
                  snapshot=dict(source_name=source.name, world_matrix=matrix.tolist(),
                      geometry_sha256=geometry, geometry_hash_method='world_f8_then_triangles_i8_C_little_endian',
                      fit_metadata=state, blender_version=bpy.app.version_string,
                      interpretation='Historical snapshot; recompute after geometry, units, model or mapping changes'))
    return report


class GNM_OT_rule_checks(Operator):
    bl_idname = 'gnm.anatomical_rule_checks'
    bl_label = 'Inspect Anatomical Rules'
    action: EnumProperty(items=[('REFRESH', 'Show bundled rule catalogue', ''),
                               ('TEMPLATE', 'Write blank feature map', ''),
                               ('MEASURE', 'Measure and export snapshot', '')])

    def execute(self, context):
        scene, settings = context.scene, context.scene.gnm_rule_checks
        # Failed/repeated actions must not leave an old case result looking current.
        settings.result_json = ''
        try:
            registry = load_registry()
            settings.catalogue_json = json.dumps(readiness(registry), ensure_ascii=False, allow_nan=False)
            if self.action == 'REFRESH':
                settings.status = 'Bundled source leads loaded; no case applicability assessed'
                return {'FINISHED'}
            if self.action == 'TEMPLATE':
                path = bpy.path.abspath(settings.mapping_path)
                protected = _protected_inputs(scene, settings)
                # The new map is the output in this action, not an input.
                protected.remove(path)
                validate_outputs(protected, [path])
                model_path = bpy.path.abspath(scene.gnm_live.npz_path)
                digest = sha256_file(model_path)
                count, _ = core._model(model_path)
                mapping = core.empty_map()
                mapping.update(model_sha256=digest, vertex_count=count)
                core.validate_map(mapping)
                if sha256_file(model_path) != digest:
                    raise ValueError('Model changed while preparing the mapping')
                with atomic_text(path) as stream:
                    stream.write(json.dumps(mapping, sort_keys=True, indent=2, allow_nan=False)+'\n')
                settings.status = 'Empty map saved; supply and review correspondences and definitions'
                return {'FINISHED'}
            output = bpy.path.abspath(settings.output_path)
            validate_outputs(_protected_inputs(scene, settings), [output])
            report = _snapshot(context, registry)
            payload = json.dumps(report, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
            with atomic_text(output) as stream:
                stream.write(payload+'\n')
            settings.result_json = payload
            settings.status = 'Snapshot exported; not live QC. Recompute after changes'
            return {'FINISHED'}
        except (ValueError, TypeError, KeyError, OSError, OverflowError, SystemExit) as exc:
            settings.status = str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


def _lines(layout, text):
    for line in textwrap.wrap(str(text), width=52) or ['']:
        layout.label(text=line)


def draw_cached(layout, settings):
    """Read only cached strings; no registry/model/filesystem/scene evaluation."""
    layout.label(text='Read-only results; no fitting constraints')
    layout.operator('gnm.anatomical_rule_checks', text='Show / Refresh Rule Catalogue').action = 'REFRESH'
    layout.prop(settings, 'source')
    layout.prop(settings, 'mapping_path')
    layout.operator('gnm.anatomical_rule_checks', text='Write Blank Feature Map').action = 'TEMPLATE'
    layout.prop(settings, 'output_path')
    layout.operator('gnm.anatomical_rule_checks', text='Measure / Export Snapshot').action = 'MEASURE'
    _lines(layout, settings.status)
    try:
        catalogue = _json(settings.catalogue_json) if settings.catalogue_json else None
        result = _json(settings.result_json) if settings.result_json else None
        if catalogue:
            layout.label(text='Source review and execution are separate')
            for row in catalogue['rules']:
                box = layout.box()
                _lines(box, row['id'])
                _lines(box, 'Review: '+row['registry_status']+'; execution: '+row['execution_status'])
                ref = row['reference']
                _lines(box, 'Source: '+(ref['citation'] or ref['supplied_reference'] or 'Unspecified'))
                _lines(box, 'DOI: '+(ref['doi'] or 'Unspecified'))
                matches = [] if result is None else [name for name, feature in result['mapping']['features'].items()
                                                       if feature['rule_id'] == row['id']]
                _lines(box, 'Bound snapshot features: '+(', '.join(matches) or 'None'))
                box.label(text='SD deviation: unavailable; light: not assessed', icon='QUESTION')
        if result:
            layout.separator()
            _lines(layout, 'LAST SNAPSHOT: '+result['snapshot']['source_name'])
            _lines(layout, 'Historical result; recompute after changes. No current-scene validation.')
            for name, feature in result['features'].items():
                box = layout.box()
                _lines(box, name+': '+feature['measurement_status'])
                measurement = feature['measurement']
                if measurement is not None:
                    _lines(box, str(measurement['value'])+' '+measurement['units'])
                _lines(box, feature['comparison']['reason'])
                box.label(text='SD deviation: unavailable; light: not assessed', icon='QUESTION')
    except (ValueError, TypeError, KeyError):
        layout.label(text='Cached display invalid; refresh and recompute', icon='ERROR')


class GNM_PT_rule_checks(Panel):
    bl_idname = 'GNM_PT_rule_checks'
    bl_label = 'Anatomical Rules / Feature Snapshot'
    bl_space_type, bl_region_type, bl_category = 'VIEW_3D', 'UI', 'GNM Markers'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_cached(self.layout, context.scene.gnm_rule_checks)


CLASSES = (GNMRuleSettings, GNM_OT_rule_checks, GNM_PT_rule_checks)


def register(addon):
    global _api
    _api = addon
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gnm_rule_checks = PointerProperty(type=GNMRuleSettings)


def unregister():
    global _api
    del bpy.types.Scene.gnm_rule_checks
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    _api = None

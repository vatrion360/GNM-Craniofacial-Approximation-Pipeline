"""Main-thread Blender adapter; uses the same target planner as the offline fit."""
import json
from pathlib import Path
import numpy as np
from .io_csv import MarkerTarget
from .tissue import load_table, parse_table, table_path
from .tissue_application import apply_table
from .blender_marker_depths import _apply_changes


def selected_table_path(settings):
    if settings.tissue_table == 'NONE':
        raise ValueError('Select a tissue table')
    if settings.tissue_table == 'FILE':
        import bpy
        if not settings.tissue_table_path.strip():
            raise ValueError('Select a local tissue table JSON file')
        return Path(bpy.path.abspath(settings.tissue_table_path)).expanduser()
    return table_path(settings.tissue_table)


def offline_weight_table(settings):
    """Capture one version for the external run before creating its case directory."""
    if not settings.offline_depth_weighting:
        return None
    raw = selected_table_path(settings).read_bytes()
    parse_table(raw)
    return raw


def _selected_marker_records(addon, context, check_source):
    scene = context.scene
    if not addon._is_mm_scene(scene):
        raise ValueError('Expected metric scene scale 0.001: 1 Blender coordinate = 1 mm')
    context.view_layer.update()
    selected = [m for m in context.scene.gnm_markers if m.adjust_depth_selected]
    if not selected:
        raise ValueError('Select at least one marker using the depth adjustment checkboxes')
    records = {}
    source_digests = {}  # Per-transaction only: evaluate each selected surface once.
    for item in selected:
        if not item.is_placed:
            raise ValueError(f'{item.label}: place bone and skin endpoints first')
        if item.bone_empty.name not in scene.objects or item.target_empty.name not in scene.objects:
            raise ValueError(f'{item.label}: marker endpoints must belong to the current scene')
        if item.label in records:
            raise ValueError(f'Duplicate selected landmark: {item.label}')
        if check_source and item.bone_empty.get('gnm_source_sha256_at_placement'):
            normals = addon._core_module('blender_marker_normals')
            obj = normals.marker_source(context.scene, item)
            source_row = next((s for s in context.scene.gnm_bone_sources if s.enabled and s.source_object == obj), None)
            flip = source_row.flip_normals if source_row else False
            key = (obj.as_pointer(), bool(flip))
            if key not in source_digests:
                source_digests[key] = addon._core_module('blender_sources').evaluated_geometry(
                    obj, context.evaluated_depsgraph_get(), flip)[2]
            digest = source_digests[key]
            if digest != item.bone_empty['gnm_source_sha256_at_placement']:
                raise ValueError(f'{item.label}: source changed since placement; review/re-place before applying directions')
        bone = np.asarray(item.bone_empty.matrix_world.translation, dtype=float)
        point = np.asarray(item.target_empty.matrix_world.translation, dtype=float)
        records[item.label] = dict(bone_xyz_mm=bone.tolist(), target_xyz_mm=point.tolist(),
            tissue_depth_mm=float(item.tissue_depth_mm), tissue_source=item.tissue_source,
            bone_source_geometry_sha256=item.bone_empty.get('gnm_source_sha256_at_placement', ''))
    return selected, records


def create_direction_template(addon, context, path):
    """Write a new, unreviewed manifest from Blender's depth selection."""
    from .tissue_directions import template_from_records
    settings = context.scene.gnm_settings
    table = load_table(selected_table_path(settings))
    selected, records = _selected_marker_records(addon, context, check_source=True)
    document = template_from_records(records, table, [item.label for item in selected])
    raw = (json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    destination = Path(path)
    stream = destination.open('xb')
    try:
        with stream:
            stream.write(raw)
    except OSError:
        destination.unlink()
        raise
    return len(selected)


def apply_selected_table(addon, context, source, axis_acknowledged=False, direction_source=None, source_acknowledged=False):
    """Explicit placed-marker replacement, preserving unselected case data and undo."""
    if direction_source is not None and not source_acknowledged:
        raise ValueError('Review the source direction manifest and frame explicitly before Apply')
    if direction_source is None and not axis_acknowledged:
        raise ValueError('Accept existing marker axes explicitly; source directions are not enforced')
    selected, records = _selected_marker_records(addon, context, check_source=direction_source is not None)
    targets = [MarkerTarget(item.label, i, np.asarray(records[item.label]['target_xyz_mm']), 1.)
               for i, item in enumerate(selected)]
    directions = None
    if direction_source is not None:
        from .tissue_directions import load_directions
        directions = load_directions(direction_source)
    metadata = dict(version=3, marker_records=records, acquisition_posture=context.scene.gnm_settings.acquisition_posture)
    metadata.update(scene_age_metadata(context.scene))
    _, _, plan = apply_table(targets, metadata, load_table(source),
                            [m.label for m in selected], 'source' if directions else 'existing', directions)
    by_label = {r['label']: r for r in plan['replacements']}
    shared = {k: v for k, v in plan.items() if k != 'replacements'}
    json.dumps(shared, allow_nan=False)
    def audit_for(row, timestamp):
        planned = by_label[row['item'].label]
        return dict(utc=timestamp, method='explicit_tissue_table',
            before_mm=row['old_depth'], after_mm=float(row['item'].tissue_depth_mm),
            previous_tissue_source=row['old_source'], application=shared, replacement=planned), planned['tissue_source']
    return _apply_changes(addon, context, selected, lambda item: by_label[item.label]['after_mm'],
                          audit_for, record_unchanged=True,
                          direction_for=(lambda item: by_label[item.label]['axis_world']) if directions else None)


def scene_age_metadata(scene):
    """Read optional age metadata on an explicit main-thread action only."""
    path = scene.gnm_settings.age_context_path
    if not path.strip():
        return {}
    import bpy
    from .age_context import load_case_age
    return load_case_age(bpy.path.abspath(path))


def latest_context_messages(scene):
    """Read the just-applied audit, without file I/O or recomputing a fit."""
    from .blender_marker_depths import history
    from .tissue_context import context_text
    for item in scene.gnm_markers:
        if item.adjust_depth_selected:
            entries = history(item)
            if entries:
                context = entries[-1].get('application', {}).get('context')
                if context:
                    return context['warnings'], context_text(context, compact=True)
    return [], ''

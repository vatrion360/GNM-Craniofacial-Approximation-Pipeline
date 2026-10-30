"""Blender-only manual depth adjustment; no BMI model or offline fit changes.

Planning validates every selected row before mutation. The adapter preserves
bone positions and current directions, coalesces callbacks and records edits.
"""
import datetime
import json
import math


def adjusted_depth(depth: float, percent: float, mode: str) -> float:
    """Scale a current depth in mm; reject invalid input instead of clamping."""
    if mode not in {'INCREASE', 'DECREASE'}:
        raise ValueError('Choose Increase or Decrease')
    if not math.isfinite(percent) or percent < 0:
        raise ValueError('Percentage must be finite and non-negative')
    if mode == 'DECREASE' and percent > 100:
        raise ValueError('Decrease cannot exceed 100%')
    if not math.isfinite(depth) or depth < 0:
        raise ValueError('Current marker depth must be finite and non-negative')
    result = depth * (1 + percent / 100 if mode == 'INCREASE' else 1 - percent / 100)
    if not math.isfinite(result) or result > 3.4028234663852886e38:
        raise ValueError('Adjusted depth exceeds Blender float range')
    return result


def history(item) -> list:
    """Read persisted audit entries, including from a scene saved before this feature."""
    records = json.loads(item.depth_adjustment_history or '[]')
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError(f'{item.label}: invalid depth adjustment history')
    return records


def apply_adjustment(addon, context, percent: float, mode: str) -> int:
    """Apply one all-or-nothing main-thread edit and request one settled refit.

    Unplaced and fit-excluded rows may be edited deliberately. Selection is
    independent of active-row and fit flags. A 100% decrease keeps the direction
    on the bone object for later direct depth edits. Increasing zero stays zero.
    """
    adjusted_depth(0., percent, mode)
    def audit_for(row, timestamp):
        record = dict(utc=timestamp, method='manual_percentage', percent=percent, mode=mode,
            before_mm=row['old_depth'], after_mm=float(row['item'].tissue_depth_mm),
            previous_tissue_source=row['old_source'])
        prefix = 'manual-percentage; base source: '
        source = (row['old_source'] if row['old_source'].startswith(prefix)
                  else prefix + (row['old_source'] or 'not recorded'))
        return record, source
    return _apply_changes(addon, context,
        [m for m in context.scene.gnm_markers if m.adjust_depth_selected],
        lambda item: adjusted_depth(float(item.tissue_depth_mm), percent, mode), audit_for)


def _apply_changes(addon, context, selected, depth_for, audit_for, record_unchanged=False):
    """Shared all-or-nothing main-thread RNA/geometry transaction for depth edits."""
    from mathutils import Vector

    scene = context.scene
    if not selected:
        raise ValueError('Select at least one marker using the adjustment checkboxes')
    if scene.library or scene.override_library:
        raise ValueError('Use a local editable scene for marker adjustment')
    planned = []
    for item in selected:
        value = adjusted_depth(depth_for(item), 0., 'INCREASE')
        records = history(item)
        direction = None
        if bool(item.bone_empty) != bool(item.target_empty):
            raise ValueError(f'{item.label}: incomplete placement; repair or clear it first')
        if item.peg_object and not item.is_placed:
            raise ValueError(f'{item.label}: orphan peg; repair or clear it first')
        objects = [o for o in (item.bone_empty, item.target_empty, item.peg_object) if o]
        for obj in objects:
            if obj.library or obj.override_library or obj.name not in scene.objects:
                raise ValueError(f'{item.label}: marker objects must be local to this scene')
            if not all(math.isfinite(v) for row in obj.matrix_world for v in row):
                raise ValueError(f'{item.label}: non-finite marker transform')
        for obj in (item.target_empty, item.peg_object):
            if obj:
                uses = sum(obj == candidate for marker in scene.gnm_markers
                           for candidate in (marker.bone_empty, marker.target_empty, marker.peg_object))
                if uses != 1:
                    raise ValueError(f'{item.label}: shared target/peg would change another marker; repair object ownership')
            if obj and (obj.parent or obj.constraints or obj.animation_data):
                raise ValueError(f'{item.label}: detach target/peg parents, constraints or animation first')
        if item.is_placed:
            if not addon._is_mm_scene(scene):
                raise ValueError('Expected metric scene scale 0.001: 1 Blender coordinate = 1 mm')
            direction = item.target_empty.matrix_world.translation - item.bone_empty.matrix_world.translation
            if direction.length < 1e-9:
                direction = Vector(item.bone_empty.get('gnm_normal', (0, 0, 0)))
            if not all(math.isfinite(v) for v in direction) or direction.length < 1e-12:
                raise ValueError(f'{item.label}: missing marker direction; re-place it first')
            direction.normalize()
        if value == item.tissue_depth_mm and not record_unchanged:
            continue
        planned.append(dict(item=item, value=value, direction=direction, history=records,
            old_depth=float(item.tissue_depth_mm), old_source=item.tissue_source,
            old_history=item.depth_adjustment_history,
            normal=list(item.bone_empty['gnm_normal']) if item.bone_empty and 'gnm_normal' in item.bone_empty else None,
            transforms=[(o, o.matrix_world.copy(), o.rotation_mode) for o in objects]))
    if not planned:
        return 0
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    normals = addon._core_module('blender_marker_normals')
    previous_batch = addon._MARKER_DEPTH_BATCH
    addon._MARKER_DEPTH_BATCH = True
    try:
        for row in planned:
            item = row['item']
            item.tissue_depth_mm = row['value']
            if item.is_placed:
                normals.set_direction(item, row['direction'], scene.gnm_settings.peg_thickness_mm)
            # Read back RNA float precision for the authoritative audit value.
            record, source = audit_for(row, timestamp)
            item.depth_adjustment_history = json.dumps(row['history'] + [record], allow_nan=False)
            item.tissue_source = source
    except Exception:
        # RNA update exceptions are normally swallowed by Blender; this path
        # calls the geometry adapter explicitly so failures can roll back.
        for row in planned:
            item = row['item']
            item.tissue_depth_mm = row['old_depth']
            item.tissue_source = row['old_source']
            item.depth_adjustment_history = row['old_history']
            for obj, matrix, rotation_mode in row['transforms']:
                obj.rotation_mode, obj.matrix_world = rotation_mode, matrix
            if item.bone_empty:
                if row['normal'] is not None:
                    item.bone_empty['gnm_normal'] = row['normal']
                elif 'gnm_normal' in item.bone_empty:
                    del item.bone_empty['gnm_normal']
        raise
    finally:
        addon._MARKER_DEPTH_BATCH = previous_batch
    normals.clear_preview(scene)
    addon._request_refit(scene)
    return len(planned)

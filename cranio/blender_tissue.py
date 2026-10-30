"""Main-thread Blender adapter; uses the same target planner as the offline fit."""
import json
import numpy as np
from .io_csv import MarkerTarget
from .tissue import load_table
from .tissue_application import apply_table
from .blender_marker_depths import _apply_changes


def apply_selected_table(addon, context, source, axis_acknowledged=False):
    """Explicit placed-marker replacement, preserving unselected case data and undo."""
    if not axis_acknowledged:
        raise ValueError('Accept existing marker axes explicitly; source directions are not enforced')
    selected = [m for m in context.scene.gnm_markers if m.adjust_depth_selected]
    if not selected:
        raise ValueError('Select at least one marker using the depth adjustment checkboxes')
    targets, records = [], {}
    for i, item in enumerate(selected):
        if not item.is_placed:
            raise ValueError(f'{item.label}: place bone and skin endpoints first')
        bone = np.asarray(item.bone_empty.matrix_world.translation, dtype=float)
        point = np.asarray(item.target_empty.matrix_world.translation, dtype=float)
        targets.append(MarkerTarget(item.label, i, point, 1.))
        records[item.label] = dict(bone_xyz_mm=bone.tolist(), target_xyz_mm=point.tolist(),
            tissue_depth_mm=float(item.tissue_depth_mm), tissue_source=item.tissue_source)
    _, _, plan = apply_table(targets, dict(version=3, marker_records=records), load_table(source),
                            [m.label for m in selected], 'existing')
    by_label = {r['label']: r for r in plan['replacements']}
    shared = {k: v for k, v in plan.items() if k != 'replacements'}
    json.dumps(shared, allow_nan=False)
    def audit_for(row, timestamp):
        planned = by_label[row['item'].label]
        return dict(utc=timestamp, method='explicit_tissue_table',
            before_mm=row['old_depth'], after_mm=float(row['item'].tissue_depth_mm),
            previous_tissue_source=row['old_source'], application=shared, replacement=planned), planned['tissue_source']
    return _apply_changes(addon, context, selected, lambda item: by_label[item.label]['after_mm'],
                          audit_for, record_unchanged=True)

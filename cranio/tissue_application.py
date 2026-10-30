"""Explicit selected-marker tissue scenarios; no automatic measurement-frame inference."""
import copy
import numpy as np
from .validation import finite_array, has_documented_tissue_source


def table_source(table, row):
    """A table ID must not turn unknown/legacy provenance into a documented source."""
    data = table.document
    if 'legacy_hardcoded' in (row['provenance'], data['provenance']):
        return 'legacy-unvalidated'
    if not has_documented_tissue_source(data['citation']):
        return 'unspecified'
    return f"{data['citation']}; table={data['id']}@{data['revision']}; existing-axis scenario; SHA256={table.sha256}"


def apply_table(targets, metadata, table, labels=(), axis_policy='unconfigured'):
    """Plan all replacements before returning detached records; never mutate inputs.

    Selection without labels preserves case values. Explicit labels authorize
    replacing even manual values. The existing bone-to-target direction is used
    only after opt-in; it is not claimed to match the table measurement method.
    Weights, bone positions, correspondence and unselected targets stay fixed.
    """
    if not isinstance(labels, (list, tuple)) or any(not isinstance(x, str) or not x for x in labels):
        raise ValueError('tissue_labels must be a list of nonempty labels')
    if len(labels) != len(set(labels)):
        raise ValueError('Duplicate tissue replacement labels')
    if axis_policy not in ('unconfigured', 'existing'):
        raise ValueError('Unknown tissue axis policy')
    if labels and axis_policy != 'existing':
        raise ValueError('Explicit --tissue-axis existing required; source measurement frames are not implemented')
    if labels and metadata.get('version') != 3:
        raise ValueError('Tissue replacement requires explicit v3 bone/skin coordinates')
    result_meta = copy.deepcopy(metadata)
    records = result_meta.get('marker_records', {})
    if not isinstance(records, dict):
        raise ValueError('marker_records must be an object')
    by_label = {t.label: t for t in targets}
    if len(by_label) != len(targets):
        raise ValueError('Duplicate target labels')
    data, planned = table.document, {}
    for label in labels:
        if label not in by_label:
            raise ValueError(f'{label}: not a placed, included marker')
        row = data['landmarks'].get(label)
        if row is None or row['central_mm'] is None:
            raise ValueError(f'{label}: no configured landmark depth in table {data["id"]}')
        old = records.get(label)
        if not isinstance(old, dict) or 'bone_xyz_mm' not in old:
            raise ValueError(f'{label}: explicit bone coordinates required')
        bone = finite_array(old['bone_xyz_mm'], label+' bone', (3,))
        point = finite_array(by_label[label].xyz, label+' target', (3,))
        distance = float(np.linalg.norm(point-bone))
        # Engineering guard inherited from the Blender depth transaction (legacy_hardcoded).
        if not np.isfinite(distance) or distance < 1e-9:
            raise ValueError(f'{label}: zero/invalid bone-to-target axis; re-place marker')
        axis, value = (point-bone)/distance, float(row['central_mm'])
        new = finite_array(bone+value*axis, label+' new target', (3,))
        planned[label] = dict(label=label, before=copy.deepcopy(old), before_target_mm=point.tolist(),
            before_axis_length_mm=distance, after_mm=value, after_target_mm=new.tolist(),
            bone_xyz_mm=bone.tolist(), axis_world=axis.tolist(), table_row=copy.deepcopy(row),
            tissue_source=table_source(table, row))
    for label, row in planned.items():
        records[label].update(target_xyz_mm=row['after_target_mm'], tissue_depth_mm=row['after_mm'],
                              tissue_source=row['tissue_source'])
    result = [t._replace(xyz=np.array(planned[t.label]['after_target_mm'])) if t.label in planned else t for t in targets]
    record = dict(table=table.record(), table_metadata={k: v for k, v in data.items() if k not in ('landmarks', 'regions')},
        axis_policy=axis_policy, source_direction_enforced=False, status='applied' if planned else 'selected_only',
        replaced_labels=list(planned), preserved_labels=[t.label for t in targets if t.label not in planned],
        replacements=list(planned.values()), dense_regions_applied=False,
        interpretation='Selected labels explicitly replace case values along existing bone-to-target axes. Source measurement direction is NOT enforced; this is a sensitivity scenario, not validation. Dense-region/scalp settings remain unchanged.')
    result_meta['tissue_application'] = record
    return result, result_meta, record

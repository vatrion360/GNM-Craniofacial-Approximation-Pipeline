"""Explicit world-frame directions for tissue scenarios; no anatomical inference.

The operator supplies signed vectors and reviews their source definitions.
A sagittal plane is insufficient to pick a unique direction within that plane.
"""
from dataclasses import dataclass
import copy
import hashlib
from pathlib import Path
import numpy as np
from .tissue import _json
from .validation import finite_array


def unit_vector(value, name):
    """Normalize finite nonzero vectors without overflow or arbitrary length floors."""
    vector = finite_array(value, name, (3,))
    scale = float(np.max(np.abs(vector)))
    if scale == 0:
        raise ValueError(f'{name}: zero direction')
    vector = vector / scale
    return vector / np.linalg.norm(vector)


def _object(value, allowed, name):
    if not isinstance(value, dict) or set(value)-set(allowed):
        raise ValueError(f'{name}: expected object with fields {sorted(allowed)}')
    return value


def _review(row, name):
    if (row.get('reviewed') is not True or not isinstance(row.get('definition'), str) or not row['definition'].strip()
            or 'todo(verify-source)' in row['definition'].lower()):
        raise ValueError(f'{name}: reviewed=true and a nonempty source/direction definition required')


@dataclass(frozen=True)
class DirectionManifest:
    """Exact source bytes hash with a detached manifest used in the application audit."""
    _document: dict
    sha256: str

    @property
    def document(self):
        return copy.deepcopy(self._document)


def load_directions(path) -> DirectionManifest:
    raw = Path(path).read_bytes()
    data = _object(_json(raw.decode('utf-8-sig')),
        {'schema_version', 'units', 'coordinate_space', 'table_sha256s', 'frame', 'landmarks'}, 'directions')
    if (type(data.get('schema_version')) is not int or data['schema_version'] != 1
            or data.get('units') != 'mm' or data.get('coordinate_space') != 'world'):
        raise ValueError('Direction manifest requires schema_version=1, units=mm, coordinate_space=world')
    hashes = data.get('table_sha256s')
    if not isinstance(hashes, list) or not hashes or any(not isinstance(x, str) or len(x) != 64
            or any(c not in '0123456789abcdef' for c in x) for x in hashes) or len(set(hashes)) != len(hashes):
        raise ValueError('Direction manifest requires distinct reviewed table_sha256s')
    if not isinstance(data.get('landmarks'), dict):
        raise ValueError('Direction manifest requires landmarks object')
    if 'frame' in data and data['frame'] is not None:
        _object(data['frame'], {'vertical_world', 'sagittal_normal_world', 'reviewed', 'definition'}, 'frame')
    return DirectionManifest(copy.deepcopy(data), hashlib.sha256(raw).hexdigest())


def resolve_direction(manifest, table, label, bone, marker_record):
    """Resolve one reviewed signed vector, checking table, anchor and geometry type.

    Bone-normal entries are supplied/reviewed normals, not recalculated from mesh.
    Vertical vectors must be parallel to the declared frame vertical (either
    explicit sign). Sagittal vectors must lie in the declared sagittal plane.
    Machine-precision checks below are algebraic, not anatomical thresholds.
    """
    data = manifest.document
    if table.sha256 not in data['table_sha256s']:
        raise ValueError('Direction manifest is not reviewed for this exact tissue table hash')
    kind = table.document['landmarks'][label]['measurement_direction']
    if kind not in ('bone_normal', 'vertical', 'sagittal'):
        raise ValueError(f'{label}: unsupported or unconfigured measurement direction {kind!r}')
    row = _object(data['landmarks'].get(label), {'bone_xyz_mm', 'axis_world', 'measurement_direction',
        'definition', 'reviewed', 'bone_source_geometry_sha256'}, label)
    _review(row, label)
    if row.get('measurement_direction') != kind:
        raise ValueError(f'{label}: direction manifest does not match table measurement_direction')
    if not np.array_equal(finite_array(row.get('bone_xyz_mm'), label+' direction anchor', (3,)), bone):
        raise ValueError(f'{label}: direction anchor differs from current bone point; review/update manifest')
    recorded_hash = marker_record.get('bone_source_geometry_sha256') or None
    supplied_hash = row.get('bone_source_geometry_sha256') or None
    if supplied_hash is not None and (not isinstance(supplied_hash, str) or len(supplied_hash) != 64
            or any(c not in '0123456789abcdef' for c in supplied_hash)):
        raise ValueError(f'{label}: invalid source geometry SHA-256')
    if recorded_hash != supplied_hash:
        raise ValueError(f'{label}: direction source geometry hash differs from marker record')
    axis = unit_vector(row.get('axis_world'), label+' axis_world')
    frame = None
    if kind != 'bone_normal':
        frame = data.get('frame')
        if not isinstance(frame, dict):
            raise ValueError(f'{label}: explicit reviewed anatomical frame required')
        _review(frame, 'frame')
        key = 'vertical_world' if kind == 'vertical' else 'sagittal_normal_world'
        reference = unit_vector(frame.get(key), key)
        tolerance = 64*np.finfo(float).eps  # floating-point algebra only
        error = np.linalg.norm(np.cross(axis, reference)) if kind == 'vertical' else abs(float(axis @ reference))
        if error > tolerance:
            raise ValueError(f'{label}: axis is not {"parallel to vertical" if kind == "vertical" else "in the sagittal plane"}')
    return axis, dict(manifest_sha256=manifest.sha256, measurement_direction=kind,
        supplied=copy.deepcopy(row), frame=copy.deepcopy(frame), geometry_hash_bound=recorded_hash is not None,
        verification='Declared direction geometry checked; anatomical source equivalence and normal sign remain operator-reviewed, not independently validated.')


def make_template(marker_path, table, labels):
    """Copy exact v3 anchors into an unreviewed template; never infer directions."""
    from .io_csv import read_marker_csv
    targets, _, meta = read_marker_csv(marker_path, {}, {})
    if meta['version'] != 3 or not labels or len(set(labels)) != len(labels):
        raise ValueError('Template requires v3 and distinct explicit labels')
    targets = {t.label: t for t in targets}
    rows = {}
    for label in labels:
        row = meta['marker_records'].get(label, {})
        if label not in targets or 'bone_xyz_mm' not in row:
            raise ValueError(f'{label}: placed included marker with bone coordinates required')
        tissue_row = table.document['landmarks'].get(label)
        if tissue_row is None:
            raise ValueError(f'{label}: absent from tissue table')
        rows[label] = dict(bone_xyz_mm=row['bone_xyz_mm'], axis_world=None,
            measurement_direction=tissue_row['measurement_direction'], reviewed=False,
            definition='TODO(verify-source): signed direction definition and source',
            bone_source_geometry_sha256=row.get('bone_source_geometry_sha256') or None)
    return dict(schema_version=1, units='mm', coordinate_space='world', table_sha256s=[table.sha256],
        frame=dict(vertical_world=None, sagittal_normal_world=None, reviewed=False,
                   definition='TODO(verify-source): anatomical frame definition'), landmarks=rows)


def main(argv=None):
    import argparse
    import json
    from .tissue import load_table, table_path
    from .validation import validate_outputs
    from .export import atomic_text
    parser = argparse.ArgumentParser(description='Prepare an unreviewed direction manifest; no inferred axes')
    parser.add_argument('--input', required=True, help='Case marker CSV v3')
    parser.add_argument('--table', required=True, help='Tissue table ID or JSON')
    parser.add_argument('--labels', required=True, nargs='+')
    parser.add_argument('--output', required=True)
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args(argv)
    try:
        validate_outputs([args.input, table_path(args.table)], [args.output], args.overwrite)
        document = make_template(args.input, load_table(args.table), args.labels)
        with atomic_text(args.output, validate=load_directions) as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        print('Unreviewed template written. Complete source-defined directions/frame and review before use.')
        return 0
    except (ValueError, OSError, UnicodeError) as exc:
        print(f'Direction template error: {exc}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

"""Opt-in saved-fit diagnostics; no fitting, correction or anatomical approval.

Reuse recorded QC without rerunning its contact/clearance searches. Only triangle
angles are newly measured, on the exact serialized statistical/final OBJ files.
"""
import argparse
import copy
import math
from pathlib import Path, PureWindowsPath

import numpy as np

from .record import build_record, validate_report, canonical_bytes, _digest, OUTPUT_KEYS
from .tissue import _json
from .review_export import geometry_lines, RECORD_FILES

INTERPRETATION = ('Saved-fit software diagnostics only, not anatomical accuracy or export authorization. '
    'Recorded local clearance is not tissue thickness or closed-volume containment. '
    'Current scene edits and original bone normals are not revalidated.')
COLORS = {'pass': 'green', 'warn': 'amber', 'block': 'red', 'not_assessed': 'gray'}
FILES = ('consistency.json', 'consistency.txt', *RECORD_FILES)


def triangle_angles(vertices, triangles):
    """Minimum angle in degrees; numerically collapsed/collinear triangles get zero.

    Scale each triangle's edge vectors before dot/cross products to avoid scale
    dependent tolerances. No anatomical or mesh-quality acceptance cutoff is used.
    """
    try:
        v, t = np.asarray(vertices, dtype=float), np.asarray(triangles)
    except (OverflowError, TypeError) as exc:
        raise ValueError('Invalid numeric mesh') from exc
    if (v.ndim != 2 or v.shape[1] != 3 or not len(v) or not np.isfinite(v).all()
            or t.ndim != 2 or t.shape[1] != 3 or not len(t) or t.dtype.kind not in 'iu'
            or np.any(t < 0) or np.any(t >= len(v))):
        raise ValueError('Expected finite vertices and nonempty valid integer triangles')
    with np.errstate(over='ignore', invalid='ignore'):
        points = v[t]
        a = np.roll(points, -1, axis=1)-points
        b = np.roll(points, 1, axis=1)-points
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('Triangle edge overflow')
    scale = np.maximum(np.abs(a).max(axis=(1, 2)), np.abs(b).max(axis=(1, 2)))
    scale[scale == 0] = 1.
    a, b = a/scale[:, None, None], b/scale[:, None, None]
    cross = np.linalg.norm(np.cross(a, b), axis=2)
    dot = np.einsum('nki,nki->nk', a, b)
    angles = np.degrees(np.arctan2(cross, dot))
    degenerate = np.all(cross == 0, axis=1)
    angles[degenerate] = 0
    smallest = angles.min(axis=1)
    return dict(status='measured', units='degrees', triangle_count=len(t),
        minimum_angle_deg=float(smallest.min()), minimum_angle_face=int(smallest.argmin()),
        degenerate_face_indices=np.flatnonzero(degenerate).tolist(),
        interpretation='All serialized OBJ triangles, including non-skin groups; no quality threshold configured')


def _indices(value, bound, name):
    if (not isinstance(value, list) or any(type(i) is not int or not 0 <= i < bound for i in value)
            or len(set(value)) != len(value)):
        raise ValueError('Invalid recorded face indices: '+name)
    return value


def clearance_summary(value):
    """Summarize recorded samples only; no coverage/area interpretation."""
    if not isinstance(value, dict) or value.get('status') == 'not_assessed':
        return dict(status='not_assessed', reason='No recorded observed-bone clearance samples')
    required = {'sample_indices', 'outward_clearance_mm', 'negative_clearance_count', 'tolerance_mm'}
    if not required <= value.keys():
        return dict(status='not_assessed', reason='Incomplete recorded local-clearance details')
    ids, raw = value['sample_indices'], value['outward_clearance_mm']
    tolerance, count = value['tolerance_mm'], value['negative_clearance_count']
    try:
        valid_tolerance = type(tolerance) in (int, float) and math.isfinite(tolerance) and tolerance >= 0
    except OverflowError:
        valid_tolerance = False
    if (not isinstance(ids, list) or not ids or any(type(i) is not int or i < 0 for i in ids)
            or len(set(ids)) != len(ids) or not isinstance(raw, list) or len(raw) != len(ids)
            or any(type(x) not in (int, float) for x in raw)
            or not valid_tolerance
            or type(count) is not int):
        raise ValueError('Malformed recorded local-clearance samples')
    try:
        values = np.asarray(raw, dtype=float)
    except (OverflowError, TypeError) as exc:
        raise ValueError('Invalid numeric clearance samples') from exc
    if not np.isfinite(values).all() or count != int(np.count_nonzero(values < -tolerance)):
        raise ValueError('Nonfinite or contradictory recorded clearance counts')
    return dict(status='recorded', sample_count=len(ids), sample_indices=ids.copy(),
        minimum_mm=float(values.min()), median_mm=float(np.median(values)),
        p10_mm=float(np.percentile(values, 10)), p90_mm=float(np.percentile(values, 90)),
        negative_sample_count=count, negative_sample_percent=100.*count/len(ids),
        tolerance_mm=tolerance, tolerance_provenance='legacy_hardcoded',
        interpretation='Sample-count fraction, not surface-area fraction, tissue depth or volumetric penetration')


def _pairs(value, bound):
    if (not isinstance(value, list) or any(not isinstance(p, list) or len(p) != 2
            or any(type(i) is not int or not 0 <= i < bound for i in p) or p[0] >= p[1] for p in value)
            or len({tuple(p) for p in value}) != len(value)):
        raise ValueError('Invalid recorded contact pairs')
    return value


def summarize(report, meshes):
    """Detached diagnostics with conservative status; missing checks never pass."""
    from .check_policy import _geometry
    validate_report(report)
    if set(meshes) != {'statistical', 'final'}:
        raise ValueError('Need both statistical and final saved meshes')
    if (meshes['statistical'][0].shape != meshes['final'][0].shape
            or not np.array_equal(meshes['statistical'][1], meshes['final'][1])):
        raise ValueError('Saved statistical/final topology differs')
    gate = _geometry(report)
    quality = report.get('geometry_quality')
    quality = quality if isinstance(quality, dict) else {}
    stages = {}
    defective = gate['status'] == 'block' or not report['solver']['converged']
    for stage, (vertices, triangles) in meshes.items():
        shape = triangle_angles(vertices, triangles)
        defective |= bool(shape['degenerate_face_indices'])
        source = quality.get(stage)
        source = source if isinstance(source, dict) else {}
        defects = {}
        for key in ('reference_degenerate_faces', 'new_degenerate_faces', 'normal_reversed_faces'):
            ids = source.get(key)
            defects[key] = (dict(status='not_assessed') if ids is None else
                dict(status='recorded', count=len(_indices(ids, len(triangles), key)), face_indices=copy.deepcopy(ids)))
            if key != 'reference_degenerate_faces' and ids:
                defective = True
        clearance = clearance_summary(source.get('bone_clearance'))
        defective |= clearance.get('negative_sample_count', 0) > 0
        contact = source.get('contacts')
        contacts = dict(status='not_assessed', reason='No recorded contact search')
        if isinstance(contact, dict):
            complete = contact.get('complete')
            if type(complete) is not bool:
                raise ValueError('Malformed recorded contact search')
            # Contact pairs index the selected exterior subset; new pairs use
            # full-mesh indices. Never conflate those two index spaces.
            selected = quality.get('contact_face_indices')
            bound = len(_indices(selected, len(triangles), 'contact_face_indices')) if selected is not None else len(triangles)
            pairs = _pairs(contact.get('pairs'), bound)
            new_pairs = source.get('new_contact_face_pairs')
            new_pairs = None if new_pairs is None else _pairs(new_pairs, len(triangles))
            defective |= bool(new_pairs)
            contacts = dict(status='recorded' if complete else 'incomplete',
                count=len(pairs), new_count=None if new_pairs is None else len(new_pairs),
                new_contact_face_pairs=copy.deepcopy(new_pairs), complete=complete,
                scope=quality.get('contact_scope'), index_mapping_recorded=selected is not None,
                candidate_pairs_tested=contact.get('candidate_pairs_tested'),
                interpretation='Nonadjacent triangle contacts in recorded scope, not a complete self-intersection certificate')
        stages[stage] = dict(serialized_mesh_angles=shape, recorded_deformation=defects,
            recorded_contacts=contacts, recorded_bone_clearance=clearance)
    unavailable = dict(
        skin_in_bone='No closed-volume signed-distance assessment; open fragments cannot certify inside/outside',
        bone_through_skin='No observed-bone area coverage assessment or configured coverage tolerance',
        regional_tissue_bands='No regional depth/direction/table-band correspondence evaluated here',
        midsagittal_reference_error='No independent reference face supplied to this saved-report action')
    status = 'block' if defective else 'not_assessed'
    return dict(schema_version=1, kind='postfit_consistency', units='mm', status=status,
        light=COLORS[status], interpretation=INTERPRETATION,
        recorded_geometry_check=gate, solver_converged=report['solver']['converged'],
        solver_scope='baseline_before_profile' if report['config'].get('profile_constraint') else 'statistical_fit',
        stages=stages, unavailable_checks={key: dict(status='not_assessed', reason=reason) for key, reason in unavailable.items()},
        warnings=copy.deepcopy(report['warnings']), correction_applied=False,
        scientific_export_authorization='not_assessed')


def text_report(summary):
    lines = ['GNM saved-fit consistency', 'Status: '+summary['status']+' / '+summary['light'], INTERPRETATION,
             'Recorded geometry check: '+summary['recorded_geometry_check']['status'],
             'Recorded solver converged: '+str(summary['solver_converged'])+' ('+summary['solver_scope']+')']
    for stage, values in summary['stages'].items():
        angles = values['serialized_mesh_angles']
        lines.extend([stage.upper(), '  Minimum serialized triangle angle: '+str(angles['minimum_angle_deg'])+' degrees',
            '  Serialized degenerate triangles: '+str(len(angles['degenerate_face_indices'])),
            '  Recorded contacts: '+str(values['recorded_contacts'])])
        for key, row in values['recorded_deformation'].items():
            lines.append('  '+key+': '+row['status']+'; count='+str(row.get('count')))
        row = values['recorded_bone_clearance']
        lines.append('  Recorded local bone clearance: '+row['status'])
        if row['status'] == 'recorded':
            lines.extend(['    Samples: '+str(row['sample_count'])+'; negative: '+str(row['negative_sample_count'])+
                ' ('+str(row['negative_sample_percent'])+'% of samples)',
                '    Median / P10 / P90 (mm): '+str([row[k] for k in ('median_mm', 'p10_mm', 'p90_mm')]),
                '    Legacy tolerance (mm): '+str(row['tolerance_mm']), '    '+row['interpretation']])
    lines.append('NOT ASSESSED:')
    lines.extend('  '+key+': '+row['reason'] for key, row in summary['unavailable_checks'].items())
    lines.extend(['Source warnings:', *map(str, summary['warnings']), 'No correction applied; no export permission granted.'])
    return '\n'.join(lines)+'\n'


def build_summary(report_path, output_dir, *, artifacts=None):
    """Verify saved artifacts via A7, then publish a separate completion manifest."""
    from .export import atomic_text
    from .record_job import read_result as read_record
    report_path, out = Path(report_path).resolve(), Path(output_dir)
    if out.exists() or out.is_symlink():
        raise ValueError('Consistency output exists; choose a new directory')
    raw = report_path.read_bytes()
    report = _json(raw.decode('utf-8-sig'))
    validate_report(report)
    request = dict(report_path=str(report_path), report_sha256=_digest(raw))
    build_record(report_path, out/'record', artifacts=artifacts)
    read_record(out/'record', request)
    directory = Path(artifacts).resolve() if artifacts is not None else report_path.parent
    pinned = {report_path: _digest(raw)}
    meshes = {}
    for key in OUTPUT_KEYS:
        row = report['outputs'][key]
        path = directory/PureWindowsPath(row['path']).name
        if not path.resolve().is_relative_to(directory):
            raise ValueError('Saved artifact escapes directory')
        data = path.read_bytes()
        if _digest(data) != row['sha256']:
            raise ValueError('Saved artifact checksum changed: '+key)
        pinned[path] = row['sha256']
        if key in ('output', 'output_statistical'):
            lines, _ = geometry_lines(data)
            vertices = np.array([[float(v) for v in line.split()[1:]] for line in lines if line.startswith('v ')])
            triangles = np.array([[int(v)-1 for v in line.split()[1:]] for line in lines if line.startswith('f ')])
            meshes['final' if key == 'output' else 'statistical'] = vertices, triangles
    summary = summarize(report, meshes)
    summary.update(source_report_sha256=_digest(raw),
        source_outputs={key: dict(sha256=report['outputs'][key]['sha256']) for key in OUTPUT_KEYS})
    expected = {}
    for name, data in (('consistency.json', canonical_bytes(summary)),
                       ('consistency.txt', text_report(summary).encode('utf-8'))):
        expected[name] = dict(sha256=_digest(data))
        with atomic_text(out/name) as stream:
            stream.write(data.decode('utf-8'))
    files = {**{name: dict(sha256=_digest((out/name).read_bytes())) for name in RECORD_FILES}, **expected}
    manifest = dict(schema_version=1, kind='postfit_consistency_bundle', status='completed',
        source_report_sha256=_digest(raw), files=files, implementation_sha256=_digest(Path(__file__).read_bytes()))
    def validate(_):
        if any(_digest(path.read_bytes()) != digest for path, digest in pinned.items()):
            raise ValueError('Consistency source changed; no completion marker')
        if any(_digest((out/name).read_bytes()) != row['sha256'] for name, row in files.items()):
            raise ValueError('Consistency output changed; no completion marker')
    with atomic_text(out/'consistency_manifest.json', validate=validate) as stream:
        stream.write(canonical_bytes(manifest).decode('utf-8'))
    return out/'consistency_manifest.json'


def read_result(output_dir, request):
    """Read only fixed outputs; verify source identity before UI display."""
    from .record_job import read_result as read_record
    root = Path(output_dir).resolve()
    def read(name):
        path = root/name
        if not path.resolve().is_relative_to(root):
            raise ValueError('Consistency output escapes directory')
        return path.read_bytes()
    manifest = _json(read('consistency_manifest.json').decode('utf-8-sig'))
    if (not isinstance(manifest, dict) or type(manifest.get('schema_version')) is not int
            or manifest['schema_version'] != 1 or manifest.get('kind') != 'postfit_consistency_bundle'
            or manifest.get('status') != 'completed' or manifest.get('source_report_sha256') != request['report_sha256']
            or not isinstance(manifest.get('files'), dict) or set(manifest['files']) != set(FILES)):
        raise ValueError('Unexpected consistency completion manifest')
    for name, row in manifest['files'].items():
        if not isinstance(row, dict) or row.get('sha256') != _digest(read(name)):
            raise ValueError('Consistency output checksum mismatch: '+name)
    read_record(root/'record', request)
    result = _json(read('consistency.json').decode('utf-8-sig'))
    if (not isinstance(result, dict) or type(result.get('schema_version')) is not int
            or result['schema_version'] != 1 or result.get('kind') != 'postfit_consistency'
            or result.get('units') != 'mm' or result.get('source_report_sha256') != request['report_sha256']
            or result.get('status') not in ('block', 'not_assessed')
            or result.get('light') != COLORS[result['status']] or result.get('correction_applied') is not False):
        raise ValueError('Unsupported consistency result')
    return result, read('consistency.txt').decode('utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('build',))
    parser.add_argument('--report', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--artifacts')
    args = parser.parse_args(argv)
    try:
        build_summary(args.report, args.output_dir, artifacts=args.artifacts)
    except (ValueError, OSError, TypeError) as exc:
        parser.error(str(exc))
    return 0  # completed diagnostic output, not an approval/quality exit code


if __name__ == '__main__':
    raise SystemExit(main())

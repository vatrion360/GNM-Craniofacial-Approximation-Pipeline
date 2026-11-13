"""Explicit, gated saved-fit mesh bundles; never fits or exports current scene edits.

Scientific/illustrative are export modes, not validation claims. The first
increment exports the saved neutral final surface only, with no textures.
"""
import argparse
from pathlib import Path, PureWindowsPath
import re

import numpy as np

from .record import build_record, canonical_bytes, validate_report, _digest, OUTPUT_KEYS
from .tissue import _json

MODES = ('scientific', 'illustrative')
RECORD_FILES = ('record/approximation_record.json', 'record/approximation_record.txt', 'record/provenance.json')
NEUTRAL_MATERIAL = 'newmtl GNM_Neutral_Gray\nKa 0.5 0.5 0.5\nKd 0.5 0.5 0.5\nKs 0 0 0\nd 1\nillum 1\n'
INTERPRETATION = ('Export mode is not scientific validation or approval. Geometry is the saved final neutral '
                  'fit in world mm; current Blender edits and presentation controls are not included.')


def geometry_lines(raw):
    """Validate the pipeline's restricted OBJ dialect; retain numeric tokens exactly.

    Only finite three-coordinate vertices, triangular positive vertex indices,
    comments and blank lines are accepted. No material, texture, group, normal,
    command or external-file directive from an input OBJ is followed or copied.
    """
    text = raw.decode('utf-8-sig')
    lines, vertices, faces = [], [], []
    for number, line in enumerate(text.splitlines(), 1):
        parts = line.split()
        if not parts or parts[0].startswith('#'):
            continue
        if len(parts) != 4 or parts[0] not in ('v', 'f'):
            raise ValueError(f'Unsupported saved-fit OBJ directive at line {number}; expected pipeline v/f triangles')
        if parts[0] == 'v':
            values = np.asarray(parts[1:], dtype=float)
            if not np.isfinite(values).all():
                raise ValueError('Non-finite saved-fit vertex')
            vertices.append(values)
        else:
            if any(re.fullmatch(r'[1-9][0-9]*', token) is None for token in parts[1:]):
                raise ValueError('Expected positive vertex-only triangle indices')
            face = [int(token) for token in parts[1:]]
            if len(set(face)) != 3:
                raise ValueError('Repeated index in saved-fit triangle')
            faces.append(face)
        lines.append(' '.join(parts))
    if not vertices or not faces or any(i > len(vertices) for face in faces for i in face):
        raise ValueError('Empty saved-fit mesh or triangle index outside vertex array')
    return lines, dict(vertices=len(vertices), triangles=len(faces))


def _read(path):
    return _json(Path(path).read_bytes().decode('utf-8-sig'))


def export_bundle(report_path, output_dir, *, mode, artifacts=None, limitations_path=None,
                  uncertainty_path=None, uncertainty_scenario=None, validity_domain_path=None,
                  domain_case_path=None, check_policy_path=None, check_override=None):
    """Write diagnostics for held scientific exports; publish one decision file last.

    Returns export_decision.json. A blocked decision is complete diagnostic output,
    not a completed mesh export. Partial failures have no decision marker. Existing
    destinations are refused. A5 overrides retain all findings and explicit text.
    """
    if mode not in MODES:
        raise ValueError('Explicit export mode must be scientific or illustrative')
    if mode == 'scientific' and check_policy_path is None:
        raise ValueError('Scientific mode requires an explicit check policy; no implicit approval')
    destination, report_path = Path(output_dir), Path(report_path)
    if destination.exists() or destination.is_symlink():
        raise ValueError('Export directory exists; choose a new destination')
    paths = [report_path, *[Path(p) for p in (limitations_path, uncertainty_path, validity_domain_path,
                                             domain_case_path, check_policy_path) if p is not None]]
    pinned = {p: p.read_bytes() for p in paths}
    raw = pinned[report_path]
    report = _json(raw.decode('utf-8-sig'))
    validate_report(report)
    directory = Path(artifacts) if artifacts is not None else report_path.parent
    sources = {}
    for key in OUTPUT_KEYS:
        name = PureWindowsPath(report['outputs'][key]['path']).name
        path = directory/name
        if not name or name in ('.', '..') or not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Saved-fit artifact escapes the supplied directory')
        sources[key] = path
    mesh_raw = sources['output'].read_bytes()
    if _digest(mesh_raw) != report['outputs']['output']['sha256']:
        raise ValueError('Saved-fit mesh checksum mismatch')
    lines, counts = geometry_lines(mesh_raw)
    # All remaining artifact/analysis checks are delegated to the existing record builder.
    destination.mkdir(parents=True, exist_ok=False)
    record_path = build_record(report_path, destination/'record', artifacts=artifacts,
        limitations_path=limitations_path, uncertainty_path=uncertainty_path, uncertainty_scenario=uncertainty_scenario,
        validity_domain_path=validity_domain_path, domain_case_path=domain_case_path,
        check_policy_path=check_policy_path, check_override=check_override)
    record = _read(record_path)
    assessment = record['assessments'].get('check_policy')
    held = mode == 'scientific' and not assessment['gate']['proceed']
    overridden = mode == 'scientific' and assessment['gate']['status'] == 'overridden'
    label = ('SCIENTIFIC EXPORT BLOCKED' if held else 'SCIENTIFIC EXPORT WITH RECORDED OVERRIDE' if overridden
             else 'SCIENTIFIC EXPORT — NOT VALIDATED' if mode == 'scientific' else 'ILLUSTRATIVE — NOT VALIDATED')
    decision = dict(schema_version=1, kind='saved_fit_export', mode=mode,
        status='blocked' if held else 'completed', label=label, units='mm',
        scientific_export_authorization='not_assessed', interpretation=INTERPRETATION,
        source_report_sha256=_digest(raw), source_final_mesh_sha256=_digest(mesh_raw), geometry=counts,
        check_policy_status=None if assessment is None else assessment['status'],
        check_gate=None if assessment is None else assessment['gate'],
        policy_applied_to_export=mode == 'scientific',
        material='neutral_gray', textures=False, geometry_transformed=False,
        standardized_captures='not_exported', final_mesh_uncertainty='not_assessed',
        implementation_sha256=_digest(Path(__file__).read_bytes()))
    files = {}
    def unchanged():
        if any(p.read_bytes() != content for p, content in pinned.items()):
            raise ValueError('Export input changed; no decision marker')
        if any(_digest(path.read_bytes()) != report['outputs'][key]['sha256'] for key, path in sources.items()):
            raise ValueError('Saved-fit artifacts changed; no decision marker')
    unchanged()
    from .export import atomic_text
    def write(name, content):
        path = destination/name
        def validate(_):
            if path.exists() or path.is_symlink():
                raise ValueError('Concurrent export output exists: '+name)
        with atomic_text(path, validate=validate) as stream:
            stream.write(content)
        files[name] = dict(sha256=_digest(path.read_bytes()))
    if not held:
        comments = [label, INTERPRETATION, 'source_report_sha256 '+_digest(raw),
                    'source_final_mesh_sha256 '+_digest(mesh_raw)]
        if assessment is not None:
            comments.extend([assessment['banner'], 'override_reason: '+str(assessment['gate']['override_reason'])])
        header = ''.join('# '+line+'\n' for text in comments for line in text.splitlines())
        write('face.mtl', NEUTRAL_MATERIAL)
        write('face.obj', header+'mtllib face.mtl\nusemtl GNM_Neutral_Gray\n'+'\n'.join(lines)+'\n')
    page = (label+'\n'+INTERPRETATION+'\n'+
        ('No face mesh was exported. Review the findings or supply an explicit override reason.\n' if held else
         'Neutral gray OBJ/MTL; no textures, captures or final-mesh uncertainty supplied.\n')+
        'The check policy gates scientific mode only. Illustrative mode retains all diagnostic findings.\n\n'+
        (destination/'record'/'approximation_record.txt').read_text(encoding='utf-8'))
    write('README.txt', page)
    for name in RECORD_FILES:
        files[name] = dict(sha256=_digest((destination/name).read_bytes()))
    decision['files'] = files
    output = destination/'export_decision.json'
    def validate(_):
        unchanged()
        if output.exists() or output.is_symlink():
            raise ValueError('Concurrent decision output exists')
        if any(_digest((destination/name).read_bytes()) != row['sha256'] for name, row in files.items()):
            raise ValueError('Export files changed before completion')
        if held and any((destination/name).exists() or (destination/name).is_symlink() for name in ('face.obj', 'face.mtl')):
            raise ValueError('Unexpected mesh files in blocked export')
    with atomic_text(output, validate=validate) as stream:
        stream.write(canonical_bytes(decision).decode('utf-8'))
    return output


def read_result(output_dir, request):
    """Verify a fixed bundle and clicked report before displaying its explicit status."""
    from .record_job import read_result as read_record
    root = Path(output_dir).resolve()
    def read(name):
        path = root/name
        if not path.resolve().is_relative_to(root):
            raise ValueError('Export result escapes its directory')
        return path.read_bytes()
    result = _json(read('export_decision.json').decode('utf-8-sig'))
    if (not isinstance(result, dict) or type(result.get('schema_version')) is not int or result['schema_version'] != 1
            or result.get('kind') != 'saved_fit_export' or result.get('status') not in ('completed', 'blocked')
            or result.get('mode') != request.get('export_mode') or result.get('mode') not in MODES
            or result.get('units') != 'mm' or result.get('source_report_sha256') != request['report_sha256']):
        raise ValueError('Unsupported export result or mismatched request')
    blocked = result['status'] == 'blocked'
    expected = {'README.txt', *RECORD_FILES} | (set() if blocked else {'face.obj', 'face.mtl'})
    files = result.get('files')
    if not isinstance(files, dict) or set(files) != expected:
        raise ValueError('Unexpected export file manifest')
    for name in sorted(expected):
        row = files[name]
        if not isinstance(row, dict) or _digest(read(name)) != row.get('sha256'):
            raise ValueError('Export result checksum mismatch: '+name)
    record, _ = read_record(root/'record', request)
    if result.get('source_final_mesh_sha256') != record['run']['outputs']['output']['sha256']:
        raise ValueError('Export mesh source differs from saved record')
    assessment = record['assessments'].get('check_policy')
    if result['mode'] == 'scientific':
        if not isinstance(assessment, dict):
            raise ValueError('Scientific result lacks a check assessment')
        if (result.get('check_gate') != assessment.get('gate')
                or result.get('check_policy_status') != assessment.get('status')
                or blocked == assessment['gate']['proceed']):
            raise ValueError('Export decision differs from recorded gate')
    elif blocked:
        raise ValueError('Illustrative exports cannot claim scientific gating')
    if blocked and any((root/name).exists() or (root/name).is_symlink() for name in ('face.obj', 'face.mtl')):
        raise ValueError('Blocked export contains unexpected mesh files')
    return result, read('README.txt').decode('utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('build',))
    parser.add_argument('--report', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--mode', required=True, choices=MODES)
    for flag in ('artifacts', 'limitations', 'uncertainty', 'validation-domain', 'domain-case', 'check-policy'):
        parser.add_argument('--'+flag)
    parser.add_argument('--uncertainty-scenario', choices=('off', 'on'))
    parser.add_argument('--allow-blocked', '--check-override', dest='check_override', help='Audited exception reason')
    args = parser.parse_args(argv)
    try:
        path = export_bundle(args.report, args.output_dir, mode=args.mode, artifacts=args.artifacts,
            limitations_path=args.limitations, uncertainty_path=args.uncertainty, uncertainty_scenario=args.uncertainty_scenario,
            validity_domain_path=args.validation_domain, domain_case_path=args.domain_case,
            check_policy_path=args.check_policy, check_override=args.check_override)
        return 3 if _read(path)['status'] == 'blocked' else 0
    except (ValueError, OSError, TypeError, KeyError, OverflowError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    raise SystemExit(main())

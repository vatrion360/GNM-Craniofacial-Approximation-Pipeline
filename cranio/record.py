"""Opt-in deterministic view of the existing v2 run report; never runs a fit.

The run report remains authoritative. Artifact integrity is not scientific
validation. Runtime paths and timestamps live in a separate provenance envelope.
"""
import argparse
import copy
import datetime
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath

from .tissue import _json

OUTPUT_KEYS = ('output', 'output_statistical', 'output_error_mesh', 'output_stats')
PATH_SETTINGS = {'input', 'output', 'output_statistical', 'output_error_mesh', 'output_stats',
                 'output_json', 'npz', 'skull', 'prior', 'landmark_map', 'protocol',
                 'case_metadata', 'craniometry', 'tissue_table', 'tissue_directions', 'profile_constraint'}
INTERPRETATION = ('Derived view of the canonical run report, not a new fit or scientific approval. '
                  'Fit residuals and local displacement are not accuracy or calibrated uncertainty. '
                  'Recorded input hashes are not revalidated by this command.')


def canonical_bytes(value) -> bytes:
    """Stable UTF-8 encoding, rejecting non-finite values anywhere in a record."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode('utf-8')


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _hash(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Expected lowercase SHA-256')
    return value


def empty_limitations() -> dict:
    """No unapproved scientific wording is invented."""
    return dict(schema_version=1, revision=None, approved=False, ro=None, en=None)


def validate_limitations(document: dict) -> dict:
    """Accept only explicitly operator-approved RO/EN wording and its revision."""
    if not isinstance(document, dict) or set(document) != set(empty_limitations()):
        raise ValueError('Limitations must contain schema_version, revision, approved, ro and en')
    if type(document['schema_version']) is not int or document['schema_version'] != 1 or document['approved'] is not True:
        raise ValueError('Limitations require schema_version=1 and explicit approved=true')
    for key in ('revision', 'ro', 'en'):
        text = document[key]
        if (not isinstance(text, str) or not text.strip()
                or text.strip().casefold() in {'unknown', 'unspecified', 'todo', 'null', 'none'}
                or 'todo(verify-source)' in text.casefold() or '[[lips' in text.casefold()):
            raise ValueError('Limitations require supplied revision and approved RO/EN text')
    return copy.deepcopy(document)


def validate_report(report: dict) -> None:
    """Validate required v2 structure, preserving extra descriptive fields."""
    if (not isinstance(report, dict) or type(report.get('schema_version')) is not int
            or report['schema_version'] != 2 or report.get('status') != 'completed' or report.get('units') != 'mm'):
        raise ValueError('Expected a completed world-mm pipeline run report schema 2')
    for key in ('software', 'config', 'inputs', 'outputs', 'marker_metadata', 'metrics', 'solver',
                'transform', 'local_correction', 'lambda_selection'):
        if not isinstance(report.get(key), dict):
            raise ValueError('Missing/malformed report object: '+key)
    for key in ('landmarks', 'skipped', 'auto_excluded', 'warnings', 'identity_coefficients'):
        if not isinstance(report.get(key), list):
            raise ValueError('Missing/malformed report list: '+key)
    if type(report['solver'].get('converged')) is not bool or type(report['config'].get('require_qc')) is not bool:
        raise ValueError('Missing/malformed convergence or required-QC state')
    if not {'model', 'markers'} <= report['inputs'].keys() or not set(OUTPUT_KEYS) <= report['outputs'].keys():
        raise ValueError('Report is missing required input/output artifacts')
    for row in [*report['inputs'].values(), *report['outputs'].values()]:
        if not isinstance(row, dict) or not isinstance(row.get('path'), str) or not row['path'].strip():
            raise ValueError('Artifact needs a path and SHA-256')
        _hash(row.get('sha256'))
    labels = set()
    records = report['marker_metadata'].get('marker_records', {})
    if not isinstance(records, dict) or any(not isinstance(row, dict) for row in records.values()):
        raise ValueError('Malformed per-marker provenance')
    for row in report['landmarks']:
        if (not isinstance(row, dict) or not isinstance(row.get('label'), str) or not row['label'].strip()
                or row['label'] in labels or type(row.get('vertex')) is not int or row['vertex'] < 0):
            raise ValueError('Malformed or duplicate fitted landmark')
        labels.add(row['label'])
    if not labels:
        raise ValueError('Run report has no fitted landmarks')
    lam = report.get('lambda')
    try:
        valid_lambda = type(lam) in (int, float) and math.isfinite(lam) and lam > 0
    except OverflowError:
        valid_lambda = False
    if not valid_lambda:
        raise ValueError('Selected lambda must be finite and positive')
    canonical_bytes(report)


def compile_record(report: dict, limitations=None) -> dict:
    """Build a detached view, without inferring missing provenance or checks.

    Runtime paths move into provenance.json. Paths/timestamps supplied as case
    metadata remain source evidence and are not recursively stripped.
    """
    validate_report(report)
    source = copy.deepcopy(report)
    source.pop('generated_utc', None)
    source['inputs'] = {key: {'sha256': row['sha256']} for key, row in report['inputs'].items()}
    source['outputs'] = {key: {'sha256': report['outputs'][key]['sha256']}
                         for key in OUTPUT_KEYS if key != 'output_stats'}
    source['config'] = {key: value for key, value in source['config'].items() if key not in PATH_SETTINGS}
    provenance = source['marker_metadata'].get('marker_records', {})
    markers = [dict(fit=copy.deepcopy(row), provenance=copy.deepcopy(provenance.get(row['label'])),
                    provenance_status='recorded' if row['label'] in provenance else 'not_recorded')
               for row in report['landmarks']]
    quality = report.get('geometry_quality')
    required = report['config']['require_qc'] or bool(report['config'].get('protocol'))
    gate = ('not_required' if not required else 'met' if isinstance(quality, dict)
            and quality.get('status') == 'passed_full_checks' else 'not_met')
    limitations_record = (dict(status='operator_declared_approved', document=validate_limitations(limitations))
                          if limitations is not None else dict(status='not_configured', document=None))
    return dict(schema_version=1, kind='derived_approximation_record', units='mm',
        status='diagnostic_only' if not report['solver']['converged'] or gate == 'not_met' else 'recorded_not_validated',
        interpretation=INTERPRETATION, run=source, markers=markers,
        prior=dict(enabled='prior' in report['inputs'], justification=report['config'].get('prior_justification'),
                   sha256=report['inputs'].get('prior', {}).get('sha256')),
        assessments=dict(geometry_gate_from_report=gate,
            solver_scope='baseline_before_profile' if report['config'].get('profile_constraint') else 'statistical_fit',
            uncertainty=dict(status='not_assessed', reason='No uncertainty artifact linked by this command'),
            calibration=dict(status='not_assessed', reason='No calibration artifact linked by this command'),
            validity_domain=dict(status='not_assessed', reason='No independently evaluated domain linked'),
            scientific_export_authorization=dict(status='not_assessed', reason='No scientific approval or override inferred')),
        limitations=limitations_record)


def _text(record):
    """Concise summary; full values remain in the canonical report and JSON view."""
    run = record['run']
    uncertainty = record['assessments']['uncertainty']
    uncertainty_label = ('Final-mesh uncertainty' if uncertainty['status'] == 'linked_uncalibrated_analysis'
                         else 'Uncertainty')
    lines = ['GNM approximation record (derived)', 'Status: '+record['status'], INTERPRETATION,
             'Model SHA-256: '+run['inputs']['model']['sha256'],
             'Pipeline version: '+str(run['software'].get('pipeline')),
             'Lambda: '+str(run['lambda'])+'; method: '+str(run['lambda_selection'].get('method')),
             'Prior enabled: '+str(record['prior']['enabled'])+'; rationale: '+str(record['prior']['justification']),
             'Geometry gate from report: '+record['assessments']['geometry_gate_from_report'],
             'Solver scope: '+record['assessments']['solver_scope'],
             uncertainty_label+' / calibration / validity domain / scientific authorization: not_assessed',
             'RO/EN limitations: '+record['limitations']['status'], 'Fitted markers:']
    for row in record['markers']:
        p = row['provenance'] or {}
        lines.append(f"  {row['fit']['label']}: vertex={row['fit']['vertex']}; bone_status={p.get('bone_status')}; "
                     f"mapping_reviewed={p.get('mapping_reviewed')}; tissue_source={p.get('tissue_source')}")
    if uncertainty['status'] == 'linked_uncalibrated_analysis':
        lines.extend(['Related uncertainty analysis: '+uncertainty['source_sha256'],
                      uncertainty['interpretation'],
                      'Selected prior scenario: '+uncertainty['selected_prior_scenario'],
                      'Analysis status: '+uncertainty['analysis_status'],
                      'Samples: '+str(uncertainty['samples']),
                      'Scenario diagnostics: '+json.dumps(uncertainty['scenario_diagnostics'], sort_keys=True),
                      'Omitted errors: '+json.dumps(uncertainty['omitted_error_inputs'], ensure_ascii=False)])
        lines.extend(uncertainty['source_warnings'])
    lines.append('Source warnings:')
    lines.extend(str(w) for w in run['warnings'])
    lines.append('Excluded markers (source report): '+json.dumps(run['skipped'], ensure_ascii=False))
    lines.append('Automatically excluded (source report): '+json.dumps(run['auto_excluded'], ensure_ascii=False))
    if record['limitations']['document']:
        lines.extend(['RO:', record['limitations']['document']['ro'], 'EN:', record['limitations']['document']['en']])
    return '\n'.join(lines)+'\n'


def build_record(report_path, output_dir, *, artifacts=None, limitations_path=None,
                 uncertainty_path=None, uncertainty_scenario=None) -> Path:
    """Verify local outputs and publish the derived JSON last as completion marker.

    Inputs/model are not opened. A moved bundle may supply --artifacts with the
    four output basenames. Existing destinations are refused; failures after
    creation leave partial output without approximation_record.json.
    """
    if (uncertainty_path is None) != (uncertainty_scenario is None):
        raise ValueError('Supply uncertainty file and explicit scenario together')
    report_path, destination = Path(report_path), Path(output_dir)
    if destination.exists() or destination.is_symlink():
        raise ValueError('Record directory exists; choose a new destination')
    raw = report_path.read_bytes()
    report = _json(raw.decode('utf-8-sig'))
    validate_report(report)
    approved_raw = Path(limitations_path).read_bytes() if limitations_path else None
    approved = validate_limitations(_json(approved_raw.decode('utf-8-sig'))) if approved_raw is not None else None
    record = compile_record(report, approved)
    uncertainty_raw = Path(uncertainty_path).read_bytes() if uncertainty_path is not None else None
    if uncertainty_raw is not None:
        from .record_uncertainty import summarize_link
        uncertainty = _json(uncertainty_raw.decode('utf-8-sig'))
        record['assessments']['uncertainty'] = summarize_link(
            report, uncertainty, uncertainty_scenario, _digest(uncertainty_raw))
    directory = Path(artifacts) if artifacts else report_path.parent
    checked, names = {}, set()
    for key in OUTPUT_KEYS:
        row = report['outputs'][key]
        name = PureWindowsPath(row['path']).name
        if not name or name in {'.', '..'} or name in names:
            raise ValueError('Output artifact basenames must be nonempty and distinct')
        names.add(name)
        path = directory/name
        if not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Output artifact escapes the supplied directory')
        if _digest(path.read_bytes()) != row['sha256']:
            raise ValueError('Output artifact checksum mismatch: '+key)
        checked[key] = dict(path=str(path.resolve()), sha256=row['sha256'])
    envelope = dict(schema_version=1, generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        record_generator=dict(module_sha256=_digest(Path(__file__).read_bytes())),
        source_report=dict(path=str(report_path.resolve()), sha256=_digest(raw), generated_utc=report.get('generated_utc')),
        source_inputs=report['inputs'], source_outputs=report['outputs'], checked_outputs=checked,
        path_settings={key: value for key, value in report['config'].items() if key in PATH_SETTINGS},
        input_verification='hashes_recorded_not_revalidated',
        limitations_file=None if approved_raw is None else dict(path=str(Path(limitations_path).resolve()), sha256=_digest(approved_raw)))
    if uncertainty_raw is not None:
        from . import record_uncertainty
        envelope['uncertainty_file'] = dict(path=str(Path(uncertainty_path).resolve()),
            sha256=_digest(uncertainty_raw), recorded_input_hashes=uncertainty['input_hashes'],
            validator_sha256=_digest(Path(record_uncertainty.__file__).read_bytes()))
    content = canonical_bytes(record)
    page = _text(record).encode('utf-8')
    envelope['derived_files'] = {name: dict(sha256=_digest(data)) for name, data in
                                [('approximation_record.json', content), ('approximation_record.txt', page)]}
    from .export import atomic_text
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in [('approximation_record.txt', page), ('provenance.json', canonical_bytes(envelope))]:
        with atomic_text(destination/name) as stream:
            stream.write(data.decode('utf-8'))
    if report_path.read_bytes() != raw or (approved_raw is not None and Path(limitations_path).read_bytes() != approved_raw):
        raise ValueError('Source record changed during export; no completion marker')
    if any(_digest(Path(row['path']).read_bytes()) != row['sha256'] for row in checked.values()):
        raise ValueError('Output artifacts changed during export; no completion marker')
    if uncertainty_raw is not None and Path(uncertainty_path).read_bytes() != uncertainty_raw:
        raise ValueError('Uncertainty source changed during export; no completion marker')
    with atomic_text(destination/'approximation_record.json') as stream:
        stream.write(content.decode('utf-8'))
    return destination/'approximation_record.json'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build')
    build.add_argument('--report', required=True)
    build.add_argument('--output-dir', required=True)
    build.add_argument('--artifacts')
    build.add_argument('--limitations')
    build.add_argument('--uncertainty', help='Related A2.1 CLI ensemble JSON (not final-mesh uncertainty)')
    build.add_argument('--uncertainty-scenario', choices=('off', 'on'))
    template = sub.add_parser('limitations-template')
    template.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'build':
            build_record(args.report, args.output_dir, artifacts=args.artifacts, limitations_path=args.limitations,
                         uncertainty_path=args.uncertainty, uncertainty_scenario=args.uncertainty_scenario)
        else:
            path = Path(args.output)
            if path.exists() or path.is_symlink():
                raise ValueError('Template output exists')
            from .export import atomic_text
            with atomic_text(path) as stream:
                stream.write(canonical_bytes(empty_limitations()).decode('utf-8'))
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

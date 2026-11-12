"""Compare explicit case observations with an operator-declared validation domain.

No anatomy, age class, sufficiency of N or scientific validity is inferred.
Matching a declared domain is not independent validation or export approval.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re

from .record import PATH_SETTINGS, canonical_bytes, validate_report, _hash
from .tissue import _json

INTERPRETATION = ('Operator-declared conditions and evidence, not independently verified validation. '
    'Matching conditions and a run signature do not establish anatomical accuracy. '
    'Regional results describe the declared study, not this face; no correction, uncertainty or export approval is applied.')
BANNERS = {
    'not_configured': 'DOMAIN NOT CONFIGURED / NOT REVIEWED',
    'indeterminate': 'DOMAIN APPLICABILITY INDETERMINATE',
    'outside_declared_domain': 'OUTSIDE DECLARED DOMAIN',
    'within_declared_conditions': 'MATCHES DECLARED CONDITIONS — NOT INDEPENDENT VALIDATION',
}


def _keys(value, expected, name):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(name+': expected exactly '+', '.join(sorted(expected)))


def _text(value, name, nullable=False):
    if nullable and value is None:
        return
    if (not isinstance(value, str) or not value.strip() or value.strip().casefold() in
            {'unknown', 'unspecified', 'none', 'null', 'n/a', 'not reported', 'not configured'}
            or value.strip().casefold().startswith('todo') or '[[lips' in value.casefold()):
        raise ValueError(name+': supply documented text, not a placeholder')


def _number(value, name):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(name+': expected finite number')


def _count(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(name+': expected positive independent-subject count')


def empty_domain():
    """No anatomical conditions, errors, cohort counts or evidence are invented."""
    return dict(schema_version=1, id=None, revision=None, reviewed=False, model_sha256=None,
        run_signatures=[], evidence=dict(reference=None, sha256=None, n_subjects=None),
        conditions={}, regional_errors=[])


def run_signature(report):
    """Conservative reproducibility signature, not proof of method equivalence.

    Config paths move out; all other settings stay. Shared assets use their hashes,
    case-specific inputs use presence only. Source and numerical environment are
    retained; git status/commit are not scientific settings. Missing source
    fingerprint returns None, never a fabricated compatibility assertion.
    """
    software = report['software']
    implementation = software.get('implementation')
    if (not isinstance(implementation, dict)
            or any(not isinstance(software.get(k), str) or not software[k].strip()
                   for k in ('pipeline', 'python', 'numpy', 'scipy', 'trimesh'))
            or not isinstance(software.get('numerical_environment'), dict)
            or not software['numerical_environment']):
        return None
    try:
        _hash(implementation.get('source_sha256'))
    except ValueError:
        return None
    payload = dict(signature_schema=1, model_sha256=report['inputs']['model']['sha256'],
        settings={k: v for k, v in report['config'].items() if k not in PATH_SETTINGS},
        input_roles=sorted(report['inputs']),
        shared_assets={k: row['sha256'] for k, row in report['inputs'].items() if k in
                       {'prior', 'landmark_map', 'protocol', 'tissue_table', 'tissue_directions'}},
        source_sha256=implementation['source_sha256'],
        software={k: software.get(k) for k in ('pipeline', 'python', 'numpy', 'scipy', 'trimesh')},
        numerical_environment=software.get('numerical_environment'))
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def validate_domain(document):
    """Validate closed schema; an honest unreviewed empty template is permitted."""
    _keys(document, empty_domain(), 'domain')
    if type(document['schema_version']) is not int or document['schema_version'] != 1:
        raise ValueError('Domain schema_version must be 1')
    if type(document['reviewed']) is not bool:
        raise ValueError('Domain reviewed must be boolean')
    nullable = not document['reviewed']
    for key in ('id', 'revision'):
        _text(document[key], key, nullable)
    if document['model_sha256'] is not None or not nullable:
        _hash(document['model_sha256'])
    signatures = document['run_signatures']
    if not isinstance(signatures, list) or (not nullable and not signatures):
        raise ValueError('Reviewed domain requires run_signatures')
    for digest in signatures:
        _hash(digest)
    if len(set(signatures)) != len(signatures):
        raise ValueError('Duplicate run signatures')
    evidence = document['evidence']
    _keys(evidence, ('reference', 'sha256', 'n_subjects'), 'evidence')
    _text(evidence['reference'], 'evidence reference', nullable)
    if evidence['sha256'] is not None or not nullable:
        _hash(evidence['sha256'])
    if evidence['n_subjects'] is not None or not nullable:
        _count(evidence['n_subjects'], 'evidence n_subjects')
    conditions = document['conditions']
    if not isinstance(conditions, dict) or (not nullable and not conditions):
        raise ValueError('Reviewed domain requires at least one condition')
    for key, row in conditions.items():
        if (not isinstance(key, str) or key in {'model_sha256', 'run_signature'}
                or re.fullmatch(r'[a-z][a-z0-9_]{0,63}', key) is None):
            raise ValueError('Condition identifiers must use lowercase letters, digits and underscores')
        _keys(row, ('definition', 'allowed_values', 'source'), 'condition '+key)
        _text(row['definition'], key+' definition', nullable)
        _text(row['source'], key+' source', nullable)
        values = row['allowed_values']
        if values is None and nullable:
            continue
        if not isinstance(values, list) or not values:
            raise ValueError(key+': allowed_values must be a nonempty list')
        for value in values:
            _text(value, key+' allowed value')
            if value != value.strip():
                raise ValueError('Condition values must not have leading/trailing whitespace')
        if len(set(values)) != len(values):
            raise ValueError('Duplicate allowed values')
    rows = document['regional_errors']
    if not isinstance(rows, list):
        raise ValueError('regional_errors must be a list')
    seen = set()
    for row in rows:
        _keys(row, ('region', 'metric', 'units', 'estimate', 'n_subjects', 'interval', 'source'), 'regional result')
        for key in ('region', 'metric', 'units', 'source'):
            _text(row[key], 'regional '+key)
        pair = (row['region'], row['metric'])
        if pair in seen:
            raise ValueError('Duplicate region/metric result')
        seen.add(pair)
        _number(row['estimate'], 'regional estimate')
        _count(row['n_subjects'], 'regional n_subjects')
        if evidence['n_subjects'] is not None and row['n_subjects'] > evidence['n_subjects']:
            raise ValueError('Regional N exceeds declared study N')
        interval = row['interval']
        if interval is not None:
            _keys(interval, ('lower', 'upper', 'kind', 'level'), 'interval')
            _number(interval['lower'], 'interval lower')
            _number(interval['upper'], 'interval upper')
            _text(interval['kind'], 'interval kind')
            if interval['lower'] > interval['upper']:
                raise ValueError('Reversed interval bounds')
            if interval['level'] is not None:
                _number(interval['level'], 'interval level')
                if not 0 < interval['level'] < 1:
                    raise ValueError('Interval level must be between 0 and 1 or null')
    canonical_bytes(document)
    return copy.deepcopy(document)


def case_template(report_sha256, domain=None):
    _hash(report_sha256)
    if domain is not None:
        validate_domain(domain)
    return dict(schema_version=1, report_sha256=report_sha256,
                observations={key: dict(value=None, source=None, reviewed=False)
                              for key in sorted(domain['conditions'] if domain else {})})


def validate_case(document, report_sha256, conditions):
    _keys(document, ('schema_version', 'report_sha256', 'observations'), 'domain case')
    if type(document['schema_version']) is not int or document['schema_version'] != 1:
        raise ValueError('Domain case schema_version must be 1')
    _hash(document['report_sha256'])
    if document['report_sha256'] != report_sha256:
        raise ValueError('Domain case belongs to a different source report')
    observations = document['observations']
    if not isinstance(observations, dict) or set(observations)-set(conditions):
        raise ValueError('Unknown domain observation keys')
    for key, row in observations.items():
        _keys(row, ('value', 'source', 'reviewed'), 'observation '+key)
        if type(row['reviewed']) is not bool:
            raise ValueError('Observation reviewed must be boolean')
        _text(row['value'], key+' value', not row['reviewed'])
        _text(row['source'], key+' source', not row['reviewed'])
        if row['value'] is not None and row['value'] != row['value'].strip():
            raise ValueError('Observation values must not have leading/trailing whitespace')
    return copy.deepcopy(document)


def assess(report, report_sha256, domain, case):
    """Compare supplied declarations only; missing observations never become matches."""
    validate_report(report)
    _hash(report_sha256)
    domain = validate_domain(domain)
    case = validate_case(case, report_sha256, domain['conditions'])
    signature = run_signature(report)
    checks = []
    if domain['reviewed']:
        checks.append(dict(condition='model_sha256', status='match' if domain['model_sha256'] ==
                           report['inputs']['model']['sha256'] else 'outside'))
        checks.append(dict(condition='run_signature', status='unknown' if signature is None else
                           'match' if signature in domain['run_signatures'] else 'outside'))
        for key, condition in sorted(domain['conditions'].items()):
            row = case['observations'].get(key)
            status = ('unknown' if row is None or not row['reviewed'] else
                      'match' if row['value'] in condition['allowed_values'] else 'outside')
            checks.append(dict(condition=key, status=status, observation=copy.deepcopy(row)))
        states = {row['status'] for row in checks}
        status = ('outside_declared_domain' if 'outside' in states else
                  'indeterminate' if 'unknown' in states else 'within_declared_conditions')
    else:
        status = 'not_configured'
    warnings = [INTERPRETATION, 'Declared subject counts do not establish a statistically sufficient cohort.']
    if not domain['regional_errors']:
        warnings.append('No regional validation errors supplied; none are inferred.')
    elif any(row['interval'] is None for row in domain['regional_errors']):
        warnings.append('Some declared regional estimates have no interval; missing intervals are not imputed.')
    return dict(status=status, banner=BANNERS[status], interpretation=INTERPRETATION,
                current_run_signature=signature, checks=checks, domain=domain, case=case,
                evidence_verification='operator_declared_not_revalidated', warnings=warnings)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('template', 'case-template'))
    parser.add_argument('--report', help='Completed run report; required for case-template')
    parser.add_argument('--domain', help='Domain whose condition keys should populate the blank case template')
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        if (args.action == 'case-template' and not args.report) or (args.action == 'template' and args.domain):
            raise ValueError('case-template needs --report; --domain is only for case-template')
        output = Path(args.output)
        if output.exists() or output.is_symlink():
            raise ValueError('Template output exists; choose a new path')
        sources = {}
        report = None
        for value in (args.report, args.domain):
            if value:
                sources[value] = Path(value).read_bytes()
        if args.report:
            report = _json(sources[args.report].decode('utf-8-sig'))
            validate_report(report)
        if args.action == 'template':
            result = empty_domain()
            if report:
                result['model_sha256'] = report['inputs']['model']['sha256']
                signature = run_signature(report)
                result['run_signatures'] = [signature] if signature else []
        else:
            domain = _json(sources[args.domain].decode('utf-8-sig')) if args.domain else None
            result = case_template(hashlib.sha256(sources[args.report]).hexdigest(), domain)
        from .export import atomic_text
        with atomic_text(output, validate=lambda _: _template_ready(sources, output)) as stream:
            stream.write(canonical_bytes(result).decode('utf-8'))
    except (ValueError, OSError, TypeError) as exc:
        parser.error(str(exc))
    return 0


def _template_ready(sources, output):
    if output.exists() or output.is_symlink():
        raise ValueError('Template output appeared during export; refusing to replace it')
    if any(Path(path).read_bytes() != data for path, data in sources.items()):
        raise ValueError('Template input changed; refusing to publish')


if __name__ == '__main__':
    raise SystemExit(main())

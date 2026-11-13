"""Opt-in saved-report checks; no fit, anatomical defaults or export approval.

Checks inspect the report snapshot, not the current Blender scene or original
scans. A decision is a configured workflow gate, never scientific validation.
"""
import argparse
import copy
import math
from pathlib import Path

import numpy as np

from .record import canonical_bytes, validate_report, _digest
from .tissue import _json

INTERPRETATION = ('Saved-report diagnostics and operator-configured criteria only; not anatomical validation '
                  'or scientific export authorization. Original scans and current scene are not revalidated.')


def empty_policy():
    """No anatomical ranges, regional minima or plane-error limits are guessed."""
    return dict(schema_version=1, id=None, revision=None, reviewed=False, rules=[])


def _text(value):
    if (not isinstance(value, str) or not value.strip() or value.strip().casefold() in
            {'todo', 'unknown', 'unspecified', 'null', 'none', 'todo(verify-source)', '[de completat]'}):
        raise ValueError('Supply non-placeholder policy text/source or override reason')
    return value


def _number(value, *, positive=False):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError('Expected a finite '+('positive' if positive else 'nonnegative')+' number')
    return value


def validate_policy(policy):
    """Closed schema; each configured criterion needs explicit severity and source."""
    from .craniometry import BY_KEY
    if not isinstance(policy, dict) or set(policy) != set(empty_policy()):
        raise ValueError('Policy fields must match the template')
    if type(policy['schema_version']) is not int or policy['schema_version'] != 1 or type(policy['reviewed']) is not bool:
        raise ValueError('Expected policy schema_version=1 and boolean reviewed')
    for key in ('id', 'revision'):
        if policy[key] is not None:
            _text(policy[key])
        elif policy['reviewed']:
            raise ValueError('Reviewed policy requires id and revision')
    if not isinstance(policy['rules'], list):
        raise ValueError('Policy rules must be a list')
    seen = set()
    for rule in policy['rules']:
        if not isinstance(rule, dict):
            raise ValueError('Rule must be an object')
        kind = rule.get('kind')
        extras = {'bone_range': {'measurement', 'minimum_mm', 'maximum_mm'},
                  'marker_count': {'region', 'labels', 'minimum'},
                  'midline_rms': {'maximum_mm'}}
        if not isinstance(kind, str) or kind not in extras or set(rule) != {'id', 'kind', 'source', 'on_fail'} | extras[kind]:
            raise ValueError('Unsupported rule kind/fields')
        name = _text(rule['id'])
        if name in seen or name.startswith('builtin:'):
            raise ValueError('Rule IDs must be distinct and cannot use builtin:')
        seen.add(name)
        _text(rule['source'])
        if rule['on_fail'] not in ('warn', 'block'):
            raise ValueError('Choose on_fail warn or block explicitly')
        if kind == 'bone_range':
            if not isinstance(rule['measurement'], str) or rule['measurement'] not in BY_KEY:
                raise ValueError('Unknown canonical cranial measurement')
            low, high = _number(rule['minimum_mm'], positive=True), _number(rule['maximum_mm'], positive=True)
            if low > high:
                raise ValueError('Bone range minimum exceeds maximum')
        elif kind == 'marker_count':
            _text(rule['region'])
            labels = rule['labels']
            if not isinstance(labels, list) or not labels or any(not isinstance(s, str) or not s.strip() or s != s.strip() for s in labels):
                raise ValueError('Region requires explicit nonempty marker labels')
            if len(set(labels)) != len(labels):
                raise ValueError('Duplicate marker label in region')
            if type(rule['minimum']) is not int or not 1 <= rule['minimum'] <= len(labels):
                raise ValueError('minimum must be an integer from 1 to number of labels')
        else:
            _number(rule['maximum_mm'])
    canonical_bytes(policy)
    return copy.deepcopy(policy)


def _row(name, status, reason, *, observed=None, provenance='software_contract', **extra):
    return dict(id=name, status=status, reason=reason, observed=observed, provenance=provenance, **extra)


def _geometry(report):
    """Summarize existing QC conservatively, without promoting basic/missing QC."""
    quality = report.get('geometry_quality')
    if not isinstance(quality, dict) or quality.get('mode') not in ('basic', 'full'):
        return _row('builtin:geometry', 'not_assessed', 'Recognized geometry QC is absent')
    status = quality.get('status')
    if status == 'needs_review':
        return _row('builtin:geometry', 'block', 'Existing geometry QC reports needs_review', observed=status,
                    provenance='legacy_hardcoded')
    unknown = []
    # Retain a guard against a contradictory/malformed success label.
    for stage in ('statistical', 'final'):
        row = quality.get(stage)
        if not isinstance(row, dict) or any(not isinstance(row.get(k), list) for k in
                                          ('new_degenerate_faces', 'normal_reversed_faces')):
            unknown.append('Incomplete geometry diagnostic details')
            continue
        if row['new_degenerate_faces'] or row['normal_reversed_faces']:
            return _row('builtin:geometry', 'block', 'Recorded degeneration or normal reversal', provenance='legacy_hardcoded')
    if unknown:
        return _row('builtin:geometry', 'not_assessed', '; '.join(unknown))
    if quality['mode'] == 'basic' and status == 'passed_basic_checks':
        return _row('builtin:geometry', 'warn', 'Basic checks only; contacts and bone clearance not assessed', observed=status)
    if quality['mode'] != 'full' or status != 'passed_full_checks':
        return _row('builtin:geometry', 'not_assessed', 'Inconsistent QC mode/status')
    baseline = quality.get('baseline_contacts', {})
    if not isinstance(baseline, dict) or baseline.get('complete') is not True:
        unknown.append('Baseline contact search incomplete')
    for stage in ('statistical', 'final'):
        row = quality[stage]
        contacts, clearance = row.get('contacts', {}), row.get('bone_clearance', {})
        if not isinstance(row.get('new_contact_face_pairs'), list) or not isinstance(contacts, dict):
            unknown.append('Missing contact details')
            continue
        if row['new_contact_face_pairs']:
            return _row('builtin:geometry', 'block', 'Recorded new surface contacts', provenance='legacy_hardcoded')
        if contacts.get('complete') is not True:
            unknown.append('Contact search incomplete')
        if not isinstance(clearance, dict) or type(clearance.get('negative_clearance_count')) is not int:
            unknown.append('Observed-bone clearance not assessed')
            continue
        if clearance['negative_clearance_count'] < 0:
            unknown.append('Invalid clearance count')
        if clearance['negative_clearance_count'] > 0:
            return _row('builtin:geometry', 'block', 'Recorded negative local outward clearance', provenance='legacy_hardcoded')
    if unknown:
        return _row('builtin:geometry', 'not_assessed', '; '.join(dict.fromkeys(unknown)))
    return _row('builtin:geometry', 'pass', 'Recorded full checks passed in their limited sampled scope', observed=status,
                provenance='legacy_hardcoded')


def _configured(report, rule):
    """Recompute bone/frame descriptors from embedded observations, not cached scalars."""
    from . import craniometry as cm, reference_frame as rf
    observed, ok = None, None
    reason = ''
    kind = rule['kind']
    if kind == 'marker_count':
        active = {row['label'] for row in report['landmarks'] if _number(row['weight']) > 0}
        present = sorted(active.intersection(rule['labels']))
        observed = dict(count=len(present), labels=present, region=rule['region'])
        ok = len(present) >= rule['minimum']
        reason = 'Positive-base-weight fitted labels; not independent constraints or anatomical coverage'
    else:
        doc = report['marker_metadata'].get('craniometry')
        if not isinstance(doc, dict):
            reason = 'Craniometry observations absent from saved report'
        elif kind == 'bone_range':
            rows = cm.measure(doc)
            row = next(r for r in rows if r['measurement'] == rule['measurement'])
            if (row['status'] != 'observed' or row['definition_reviewed'] is not True
                    or row['sources_current'] is not True or row['bone_mm'] is None):
                reason = 'Both endpoints require observed, reviewed, source-current bone in the snapshot'
            else:
                observed = row['bone_mm']
                ok = rule['minimum_mm'] <= observed <= rule['maximum_mm']
                reason = 'Absolute world-mm chord versus supplied inclusive range; not a diagnosis of scale error'
        else:
            frame = doc.get('reference_frame')
            if not isinstance(frame, dict) or frame.get('status') != 'current':
                reason = 'Current reference-frame snapshot absent'
            else:
                try:
                    signature = rf.input_signature(doc, frame['configuration'])
                except ValueError as exc:
                    reason = 'Reference frame cannot be reassessed: '+str(exc)
                else:
                    if signature != frame.get('input_signature'):
                        reason = 'Reference-frame observations differ from stored signature'
                    else:
                        points = {code: np.asarray(row['xyz_mm']) for code, row in cm.validate_document(doc)[0].items()}
                        geometry = rf.geometry_frame(points, frame['configuration'])
                        observed = geometry['midsagittal']['residual_rms_mm']
                        ok = observed <= rule['maximum_mm']
                        reason = 'Recomputed plane residual; not anatomical confidence or an accuracy estimate'
    return _row(rule['id'], 'not_assessed' if ok is None else 'pass' if ok else rule['on_fail'],
                reason, observed=observed, provenance='operator_configured', rule=copy.deepcopy(rule))


def assess(report, policy, override_reason=None):
    """Return deterministic findings and gate; override never erases a failed check."""
    validate_report(report)
    policy = validate_policy(policy)
    if override_reason is not None:
        _text(override_reason)
    for row in report['landmarks']:
        _number(row.get('weight'))
        point = np.asarray(row.get('target_mm'), dtype=float)
        if point.shape != (3,) or not np.isfinite(point).all():
            raise ValueError('Malformed target coordinates')
    checks = [_row('builtin:convergence', 'pass' if report['solver']['converged'] else 'block',
                   'Baseline solver convergence only' if report['config'].get('profile_constraint') else 'Statistical solver convergence',
                   observed=report['solver']['converged'])]
    transform = report['transform']
    rotation = np.asarray(transform.get('rotation'), dtype=float)
    translation = np.asarray(transform.get('translation_mm'), dtype=float)
    scale = transform.get('scale')
    _number(scale, positive=True)
    if rotation.shape != (3, 3) or translation.shape != (3,) or not np.isfinite(rotation).all() or not np.isfinite(translation).all():
        raise ValueError('Malformed finite similarity transform')
    proper = bool(np.linalg.det(rotation) > 0 and np.allclose(rotation.T@rotation, np.eye(3), rtol=0,
                                                            atol=64*np.finfo(float).eps))
    checks.append(_row('builtin:proper_transform', 'pass' if proper else 'block',
        'Proper orthonormal rotation required; 64 float64 eps is a numerical tolerance', observed=dict(scale=scale)))
    if proper:
        from .checks import check_side_swap
        from .landmarks import side_of
        targets = [(r['label'], r['vertex'], np.asarray(r['target_mm'], dtype=float), r['weight']) for r in report['landmarks']]
        if any(p.shape != (3,) or not np.isfinite(p).all() for _, _, p, _ in targets):
            raise ValueError('Malformed target coordinates')
        lateral = [label for label, _, _, _ in targets if side_of(label)]
        # Normalize before the legacy side predicate to avoid scale**2 underflow.
        with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
            normalized = [(label, vertex, (p-translation)/scale, weight) for label, vertex, p, weight in targets]
        if any(not np.isfinite(p).all() for _, _, p, _ in normalized):
            raise ValueError('Target inverse transform overflow')
        swapped = check_side_swap(normalized, rotation, np.zeros(3), 1.)
        checks.append(_row('builtin:side_labels', 'block' if swapped else 'pass' if lateral else 'not_assessed',
            'Existing model-space 5 mm heuristic; cannot certify all L/R labels',
            observed=dict(suspect=swapped, evaluated=lateral, tolerance_model_mm=5.0), provenance='legacy_hardcoded'))
    else:
        checks.append(_row('builtin:side_labels', 'not_assessed', 'Invalid rotation; side heuristic not applied'))
    checks.append(_geometry(report))
    if not policy['reviewed'] or not policy['rules']:
        checks.append(_row('builtin:policy', 'not_assessed', 'Reviewed criteria not configured; no anatomical ranges guessed'))
    else:
        for rule in policy['rules']:
            try:
                checks.append(_configured(report, rule))
            except (KeyError, TypeError, OverflowError, np.linalg.LinAlgError) as exc:
                raise ValueError('Malformed evidence for rule '+rule['id']+': '+str(exc)) from exc
    for kind in ('bone_range', 'marker_count', 'midline_rms'):
        if not policy['reviewed'] or not any(r['kind'] == kind for r in policy['rules']):
            checks.append(_row('builtin:missing_'+kind, 'not_assessed', kind+' criteria not configured'))
    states = {row['status'] for row in checks}
    status = next(s for s in ('block', 'not_assessed', 'warn', 'pass') if s in states)
    held = status in ('block', 'not_assessed')
    return dict(schema_version=1, status=status, banner='CHECK POLICY: '+status.upper(), checks=checks,
                policy=policy, interpretation=INTERPRETATION,
                gate=dict(status='overridden' if held and override_reason is not None else 'held' if held else 'criteria_met',
                          proceed=not held or override_reason is not None, override_reason=override_reason),
                scientific_export_authorization='not_assessed')


def main(argv=None):
    """Write a new assessment; exit 3 for held checks, 2 for invalid input, 0 otherwise."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    template = sub.add_parser('template')
    template.add_argument('--output', required=True)
    evaluate = sub.add_parser('assess')
    evaluate.add_argument('--report', required=True)
    evaluate.add_argument('--policy', required=True)
    evaluate.add_argument('--output', required=True)
    evaluate.add_argument('--allow-blocked', help='Explicit recorded reason; does not confer scientific approval')
    args = parser.parse_args(argv)
    try:
        output = Path(args.output)
        sources = {} if args.command == 'template' else {Path(p): Path(p).read_bytes() for p in (args.report, args.policy)}
        def unchanged(_=None):
            if output.exists() or output.is_symlink():
                raise ValueError('Output exists; choose a new destination')
            if any(p.read_bytes() != raw for p, raw in sources.items()):
                raise ValueError('Input changed during check assessment')
        unchanged()
        result = empty_policy() if args.command == 'template' else assess(
            _json(sources[Path(args.report)].decode('utf-8-sig')), _json(sources[Path(args.policy)].decode('utf-8-sig')),
            args.allow_blocked)
        if args.command == 'assess':
            result['implementation_sha256'] = _digest(Path(__file__).read_bytes())
            result['source_hashes'] = dict(report_sha256=_digest(sources[Path(args.report)]),
                                         policy_sha256=_digest(sources[Path(args.policy)]))
        from .export import atomic_text
        with atomic_text(output, validate=unchanged) as stream:
            stream.write(canonical_bytes(result).decode('utf-8'))
        return 3 if args.command == 'assess' and not result['gate']['proceed'] else 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, np.linalg.LinAlgError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    raise SystemExit(main())

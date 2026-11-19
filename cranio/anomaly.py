"""Case-bound descriptive bone screens. No diagnostic thresholds or diagnoses."""
import math
from pathlib import Path

import numpy as np

from . import craniometry as cm
from .validation import has_documented_tissue_source
from .tissue import _json

# The order of the points is part of the v1 score definition.
SCORES = {
    'axis_obliquity': (('eu_R', 'eu_L', 'g', 'op'), 'absolute_cosine',
                        'Obliquity of transverse and longitudinal vault chords; placement also affects it.'),
    'vault_breadth_length': (('eu_R', 'eu_L', 'g', 'op'), 'ratio',
                             'Breadth divided by length; does not distinguish compression, modification or variation.'),
    'vault_side_difference': (('eu_R', 'eu_L', 'b'), 'mm',
                             'Difference between right and left bregma-to-eurion distances; not a suture diagnosis.'),
    'jaw_transverse_offset': (('eu_R', 'eu_L', 'me'), 'mm',
                              'Absolute menton offset along the eurion chord from its midpoint; depends on articulation.'),
    'anterior_mandible_chord': (('id', 'me'), 'mm',
                                'Infradentale-to-menton chord; does not establish alveolar resorption or tooth loss.'),
    'absent_reviewed_sites': ((), 'fraction',
                             'Fraction marked absent among explicitly inspected tooth sites; timing and cause unknown.'),
}


def documented(value):
    return has_documented_tissue_source(value) and value.strip().casefold() not in {
        'unknown', 'todo', 'none', 'null', 'todo(verify-source)', '[de completat]'}


def template(case_id=None):
    """Fill the case ID before use. No clinical cutoffs or factors are provided."""
    return dict(schema='gnm.anomaly.v1', case_id=case_id, rules={})


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def load_policy(path):
    return _json(Path(path).read_text(encoding='utf-8-sig'))


def _validate(policy, case_id, labels):
    if (not isinstance(policy, dict) or set(policy) != set(template())
            or policy['schema'] != 'gnm.anomaly.v1' or not documented(case_id)
            or policy['case_id'] != case_id or not isinstance(policy['rules'], dict)):
        raise ValueError('Provide a gnm.anomaly.v1 policy bound to this v3 marker case')
    for key, rule in policy['rules'].items():
        if key not in SCORES or not isinstance(rule, dict) or set(rule) != {
                'units', 'low', 'high', 'source', 'action', 'labels', 'factor'}:
            raise ValueError(f'{key}: unknown score or malformed rule')
        low, high = rule['low'], rule['high']
        if (rule['units'] != SCORES[key][1] or not documented(rule['source'])
                or (low is None and high is None) or any(not _number(v) for v in (low, high) if v is not None)
                or (low is not None and high is not None and low > high)):
            raise ValueError(f'{key}: supply matching units, sourced finite bounds in order')
        action, sites, factor = rule['action'], rule['labels'], rule['factor']
        if (action not in ('flag', 'reduce', 'exclude') or not isinstance(sites, list)
                or any(not isinstance(s, str) or s not in labels for s in sites)
                or len(sites) != len(set(sites)) or bool(sites) != (action != 'flag')
                or (action == 'reduce' and (not _number(factor) or not 0 < factor < 1))
                or (action != 'reduce' and factor is not None)):
            raise ValueError(f'{key}: invalid action, affected CSV labels or reduction factor')


def _dentition(row, sources):
    if row is None:
        return None, 'No reviewed tooth-site inventory'
    fields = {'source_id', 'source_geometry_sha256', 'observation_source', 'sites'}
    if not isinstance(row, dict) or set(row) != fields or not documented(row['observation_source']):
        raise ValueError('Invalid dentition_observation; document the observation source')
    sites = row['sites']
    if not isinstance(sites, dict) or any(not documented(k) or v not in ('present', 'absent', 'unknown') for k,v in sites.items()):
        raise ValueError('Dentition sites require distinct documented IDs and present/absent/unknown')
    if not isinstance(row['source_id'], str) or not sources.get(row['source_id']) or sources[row['source_id']] != row['source_geometry_sha256']:
        return None, 'Tooth-site source missing or stale'
    known = [v for v in sites.values() if v != 'unknown']
    if not known:
        return None, 'No tooth site with a reviewed presence/absence observation'
    return known.count('absent') / len(known), f'{known.count("absent")} absent / {len(known)} inspected with known status'


def _geometry(key, p):
    with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        a = p[0] - p[1]
        norm = np.linalg.norm
        width = norm(a)
        if not 0 < width < np.inf:
            return None
        if key in ('vault_breadth_length', 'axis_obliquity'):
            axis = p[2] - p[3]
            length = norm(axis)
            if not 0 < length < np.inf:
                return None
            value = width / length if key == 'vault_breadth_length' else np.clip(abs((a/width) @ (axis/length)), 0, 1)
        elif key == 'anterior_mandible_chord':
            value = width
        elif key == 'vault_side_difference':
            spans = [norm(p[2] - x) for x in p[:2]]
            if min(spans) == 0:
                return None
            value = abs(spans[0] - spans[1])
        else:
            value = abs(((p[2]-p[1]) - a/2) @ (a/width))
        return float(value) if np.isfinite(value) else None


def screen(policy, metadata, document, targets, known_labels):
    """Return new fit targets, exclusions and a serializable audit without mutating inputs."""
    case = metadata.get('case_id')
    _validate(policy, case, set(known_labels))
    if metadata.get('version') != 3 or (document is not None and document.get('case_id') != case):
        raise ValueError('Anomaly screening requires a v3 case and matching craniometry case ID')
    # An old auxiliary bone manifest is not evidence of current geometry.
    doc = dict(document or cm.empty_document(case), bone_sources=metadata.get('bone_sources', []))
    points, _ = cm.validate_document(doc)
    cm.measure(doc)  # validate source IDs, geometry digests and duplicates
    sources = {s['id']: s['geometry_sha256'] for s in doc['bone_sources']}
    case_meta = metadata.get('case_metadata', {})
    if not isinstance(case_meta, dict):
        raise ValueError('Invalid case metadata object')
    inventory = case_meta.get('dentition_observation')
    if inventory is not None and case_meta.get('case_id') != case:
        raise ValueError('Dentition observation must be bound to the same marker case')
    results, decisions = {}, {}
    for key, (codes, units, explanation) in SCORES.items():
        reason = ''
        value = None
        if key == 'absent_reviewed_sites':
            value, reason = _dentition(inventory, sources)
        else:
            for code in codes:
                row = points.get(code, {})
                if not (row.get('status') == 'observed' and row.get('definition_reviewed') is True
                        and sources.get(row.get('source_id')) and sources[row['source_id']] == row.get('source_geometry_sha256')):
                    reason = f'{code}: missing, not observed, unreviewed or stale'
                    break
            if not reason and key == 'jaw_transverse_offset' and metadata.get('mandible_articulation_reviewed') is not True:
                reason = 'Cranium-to-mandible articulation unreviewed'
            if not reason:
                value = _geometry(key, [np.asarray(points[c]['xyz_mm']) for c in codes])
                if value is None:
                    reason = 'Degenerate or nonfinite geometry'
        rule = policy['rules'].get(key)
        flag = None
        status = 'not_assessed' if value is None else 'no_thresholds_configured'
        if value is not None and rule:
            flag = ((rule['low'] is not None and value < rule['low'])
                    or (rule['high'] is not None and value > rule['high']))
            status = 'flagged' if flag else 'within_configured_bounds'
            if flag:
                for label in rule['labels']:
                    decisions.setdefault(label, []).append(key)
        results[key] = dict(points=list(codes), units=units, score=value, flag=flag, status=status,
                            explanation=explanation, evidence_note=reason, rule=rule)
    kept, skipped, changes = [], [], {}
    for t in targets:
        triggered = decisions.get(t.label, [])
        if not triggered:
            kept.append(t)
            continue
        rules = [policy['rules'][k] for k in triggered]
        exclude = any(r['action'] == 'exclude' for r in rules)
        weight = None if exclude else t.weight * min(r['factor'] for r in rules)
        if exclude:
            skipped.append((t.label, 'anomaly policy: '+', '.join(triggered)))
        elif not 0 < weight <= t.weight:
            raise ValueError(f'{t.label}: anomaly reduction produced an invalid fit weight')
        else:
            kept.append(t._replace(weight=weight))
        changes[t.label] = dict(triggered=triggered, before=t.weight, after=weight)
    return kept, skipped, dict(schema=policy['schema'], case_id=case, scores=results,
                               changes=changes, interpretation='Descriptive screening only; no diagnosis or retro-deformation.')


def report_text(audit):
    lines = ['Cranial anomaly screen: '+audit['interpretation']]
    if all(row['rule'] is None for row in audit['scores'].values()):
        lines.append('No thresholds configured.')
    for name, row in audit['scores'].items():
        score = 'unavailable' if row['score'] is None else f"{row['score']:.6g} {row['units']}"
        lines.append(f"{name}: {score}; {row['status']}. {row['explanation']} {row['evidence_note']}".rstrip())
        if row['rule']:
            rule = row['rule']
            lines.append(f"  Bounds: [{rule['low']}, {rule['high']}]; action: {rule['action']}; source: {rule['source']}")
    for label, row in audit['changes'].items():
        after = 'excluded' if row['after'] is None else str(row['after'])
        lines.append(f"{label}: weight {row['before']} -> {after} ({', '.join(row['triggered'])})")
    return '\n'.join(lines)

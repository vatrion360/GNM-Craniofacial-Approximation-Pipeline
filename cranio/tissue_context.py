"""Descriptive tissue estimator/posture audit; never changes targets or weights."""
import json

UNKNOWN_POSTURES = {'', 'unknown', 'unspecified', 'not reported', 'not recorded', 'unavailable'}


def normalized_posture(value):
    """Compare labels conservatively: whitespace/case only, no anatomical synonyms."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('Acquisition posture must be a string or null')
    text = ' '.join(value.split()).casefold()
    return None if text in UNKNOWN_POSTURES else text


def with_case_metadata(metadata, path):
    """Keep the existing external case-document precedence, shared by CLI/compare."""
    if not path:
        return metadata
    with open(path, encoding='utf-8') as stream:
        case = json.load(stream)
    if not isinstance(case, dict):
        raise ValueError('Case metadata must be a JSON object')
    return dict(metadata, case_metadata=case)


def case_posture(metadata, explicit=None):
    """Resolve explicit declarations without inferring posture from CT modality.

    Different nonempty labels conflict instead of silently overriding each other.
    All raw declarations are retained, including unknown labels.
    """
    case = metadata.get('case_metadata')
    if case is None:
        case = {}
    if not isinstance(case, dict):
        raise ValueError('Case metadata must be a JSON object')
    declarations = dict(cli=explicit, csv=metadata.get('acquisition_posture'),
                        case_metadata=case.get('acquisition_posture'))
    known = [(key, value, normalized_posture(value)) for key,value in declarations.items()]
    known = [(key,value,norm) for key,value,norm in known if norm is not None]
    if len({row[2] for row in known}) > 1:
        raise ValueError('Conflicting acquisition posture declarations; reconcile CLI/CSV/case metadata')
    return dict(value=known[0][1] if known else None, normalized=known[0][2] if known else None,
                declarations=declarations)


def describe_context(table, metadata, replaced_labels=(), explicit_posture=None):
    """Audit source estimators separately from which depths were actually applied."""
    data = table.document
    case = case_posture(metadata, explicit_posture)
    reference = normalized_posture(data['posture'])
    status = ('unknown' if reference is None or case['normalized'] is None else
              'matching_labels' if reference == case['normalized'] else 'different_labels')
    warnings = []
    if status == 'unknown':
        warnings.append('Tissue posture comparison unavailable: case and/or table posture is unknown; no posture inferred or correction applied.')
    elif status == 'different_labels':
        warnings.append(f"Tissue posture mismatch: case label {case['value']!r}, table label {data['posture']!r}. Review source applicability; no posture correction applied.")
    selected = set(replaced_labels)
    rows = {scope: {label: dict(estimator=row['estimator'], central_mm=row['central_mm'],
              depth_applied=scope == 'landmarks' and label in selected,
              provenance=row['provenance']) for label,row in data[scope].items()}
            for scope in ('landmarks','regions')}
    return dict(table_id=data['id'], table_sha256=table.sha256, table_posture=data['posture'],
        case_posture=case, posture_comparison=status, estimators=rows, warnings=warnings,
        interpretation='Posture label comparison only, not biological equivalence or a calibrated correction. '
            'Estimator labels and central values are supplied table data. No shorth/75-shormax is derived from means; '
            'unapplied rows are reference metadata, not case measurements.')


def context_text(record, compact=False):
    """Render explicit unknowns and per-row estimator/application status in TXT."""
    lines = [f"Tissue posture: table={record['table_posture']!r}; case={record['case_posture']['value']!r}; comparison={record['posture_comparison']}. No posture correction."]
    if compact:
        from collections import Counter
        counts = Counter(row['estimator'] or 'unknown' for row in record['estimators']['landmarks'].values() if row['depth_applied'])
        lines.append('Applied landmark estimators: '+(', '.join(f'{k}: {v}' for k,v in sorted(counts.items())) or 'none'))
        lines.extend(record['warnings'])
        return '\n'.join(lines)
    for scope, rows in record['estimators'].items():
        for label,row in rows.items():
            lines.append(f"Tissue estimator {scope}.{label}: {row['estimator'] or 'unknown'}; "
                         f"central_mm={row['central_mm']}; depth={'applied' if row['depth_applied'] else 'reference only'}; "
                         f"provenance={row['provenance']}.")
    lines.append('Central values used as supplied; no estimator is calculated from means. Source validation remains separate.')
    return '\n'.join(lines)

"""Operator-declared age intervals: a tissue-table audit, never a fitting rule.

Bounds imply neither a distribution nor a confidence level. Operator review is
not independent validation. All unknown scientific values stay null.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from .tissue import _json, load_table

KEY = 'age_at_death_estimate'
LIMITATION = ('Soft-tissue ageing is not modelled. No age parameter is inferred for GNM. '
              'Age-range overlap alone does not establish table applicability or accuracy; '
              'no table is selected and no target or fit is changed by this audit.')


def empty_estimate() -> dict:
    """Template with no invented age, method or source."""
    return dict(schema_version=1, range_years=None, method=None, source=None, reviewed=False)


def validate_estimate(value: dict | None) -> dict | None:
    """Validate a closed versioned declaration and return an independent copy."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != set(empty_estimate()):
        raise ValueError(f'{KEY}: expected fields {sorted(empty_estimate())}')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError(f'{KEY}: schema_version must be 1')
    if type(value['reviewed']) is not bool:
        raise ValueError(f'{KEY}: reviewed must be boolean')
    bounds = value['range_years']
    if bounds is not None:
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError(f'{KEY}: range_years must contain two bounds or be null')
        for number in bounds:
            try:
                valid = type(number) in (int, float) and math.isfinite(number) and number >= 0
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError(f'{KEY}: bounds must be finite nonnegative numbers')
        if bounds[0] > bounds[1]:
            raise ValueError(f'{KEY}: lower bound exceeds upper bound')
    for key in ('method', 'source'):
        if value[key] is not None and not isinstance(value[key], str):
            raise ValueError(f'{KEY}: {key} must be text or null')
        text = ' '.join((value[key] or '').split()).casefold()
        if value['reviewed'] and (text in {'', 'unknown', 'unspecified', 'not reported',
                                         'not recorded', 'unavailable', 'null', 'none', 'n/a'}
                                  or text.startswith('todo')):
            raise ValueError(f'{KEY}: reviewed estimate requires documented {key}')
    if value['reviewed'] and bounds is None:
        raise ValueError(f'{KEY}: reviewed estimate requires range_years')
    return copy.deepcopy(value)


def _case(metadata: dict) -> dict:
    case = metadata.get('case_metadata')
    if case is None:
        return {}
    if not isinstance(case, dict):
        raise ValueError('Case metadata must be a JSON object')
    return case


def is_declared(metadata: dict) -> bool:
    """Distinguish an explicitly unknown age from the unchanged legacy path."""
    return KEY in metadata or KEY in _case(metadata)


def resolve(metadata: dict) -> dict:
    """Reject conflicting non-null declarations, without averaging or overriding."""
    declarations = dict(csv=validate_estimate(metadata.get(KEY)),
                        case_metadata=validate_estimate(_case(metadata).get(KEY)))
    supplied = [v for v in declarations.values() if v is not None]
    if supplied and any(v != supplied[0] for v in supplied[1:]):
        raise ValueError('Conflicting age_at_death_estimate declarations; reconcile CSV/case metadata')
    return dict(estimate=copy.deepcopy(supplied[0]) if supplied else None, declarations=declarations)


def describe_age(metadata: dict, table=None) -> dict:
    """Compare inclusive reported intervals without selecting or applying a table."""
    case = resolve(metadata)
    estimate = case['estimate']
    bounds = estimate['range_years'] if estimate else None
    reference = table.document['age_range_years'] if table else None
    intersection = None
    if bounds is None:
        status = 'no_estimate'
    elif not estimate['reviewed']:
        status = 'unreviewed_estimate'
    elif table is None:
        status = 'no_table_selected'
    elif reference is None:
        status = 'table_age_unknown'
    else:
        lo, hi = max(bounds[0], reference[0]), min(bounds[1], reference[1])
        intersection = [lo, hi] if lo <= hi else None
        status = ('outside_reported_range' if intersection is None else
                  'within_reported_range' if reference[0] <= bounds[0] and bounds[1] <= reference[1]
                  else 'partial_overlap')
    warnings = []
    if status != 'within_reported_range':
        warnings.append(f'Age assessment: {status}; review case estimate and tissue-table source. No age correction applied.')
    warnings.append(LIMITATION)
    return dict(schema_version=1, case=case, table=table.record() if table else None,
                source_file=copy.deepcopy(metadata.get('age_estimate_source_file')),
                table_range_years=copy.deepcopy(reference), comparison=status,
                intersection_years=intersection, warnings=warnings, interpretation=LIMITATION)


def age_text(record: dict) -> str:
    """Render supplied bounds, method and source, including explicit unknowns."""
    age = record['case']['estimate'] or empty_estimate()
    return (f"Age at death: range_years={age['range_years']}; reviewed={age['reviewed']}; "
            f"method={age['method']!r}; source={age['source']!r}.\n"
            f"Tissue age range_years={record['table_range_years']}; comparison={record['comparison']}.\n"
            + LIMITATION)


def load_case_age(path: str | Path) -> dict:
    """Hash the same bytes that are parsed. Other case fields are not imported.

    Blender calls this only on Apply/export, never during redraw or live fitting.
    """
    raw = Path(path).read_bytes()
    document = _json(raw.decode('utf-8-sig'))
    if not isinstance(document, dict) or KEY not in document:
        raise ValueError(f'Age case document must contain {KEY}')
    return {KEY: validate_estimate(document[KEY]),
            'age_estimate_source_file': dict(name=Path(path).name, sha256=hashlib.sha256(raw).hexdigest())}


def main(argv=None) -> int:
    """Create an unknown template or audit explicitly listed source tables."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    template = sub.add_parser('template')
    template.add_argument('--output', required=True)
    compare = sub.add_parser('compare')
    compare.add_argument('--case-metadata', required=True)
    compare.add_argument('--tables', nargs='+', required=True, help='Bundled IDs or JSON paths')
    compare.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        output = Path(args.output)
        if output.exists() or output.is_symlink():
            raise ValueError('Output exists; choose a new path')
        if args.command == 'template':
            result = {KEY: empty_estimate()}
        else:
            metadata = load_case_age(args.case_metadata)
            tables = [load_table(source) for source in args.tables]
            result = dict(schema_version=1, case_metadata=metadata,
                          comparisons=[describe_age(metadata, table) for table in tables],
                          interpretation=LIMITATION)
        from .export import atomic_text
        with atomic_text(output) as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
            stream.write('\n')
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

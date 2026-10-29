"""Versioned tissue-depth data exchange; no fitting or automatic case updates.

Structural validation is not source verification. Missing scientific information
stays None and is returned as diagnostics, never imputed. Standard library only
until an atomic writer or CLI output-path check is invoked (shared NumPy helpers).
"""
import argparse
import copy
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re

DATA_DIR = Path(__file__).resolve().parent / 'data' / 'tissue'
CSV_MAGIC = '# gnm-tissue-table-csv v1'
ROW_DEFAULTS = dict(estimator=None, sd_mm=None, p10_mm=None, p90_mm=None,
                    n=None, measurement_direction=None, direction_notes=None, notes='')
CSV_FIELDS = ['scope', 'label', 'central_mm', *ROW_DEFAULTS, 'provenance']
NUMERIC_FIELDS = {'central_mm', 'sd_mm', 'p10_mm', 'p90_mm'}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _json(text):
    def reject(value):
        raise ValueError(f'Non-finite JSON number: {value}')
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=reject)


def _validate(value, node, root, path='table'):
    """Evaluate only the documented subset used by our bundled JSON Schema.

    No remote references, dynamic code or general JSON Schema implementation.
    Unknown keywords fail closed so schema evolution requires matching code.
    """
    supported = {'$schema', '$defs', '$ref', 'title', 'description', 'type', 'const',
                 'enum', 'minimum', 'minLength', 'pattern', 'minItems', 'maxItems',
                 'items', 'properties', 'propertyNames', 'required', 'additionalProperties'}
    if set(node) - supported:
        raise ValueError(f'{path}: unsupported schema keywords {sorted(set(node)-supported)}')
    if '$ref' in node:
        reference = node['$ref']
        if not reference.startswith('#/$defs/') or reference[8:] not in root.get('$defs', {}):
            raise ValueError(f'{path}: unsupported schema reference')
        _validate(value, root['$defs'][reference[8:]], root, path)
    types = node.get('type', [])
    if isinstance(types, str):
        types = [types]
    matches = {'object': type(value) is dict, 'array': type(value) is list,
               'string': type(value) is str, 'null': value is None,
               'number': type(value) in (int, float), 'integer': type(value) is int}
    if types and not any(matches.get(kind, False) for kind in types):
        raise ValueError(f'{path}: expected {types}')
    if 'const' in node and value != node['const']:
        raise ValueError(f'{path}: expected {node["const"]!r}')
    if 'enum' in node and value not in node['enum']:
        raise ValueError(f'{path}: unsupported value {value!r}')
    if value is None:
        return
    if type(value) in (int, float):
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite or value < node.get('minimum', -math.inf):
            raise ValueError(f'{path}: non-finite or below minimum')
    if isinstance(value, str):
        if len(value) < node.get('minLength', 0) or ('pattern' in node and not re.fullmatch(node['pattern'], value, flags=re.DOTALL)):
            raise ValueError(f'{path}: empty or invalid text')
    if isinstance(value, list):
        if not node.get('minItems', 0) <= len(value) <= node.get('maxItems', math.inf):
            raise ValueError(f'{path}: invalid array length')
        for i, item in enumerate(value):
            _validate(item, node.get('items', {}), root, f'{path}[{i}]')
    if isinstance(value, dict):
        missing = set(node.get('required', [])) - set(value)
        if missing:
            raise ValueError(f'{path}: missing fields {sorted(missing)}')
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError(f'{path}: object keys must be strings')
            _validate(key, node.get('propertyNames', {}), root, path+'.key')
            child = node.get('properties', {}).get(key, node.get('additionalProperties', {}))
            if child is False:
                raise ValueError(f'{path}: unknown field {key}')
            _validate(item, child, root, f'{path}.{key}')


def empty_table(identifier: str, revision: str = '1') -> dict:
    """Template with no numerical tissue values or inferred metadata."""
    return dict(schema_version=1, id=identifier, revision=revision, units='mm',
                provenance='user_supplied', citation=None, doi=None, measurement_method=None,
                posture=None, sex=None, age_range_years=None, ancestry_label=None, n=None,
                notes='TODO(verify-source): complete metadata and source-verified rows.',
                landmarks={}, regions={})


def validate_table(document: dict) -> tuple[dict, tuple[str, ...]]:
    """Return a normalized copy and warnings; reject invalid values, not unknowns.

    SD absence/zero never becomes a weighting rule. Estimator/direction metadata
    is descriptive here; this module does not apply depths or estimate shorth.
    """
    schema = _json((DATA_DIR / 'schema.json').read_text(encoding='utf-8'))
    _validate(document, schema, schema)
    result = copy.deepcopy(document)
    warnings = []
    for key in ('citation', 'doi', 'measurement_method', 'posture', 'sex', 'age_range_years', 'ancestry_label', 'n'):
        if result[key] is None:
            warnings.append(f'TODO(verify-source): table {key} unknown')
    age = result['age_range_years']
    if age is not None and age[0] > age[1]:
        raise ValueError('age_range_years: lower bound exceeds upper bound')
    for scope in ('landmarks', 'regions'):
        for label, row in result[scope].items():
            for key, default in ROW_DEFAULTS.items():
                row.setdefault(key, default)
            row.setdefault('provenance', result['provenance'])
            lo, hi = row['p10_mm'], row['p90_mm']
            if lo is not None and hi is not None and lo > hi:
                raise ValueError(f'{scope}.{label}: P10 exceeds P90')
            missing = [k for k in ('central_mm', 'sd_mm', 'estimator', 'measurement_direction') if row[k] is None]
            if missing:
                warnings.append(f'TODO(verify-source): {scope}.{label} unknown: {", ".join(missing)}')
            if row['sd_mm'] == 0:
                warnings.append(f'{scope}.{label}: SD is zero; inverse-variance weighting is undefined')
            if row['measurement_direction'] == 'other' and row['direction_notes'] is None:
                warnings.append(f'TODO(verify-source): {scope}.{label} direction explanation missing')
    if not result['landmarks'] and not result['regions']:
        warnings.append('No tissue measurements configured')
    return result, tuple(warnings)


@dataclass(frozen=True)
class TissueTable:
    """Loaded normalized data, diagnostics and SHA-256 of the exact source bytes.

    document returns a detached copy, so editing it cannot alter this record.
    Use write_table/load_table to record a new revision.
    """
    _document: dict
    warnings: tuple[str, ...]
    sha256: str

    @property
    def document(self) -> dict:
        return copy.deepcopy(self._document)

    def record(self) -> dict:
        return {**{key: self._document[key] for key in ('id', 'revision', 'citation', 'doi', 'provenance')},
                'sha256': self.sha256, 'warnings': list(self.warnings)}


def table_path(source: str | Path) -> Path:
    """Bare IDs refer to bundled data; explicit Paths always refer to local files."""
    if isinstance(source, str) and re.fullmatch('[a-z][a-z0-9_]*', source):
        return DATA_DIR / (source + '.json')
    return Path(source).expanduser()


def load_table(source: str | Path) -> TissueTable:
    raw = table_path(source).read_bytes()
    document, warnings = validate_table(_json(raw.decode('utf-8-sig')))
    return TissueTable(document, warnings, hashlib.sha256(raw).hexdigest())


def write_table(path: str | Path, document: dict) -> None:
    """Validate before atomic replacement; callers choose overwrite policy."""
    from .export import atomic_text
    normalized, _ = validate_table(document)
    with atomic_text(path, validate=lambda p: load_table(p)) as stream:
        json.dump(normalized, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def export_csv(path: str | Path, document: dict) -> None:
    """Lossless table CSV, distinct from marker coordinates CSV v3."""
    from .export import atomic_text
    normalized, _ = validate_table(document)
    metadata = {k: v for k, v in normalized.items() if k not in ('landmarks', 'regions')}
    with atomic_text(path, validate=lambda p: import_csv(p)) as stream:
        stream.write(CSV_MAGIC+'\n# '+json.dumps(metadata, ensure_ascii=False, allow_nan=False)+'\n')
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator='\n')
        writer.writeheader()
        for scope in ('landmarks', 'regions'):
            for label, row in normalized[scope].items():
                writer.writerow(dict(scope=scope, label=label, **row))


def import_csv(path: str | Path) -> dict:
    """Parse UTF-8 table CSV without silently accepting duplicates or lost cells."""
    with open(path, encoding='utf-8-sig', newline='') as stream:
        if stream.readline().rstrip('\r\n') != CSV_MAGIC:
            raise ValueError('Expected tissue-table CSV v1, not a marker CSV')
        metadata_line = stream.readline()
        if not metadata_line.startswith('# '):
            raise ValueError('Missing JSON metadata line')
        document = _json(metadata_line[2:])
        if not isinstance(document, dict) or {'landmarks', 'regions'} & set(document):
            raise ValueError('Invalid table metadata')
        document.update(landmarks={}, regions={})
        reader = csv.DictReader(stream, strict=True)
        try:
            fields = reader.fieldnames or []
        except csv.Error as exc:
            raise ValueError(f'Malformed tissue CSV header: {exc}') from exc
        if (len(set(fields)) != len(fields) or set(fields)-set(CSV_FIELDS)
                or not {'scope', 'label', 'central_mm'} <= set(fields)):
            raise ValueError('Invalid/duplicate CSV columns')
        try:
            for raw in reader:
                if None in raw or any(value is None for value in raw.values()):
                    raise ValueError(f'CSV line {reader.line_num}: wrong cell count')
                scope, label = raw.pop('scope'), raw.pop('label')
                if scope not in ('landmarks', 'regions') or not label.strip():
                    raise ValueError('Invalid scope/label')
                if label in document[scope]:
                    raise ValueError(f'Duplicate {scope} label: {label}')
                row = {}
                for key, value in raw.items():
                    if key in NUMERIC_FIELDS:
                        row[key] = float(value) if value else None
                    elif key == 'n':
                        row[key] = int(value) if value else None
                    elif key == 'provenance' and not value:
                        continue
                    else:
                        row[key] = value if value or key == 'notes' else None
                document[scope][label] = row
        except csv.Error as exc:
            raise ValueError(f'Malformed tissue CSV: {exc}') from exc
    return validate_table(document)[0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    inspect = sub.add_parser('inspect')
    inspect.add_argument('input')
    for command in ('template', 'import-csv', 'export-csv'):
        child = sub.add_parser(command)
        child.add_argument('--id' if command == 'template' else '--input', required=True)
        child.add_argument('--output', required=True)
        child.add_argument('--overwrite', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'inspect':
            table = load_table(args.input)
            print(json.dumps(dict(table=table.document, record=table.record()), ensure_ascii=False, indent=2))
            return 0
        from .validation import validate_outputs
        source = (table_path(args.input) if args.command == 'export-csv' else
                  Path(args.input) if args.command == 'import-csv' else None)
        validate_outputs([source], [args.output], args.overwrite)
        if args.command == 'template':
            document = empty_table(args.id)
        elif args.command == 'import-csv':
            document = import_csv(source)
        else:
            document = load_table(source).document
        (export_csv if args.command == 'export-csv' else write_table)(args.output, document)
        _, warnings = validate_table(document)
        print(json.dumps(dict(output=args.output, warnings=warnings), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, UnicodeError) as exc:
        print(f'Tissue table error: {exc}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

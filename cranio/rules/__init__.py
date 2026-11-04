"""Evidence metadata for anatomical rules; no prediction or fitting side effects.

A registry status records supplied review claims, not software certification or
case applicability. This A3.1 module does not import or execute implementation IDs.
"""
import copy
from dataclasses import dataclass
import hashlib
from pathlib import Path

from ..tissue import _json, _validate

DATA_DIR = Path(__file__).resolve().parent
REVIEW_STATES = {'source': ('not_verified', 'verified'),
                 'implementation': ('not_tested', 'tested'),
                 'external': ('not_validated', 'documented')}


def empty_registry(identifier: str = 'user_rules') -> dict:
    """Return an empty versioned catalogue; no anatomical values are supplied."""
    return dict(schema_version=1, id=identifier, revision='1', rules=[])


def empty_rule(identifier: str, feature: str) -> dict:
    """Template with unknown citation, error and applicability fields left null."""
    return dict(id=identifier, feature=feature, status='needs_verification',
        reference=dict(citation=None, doi=None, supplied_reference=None),
        tested_error=None, applicability=dict(sex=None, ancestry=None, dentition=None, notes=None),
        implementation_id=None,
        verification={key: dict(status=states[0], reviewer=None, evidence=None, scope=None)
                      for key, states in REVIEW_STATES.items()},
        notes='TODO(verify-source): supply the primary source and review the exact rule.')


def _documented(text: str | None) -> bool:
    return (isinstance(text, str) and bool(text.strip())
            and text.strip().casefold() not in {'unknown', 'unspecified', 'none', 'null', 'todo'}
            and 'todo(verify-source)' not in text.casefold())


def validate_registry(document: dict) -> tuple[dict, tuple[str, ...]]:
    """Validate schema and review consistency, returning detached data/diagnostics.

    Missing metadata warns without imputation. A declared validated status needs
    three separately documented review claims. This is not an external audit of
    those claims and does not enable a rule in the fitting pipeline.
    """
    schema = _json((DATA_DIR / 'schema.json').read_text(encoding='utf-8'))
    _validate(document, schema, schema, 'registry')
    result = copy.deepcopy(document)
    warnings = ['Registry metadata does not establish case applicability or authorize rule execution.']
    seen = set()
    for row in result['rules']:
        identifier = row['id']
        if identifier in seen:
            raise ValueError(f'Duplicate rule id: {identifier}')
        seen.add(identifier)
        missing = []
        for key in ('citation', 'doi'):
            if row['reference'][key] is None:
                missing.append('reference.'+key)
        for key, value in row['applicability'].items():
            if value is None:
                missing.append('applicability.'+key)
        error = row['tested_error']
        if error is None:
            missing.append('tested_error')
        else:
            missing.extend('tested_error.'+key for key, value in error.items() if value is None)
            if any(error[key] is not None for key in ('mean', 'sd', 'n')):
                for key in ('metric', 'units', 'cohort', 'source_locator'):
                    if not _documented(error[key]):
                        raise ValueError(f'{identifier}: numerical error requires {key}')
        if row['implementation_id'] is None:
            missing.append('implementation_id')
        completed = []
        for key, states in REVIEW_STATES.items():
            review = row['verification'][key]
            complete = review['status'] == states[1]
            completed.append(complete)
            if complete:
                for field in ('reviewer', 'evidence', 'scope'):
                    if not _documented(review[field]):
                        raise ValueError(f'{identifier}: {key} review requires documented {field}')
            else:
                missing.append('verification.'+key)
        if completed[0] and not _documented(row['reference']['citation']):
            raise ValueError(f'{identifier}: verified source requires a full citation')
        if completed[1] and row['implementation_id'] is None:
            raise ValueError(f'{identifier}: tested implementation requires implementation_id')
        if row['status'] == 'validated' and not all(completed):
            raise ValueError(f'{identifier}: validated requires source, implementation and external evidence')
        if missing:
            warnings.append(f'TODO(verify-source): {identifier} unknown/unreviewed: '+', '.join(missing))
        if row['status'] == 'unused':
            warnings.append(f'{identifier}: unused; feature remains unspecified by this rule')
    if not result['rules']:
        warnings.append('No anatomical rules configured')
    return result, tuple(warnings)


@dataclass(frozen=True)
class RuleRegistry:
    """Loaded catalogue, exact source-byte hash and schema hash for traceability."""
    _document: dict
    warnings: tuple[str, ...]
    sha256: str
    schema_sha256: str

    @property
    def document(self) -> dict:
        """Detached data; callers cannot mutate the loaded record through this view."""
        return copy.deepcopy(self._document)

    def record(self) -> dict:
        """Stable metadata summary; no timestamp, automatic applicability or score."""
        return dict(id=self._document['id'], revision=self._document['revision'],
                    sha256=self.sha256, schema_sha256=self.schema_sha256,
                    warnings=list(self.warnings), execution='not_implemented')


def load_registry(path: str | Path | None = None) -> RuleRegistry:
    """Read bundled metadata by default or one explicit local UTF-8 JSON file.

    Duplicate JSON keys and non-finite numbers are rejected. No network, dynamic
    imports, formulas, weights or thresholds are evaluated from registry content.
    """
    raw = (DATA_DIR / 'registry.json' if path is None else Path(path).expanduser()).read_bytes()
    document, warnings = validate_registry(_json(raw.decode('utf-8-sig')))
    return RuleRegistry(document, warnings, hashlib.sha256(raw).hexdigest(),
                        hashlib.sha256((DATA_DIR / 'schema.json').read_bytes()).hexdigest())

"""Eye-rule entry point; no orbital offsets or coordinate convention inferred."""
from collections.abc import Mapping
from .contracts import NotConfigured, RuleResult


def predict(observations: Mapping[str, object] | None, *, rule_id: str) -> RuleResult:
    """Refuse prediction until the source formula and reference tests are supplied.

    Observations are deliberately not read, validated or modified by this stub.
    """
    raise NotConfigured(rule_id, (
        'TODO(verify-source): exact eye/orbit rule and landmark definitions',
        'TODO(verify-source): coordinate convention, coefficients and units',
        'Source-confirmed implementation and hand-computed reference tests'))

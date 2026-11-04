"""Pronasale/projection entry point; no regression coefficients are guessed."""
from collections.abc import Mapping
from .contracts import NotConfigured, RuleResult


def predict(observations: Mapping[str, object] | None, *, rule_id: str) -> RuleResult:
    """Refuse prediction; no reading, validation or mutation of observations."""
    raise NotConfigured(rule_id, (
        'TODO(verify-source): complete nose reference and primary-source formula',
        'TODO(verify-source): coefficients, units and geometric conventions',
        'Source-confirmed implementation and hand-computed reference tests'))

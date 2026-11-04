"""Mouth-width entry point; no canine/pupil fraction is supplied implicitly."""
from collections.abc import Mapping
from .contracts import NotConfigured, RuleResult


def predict(observations: Mapping[str, object] | None, *, rule_id: str) -> RuleResult:
    """Refuse prediction; no reading, validation or mutation of observations."""
    raise NotConfigured(rule_id, (
        'TODO(verify-source): full mouth-width formula and dentition applicability',
        'TODO(verify-source): coefficients/fractions, units and landmark definitions',
        'Source-confirmed implementation and hand-computed reference tests'))

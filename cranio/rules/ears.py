"""Ear prediction is unused; an unspecified ear is not a negative finding."""
from collections.abc import Mapping
from .contracts import RuleResult


def predict(observations: Mapping[str, object] | None, *, rule_id: str) -> RuleResult:
    """Return no prediction/SD/applicability; never read or modify observations."""
    return RuleResult(None, None, None, (
        f'{rule_id}: ear prediction unused; feature unspecified',
        'No case applicability assessment or observation validation performed'))

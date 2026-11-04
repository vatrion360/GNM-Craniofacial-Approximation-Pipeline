"""Fail-closed dispatch for A3.2 stubs, not an executable formula catalogue.

Only fixed code-owned IDs are routed. Registry status/implementation_id cannot
load Python, evaluate expressions or activate predictions. No formula is enabled.
"""
from collections.abc import Mapping

from . import RuleRegistry, load_registry, validate_registry
from . import eyes, mouth, nose, ears
from .contracts import NotConfigured, RuleResult

# Deliberate code associations, not a plugin or dynamically imported namespace.
_ROUTES = {
    'eyes_stephan_davidson_2008': ('eyes', eyes.predict),
    'eyes_stephan_huang_davidson_2009': ('eyes', eyes.predict),
    'mouth_stephan_evaluation': ('mouth', mouth.predict),
    'mouth_stephan_murphy_2008': ('mouth', mouth.predict),
    'nose_projection_guidelines': ('nose', nose.predict),
    'ears_guyomarch_stephan_2012': ('ears', ears.predict),
}


def _rows(registry: RuleRegistry) -> list[dict]:
    # Recheck detached metadata; a review flag never bypasses the stub policy.
    return validate_registry(registry.document)[0]['rules']


def _predict(row: dict, observations: Mapping[str, object] | None) -> RuleResult:
    if row['status'] == 'unused':
        return RuleResult(None, None, None, (
            f"{row['id']}: registry marks rule unused; feature unspecified",
            'No case applicability assessment or observation validation performed'))
    route = _ROUTES.get(row['id'])
    if route is None:
        raise NotConfigured(row['id'], ('No code-owned implementation for this rule ID',))
    feature, function = route
    if feature != row['feature']:
        raise ValueError(f"{row['id']}: feature conflicts with the code-owned route")
    return function(observations, rule_id=row['id'])


def predict(rule_id: str, observations: Mapping[str, object] | None = None,
            *, registry: RuleRegistry | None = None) -> RuleResult:
    """Try a known rule; stubs raise NotConfigured and unused rules return nulls.

    No input observation schema is claimed: until a formula is verified its
    anatomical inputs cannot be defined safely. Stub calls do not validate a case.
    """
    selected = load_registry() if registry is None else registry
    rows = _rows(selected)
    for row in rows:
        if row['id'] == rule_id:
            return _predict(row, observations)
    raise ValueError(f'Unknown rule id in selected registry: {rule_id}')


def readiness(registry: RuleRegistry | None = None, rule_id: str | None = None) -> dict:
    """Case-free availability report, separate from A3.1's declared review status.

    This catches only expected NotConfigured errors. Malformed metadata and
    routing conflicts remain errors, rather than being disguised as missing data.
    """
    selected = load_registry() if registry is None else registry
    rows = _rows(selected)
    if rule_id is not None:
        rows = [row for row in rows if row['id'] == rule_id]
        if not rows:
            raise ValueError(f'Unknown rule id in selected registry: {rule_id}')
    reports = []
    for row in rows:
        try:
            result = _predict(row, None)
            if result.prediction is not None or result.sd is not None or result.applicable is not None:
                raise ValueError('No numerical rule execution enabled in this release')
            status, missing = 'unused', []
        except NotConfigured as exc:
            status, missing = 'not_configured', list(exc.missing)
            result = RuleResult(None, None, None, (
                str(exc), 'No case applicability assessment or observation validation performed'))
        reports.append(dict(id=row['id'], feature=row['feature'], registry_status=row['status'],
            execution_status=status, reference=row['reference'], verification=row['verification'],
            missing=missing, result=result.as_dict()))
    return dict(schema_version=1, registry=selected.record(), rules=reports,
                interpretation='Availability only; no case, anatomical prediction or scientific validation assessed')

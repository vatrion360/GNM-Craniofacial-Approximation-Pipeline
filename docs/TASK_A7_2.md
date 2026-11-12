# A7.2 — Operator-declared validity-domain comparison

Base: `e4e32d0861cd9f902daea99db80046f5220fadf5` (PR #40 merged).
Target: `feature/uncertainty-calibration-harness`.

## Changes
- `cranio/validity_domain.py`: closed versioned declarations, blank templates,
  conservative run signatures, exact source-report binding and explicit case
  comparison. No completeness/age class or scientific threshold is inferred.
- `cranio/record.py`: paired opt-in domain/case inputs, retained declarations and
  source hashes, prominent status banner, source-drift checks before completion.
- `cranio/record_job.py` / `cranio/blender_record.py`: explicit optional fields
  passed to the external exporter and a completion-status banner.
- `tests/test_validity_domain.py`: 54 synthetic cases; packaging assertion and
  actual-ZIP Blender banner check added.
- README, record/Blender workflow, task comparison, changelog and
  `VALIDITY_DOMAIN.md`: schema, signature recipe, options and interpretation.

## Verification
- Before changes: **1073 passed, 1 skipped**, 59.56 seconds.
- Final full Python suite: **1127 passed, 1 skipped**, 57.18 seconds.
- Official-model hash:
  `e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
- Linux, Python 3.12; OPENBLAS_NUM_THREADS=1. One host pytest-plugin CallSpec2
  deprecation warning is unrelated to this feature.
- Ruff passed. Wheel, sdist and Blender ZIP built successfully. The local build
  was resumed with `python -m build --no-isolation` after runtime restart;
  setuptools 84.2.1 and wheel 0.48.0 satisfy the declared build requirements.
- Base hosted runs 43227063100 (Python/packaging) and 43227062742 (Blender)
  succeeded. Feature-specific Windows/Linux CI and the new
  BLENDER_DECLARED_VALIDITY_DOMAIN_BANNER_PASS check are tracked on the PR.
  Local Blender remains unavailable; no local Blender pass is claimed.

Tests include a synthetic partial skull outside a complete-only declared domain;
unknown/unreviewed observations; model/settings/source/environment mismatches;
wrong-report binding; malformed/duplicate/nonfinite declarations; signed regional
metrics and missing intervals; deterministic exports; no input/fit changes;
source drift and concurrent template destination protection.

## Interpretation, limits and remaining work
This implements the A7.2 configuration/comparison framework, not a supplied
independently validated domain. The user must supply reviewed study evidence and
case observations. Evidence references/hashes and independent-subject counts are
operator-declared and not reopened or independently verified.

Statuses distinguish not_configured, indeterminate, outside_declared_domain and
within_declared_conditions. Even matching conditions do not establish anatomical
accuracy. Regional values describe the declared study, not predicted errors of
the current face. There is no sufficient-N rule, scientific approval, correction,
calibration application or new export gate.

The signature is deliberately conservative; configuration, shared assets, source
and numerical environment changes may require explicit domain revision/review.
Case-specific data are excluded from the method signature but observations are
bound to the exact source report. Missing fingerprint/environment metadata stays
unknown. Empty unreviewed templates degrade to not_configured.

Fitting, meshes, CSV formats and defaults are unchanged. CT evaluation remains
manual. Calibration linkage and formal scientific/illustrative export modes
remain separate work.

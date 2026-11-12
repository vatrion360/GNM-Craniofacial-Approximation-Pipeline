# A7.1 increment 2 — Explicit Monte Carlo evidence association

Base: `ddaed9d9d0b2bea94ed3170a372388049b4857f0` (PR #38 merged).
Target: `feature/uncertainty-calibration-harness`.

## Changes

- `cranio/record_uncertainty.py`: read-only validation and summary of an explicit
  A2.1 CLI ensemble. Require shared recorded model/CSV hashes and matching selected
  prior state/hash. Retain per-scenario convergence/clipping, source settings,
  omitted errors, placement/depth metadata, warnings and source fingerprint.
- `cranio/record.py`: paired opt-in `--uncertainty` and
  `--uncertainty-scenario` options; JSON/TXT association and path/hash provenance.
  Recheck the supplied file before the completion marker. Existing unlinked
  records and all fitting defaults remain unchanged.
- `tests/test_record_uncertainty.py`: 34 new synthetic checks; packaging requires
  the new module.
- README, changelog, uncertainty/record docs and task comparison describe the
  supported scope, rejection cases and remaining work.

## Verification

- Existing suite: **1020 passed, 1 skipped**, 38.38 seconds.
- Final suite: **1054 passed, 1 skipped**, 40.78 seconds.
- Focused record suites: **78 passed** (44 existing + 34 new).
- Ruff passed; wheel, sdist and Blender ZIP built successfully.
- Official-model SHA-256:
  `e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
- Linux, Python 3.12, NumPy 2.3.5, SciPy 1.17.0, trimesh 5.2.0,
  pytest 9.2.0; OPENBLAS_NUM_THREADS=1. The host pytest plugin emits one
  CallSpec2 deprecation warning, unrelated to the feature.
- Base hosted Python/packaging run 43181664245 and Blender integration run
  43181664073 both succeeded. Local Blender remains unavailable after its
  earlier startup failure; no local Blender pass is claimed. Feature-specific
  hosted Windows/Linux gates are reported in the PR.

Tests exercise real synthetic pipeline and ensemble CLIs, both prior scenarios,
mismatched recorded inputs, malformed JSON, sample transforms/dimensions,
inconsistent convergence/clipping counts, partial errors, deterministic replay
warnings, unchanged source files, moved files, and source drift during export.

## Interpretation and remaining work

This is evidence association, not final-mesh uncertainty or calibration. Even exact
central-target equality leaves fitting equivalence unestablished. A2.1 excludes
dense/TPS/profile and other additional losses. No SD, multiplier or confidence
interval is applied to a fitted mesh. Related nonconverged evidence stays visible.

The ensemble's legacy input hash map does not assign typed roles. The association
is labelled hashes_present_in_recorded_inputs; it is not fresh input verification
or authenticity. Embedded paths are never opened. Keep the original ensemble
with the case evidence: only its hash and summary are linked, not a full copy.

CT validation remains operator-led. Calibration links, validity-domain comparison,
Blender controls and scientific export modes remain separate increments. No
scientific values, sources, thresholds or subject-level results were invented.

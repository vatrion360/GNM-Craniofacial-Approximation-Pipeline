# A5.1 — saved-report check contract

## Scope

This increment precedes A7.3 export modes. It adds a common configured diagnostic
gate, not full A5 mesh-export enforcement. It follows PR #41 on the merged base
`63bf6466251e84ae55d31d0c2ea41518a82db6ce` (same source tree as tested PR #41).

Changed files: `cranio/check_policy.py`, record/job/Blender adapters, packaging
assertion, `tests/test_check_policy.py`, actual-ZIP Blender record checks, README,
changelog, record documentation, roadmap and the check-policy documentation.

## Behavior and evidence

- Pure NumPy/standard-library assessment of completed reports. Empty policies
  contain no scientific values. Each applied rule has source, explicit severity,
  reviewed policy ID/revision and closed validated fields.
- Synthetic skull scaling by 1.33 changes a 100 mm test chord to 133 mm and fails
  a deliberately synthetic 90–110 mm range. These are software test inputs, not
  proposed anatomical limits or results on a person.
- Missing/reconstructed/unreviewed/stale endpoints remain not assessed. A mixed
  right-cranium/left-mandible fixture does not fill missing left cranial bone.
  A missing Porion prevents the configured frame criterion from passing.
- Region counts use the actual fitted labels and positive base weights. Plane
  RMS is recomputed from internally consistent snapshot observations, not a
  cached scalar and not interpreted as anatomical confidence.
- Existing convergence, transform, side-label and geometry diagnostics retain
  their limited scope. Legacy geometric/side thresholds are labelled; missing
  or incomplete tests do not become green.
- Exceptions preserve findings, original aggregate status and an explicit reason.
  Derived blocked/incomplete records stay diagnostic, even after override.
- CLI output refuses overwrite and rechecks sources; deterministic records,
  default-path preservation, malformed data and input-change failures are tested.
- Blender adds two empty-by-default fields to the saved-fit record panel. The
  actual-ZIP smoke test expects `BLENDER_EXPLICIT_CHECK_POLICY_PASS`, checks the
  status/text banner, exception retention and unchanged meshes/targets, and
  retains the prior cancellation and deleted-scene lifecycle checks.

## Verification

- Before changes: **1127 passed, 1 skipped**, with the official GNM model,
  Python 3.12, Linux and `OPENBLAS_NUM_THREADS=1` (53.62 s).
- Focused final new module suite: **55 passed** (3.60 s).
- Base Blender Windows/Linux workflows passed for PR #41. Local Blender remains
  unavailable; this task relies on hosted actual-ZIP Blender integration.
- Complete final suite: **1182 passed, 1 skipped** (58.69 s), with the official model.
- Ruff, whitespace validation, wheel/sdist and Blender ZIP builds passed.
- Hosted feature workflow outcomes are recorded in the PR.

## Deviations and remaining choices

The common engine is a separate `check_policy.py`, preserving existing
`checks.py` numerical behavior. It reuses the existing side heuristic and
craniometry/reference-frame implementations. The ordinary mesh exports remain
unchanged; A5 is not complete until explicit export operations enforce the gate.
Scientific/illustrative modes, live-scene checks and a calibrated midsagittal
confidence criterion remain future tasks. The RMS criterion is descriptive only.

No CT case was evaluated. Population-specific ranges, regional minimums, plane
residual criteria, their applicability and supporting sources remain supplied
and reviewed by the operator. No default tissue, fit, prior, CSV or model change.

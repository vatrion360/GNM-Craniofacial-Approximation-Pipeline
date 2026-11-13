# B4.1 — explicit saved-fit consistency diagnostics

Base: merged PR #44, `0f9c2c34284b0bf6ac5f14c08818f2f412f21178`.
Branch: `feature/postfit-consistency-summary`.

## Changes

- `cranio/consistency.py`: reuse recorded A5/geometry diagnostics, add triangle
  angles on verified serialized meshes and sampled-clearance descriptive
  statistics; retain unassessed anatomical checks and legacy tolerance provenance.
- `cranio/record_job.py`, `cranio/blender_record.py`: explicit external diagnostic
  action using the existing lifecycle. No live mesh reads/mutations or new default
  pipeline behavior; submitted report identity is checked before result display.
- Unit tests: known triangle geometry, scale/rigid invariance, incomplete/partial
  evidence, malformed diagnostics, contradictions, nonfinite data, topology,
  deterministic metrics, input/output integrity and Unicode subprocess paths.
- Actual installed-ZIP Blender smoke: official-model saved result, diagnostic
  Text Editor output, unchanged scene/markers/source artifacts and cancellation.
- Documentation, README options, packaging and roadmap updated.

## Verification

Baseline: **1259 passed, 1 skipped**, official model, Python 3.12/Linux,
`OPENBLAS_NUM_THREADS=1` (110.31 s). Baseline source tree equals PR #44's verified
tree `aac10507801f9a45ad3d4505bcafc8aff29e8a04`; its hosted Windows/Linux Blender
jobs passed. Local Blender is unavailable, so no local headless success is claimed.

Initial focused suite: **60 passed**; expanded focused suite: **67 passed**.
Final full suite: **1307 passed, 1 skipped** (78.94 s), including 48 new tests.
Ruff, whitespace checks, wheel/sdist and Blender ZIP builds passed. The runtime's
development dependencies were restored after a session reset before final checks.
Hosted Windows/Linux outcomes are recorded in the PR. The new actual-ZIP marker is
`BLENDER_SAVED_FIT_CONSISTENCY_PASS`.

## Scope and open work

This is an incremental B4 summary, not complete B4/T0.3. Closed-volume signed
distance, bone-area coverage, regional source-table bands, independent profile
comparison and any corrective deformation remain unimplemented here. The report
does not relabel sampled normal-projected clearance as tissue depth or area
coverage. No anatomical threshold, source table, calibrated confidence, CT result
or automatic export authorization is introduced. CT analysis remains manual.

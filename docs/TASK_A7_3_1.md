# A7.3.1 — explicit saved-fit mesh export

Base: merged PR #42, commit `a71ae7e7d8ba7f81f43019b644ccfddf7e92f41a`.
One task/branch: `feature/gated-fit-export`.

## Changes

- `cranio/review_export.py`: restricted saved-pipeline OBJ validation; scientific
  check-gate enforcement and labelled illustrative mode; unchanged world-mm
  geometry, neutral gray MTL, diagnostics, atomic decision marker and input/output
  hashes. Refuse existing destinations and unsupported/external OBJ directives.
- `cranio/record_job.py`, `cranio/blender_record.py`: explicit mode request and a
  second fixed external module using the existing lifecycle. Default record
  action unchanged. Held exit code 3 displays a blocked result rather than an
  unexplained process failure; no current-scene geometry is exported or mutated.
- `tests/test_review_export.py`, packaging assertion and actual-ZIP Blender checks:
  scientific pass/held/override, illustrative labels, unchanged geometry, missing
  inputs, integrity failures, source drift, fixed manifest paths, safe Unicode
  subprocess arguments and Blender scene/marker immutability.
- README/options, changelog, check-policy/record documentation and roadmap updated.

## Verification

Before edits: **1182 passed, 1 skipped**, official GNM model, Python 3.12/Linux,
`OPENBLAS_NUM_THREADS=1` (33.87 s). The host environment had lost pytest between
turns; reinstalling the declared development dependencies restored the test
runner before the baseline was taken. No source change was used to fix the host.

After: **1229 passed, 1 skipped** (35.71 s), including **47 new tests**. Ruff and
whitespace checks passed. The first focused run had 63 passing export/job tests;
the full run includes the additional explicit scientific-pass, relocated-artifact
and contradictory-decision cases.

Base Windows/Linux Blender CI passed for PR #42. Local Blender remains
unavailable. The new hosted actual-ZIP gate prints
`BLENDER_GATED_SAVED_FIT_EXPORT_PASS` after checking blocked/no-mesh output,
overridden scientific export without texture directives, labelled illustrative
export, exact saved v/f rows, unchanged scene vertices/targets and cancellation.
Wheel/sdist and Blender ZIP builds passed. Hosted workflow outcomes are recorded
in the PR.

## Scope and deviations

This is the first A7.3 increment, **not all of A7.3**. It implements explicit
saved-neutral export modes and connects scientific mode to the existing A5 gate.
It does not add export of current textured/expressive presentation copies,
Frankfort captures, scale bars or final-mesh uncertainty heatmaps. Those omissions
are explicit in the bundle manifest and documentation. No displacement heatmap or
marker-only ensemble is presented as final-mesh confidence.

The configured policy controls this new scientific export operation only. Ordinary
pipeline mesh exports and the existing record command retain their behavior.
Passing the policy, choosing scientific mode or supplying an override does not
constitute scientific validation. Illustrative mode retains findings without
claiming they have passed. No CT validation or anatomical constants were added.

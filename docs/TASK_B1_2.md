# B1.2 — Shared local-correction preparation

Base: merged PR #46, `2e0c7dc281fd0fa9abf399d27b8b0094f310401f`.
Branch: `feature/shared-local-correction`.

## Changes

- `cranio/local_correction.py`: NumPy-only centre assembly, regional caps,
  frozen numerical snapshot, repeated application from the original statistical
  mesh and detached row-selection record.
- `cranio/pipeline.py`: use the common preparation in the opt-in local stage;
  retain SciPy, original confidence multipliers and existing post-fit QC.
- Reject malformed input indices, incomplete dense arrays and coincident or
  rank-deficient selected centres; preserve missing regions without imputation.
- Preserve fractional scalp caps even if a Python caller supplies an integer
  face cap (former integer-array truncation). CLI float parsing is unchanged.
- Regression tests, installed-ZIP Blender preparation/oracle checks, packaging
  assertion and API/roadmap documentation.

## Verification

Baseline: **1375 passed, 1 skipped** (17.55 s), Python 3.12/Linux, official model,
`OPENBLAS_NUM_THREADS=1`. The first attempt found pytest absent from the resumed
runtime; development dependencies were restored before this baseline. Baseline
Windows/Linux Blender evidence is merged PR #46's successful hosted runs; local
Blender remains unavailable.

Focused suite: **109 passed** (1.41 s). Full suite: **1464 passed, 1 skipped**
(18.25 s), including **89 new tests**. Ruff and whitespace checks passed.
Build and hosted Windows/Linux Blender outcomes are recorded on this PR, using
`BLENDER_LOCAL_PREPARATION_PASS` and the existing complete smoke marker.

An additional end-to-end comparison ran the actual base checkout and this branch
in separate Python processes on two synthetic official-model scenarios:

- 48 targets displaced from the mean with seeded Gaussian vectors (seed 1942,
  2 mm scale) and synthetic confidence multipliers drawn uniformly from 0.3–1.
- The same markers with dense local constraints against an artificial exterior
  shell offset 5 mm from the model along computed normals. Sampling used 5,000
  points and seed 42; dense identity fitting was disabled to isolate the local
  stage. Fixed ridge lambda was 30 in both scenarios.

These are software fixtures, not anatomical depths or CT subjects. Both cases
produced **byte-identical statistical OBJ, final OBJ and displacement PLY**.
Metrics, coefficients, pose, geometry QC, centres and prescribed vectors matched
exactly. JSON files intentionally differ in source provenance, generation time
and the added preparation record. The persistent unit tests also retain a
pre-extraction assembly oracle with exact array/output comparisons.

## Scope and remaining work

This completes shared preparation, not the whole B1 milestone. No Finalize UI,
scene modification, new default or change to live previews is introduced.
The next increment must bind a fresh scene snapshot to a reversible Blender
operation with provenance and explicit QC scope. The numerical API's prepared
snapshot alone does not provide that scene transaction or an anatomical check.
No scientific choice or user data is required for this extraction; CT checks
remain manual.

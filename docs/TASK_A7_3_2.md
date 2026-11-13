# A7.3.2 — reviewed saved-fit captures

Base: merged PR #43, commit `84eb17335be2c5288a78943f29b3fb2f19c47d9b`.
One task/branch: `feature/standardized-fit-captures`.

## Changes

- `cranio/capture_plan.py`: NumPy-only snapshot/frame validation and shared-scale
  orthographic camera/bar planning; no orientation fallback or fit changes.
- `cranio/capture_render.py`: fixed background-Blender CPU rendering of the saved
  neutral face, mode/override labels, metric bars and hashed completion manifest.
- `cranio/capture_job.py`, `cranio/blender_record.py`: explicit asynchronous action
  using the current Blender executable; source/result checks and existing bounded
  cancellation/scene lifecycle. No `bpy` in workers or current-scene mutations.
- Numeric/integrity tests, packaging assertion and actual-ZIP three-view rendering
  check, including decoded scale-bar pixels and unchanged parent-scene geometry.
- README, workflow documentation, changelog and roadmap updated.

## Verification

Before edits: **1229 passed, 1 skipped**, official model, Python 3.12/Linux,
`OPENBLAS_NUM_THREADS=1` (58.32 s). Declared development dependencies were restored
after the runtime reset; no source change was needed to restore the test runner.
Focused tests: **96 passed**. Full suite after edits: **1259 passed, 1 skipped**
(100.30 s), including 30 new tests. Ruff, whitespace checks and the Blender ZIP
build passed. Hosted Blender and packaging run outcomes are recorded on the PR.
Local Blender is unavailable; no local render
success is claimed. Windows/Linux CI exercises real rendering rather than the
stub used by the older A4.2 camera-placement test.

## Scope and deviations

This advances A7.3 with standardized captures and scale bars, not final-mesh
uncertainty or textured presentation export. It requires a saved canonical fit
and reviewed reference frame. Earlier bundles remain immutable; a separate
manifest records capture provenance. No new fitting defaults, anatomical values,
automatic approval or CT evidence are introduced. CT evaluation remains manual.

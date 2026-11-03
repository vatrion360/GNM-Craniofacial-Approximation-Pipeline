# A4.3 — protocol-defined cranial measurements

Based on `e0c28b6e10fe439a5657db6d7e6569b203e95baf` (merged A4.2 PR #26)
in `feature/uncertainty-calibration-harness`. Prerequisite PR #26 passed both
Python/packaging and Blender CI before this task. One task branch:
`feature/cranial-feature-measurements`. No automatic merge.

## Files and behavior

- `cranio/features.py`: NumPy-only construction/provenance contract, per-feature
  eligibility, geometry primitives, optional conditional placement intervals,
  definition-bound descriptive thresholds and safe template/compute CLI.
- `cranio/landmarks.py`, `cranio/craniometry.py`: four bone counterparts
  (pr, pg, go_R/L) reuse existing tissue-site definitions/associations. No new
  skin targets, GNM vertices, tissue values or chord controls.
- `cranio/blender_craniometry.py`: separate opt-in 38-row initialization;
  original/extended initialization remains 22/34. Definition/source review,
  explicit link associations and duplicate-skin-target prohibition apply.
- `cranio/blender_features.py`, `addon_v13.py`: explicit fresh compute/export,
  mandibular review gate, safe output paths, JSON plus Blender text results.
  No work during redraw/refit and no changes to fitting defaults.
- `tests/test_features.py`: 29 tests of known geometry, rigid transforms/units,
  partial anatomy, stale evidence, frame/error propagation, missing SDs, invalid
  samples, threshold binding, safe CLI outputs and default-fit byte parity.
- `tests/test_extended_references.py`: accepted registry count becomes 38;
  existing 22/34 initialization tests remain intact.
- `tools/blender_feature_checks.py`, `tools/blender_smoke.py`: real Blender
  placement/review, 22/34/38 initialization, no extra skin targets, mandibular
  gating, partial features, moved points, safe exports and unchanged geometry.
- README options, `CRANIAL_FEATURES.md`, marker/extended-reference notes and this report.

## Executed checks (rerun 2026-11-03)

| Gate | Baseline | Changed code |
|---|---|---|
| Python suite with official GNM model | 627 passed, 1 Windows-only skip | 656 passed, 1 Windows-only skip |
| Blender 4.5.0 Linux ZIP/model/external Python | Pass | Pass, including BLENDER_FEATURES_PASS |
| Ruff / whitespace | — | Pass |
| Wheel, sdist, addon ZIP | — | Built successfully |
| Installed wheel outside checkout | — | Feature template CLI, registry and empty protocol computation pass |
| Default statistical/final OBJ and displacement PLY | — | Byte-identical with/without new bone metadata on synthetic fixture |

Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, pytest 9.2.0, Linux x86_64.
The Blender archive was verified against its official checksum manifest.
Official model SHA-256 remained
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
No model, subject scan, non-commercial asset, dependency or default solver change.
All new measured geometry is synthetic. Windows/interactive/anatomical checks
were not performed locally; published commit CI is separate. The existing
synthetic renderer-error traceback is an expected A4.2 test, not a failed suite.

The initial 2026-11-02 publication attempt was not executed because automatic
GitHub approval review hit a usage limit. After the workspace reset, the code
was reconstructed from the retained implementation and both baseline/changed
suites were rerun. This report refers to the restored, tested code.

## Scientific choices, deviations and open inputs

The requested gnathic construction is Ba–Pr/Ba–N, implemented as a ratio without
multiplication by 100. Bigonial width uses the reviewed bilateral Gonion chord.
A–N–B and Pogonion/Nasion endpoints are fixed; projection/sign choices are
explicit. Other features have multiple possible constructions without a complete
supplied protocol. Their geometry/framework is implemented, but definitions start
null pending operator source/review. No clinical defaults, tangents, coefficients
or norms are invented. New bone definitions reuse existing project Table 2 text
and still require case review.

Sagittal projection explicitly means the Frankfort frame YZ plane, not the
independent fitted midline plane. Required references are rechecked and perturbed
with the feature points. Missing opposite-side bone is not substituted. Mandibular
observations require a documented assembly/pose assumption, including intrinsic
measurements on assembled fragments.

A2's per-coordinate SD contract is reused. Intervals are the 2.5th/97.5th
percentiles of the declared independent Gaussian placement model, labelled
conditional/uncalibrated, not empirical confidence intervals. Missing SDs are
not imputed. Invalid draws withhold the whole dependent interval; no favourable
sample filtering occurs. Point-stream order is recorded. Correlated/systematic
errors, segmentation uncertainty, jaw-pose sampling and population calibration
require further evidence/tasks.

Classification defaults to no_thresholds_configured. Optional thresholds require
source, exact construction hash and units; labels are descriptive, not diagnoses.
A conditional interval crossing bins is indeterminate. Missing uncertainty never
produces an interval label. A source string is documentation, not verification
that a threshold or definition is scientifically appropriate.

Outputs are separate measurements, not face-fitting constraints. All behavior is
opt-in. CT validation remains the user's manual task. A4.4 (profile constraint)
remains next; A4.5/A4.6 handle articulation tooling and pose sensitivity.

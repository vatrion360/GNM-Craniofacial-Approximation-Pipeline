# A4.6 — Explicit mandibular pose sensitivity

Base: `cff9db56f5d8c72f6d0476ba81bbe4bca33352c8` (merged PR #29).
Branch: `feature/mandible-pose-sensitivity`.

## Changes

- `cranio/sensitivity.py`: pure NumPy scenario engine and template/compute CLI;
  baseline, unique range corners and seeded uniform draws; explicit source-bound
  rigid transforms; A4.3 features, optional profile targets and auditable JSON.
- `cranio/blender_sensitivity.py`, `addon_v13.py`: optional panel, blank configuration,
  reviewed articulation gate and safe export using the shared core. No scene move,
  implicit fitting, worker-thread bpy or new numerical dependencies.
- `tests/test_sensitivity.py`: 34 synthetic cases covering analytical translation,
  rotation, coordinate equivariance, exact rigid invariants, threshold crossings,
  missing references, invalid/stale evidence, degeneracy, angle branches,
  deterministic CLI output and input/output protection.
- `tools/blender_sensitivity_checks.py`, `tools/blender_smoke.py`: template/export,
  configured ranges, missing thresholds, review gate, unchanged scene and safe
  file handling, included in the actual addon ZIP smoke suite.
- `README.md`, `docs/POSE_SENSITIVITY.md`: controls, configuration, interpretation
  and explicit limitations. This file records task verification and deviations.

## Executed verification — 2026-11-03

| Gate | Before | After |
|---|---|---|
| Python suite with official GNM model | 715 passed, 1 Windows-only skip | 749 passed, 1 Windows-only skip |
| Blender 4.5.0 Linux ZIP/model/external Python | Passed | Passed, including pose sensitivity |
| Ruff / whitespace | — | Passed |
| Wheel, sdist, addon ZIP | — | Built |
| Installed wheel outside checkout | — | Module origin checked; template CLI passed |

Runtime: Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, trimesh 5.2.0, pytest 9.2.0.
The workspace reset during implementation; baseline checks were rerun on the
fresh base before restoring changes. Model SHA-256 remained
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
No scan, model asset, anatomical constant or licensed third-party asset was added.
Local Windows, interactive Blender and CT validation were not performed. Hosted
CI results are reported separately. Ordinary live/offline fitting is unchanged.

## Scope decisions, deviations and remaining work

This increment implements landmark/feature/profile-target sensitivity. The
optional profile contains sourced bone-normal targets, not an A4.4 GNM vertex
chain or an ensemble of fitted faces. Full facial-surface propagation is not
claimed. These are sampled scenario ranges, not guaranteed extrema, confidence
intervals or calibrated biological uncertainty. No numerical scientific ranges,
thresholds, tissue depths, placement errors or sample counts are defaulted.

One selected mandibular source group moves rigidly; missing/reconstructed or
unreviewed points remain unavailable. Independent multigroup motion and combined
placement/depth Monte Carlo remain outside this increment. Degenerate scenarios
are retained and withhold affected ranges; signed-angle branch crossings do not
produce misleading linear intervals. Rigid invariants retain exact baseline
values to prevent false threshold crossings from floating-point roundoff.

No pose is filtered for collision, contact or anatomical plausibility. The user
must document/review the pivot, axes, ranges, feature definitions and any tissue
or classification sources, and use articulation checks when choosing the domain.
Missing thresholds are reported explicitly; sampled class crossings are labelled
indeterminate. The Blender action is synchronous and on demand; large scenario
counts increase runtime and JSON size. Validation against CT remains with the
user and is not a prerequisite substituted by synthetic engineering tests.

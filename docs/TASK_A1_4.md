# A1.4 — optional tissue SD weighting

Implementation based on `feature/tissue-table-selection`, commit
`5d0ca06d5cd0a6c1ec133d71e8e8cf3af72e393d`. This is a stacked task branch;
publication of its PR does not imply that predecessor branches have merged to main.

## Changes

- `cranio/depth_weighting.py`: NumPy-only inverse-SD-square factors, explicit
  fallback, representability checks, table/row provenance and base/effective
  marker weight records. No scientific values added.
- `cranio/config.py`, `gnm_reconstruct.py`, `cranio/pipeline.py`: optional offline
  `--depth-weighting {none,sd}`, default `none`; table reference required in SD
  mode, target geometry preserved unless separately selected for replacement.
  TPS uses original confidence, including after automatic marker exclusion.
- `cranio/fit_contract.py`, `cranio/geometry.py`, `cranio/optimize.py`,
  `cranio/preview.py`: shared dense weights normalized using original marker
  confidence, then multiplied by selected regional precision. Original and
  effective dense weights are reported; normal filtering and sampling are unchanged.
- `cranio/tissue_compare.py`: propagate mode, preflight SD factors for each
  scenario, identify the mode in the comparison summary.
- `tests/test_depth_weighting.py`: 22 synthetic engineering checks.
- `README.md`, `docs/TISSUE_SCENARIOS.md`: switch, semantics, limits and audit fields.

## Verification (2026-10-30)

Linux, Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, trimesh 5.1.0,
pytest 9.1.1, Ruff 0.17.3; `OPENBLAS_NUM_THREADS=1`.
Official GNM asset SHA-256:
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
Blender 4.5.0 Linux archive checked against its official checksum manifest.

| Check | Before | After |
|---|---|---|
| `GNM_MODEL_PATH=... python -m pytest -q` | 349 passed, 1 skipped | 371 passed, 1 skipped |
| Actual add-on ZIP, Blender headless, official model and external Python fit | `BLENDER_SMOKE_PASS` | `BLENDER_SMOKE_PASS` |
| Ruff and `git diff --check` | Existing baseline | Pass |
| Wheel/sdist build, wheel installed outside source tree | Existing baseline | Pass; SD module, CLI flag and bundled table load from installed wheel |

The skipped test is Windows-only; local execution does not establish Windows
success. The existing CI matrix runs Python and Blender integration separately.
The old roadmap counts (57/57 and 46/47) are historical, not the current suites.

The new tests cover a hand-computed ridge solution, reduced influence of a
high-SD target in actual fitting, regional sampling and normalization, preview
parity, exact missing-SD fallback (markers, dense fit and TPS), invalid/tiny/huge
SD, overflow/underflow, zero-strength nasal rows, preserved target CSV, automatic
exclusion/refit budgets, table comparison and frozen protocol settings.
All numerical SD values in these tests are synthetic, not tissue recommendations.

`tools/verify_tissue_migration.py` was run in separate processes against the
baseline and changed trees using the official asset and seed 1902. Both
`statistical_default` and `local_correction` produced identical numerical
manifests (pose, coefficients, lambda, metrics, iteration/solver records) and
identical OBJ/PLY hashes with all new flags off:

| Output | SHA-256, identical before/after |
|---|---|
| Statistical OBJ | `0688d1a8356003d76607b2089836564bc323d9f581f53bcc4c385a543a5ef56b` |
| Statistical PLY | `91974b1fa57c6bf77b55ce273f8ca79640c8d65907777f2dc1314469d64a88d7` |
| Local-correction OBJ | `a5d99a410f03955023bb1815553d5e747578fcb4839f78eb014f08bc7330de18` |
| Local-correction PLY | `5da8b1143b39cae37aa7d04d9d71c80af38f1079b94395bd70bc5de9825f34cd` |

These artificial replay targets reach the existing iteration limit in both
trees (`converged=false`). This is regression evidence, not convergence or
anatomical validation. No CT cases were evaluated; those remain a manual user task.

## Scope decisions and open scientific questions

1. The table schema has no default-weight field. Missing SD therefore retains
   the existing case confidence or normalized dense weight, with an explicit
   warning. It never substitutes an invented SD or table-specific constant.
2. The switch is offline CLI only. The shared NumPy adapter supports prepared
   precision weights, but no Blender UI option or default scene change is added.
3. SD weights change pose/identity fitting. TPS is not an inverse-variance solver;
   its confidence displacement multipliers are kept separate so `SD < 1 mm`
   cannot amplify a prescribed correction simply through the weight factor.
4. Scalar depth SD is used as a sensitivity multiplier on all three coordinates.
   It is not a calibrated placement covariance or posterior uncertainty model.
   Changing absolute weight scale also changes the balance with regularization
   and optional measurement/distance terms. Source-direction enforcement is a
   later task, not silently implemented here.
5. Both bundled tables retain unknown SDs. Source-verified SDs and their
   applicability are needed before this option can have substantive tissue-data
   effects. No external references or scientific constants were introduced.

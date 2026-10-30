# A2.1 — seeded marker-error propagation

Base: `fb875614d0117a829b7aaa10d6b9474b09e375ba`,
`feature/tissue-estimator-posture` (PR #20). Both predecessor workflows completed
successfully before this task. Changes are on `feature/uncertainty-monte-carlo`;
a feature branch/PR does not imply a merge into main.

## Implemented

- `cranio/uncertainty.py`: NumPy-only sampling/fit engine and standalone opt-in
  CLI. Each draw calls the existing `fit_identity`, including pose and Huber
  refitting and optional conditional LOO lambda. The solver was not changed.
- Per-label placement SD/source validation; versioned tissue mean/SD input with
  existing/reviewed source axes; rejection-sampled nonnegative depths; paired,
  separately reported prior scenarios; explicit partial-analysis mode.
- Replayable JSON with actual perturbations, coefficients/transforms, hashes,
  data sources, omitted terms, convergence/clipping/conditioning diagnostics.
  Input changes and output collisions fail before publication. Failed fits abort;
  nonconverged fits are retained with warning and `numerical_status`.
- `tests/test_uncertainty.py`: 39 new synthetic engineering tests.
- `tools/blender_uncertainty_checks.py` and `tools/blender_smoke.py`: actual packaged
  engine in Blender. `tools/benchmark_uncertainty.py`: repeatable runtime check.
- README options and `docs/UNCERTAINTY.md`: schema, commands, assumptions/limits.

## Verification — 2026-10-30

After a transient environment reset, the published A1.6 base was freshly checked
out and both baseline suites rerun. The recovered A2.1 code was then verified
again; counts below refer to this recovered checkout, not a lost working copy.

Environment: Linux x86-64, Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0,
trimesh 5.2.0, pytest 9.2.0, Ruff 0.17.3; `OPENBLAS_NUM_THREADS=1`.
Blender 4.5.0 Linux archive checked against its official checksum manifest.
Official GNM v3 SHA-256:
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.

| Gate | Before | After |
|---|---|---|
| Pytest with official model | 426 passed, 1 Windows-only skip | 465 passed, 1 Windows-only skip |
| Actual Blender ZIP, official model, external Python | `BLENDER_SMOKE_PASS` | `BLENDER_SMOKE_PASS`, `BLENDER_UNCERTAINTY_NUMPY_PASS` |
| Ruff / diff check | Existing baseline | Pass |
| Wheel / sdist | Existing packaging | Build passed; installed-wheel CLI outside source checkout exercised separately |
| Default numerical replay | Seed 1902 official-model synthetic case | Identical numerical manifests and OBJ/PLY SHA-256 for statistical and local-correction modes |

The default replay retains the existing max-iteration warning (`converged=false`)
in both trees and both modes. Identical replay is regression evidence, not a
convergence or anatomical-accuracy result. Existing solver/pipeline/add-on fitting
source and default settings remain unchanged. No model asset was edited.

Tests cover exact shared-solver parity, zero-error synthetic truth, seed/global-RNG
isolation, paired prior order independence, per-draw automatic lambda, truncation
moments, source-axis/hash binding, null/error inputs, no inferred means from other
estimators, aborted failures, retained nonconvergence, deterministic CLI records,
input-change refusal and existing-output protection.

## Convergence finding and benchmark

An initial diagnostic run on the previous Intel Xeon Platinum 8573C environment
(NumPy 2.3.5, one BLAS thread) took 81.74 s for 200 synthetic draws but **199/200
reached the shared default 30-iteration limit**. The first such draw converged at
iteration 56 when allowed 100 iterations, without changing convergence tolerances.
This motivated an explicit `--max-iter` option; its default remains 30. This is
not a silent speed/accuracy trade-off or an alteration of the existing addon.

The recovered implementation was benchmarked with:

```bash
OPENBLAS_NUM_THREADS=1 python tools/benchmark_uncertainty.py --npz models/gnm_head.npz --sigma-mm 0.2 --samples 200 --seed 0 --max-iter 100
```

- Host reports AMD EPYC 9V74, 9 logical CPUs available; one OpenBLAS thread.
- Official model: 48 markers, 253 components; targets from the model mean;
  independent synthetic per-coordinate placement SD 0.2 mm; lambda 30; no prior,
  depth sampling, dense constraints or TPS. The SD is a **test input**, not a
  measured or recommended human placement error.
- 200 draws plus the central baseline: **94.83 s**; baseline and **200/200 draws
  converged**, maximum 82 iterations; no sample had clipped coefficients.

Timings from different hosts are not a performance comparison. These results do
not establish convergence on other inputs, speed on the user's Windows machine,
coverage, robustness to damaged skulls, or forensic accuracy.

## Deviations and unresolved scientific inputs

- The stronger no-invented-values rule replaces TASKS.md's proposed placeholder
  placement SD: null remains null. No configured errors means no ensemble; an
  explicitly allowed partial analysis is labelled conditional sensitivity.
- A2.1 is marker-only statistical propagation. It does not assert full offline
  dense/TPS parity or attach uncertainty to the existing final face. Source SDs
  and measured placement errors are still needed for actual cases. Existing
  bundled tables do not contain the SDs required for depth distributions.
- A table estimator other than mean is not silently made a Gaussian mean.
  Distribution shape, independence and fixed-axis assumptions require human
  scientific review; model bias, missing anatomy and systematic errors remain
  outside this error budget.
- No posterior, 95% interval or calibrated confidence is exported. A2.2 mesh/SD
  outputs, A2.3 analytic cross-check and A2.4 calibration remain subsequent tasks.
- No CT cases were analysed. CT assessment/calibration stays with the user.
  Local integration is Linux; Windows CI and interactive workstation acceptance
  must be reported separately from these local results.

# A2.2 — ensemble mean, SD fields and representative samples

Base: `78b5bb1bb5d984476b52043bbcab4347391028ec`,
`feature/uncertainty-monte-carlo` (PR #21). Both predecessor CI workflows completed
successfully before this task. Branch: `feature/uncertainty-exports`; publication
as a stacked PR does not mean the change is merged into main.

## Changes

- `cranio/uncertainty_export.py`: NumPy summaries and standalone export CLI for
  existing A2.1 records. Strict convergence/transform/sample-count checks; model
  hash binding; streaming posed-world-coordinate means and sample SDs (ddof=1).
- Mean OBJ, numerical coordinate SD/3-D spread PLY and 3–5 requested actual sample
  OBJ variants per prior scenario. Selection uses beta centroid/farthest-point
  sampling with deterministic ties and exact replay deduplication.
- Explicit region vertex sets with model hash and source; all-vertex statistics
  by default. Regional spatial percentiles have distinct names and are not called
  confidence intervals. Partial-input/clipping/source warnings stay visible.
- Temporary directory staging, source hash rechecks, new destination only,
  output hashes and a final completion summary. No embedded historical paths
  are opened, no fit is rerun and no new registration is performed.
- `cranio/export.py`: optional OBJ comment lines; callers without comments retain
  exactly the existing bytes. No solver, pipeline default or model asset changes.
- `tests/test_uncertainty_export.py`: 36 synthetic tests. The existing actual
  Blender uncertainty check now exercises the NumPy geometry summary.
- README options and `docs/UNCERTAINTY_EXPORTS.md`; A2.1 guide links the exporter.

## Verification — 2026-10-30

Linux x86-64, Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, trimesh 5.2.0,
pytest 9.2.0, Ruff 0.17.3; `OPENBLAS_NUM_THREADS=1`. Actual Blender 4.5.0 Linux
from the checksum-verified archive. Official GNM v3 NPZ SHA-256:
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.

| Gate | Before | After |
|---|---|---|
| Pytest, official model enabled | 465 passed, 1 Windows-only skip | 501 passed, 1 Windows-only skip |
| Actual add-on ZIP/model/external Python | `BLENDER_SMOKE_PASS` | `BLENDER_SMOKE_PASS`, including `BLENDER_UNCERTAINTY_SUMMARY_PASS` |
| Ruff / diff check | Existing baseline | Pass |
| Wheel/sdist and installed wheel outside source tree | Existing packaging | Build passed; official-model CLI export and artifact parity checked |
| Default fitting replay | Previous seed-1902 manifest | Exact numeric manifest and OBJ/PLY hashes retained for statistical and local-correction modes |

The default fitting replay still contains the same `converged=false` max-iteration
warning in both modes; parity does not claim convergence or anatomical accuracy.
The new exporter deliberately refuses such unconverged records instead of
dropping their samples. No CT cases were evaluated.

Tests check known translation mean/variance, Welford versus NumPy ddof=1, mean of
posed vertices versus mean parameters, rigid-frame equivariance, no pose-removal,
prior separation, actual-sample selection, zero/duplicate ensembles, explicit
regions, nonfinite/reflected/malformed/nonconverged input, consistent clipping,
hash binding, source mutation, failed staging cleanup, concurrent destination
preservation, output hashes/bytes, PLY numeric fields and legacy OBJ compatibility.

## Official-model synthetic integration

A new A2.1 ensemble used the model mean with 48 markers, 253 components, 200
draws, seed 0, synthetic per-coordinate placement SD 0.2 mm, fixed lambda 30 and
explicit max_iter=100. Baseline and all draws converged; no clipped coefficients.
This SD is an engineering fixture value, not human placement-error data.

On the available AMD EPYC 9V74 host (9 logical CPUs, one BLAS thread):

- Sampling and JSON writing: 94.11 s (separate from the exporter).
- Export: 3.11 s, all 17,821 vertices; selected zero-based sample indices
  97, 118 and 198. Mean OBJ, SD PLY, three sample OBJs and summary produced.
- The installed wheel reproduced the same scenario statistics and every mesh/PLY
  artifact hash from the source-checkout export.

These timings describe one synthetic execution, not the user's Windows system,
an anatomical benchmark, or a performance guarantee.

## Scientific interpretations and deviations from TASKS.md

- The original request's “mean and 95% SD” is ambiguous. This implementation
  provides explicitly named mean dispersion and **spatial** P2.5/P97.5 of the
  dispersion field across region vertices. It does not substitute these for
  confidence/credible intervals or CT-calibrated coverage.
- An SD is not a hard bound on samples. The original “variants within reported
  SD” criterion is therefore not asserted or enforced by clipping. Actual draws
  are kept intact; distances and fractions within one 3-D spread are reported.
- “Plausible variants” are labelled representative simulation samples, without
  an unvalidated anatomical plausibility claim. The mean is a vertex average and
  need not correspond to one GNM coefficient/pose combination.
- Requested 3–5 variants can reduce to fewer distinct replays (one for a fully
  deterministic ensemble), with an explicit warning rather than duplicated faces.
- A fresh directory is required, and all scenarios must converge. No permissive
  export override or silent row removal has been introduced.
- Without reviewed region membership, only all vertices—including internal
  anatomy—are summarized. No anatomical thresholds or tissue values are invented.
- A2.3 analytic cross-check, A2.4 calibration, interactive workstation testing and
  independent CT validation remain separate. Local tests are Linux; Windows CI
  status must be checked independently for this commit.

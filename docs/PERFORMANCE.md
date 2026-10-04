# Blender preview performance: 18.0.1 / 5.0.0rc7

This patch responds to a Windows V18 slowdown after adding measurement points
and loading GNM. The actual user's `.blend`, Blender version and CPU have not
been profiled. The defects below were reproduced on a synthetic scene.

## Causes and changes

1. `_draw_live_section` called `_build_snapshot` to display a marker count.
   With skin-distance strength above zero, every redraw evaluated and hashed
   all registered bone geometry and hashed the 53 MB model file, even with
   live fitting stopped. Drawing now shares a cheap eligibility iterator with
   the snapshot builder, without snapshot construction or validation writes.
2. `_request_refit` built the same expensive snapshot on every property or
   depsgraph callback. It now records the request only. The timer reads the
   latest state once no new edit has arrived for 0.35 s (configurable).
   Starting Live explicitly still requests the first fit immediately.
3. Bone-only measurement changes requested refits with controls disabled.
   They no longer do so; turning strength on **or off** still requests a fit.
4. Conditional LOO repeated 384 augmented least-squares decompositions for
   48 markers and eight lambda values. It now computes 48 thin SVDs, reusing
   each across the grid. The weighted isotropic ridge solution is
   `V diag(s / (s² + lambda)) U.T b`; weights, fixed-pose CV convention,
   grid and scoring are unchanged. No normal equations or approximate CV.

The actual fit/export path retains input, duplicate, articulation and source
provenance checks. Evaluated source geometry is still freshly hashed on actual
measurement snapshots; no mesh hash cache can outlive geometry changes.
Preview uses the checksum established when its in-memory model was loaded.
Standalone document/CSV exports still hash the current disk file.
The core identity solver remains shared by the preview and offline pipeline.

## Measured evidence, 2026-10-04

Blender 4.5.0 official Linux build `8cb6b388974a`, bundled NumPy 1.26.4,
`OPENBLAS_NUM_THREADS=1`, Blender `-t 2`. Same host, sequential runs; baseline
commit `57a81d24163a51024bbd32e42d0eef4d0b1e213b` versus this patch. Fixture:
official GNM v3, seed 43, 48 nontrivial synthetic skin targets, 22 initialized
bone references and a 500,000-triangle plane registered as a source. The plane
tests geometry cost, not anatomy. Skin-distance strength 0.5, no enabled
distance bindings, no dense constraints. Active bindings and stale geometry
are exercised separately by `blender_craniometry_checks.py`.

| Operation | V18 | 18.0.1 |
| --- | ---: | ---: |
| Panel callback, median of 20 calls | 184.77 ms | 0.138 ms |
| Source evaluations / model file hashes in those redraws | 20 / 20 | 0 / 0 |
| Refit request callback, median of 20 calls | 180.63 ms | 0.00072 ms |
| Full adaptive fit, 30 sweeps | 0.686 s | 0.689 s |
| Full conditional-LOO fit | 9.338 s | 1.464 s |

Callback timings do not measure interactive frame rate or include the deferred
fit. The numerical fit remains synchronous, so long dense fits can still pause
the UI. Both runs chose lambda 1.0; final coefficients, transform and residual
RMS were identical in this fixture (adaptive RMS 1.273638 mm, LOO 1.274679 mm).
Both used the iteration budget; speed does not imply convergence or accuracy.
General ridge-path tests compare against independent augmented solves with
under/overdetermined, rank-deficient and poorly scaled designs to 1e-8 tolerance.
Raw metadata/results: [performance_v18.json](performance_v18.json).

This is headless Linux evidence, not a measurement of an RTX 5090 workstation,
a Windows frame-rate guarantee or an anatomical validation. No GPU fitting was
introduced. NumPy fitting, source evaluation and hashing are CPU operations.

## Reproduce

Set `GNM_MODEL_PATH` to the reviewed local official asset, then run:

```bash
blender --background --factory-startup --threads 2 --python-exit-code 1 --python tools/blender_benchmark.py
```

`GNM_BENCHMARK_REPO` can select a baseline checkout; the script itself must be
from this revision. `GNM_BENCHMARK_OUTPUT` writes full JSON including numerical
results. The benchmark creates a synthetic scene; run with factory startup.
Its wall-clock measurements are not brittle CI pass/fail thresholds. The
installed-ZIP suite separately prevents draw-time snapshots, verifies deferred
latest-position use, model checksum reuse, disabled-control behavior, error
reporting and stopping. Existing tests retain geometry-change rejection,
shared-fit equality and external process/import/cancel checks.

## Workstation use

Save the case, stop Live, disable the old add-on, install the complete new ZIP,
restart Blender and reload GNM. Existing marker coordinates and measurement
definitions are not migrated or moved by this patch.

Keep **Refit after idle (s)** at 0.35 initially. For editing, start with
**Conditional LOO tuning** and **Dense on each refit** off; record the intended
settings for the final run. Stop Live while placing many points if necessary,
then use **Run Offline Fit and Import** for expensive fits in the external
Python process. Extra RAM/VRAM does not accelerate these NumPy operations.

If slowdown persists, record the exact Blender/Windows/CPU versions, source
triangle counts, enabled modifiers, LOO/dense/distance settings, and the shown
fit time. Distinguish viewport rotation with Live stopped from the pause during
a fit. A pseudonymized `.blend` plus those settings permits specimen-specific
profiling; this patch does not prove all possible scene bottlenecks resolved.

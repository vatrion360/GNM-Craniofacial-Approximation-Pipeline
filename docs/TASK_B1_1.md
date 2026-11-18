# B1.1 — NumPy polyharmonic solver and shared bounded correction

Base: merged PR #45, `7a7b5f798f346509bc14562d86d95c70945fccae`.
Branch: `feature/numpy-local-spline`.

## Changes

- `cranio/tps.py`: independent NumPy implementation of the **existing** 3-D `-r`
  radial system with affine tail and zero smoothing; numerical rank/solve checks,
  detached diagnostics, chunked evaluation and no implicit fallback.
- `cranio/optimize.py`: keyword-only backend selector, SciPy default unchanged;
  shared cap/damping arithmetic and explicit invalid mesh/protected-index errors.
- Tests for parity, affine/rigid behavior, invalid/degenerate inputs, default
  exact equality, NumPy-only execution and official-mesh 700-centre correction.
- Installed-ZIP Blender test compares the NumPy result to an external SciPy
  oracle, with forbidden numerical dependency imports blocked during evaluation.
- Reproducible benchmark, documentation, packaging and roadmap updates.

## Verification

Baseline: **1307 passed, 1 skipped**, official model, Python 3.12/Linux,
`OPENBLAS_NUM_THREADS=1` (87.58 s). Baseline Windows/Linux Blender evidence is the
merged PR #45 CI; its source tree is unchanged by the merge. Local Blender remains
unavailable. Initial focused suite: **76 passed**, including official-mesh parity.
Final suite: **1375 passed, 1 skipped** (96.42 s), including 68 new tests. Ruff
and whitespace checks passed. Build and hosted CI outcomes are recorded on the PR. The new marker is
`BLENDER_NUMPY_SPLINE_PARITY_PASS`.

The benchmark uses synthetic displacement vectors, not CT cases or anatomical
measurements. Its JSON records single-run timings and actual maximum field/vertex
differences against SciPy, along with runtime and implementation identity.
On the recorded shared Linux x86_64 runtime (Python 3.12.14, NumPy 2.3.5,
SciPy 1.17.0, OpenBLAS with one thread), a sequential run at 700 centres and
17,821 vertices took **0.237 s SciPy / 1.294 s NumPy**. Maximum Euclidean
differences were **4.638e-11 mm** before caps and **4.552e-11 mm** at final vertices.
The NumPy implementation was slower in this benchmark. This supports numerical
portability, not a speedup claim or CT accuracy claim. No exposed CPU-model name
was available; timings depend on shared-runtime load and are not guarantees.

## Scope and deviations

This is B1's numerical foundation, not a completed Blender Finalize workflow.
The current source uses `linear (-r)` in 3D, not the 2-D `r² log(r)` kernel named
in older task descriptions; changing the kernel would break mathematical parity.
The choice was taken directly from the existing implementation.

No CLI/Blender backend selector, automatic finalization, new centres, caps, source
tables, smoothing, anatomical constants or validation claim is added. Existing
offline calls still use SciPy; new code is opt-in through the numerical API.
Near-singular NumPy systems fail rather than guessing an alternative fit. Invalid
protected IDs and mesh shapes now fail clearly in both backends. CT evaluation
remains manual. The next B1 increment must bind shared centre preparation and
the new solver to a reversible Blender operation with provenance and QC.

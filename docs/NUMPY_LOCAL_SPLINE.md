# B1.1 — NumPy local-correction backend

The shared numerical API now offers a NumPy-only implementation of the existing
3-D local displacement spline. This prepares B1 finalization inside Blender;
**this increment does not add a Finalize button or change live/offline defaults**.
The offline pipeline still calls the default SciPy backend, now through
[shared preparation](LOCAL_CORRECTION_PREPARATION.md). SciPy remains an
offline dependency. No centres, targets, caps, weights or mesh topology change.

## Explicit numerical API

```python
from cranio.optimize import bounded_tps_correction

final_mm, field_mm, prescribed_magnitudes_mm = bounded_tps_correction(
    vertices_mm, centres_mm, prescribed_vectors_mm, per_vertex_caps_mm,
    protected_idx=protected_vertex_indices,
    protect_damping=0.25,
    backend="numpy",
)
```

All positions/vectors/caps are in the same world-mm frame. The caller supplies
the actual centres, prescribed displacement vectors and regional caps. The
example damping is the existing offline default, not a newly validated value.

| API option | Default | Contract |
|---|---|---|
| `backend` | `scipy` | Explicit `numpy` selects the new solver; unknown names fail |
| `protected_idx` | `None` | Distinct in-range integer vertex IDs; invalid masks/indices fail |
| `protect_damping` | 1.0 at numerical API level | Existing multiplier in [0, 1]; pipeline supplies its own existing default |
| `LinearPolyharmonic3D.__call__(..., chunk_size=...)` | 2048 | Evaluation batch size only; no centre subsampling |

For uncapped evaluation and numerical diagnostics, use
`LinearPolyharmonic3D(centres_mm, vectors_mm)` from `cranio.tps`; call the resulting
object on evaluation points and inspect its detached `.diagnostics` dictionary.
Do not interpret its uncapped output as an approved facial surface. Empty query
arrays are supported by this low-level evaluator; the bounded mesh API requires
a nonempty mesh.

## Mathematical contract

Despite the historical `tps` name, the current pipeline uses SciPy
`RBFInterpolator(kernel="linear", degree=1, smoothing=0.0)`: radial kernel `-r`
and an affine tail. It does **not** use the `r² log(r)` kernel named
`thin_plate_spline` in SciPy. The public
[SciPy RBFInterpolator documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.RBFInterpolator.html)
specifies these kernels and the augmented interpolation equations. The new code
implements that system independently using NumPy.

For normalized centre coordinates `q_i = (c_i - origin) / scale`, let
`K_ij = -norm(q_i - q_j)` and `P_i = [1, q_ix, q_iy, q_iz]`. Solve the block system
with rows `[K, P]` and `[P.T, 0]`, against `[D, 0]`, using `numpy.linalg.solve`.
The solution gives `f(x) = K(x, q) A + P(x) B`. Translation and uniform coordinate
scaling are internal conditioning operations; at zero smoothing they retain the
same physical interpolant. Displacement outputs remain in mm.

The existing cap/damping arithmetic stays in **one shared function**, after
either backend computes the field. Vector magnitudes are limited once using
`cap * tanh(norm(field) / cap)`, followed by the protection multiplier. The
existing small-norm safeguard is retained. The default SciPy branch is checked
against the previous arithmetic with exact array equality.

## Degeneracy and numerical limits

The existing `validate_points(minimum=4, rank=3)` preflight is retained, including
its legacy rank/scale guards. Duplicate centres, nonfinite data, coplanar or
near-coplanar centre geometry fail. Mesh inputs and protected indices now receive
explicit shape/index checks rather than permitting accidental broadcasting or
negative-index selection.

The NumPy backend additionally requires full numerical rank of its augmented
system using `size * float64_epsilon * largest_singular_value`. It checks the
relative backward error against `64 * size * float64_epsilon`. These are numerical
acceptance criteria, not anatomical thresholds. Some near-duplicate arrangements
that SciPy attempts to solve can therefore be refused by the opt-in backend.
There is no least-squares fallback, jitter, regularization, smoothing or inferred
replacement of missing landmarks.

Diagnostics include rank, condition number, coordinate normalization and backward
error. A small residual does not establish a small forward error or anatomical
validity. Caps bound displacements only; they do not guarantee absence of
self-intersections or plausible anatomy. Existing post-fit QC remains necessary.

The dense solve uses quadratic centre storage and cubic factorization work;
evaluation is chunked, but all centres contribute. Do not use this as a per-marker
continuous-refit operation. No GPU acceleration or cross-platform speed claim is
made. The external pipeline remains available for long computations.

## Verification and benchmark

- Synthetic interpolation/extrapolation, affine reproduction, zero fields,
  rigid transforms/scales, input immutability and invalid/degenerate inputs.
- SciPy/NumPy parity before and after caps/damping; engineering tolerance
  `1e-6 mm`, not a CT accuracy claim.
- Official 17,821-vertex asset with 700 unique physical centre positions and
  seeded **synthetic** displacement vectors. Model weights are not redistributed.
- Hosted installed-ZIP Blender test blocks numerical imports of SciPy, trimesh,
  TensorFlow and `bpy` during the NumPy call; an external Python generates the
  separate SciPy oracle. It checks all output vertices and preservation of inputs.

Reproduce the benchmark with a new output path:

```bash
OPENBLAS_NUM_THREADS=1 python tools/benchmark_local_spline.py --model models/gnm_head.npz --output spline-benchmark.json
```

On Windows PowerShell set `$env:OPENBLAS_NUM_THREADS = '1'` before running the
Python command. The recorded [benchmark JSON](benchmark_numpy_spline.json)
contains actual timings, Euclidean maximum discrepancies, versions, BLAS/thread
details, model and implementation hashes. It uses one sequential run per backend
without warm-up; timings are descriptive, not a performance guarantee. The shared
Linux runtime does not expose a CPU model through `platform.processor()`.

This is the numerical foundation of B1. [B1.2](LOCAL_CORRECTION_PREPARATION.md)
adds shared centre assembly and a selection audit. A reversible Blender Finalize
operator, scene-bound result provenance and its end-to-end QC remain pending. CT evaluation remains manual. See [task evidence](TASK_B1_1.md).

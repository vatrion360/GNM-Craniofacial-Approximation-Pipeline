# Marker-error propagation (A2.1)

This opt-in engine repeatedly calls `cranio.optimize.fit_identity`. It reports
**uncalibrated propagation of specified input errors**, not the probability that
a face is correct, a posterior over human faces, or validated confidence intervals.
Existing live fitting, external fitting and displacement heatmaps are unchanged.
The latter still do not represent uncertainty.

## Scope and assumptions

- Marker-only statistical fitting. Similarity pose, identity, Huber weights and,
  with `--regularization auto`, conditional LOO lambda are refitted for each draw.
  Base weights remain the CSV confidences; the separate `--depth-weighting sd`
  sensitivity option is not enabled by this command.
- No dense constraints, craniometry loss, automatic exclusion, TPS or post-fit
  presentation controls. This command does **not** reproduce a session with those
  options enabled and must not label that session's final mesh with its results.
  Excluded CSV rows remain excluded.
- Bone/target pairs translate by independent isotropic placement noise. The
  supplied `sigma_mm` is **one Cartesian coordinate's SD**, not a 3-D displacement
  distance, radial RMSE, or the SD of distances between repeated placements.
  Conversion from repeat measurements requires a justified statistical model;
  no automatic conversion is provided in A2.1.
- Depths follow independent parent normal distributions with supplied means/SDs,
  conditioned on depth >= 0. Rejection sampling avoids artificial probability
  mass at zero. Truncation changes the resulting mean and SD: supplied values
  describe the parent, not the truncated moments. Normality and independence
  are modelling assumptions, not established by the tissue-table schema.
- Axes stay fixed. Placement noise does not recompute normals, slide anchors
  over a skull surface, model directional error or compensate for correspondence
  bias, missing bone, segmentation error, model/population mismatch or systematic
  operator error.
- Priors are **separate scenarios with paired draws**, never pooled as posterior
  samples. A supplied prior uses the shared solver's existing default weight 1.
  Head-only fitting keeps inactive coefficients zero under the existing contract.

## Input errors

Create placement JSON with exact included CSV labels. This intentionally
incomplete example makes no numerical assumption:

```json
{
  "schema_version": 1,
  "placement": {
    "Nasion": {"sigma_mm": null, "source": null}
  }
}
```

Supply measured/documented SDs and their sources, or explicitly stated scenario
assumptions. Missing entries and null values remain unknown. Unknown/excluded
labels, extra fields, duplicate JSON keys, negative/nonfinite SDs and configured
SDs without a source statement are rejected. Structural validation does not
verify a source scientifically. Explicit zero means held fixed, not certain.

For depth sampling select a versioned table and exact `--depth-labels`. Only those
depths are replaced by table central values; other targets retain their CSV values.
Source mode reuses A1.5's reviewed direction manifest. Existing-axis mode is an
explicit sensitivity scenario, without establishing equivalence to the source's
measurement direction. v3 bone coordinates are required for depth sampling.
Legacy CSVs can be used for placement-only propagation, with a provenance warning.

`estimator=mean` is required when a depth SD is supplied. The engine does not
reinterpret medians, shorth or 75-shormax as normal means. Bundled legacy/Table 2
data currently have no documented SDs; selecting them cannot create a depth
uncertainty distribution.

Missing requested errors block sampling by default. `--allow-partial` holds
unknown terms fixed only if at least one other SD is configured. The result is
labelled `partial_conditional_sensitivity`; omitted terms are listed and their
nulls preserved. No fabricated placeholder SD is inserted. If all SDs are
unknown, no ensemble is produced. All-zero configured SDs produce a prominently
labelled deterministic replay. Missing depth SDs in partial mode fix selected
depths at the table central values; they do not restore the previous CSV depths.

## CLI

After preparing a placement file for the actual labels:

```bash
python -m cranio.uncertainty --input markers.csv --npz models/gnm_head.npz --placement placement_error.json --samples 200 --seed 0 --regularization 30 --output outputs/case01/marker_ensemble.json
```

| Option | Default | Meaning |
|---|---|---|
| `--input`, `--npz`, `--output` | Required | Marker CSV, unchanged local model, new JSON output |
| `--placement` | Missing | Per-label error JSON; no imputation |
| `--samples` | 200 | Perturbations per prior scenario; integer >= 2 |
| `--seed` | 0 | Nonnegative PCG64 seed; no global NumPy random state |
| `--max-iter` | 30 | Shared solver iteration budget per fit; increase explicitly without relaxing tolerances |
| `--allow-partial` | Off | Conditional sensitivity with missing errors held fixed and listed |
| `--tissue-table` | None | Table for explicitly requested depth labels |
| `--depth-labels LABEL ...` | Empty | Selected mean/SD depth rows; other depths fixed |
| `--tissue-axis existing/source` | Unconfigured | Explicit policy required for depth sampling |
| `--tissue-directions FILE` | None | Reviewed manifest required for source mode |
| `--regularization` | 30 | Fixed positive lambda or `auto` reselected per draw; not the add-on's adaptive-count policy |
| `--identity-subspace all/head` | all | Shared identity subspace contract |
| `--prior` | None | Optional safely loaded prior NPZ |
| `--prior-variants off on` | off | One/both scenarios; `on` requires a prior and vice versa |

Output must not already exist or alias an input. Inputs are hashed before the run
and checked again before atomic publication. Failed draws abort the run; they
are not discarded or resampled to hide numerical failure. Nonconverged fits and
clipped components are retained, indexed and warned about, including the baseline.
Success means the computation was recorded, not that all fits converged or that
the result is anatomically valid. Inspect each scenario's `numerical_status` and
last-iteration changes before interpretation. The task benchmark needed more
than the default 30 iterations; see [verification](TASK_A2_1.md).

## Output and replay

JSON records input hashes/marker metadata, software and implementation hashes,
sources and omitted errors, table/direction provenance, central/perturbed targets,
actual draws, and central plus sample fits for each prior scenario. Each fit
includes coefficients, similarity transform, lambda, residuals, convergence,
clipping, conditioning and final Huber weights. No scan or face mesh is embedded.
Marker coordinates remain potentially sensitive case data; outputs are not
automatically published or committed.

Reconstruct each statistical surface in the original world-mm frame, without a
new registration:

```python
vertices_mm = sample["scale"] * (
    model.generate(sample["coefficients"]) @ np.asarray(sample["rotation"]).T
) + np.asarray(sample["translation_mm"])
```

There is no sample re-alignment to suppress pose variability. Identical inputs,
seed and numerical environment give identical records; cross-platform bit
identity is not promised. Timings/timestamps are excluded from the record.

[A2.2](UNCERTAINTY_EXPORTS.md) now exports mean meshes, numerical SD/spread fields
and representative samples from this JSON, requiring converged scenarios.
A2.3 (analytic comparison under an explicit linear/fixed-pose model) and A2.4
(external calibration) remain subsequent tasks. No coverage, 95% interval or
calibrated confidence is claimed here.

## Developer checks

Synthetic tests cover known zero-error truth, exact shared-solver parity, paired
scenarios, partial-input refusal/labelling, truncation moments, source axes,
failed/nonconverged draws and atomic output safety. The actual Blender ZIP
exercises the NumPy engine; this task adds no interactive sampling button.

Runtime-only benchmark (0.2 mm is an explicitly synthetic engineering input,
not a recommended placement SD):

```bash
OPENBLAS_NUM_THREADS=1 python tools/benchmark_uncertainty.py --npz models/gnm_head.npz --sigma-mm 0.2 --samples 200 --seed 0 --max-iter 100
```

On Windows set `OPENBLAS_NUM_THREADS` in the shell environment before Python.
See [task verification](TASK_A2_1.md) for measured timings and convergence.

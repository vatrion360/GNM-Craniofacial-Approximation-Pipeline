# A2.2 — mean surfaces, simulated spread and representative samples

The exporter consumes an existing A2.1 JSON record; it does not fit the model
again. Every scenario's baseline and samples must have converged. Malformed,
inconsistent, reflected or nonfinite replay transforms are rejected. No samples
are silently removed. For nonconverged input, inspect A2.1 diagnostics and rerun
with an explicit larger iteration budget; do not edit convergence flags.

```bash
python -m cranio.uncertainty_export --ensemble marker_ensemble.json --npz models/gnm_head.npz --output-dir outputs/case01/spread --variants 3
```

| Option | Default | Meaning |
|---|---|---|
| `--ensemble FILE` | Required | A2.1 JSON with replay parameters and input hashes |
| `--npz FILE` | Required | Exact model recorded among the ensemble's input hashes |
| `--output-dir DIR` | Required/new | Existing folders, including empty folders/symlinks, are refused |
| `--variants {3,4,5}` | 3 | Requested representative sample count; fewer if fewer distinct replays exist |
| `--regions FILE` | None | Explicit hash-bound anatomical vertex sets; no inferred anatomical partition |

The command is standalone and opt-in. Existing marker fitting, live preview,
offline fitting and displacement PLYs are unchanged. No interactive export
button is added in this task; the NumPy summary code is exercised inside Blender.

## Files

Prior scenarios remain separate in `prior_off/` and/or `prior_on/`:

| File | Meaning |
|---|---|
| `mean.obj` | Vertex-wise arithmetic mean of posed statistical surfaces, world mm |
| `spread.ply` | Same mean surface, numerical coordinate SDs and 3-D RMS spread; greyscale display |
| `variant_01.obj`, etc. | Actual selected simulation samples, unchanged; their indices appear in comments and JSON |
| Root `summary.json` | Completion marker: source/model/region and output hashes, settings, statistics, selections and warnings |

No new alignment, ICP or Procrustes operation is applied. Pose/scale variability
therefore contributes to the spread. The mean is computed after each sample's
own transformation; averaging coefficients/transforms instead is generally not
equivalent. The mean need not be representable as a single GNM identity and pose.
Topology and vertex correspondence are preserved, but neither the mean nor the
selected samples receive an anatomical plausibility or collision guarantee.

OBJ coordinates use the existing six-decimal mm serialization. PLY uses double
properties with 17 significant decimal digits. All OBJ/PLY headers identify
uncalibrated simulation and the partial/configured analysis status. The PLY has
`sd_x_mm`, `sd_y_mm`, `sd_z_mm` and `spread_rms_mm`. A shared greyscale runs from
black at zero to white at the maximum across all exported prior scenarios. The
numeric range and units are in the header and summary; all-zero spread is black.
Colours are a display mapping, not confidence categories.

## Definitions

For N sampled world-frame vertex coordinates x_jv:

- Mean: m_v = sum_j(x_jv) / N.
- Coordinate variance: s_vk² = sum_j((x_jvk - m_vk)²) / (N - 1), for k = x,y,z.
- `spread_rms_mm` = sqrt(s_vx² + s_vy² + s_vz²), the square root of the trace of
  sample covariance. Equivalently it is sqrt(sum_j(||x_jv-m_v||²)/(N-1)).

Welford accumulation computes the mean and coordinate variances without storing
all full meshes. These are sample dispersions, not standard errors of the mean.
`spread_rms_mm` is **not** the SD of radial distances, a 95% radius, a credible
interval, or a bound on facial accuracy. Multiplying it by 1.96 would not create
a calibrated 3-D coverage region. Correlations, model bias and missing error
terms retain the limitations of [A2.1](UNCERTAINTY.md).

## Representative variants

Selection starts with the sample nearest the beta-space centroid, then chooses
the farthest sample from those already selected (Euclidean beta distance).
Ties use input index; exact duplicate coefficient/pose replay vectors are removed.
The requested count is 3–5, but identical deterministic simulations yield just
one distinct variant. Distances do not include pose, so pose-only differences
can be underrepresented by this selection strategy; ties are not quantiles.

Variants are actual draws, not interpolated faces, quantile surfaces, bounding
surfaces or independently validated plausible reconstructions. They may exceed
one SD locally. The summary provides sample indices, coefficients, maximum
Euclidean distance from the mean, regional mean distances and the fraction of
vertices within one `spread_rms_mm`. That fraction is descriptive and is not an
empirical calibration/coverage score against known faces. No geometry is clipped
to meet a claimed one-SD bound.

## Regions

Without `--regions`, only `all_vertices` is reported, including eyes/teeth/internal
geometry. This is not automatically a facial-skin ROI. An explicit region file
has fields:

- `schema_version`: 1;
- `model_sha256`: exact selected NPZ digest;
- `regions`: object mapping chosen region names to `vertex_indices` (nonempty,
  distinct in-range integers) and `source` (definition/review statement).

`all_vertices` is reserved. Regions may overlap; their membership is recorded in
the summary. Empty, duplicate, out-of-range, boolean or noninteger indices and
model-hash mismatches are rejected. Region names are never used as file paths.
No anatomical thresholds or source data are fabricated to populate this file.

For each region the JSON provides vertex count, mean coordinate SDs, the mean
3-D spread, and spatial P2.5/P97.5 of that spread across vertices. These percentiles
describe the distribution of the field **across the selected vertices**, not a
95% interval for a person's face, a mean, or an SD estimate. Each vertex is equally
weighted; this is not an area-weighted surface statistic. Sampling-density and
ROI selection affect these summaries.

## Provenance and failure handling

Model hash must occur among the ensemble input hashes; an embedded marker model
hash, if supplied, must also agree. This checks file consistency, not scientific
authenticity of an edited ensemble. Embedded historical source paths are not
opened. The current ensemble, NPZ and optional region file are independently
hashed and checked again before publication.

Files are staged in a temporary sibling directory. On failure it is cleaned;
no completed bundle is published. After all outputs and the summary are written,
the new directory is renamed into place. Existing outputs are never intentionally
replaced; concurrent creation is checked again before publishing. Hashes refer
to artifact bytes; the summary does not recursively hash itself. Timestamps are
omitted, so repeated exports with the same inputs/environment are byte-identical.

Source warnings, omitted error terms, partial-analysis status and coefficient
clipping remain visible. Nonconvergence blocks export rather than changing the
sample population. Outputs are **uncalibrated simulated dispersion**, not full
dense/TPS final-fit uncertainty, known facial accuracy or calibrated confidence.
A2.3 analytic comparison and A2.4 external calibration remain separate tasks.
No CT-derived validity claim is added by this exporter.

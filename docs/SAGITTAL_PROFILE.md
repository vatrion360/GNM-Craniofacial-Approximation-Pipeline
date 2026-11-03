# Optional reviewed sagittal profile (A4.4)

This experimental **offline** stage refines identity at the baseline similarity
pose. It is off by default. Blender's **Run Offline Fit and Import** and the CLI
use the same `cranio.profile` NumPy implementation; live preview remains the
baseline shared `fit_identity` result. No source-derived depth, SD, normal,
anatomical path, plausible range or missing-bone position is guessed.

## Configure and run

```bash
python -m cranio.profile --template profile_constraint.json
# Fill and independently review the manifest before use.
python gnm_reconstruct.py --input markers.csv --npz gnm_head.npz \
  --profile-constraint profile_constraint.json --output profile_face.obj
```

In Blender select **Offline fit → Reviewed sagittal profile offline**, select
the reviewed JSON, then **Run Offline Fit and Import**. The JSON is copied into
the new case folder and its SHA-256 is recorded. Disabling the checkbox ignores
the path. Creating a blank template refuses overwrite; null fields cannot fit.
No JSON editor, automatic chain extractor or interactive profile preview is
included in this increment.

The current combination requires marker-only statistical fitting. Dense skull
constraints, prior, symmetry/distance/craniometry loss, soft prior, local
correction, automatic outlier exclusion, tissue comparison and frozen protocols
are rejected rather than silently omitted. An individual selected tissue table
can still define the baseline marker targets; profile depths/SDs are separately
explicit in the manifest and must have their own documented source. Existing
uncertainty tools do **not** propagate this refinement.

## Manifest contract (schema 1)

All coordinates and lengths are in the same world-mm frame as the marker CSV.
Supply every field produced by the template; extra fields are rejected.

| Field | Required meaning |
|---|---|
| `model_sha256`, `case_id` | Exact current model hash and marker CSV case ID |
| `source` | Source/protocol and justification for this case's profile construction |
| `mapping_reviewed` | Explicit human review of anatomical labels, skin correspondence and order |
| `mandible_reviewed` | Explicit articulation review; CSV `mandible_articulation_reviewed` must also be true |
| `plane` | `origin_mm`, nonzero `normal_world`, documented `source`, `reviewed: true` |
| `plane_tolerance_mm` | Explicit positive allowed deviation from the reviewed plane; no anatomical default |
| `segments` | Ordered lists of vertex IDs, each at least two; distinct IDs across all segments |
| `gap_notes` | One documented reason per break between segments; breaks are never interpolated |
| `samples` | One observed, reviewed bone/depth sample per vertex, in the same flattened order |
| `strength` | Positive dimensionless profile-block multiplier |
| `delta_regularization` | Positive dimensionless ridge penalty on the coefficient increment |
| `marker_preservation_weight` | Nonnegative marker-displacement penalty, in mm^-2 |
| `marker_displacement_limit_mm` | Nonnegative hard per-marker displacement limit from baseline |

The plane is explicitly reviewed, not inferred from a damaged skull. A4.2's
independent midsagittal plane may inform it only after the operator verifies
its applicability; the Frankfort YZ plane is not silently substituted.

Each vertex must be self-mirrored in the current GNM template and consecutive
vertices within each segment must share a triangle edge. These topological
checks do **not** certify anatomy. The first sample must be labelled `Glabella`
and the last `Menton`; all sample labels must be unique. Human review must
confirm the order and that points belong to the intended skin profile, excluding
dental, oral-interior or unrelated surfaces. Anatomical labels and endpoints
are not inferred from a vertex index. Use separate segments for missing bone or
surface breaks (including the mouth); never join them with an invented curve.

Every sample has exactly these fields; nulls below denote unconfigured data,
not usable numerical values:

```json
{
  "label": "Glabella",
  "bone_xyz_mm": null,
  "normal_world": null,
  "source_id": null,
  "source_geometry_sha256": null,
  "status": "observed",
  "reviewed": false,
  "depth_mm": null,
  "sd_mm": null,
  "tissue_source": null,
  "direction": "bone_normal"
}
```

Review covers bone placement, outward normal, correspondence, depth and SD
applicability. `tissue_source` documents the provenance of **both** depth and SD.
`source_id` and hash must match the CSV's registered `bone_sources`; mirrored or
donor samples are refused. Hash matching checks the recorded source identity,
not point-on-surface correctness or whether the observation was made honestly.
Verify the supplied points/normals against the preserved bone before marking
reviewed. Missing mandible or endpoints makes this complete-profile option
unavailable; it does not synthesize them.

Depth must be finite and nonnegative; SD finite and positive. Only an explicitly
reviewed `bone_normal` direction is currently supported. A table measured in a
different direction is not converted implicitly. Bone points **and** derived
skin targets must lie within the declared plane tolerance. SD sets soft relative
influence, not an empirical confidence interval or permission to bypass review.

## Mathematics and acceptance

Let baseline coefficients be beta0, fixed similarity `(s, R, t)`, and
`V0 = s * (generate(beta0) @ R.T) + t`. For profile sample j, the target is
`q_j = bone_j + depth_j * normal_j / ||normal_j||`. No projection or curve
interpolation is applied: the residual is a full 3-D world-mm distance.

For active identity components only, let J be the world-space identity basis.
The coefficient increment delta minimizes the augmented least-squares objective:

```
(strength / N) * sum_j ||V0_j + J_j delta - q_j||^2 / sd_j^2
+ marker_preservation_weight * sum_i (w_i / sum(w)) * ||J_i delta||^2
+ delta_regularization * ||delta||^2
```

N is the number of profile samples; w are the effective baseline marker weights,
including optional SD weighting. The second term preserves marker **positions**,
not the original target objective. The solve uses `numpy.linalg.lstsq`; nonfinite
or numerically rank-deficient systems fail clearly. The candidate is
`clip(beta0 + delta, -clip_sigma, +clip_sigma)` for active components; inactive
coefficients stay exactly unchanged. This is not the constrained ridge optimum
and not a joint MAP estimator. Baseline lambda selection/IRLS is not rerun.

Accept only if all three gates pass after clipping:

1. No configured profile point has a greater target residual than at baseline.
2. Every included fit marker moves at most `marker_displacement_limit_mm`.
3. All configured profile vertices remain within the reviewed plane tolerance.

Comparisons use a recorded scale-dependent floating-point tolerance (64 machine
epsilons times the maximum absolute coordinate or 1). It is a numerical tolerance,
not an anatomical threshold. A failed gate preserves the baseline coefficients
exactly and reports `baseline_retained`; it is not silently labelled improved.
Malformed, unreviewed or incompatible inputs stop the run before export.

## Audit and interpretation

The JSON contains the complete manifest, baseline/candidate/final coefficients,
active indices, rank/singular values, gate results, numerical tolerance and
before/candidate/final residual per profile point in mm. It records maximum
marker displacement and fixed-pose policy. Text output lists per-point results.
`solver`, its iteration history, convergence, clipping and IRLS diagnostics
remain explicitly scoped to the **baseline** fit. For profile runs, per-marker
IRLS weights are named `baseline_final_irls_weight`. Top-level exported coefficients
and fit residuals describe the final accepted mesh. The ordinary displacement
PLY remains the local-correction diagnostic, not a profile-improvement heatmap.

A statistical coefficient change can move unconstrained regions; these gates
cannot certify the rest of the face or bone penetration. More samples in a
region change its influence; samples are not assumed independent observations
for uncertainty estimation. No CT accuracy, calibration, anatomical sufficiency
or complete-profile recovery claim follows from reduced training residuals.
Use the existing geometric QC and review the full face. CT evaluation remains
an independent task, performed by the user on held-out faces.

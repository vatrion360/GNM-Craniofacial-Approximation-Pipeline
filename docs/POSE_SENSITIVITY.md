# Mandibular pose sensitivity (A4.6)

This opt-in analysis evaluates **hypothetical rigid poses** around the reviewed
baseline assembly. It reports changes in observed/reviewed bone references,
configured cranial features and optional bone-to-skin profile targets. It never
moves Blender objects, rewrites source hashes, selects an optimal jaw position,
or refits a GNM face. All pose ranges, tissue values and thresholds are explicit
operator inputs; no population or anatomical limits are supplied.

## Workflow

```bash
python -m cranio.sensitivity template --output sensitivity_config.json
# Fill/review the null fields and feature definitions before computing.
python -m cranio.sensitivity compute --input craniometry.json \
  --config sensitivity_config.json --output pose_sensitivity.json
```

The input is the current world-mm craniometry JSON, not the marker CSV. In Blender,
use **Mandibular Pose Sensitivity → Write Blank Configuration**, configure the
JSON, then **Compute / Export Pose Scenarios**. The addon uses current craniometry
observations and the same NumPy core as the CLI. The baseline articulation must be
reviewed; stale or pending A4.5 articulation is refused. Review moved bone-point
definitions after A4.5 before measuring them. Results are written to a new JSON
and `GNM_Pose_Sensitivity` Blender text. Existing files and input paths cannot be
overwritten. No calculation occurs on redraw or marker movement.

## Configuration (schema 1)

| Field | Required meaning |
|---|---|
| `case_id`, `reviewed`, `source` | Matching case ID, explicit review and rationale/source for this scenario study |
| `moving_sources` | Nonempty list of `{id, geometry_sha256}` matching current sources explicitly classified `MANDIBLE` |
| `pivot_mm` | Explicit world-mm rotation pivot; not an inferred joint centre |
| `axes_world` | Right-handed orthonormal 3×3 matrix; **columns** are the local axes in world coordinates |
| `translation_mm` | Three `[lower, upper]` intervals for translations along these axes |
| `rotation_deg` | Three `[lower, upper]` intervals for right-handed rotations about these axes |
| `samples`, `seed` | Explicit nonnegative integer random-draw count and seed; zero draws is allowed |
| `feature_config` | Complete A4.3 configuration, including reviewed baseline `mandible_pose`; `uncertainty` must be null |
| `profile` | Null by default; optional reviewed profile-target definitions below |

Every interval must be finite, ordered and include zero, the baseline offset.
`[0, 0]` fixes a degree of freedom; it does not assert zero empirical uncertainty.
All selected sources move as **one rigid group**; other sources remain fixed.
For independently moving fragments, run separately specified studies; this
implementation does not construct a joint multigroup pose distribution.

A moving source cannot contain cranial/nonmandibular reference codes. This avoids
moving the cranial frame with the jaw or silently compensating an anatomical
registration error. Missing, reconstructed, unreviewed or stale bone points remain
unavailable. Missing opposite-side anatomy is not inferred. At least one reviewed,
observed point on a selected source is required. Source hashes bind the baseline
observations; derived poses are recorded separately, never as new observed scans.

Feature definitions, projections, units and threshold hashes follow
[CRANIAL_FEATURES.md](CRANIAL_FEATURES.md). No skeletal class is assigned without
an explicitly supplied, source-documented threshold rule bound to the exact
feature definition and units. `source` in the scenario configuration should state
why the pose ranges, pivot and axis convention are appropriate for this case.

## Sampling and transform

The engine evaluates, in order:

1. The exact baseline (all offsets zero).
2. Every unique combination of lower/upper endpoints of the six intervals.
3. `samples` independent uniform draws within the six-dimensional box using PCG64
   and the supplied seed.

Duplicate parameter tuples are removed, preserving first occurrence. There are
at most `samples + 65` unique poses; fixed axes reduce that count. Corners are
included to expose endpoints; neither corners nor random draws prove that a
nonlinear metric reaches its continuous extrema there. The mixed scenario set
is **not a probability sample** of actual jaw position. No 95% confidence interval,
posterior distribution, empirical SD or calibrated uncertainty is reported.

For column-vector point p, axis matrix A and pivot o:

```
R = A @ Rz(rz) @ Ry(ry) @ Rx(rx) @ A.T
p_scenario = o + R @ (p - o) + A @ translation
```

Rotations are applied about fixed local axes in X, then Y, then Z order, followed
by translation. The baseline matrix is exactly identity. Normals use R only,
without translation. Frame-based metrics reuse the explicit A4.3 frame geometry;
cranial frame references cannot be selected as moving references.

Static metrics and 3-D Euclidean distance/ratio/angle constructions whose points
all share the same rigid motion retain their baseline value exactly. This uses
their mathematical invariance and prevents roundoff from creating a false
threshold crossing. Projected or frame-relative metrics are recalculated.

## Optional profile targets

The optional profile describes ordered **bone reference codes**, not a GNM vertex
chain. It is not interchangeable with A4.4's model-bound fitting manifest.
Its keys are `reviewed`, `source`, `segments`, `gap_notes` and `points`.
Each segment lists at least two distinct registered bone codes; all codes are
unique across segments. Each break has an explicit note and is never interpolated.
Each code has this definition (nulls are unconfigured and cannot compute):

```json
{
  "depth_mm": null,
  "normal_world": null,
  "tissue_source": null,
  "reviewed": false,
  "direction": "bone_normal"
}
```

Supply a finite nonnegative depth, nonzero reviewed outward normal, and documented
source. Only `bone_normal` is supported. Depths stay fixed across pose scenarios;
this is not tissue-depth uncertainty propagation. The target is the transformed
bone point plus depth times the transformed unit normal. Cranial normals remain
fixed. Each available target reports all world-mm positions, per-coordinate
sampled ranges and maximum displacement from baseline. Missing endpoints remain
unavailable; adjacent gaps are not filled and no planar projection is imposed.

## Output and interpretation

JSON contains the complete configuration, case ID, baseline input signature,
CLI input/config hashes (or Blender canonical input hash), implementation hash,
software/NumPy versions, all pose parameters and world matrices, landmark
trajectories, unavailable-point reasons, baseline feature results, each scenario
value/failure, sampled min/max and the pose indices producing those extrema.
Classification reports `no_thresholds_configured` when no rule exists. If sampled
extrema span different configured classes, the label is **`indeterminate`**.
Threshold equality follows A4.3's `searchsorted(..., side='right')` convention.

If any scenario makes a feature undefined, that feature's range is withheld and
the failed pose/reason remains visible. No favourable subset is selected. Signed
angles crossing the ±180-degree branch also withhold a linear range. Other valid
features remain available. An unavailable/failed feature with a threshold is
reported indeterminate. Profile coordinate bounds are separate axis bounds, not
a coherent new face or a jointly realizable extreme point.

No pose is silently discarded because of dental contact, penetration or anatomical
plausibility. Use A4.5 checks and expert review to choose/document a defensible
scenario domain. The analysis does not replace occlusal evaluation, full-surface
collision checks, uncertainty calibration or independent CT validation. Placement
MC, depth sampling, facial-fit ensembles and combined multigroup sensitivities are
outside this increment. Large requested sample sets increase runtime and JSON
size; the operation is explicit and synchronous in Blender.

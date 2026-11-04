# Native-topology measurements and rule comparison (A3.3 core)

This separate, opt-in tool measures reviewed correspondences on the fitted mesh.
It does not change the mesh, fitting objective, marker values or default workflow.
The shared engine requires NumPy only and is included in the Blender ZIP. There
is no Blender panel in this increment; A3.4 remains separate.

## Prepare a reviewed mapping

```bash
python -m cranio.rules.comparison template --npz models/gnm_head.npz --output feature_map.json
python -m cranio.rules.comparison measure --npz models/gnm_head.npz --face face.obj --mapping feature_map.json --output feature_report.json
```

The first command binds an empty mapping to the exact model SHA-256 and vertex
count. All anatomical indices, definitions, sources, rules and thresholds remain
null/unreviewed. No legacy candidate index is imported or automatically trusted.
Outputs must be new paths; neither command overwrites an input or existing file.
JSON is UTF-8, sorted, finite and timestamp-free for deterministic comparisons.

Only native-topology OBJ in **world millimetres** is accepted. Use the pipeline's
OBJ or an export retaining its vertex indexing and exact triangle order. No unit
conversion, alignment, remeshing, welding, scene merge or index remapping occurs.
The model is loaded with `allow_pickle=False`; template positions establish the
count only, so their model-space metre units are not used as face measurements.
The CLI records hashes of model, face, mapping and comparison implementation;
it rejects inputs whose hashes change while it runs. Preserve the software commit
and environment with the case for complete reproduction.

The vertex count and triangle array must match the model exactly. These checks
cannot detect arbitrary permutations of coordinate values that leave the face
index array untouched. Preserving native vertex identity remains an operator
responsibility. File units are declared by the workflow, not inferred from size.

## Correspondences and definitions

The schema supplies names for medial/lateral canthi L/R, pupil centres L/R,
pronasale and cheilion L/R. For each point, provide its zero-based `vertex`,
`definition`, `source`, and explicitly set `reviewed: true` after anatomical
inspection. Distinct named points cannot share an index. Unreviewed points are
excluded from dependent measurements; independent reviewed features still work.
Metadata checks establish documentation presence, not the correctness of the
operator's anatomical decision. A pupil centre may not correspond to a surface
vertex; if it cannot be represented accurately, leave it unmapped. No centroid,
barycentric construction or substitute surface point is guessed.

Each feature also needs a reviewed definition and source. The geometric
operators are fixed as follows; a textual definition cannot change the operator.

| Feature | Geometric quantity |
|---|---|
| `inner_canthal_width` | 3-D Euclidean distance between medial canthi |
| `outer_canthal_width` | 3-D Euclidean distance between lateral canthi |
| `interpupillary_width` | 3-D Euclidean distance between pupil centres |
| `mouth_width` | 3-D Euclidean distance between cheilion points |
| `pupil_position_L`, `pupil_position_R` | A mapped world-mm point |
| `pronasale_position` | A mapped world-mm point |

These widths are not projected frontal measurements. Pronasale position is not
nose projection against a reference plane. Source methods using other definitions
require a separate implementation and compatibility check. Coincident endpoints
make a width unavailable rather than a successful zero-valued observation.

## Rule availability and residual API

Optional `rule_id` must exist in the registry and belong to the same feature
family. The current eye/mouth/nose rules are source-missing stubs. Consequently,
the CLI retains the geometric measurement but reports `not_configured`, with
comparison/light `not_assessed`. No anatomical rule can currently produce a
traffic light. Future numerical rules need explicit skull/case-input adapters,
definition compatibility and applicability checks. The measurement engine refuses
numeric predictions until these adapters exist; setting registry review flags
does not activate a formula.

The independent `compare_prediction(Prediction, RuleResult, thresholds=None)`
API is ready for explicitly supplied, compatible results. For measured value
`m`, prediction `p` and positive supplied SD `s`, it reports:

```text
residual = m - p
standardized_residual = (m - p) / s
```

Scalars must share units; points must share the world-mm frame. Point residuals
use three supplied marginal coordinate SDs, not an isotropic SD inferred from a
scalar. The reported point distance is the Euclidean residual norm in mm. The
standardized vector is coordinate-frame dependent; it is not a Mahalanobis
distance, confidence region, probability or calibrated reconstruction error.
Missing or zero SD leaves standardization and the light unavailable, even at
zero residual. An inapplicable/unavailable prediction has no residual.

Without configured cuts, standardization may be reported but the light remains
`not_assessed`. Configured cuts require all these fields:

```json
{
  "metric": "abs_z",
  "green_max": null,
  "amber_max": null,
  "source": null,
  "reviewed": false
}
```

This fragment is deliberately incomplete and **cannot be activated**. Set the
whole `thresholds` field to null to leave thresholds unconfigured. To enable a
documented policy in the residual API, supply finite `0 <= green_max < amber_max`,
a source and explicit review. For points the metric is `max_abs_coordinate_z`:
the maximum absolute marginal residual, with no covariance interpretation. For
scalars it is `abs_z`. Green includes the lower cutoff, amber includes the upper
cutoff, red is above it. Labels describe that supplied policy, not scientific
validation. No cutoffs or source formulas are bundled.

## Scope still pending

This completes only the measurement/comparison foundation of A3.3. Verified
anatomical mappings, numerical A3.2 rules and compatible case adapters, optional
soft constraints, integration into the normal fit report and A3.4 UI are pending.
There is no anatomical accuracy claim, CT analysis or automatic face adjustment.
Synthetic tests check geometry, missing-data semantics, safety and packaging;
the real-model test checks OBJ topology preservation only.

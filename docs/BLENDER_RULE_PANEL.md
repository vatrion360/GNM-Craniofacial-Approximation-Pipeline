# Anatomical-rule inspection in Blender (A3.4)

The closed-by-default **Anatomical Rules / Feature Snapshot** panel is in the
**GNM Markers** sidebar. It displays source metadata, execution availability and
explicitly requested measurements. It does not fit, move, colour or modify the
face, change marker depths, or enable anatomical rules.

## Controls

| Control | Default | Effect |
|---|---|---|
| Show / Refresh Rule Catalogue | Not run | Load the bundled registry and show source, DOI, review state and execution state |
| Neutral fitted mesh | None | Explicitly select an existing fitted mesh from this scene |
| Reviewed feature map | `//feature_map.json` | A3.3 model-bound correspondences and measurement definitions |
| Write Blank Feature Map | Explicit action | Create an empty map bound to the selected local model; refuse overwrite |
| Feature snapshot JSON | `//feature_snapshot.json` | New report destination |
| Measure / Export Snapshot | Explicit action | Read the selected mesh, run the shared NumPy measurement engine, export JSON and display its snapshot |

`//` paths are relative to the current blend file. Save the project first or use
explicit absolute paths. The selected model is the existing **GNM Live** model
path. Creating a map does not assign or review any anatomical point. Fill and
review the JSON using the [A3.3 mapping contract](RULE_COMPARISON.md); no vertex
selection/automatic correspondence tool is added here.

The catalogue can be inspected without a model or case. It uses only the bundled
registry; external registry selection is not exposed in this panel. A source's
`needs_verification` review state is separate from the predictor's
`not_configured` or `unused` execution state. Bibliographic leads are not verified
primary-source formulas. The ear predictor remains unused/unspecified.

## Measurement requirements

Use the **original neutral fitted mesh**, retaining GNM vertex identity and exact
triangle order. The source must belong to the current scene, carry live-fit
metadata or a completed offline fit report, and match the selected model hash.
Metadata does not establish anatomical validity or prove that the geometry has
never been manually edited. The report describes the coordinates read at the
time of the action.

Use metric scene scale `0.001`, meaning world coordinates are millimetres. The
object's world matrix is applied to vertex coordinates and recorded. Edit mode,
modifiers, shape keys, animation, constraints, parenting and post-fit presentation
copies are rejected so that base mesh data cannot silently stand in for a
different evaluated surface. Select the retained neutral fit for expression/UV
projects. Missing/unreviewed correspondences disable only dependent measurements.

The addon calls `cranio.rules.comparison.measure_and_compare` directly on NumPy
arrays. It does not run trimesh, SciPy, a network request or a worker thread.
The CLI and addon therefore use the same measurement operators and unknown-state
semantics. UI redraw reads cached strings only: it performs no file/model reads,
geometry hashing, measurement or refit. Actions run on Blender's main thread.

## Results and limits

The catalogue lists each rule and its bound snapshot features. Below it, the
panel lists each measurement or its unavailable reason. In this release all
anatomical predictors remain unavailable, so **SD deviation is unavailable and
the traffic-light state is not assessed**. An accurately computed width is not
evidence of an accurate reconstruction. The standalone residual API does not
activate a rule in Blender. There is no green/amber/red anatomical judgment in
this panel until verified predictors and compatible case adapters are implemented.

Displayed case values are prominently labelled **LAST SNAPSHOT**. They are not
live checks and do not track later geometry edits, refits, model/file edits or
scene-unit changes. Recompute explicitly after such changes. Changing the source
selection or mapping path clears the case display. Refreshing the catalogue or
starting an action also clears it; failed actions cannot leave an old result
looking like a successful new measurement. Cached displays in saved projects
remain historical and require recomputation for current-scene use.

The JSON includes the core's measurements, mapping and registry record plus model,
mapping and (when used) offline-report hashes; world-coordinate/triangle hash,
world matrix, object name, fit metadata, Blender version and hashes of the core
and Blender adapter. The geometry hash uses C-order little-endian float64 world
coordinates followed by C-order little-endian int64 triangles. Preserve the blend
file, model, mapping, software revision and environment with the report. The
snapshot JSON alone does not contain a reproducible face mesh.

Existing outputs and input paths are protected against overwrite. A new filename
is required for another snapshot. Input model/mapping/report hashes are checked
again before publication to detect changes during computation.

This increment supplies the read-only A3.4 UI for the available A3.1–A3.3
infrastructure. Numerical anatomical formulas, case-input adapters, verified
feature mappings, soft constraints and integration into the normal fit report
remain pending. No CT accuracy, interactive usability or diagnostic validation is
inferred from the engineering tests.

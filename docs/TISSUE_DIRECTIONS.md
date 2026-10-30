# Explicit tissue measurement directions (A1.5)

This optional mode applies **selected landmark** depths using explicit reviewed
world-frame vectors. It does not infer source methods, automatically orient a
skull, or assume Blender Z/GNM Y is anatomical vertical. Existing bundled tissue
tables retain unknown measurement directions; source mode refuses those rows.
No source definitions, anatomical thresholds or empirical values are supplied.

## Direction contract

For bone anchor `b`, table depth `d` in mm and a supplied vector `v`, the new
skin target is `b + d * v / ||v||`. The bone point, correspondence, confidence,
inclusion flag and unselected markers stay unchanged. The signed vector is
explicit: no automatic sign flip toward a camera, skull centre or old target.

| Table `measurement_direction` | Required case information | Check |
|---|---|---|
| `bone_normal` | Operator-reviewed surface normal in `axis_world`, anchored at the actual bone point | Finite nonzero supplied normal; no normal recalculation or independent perpendicularity validation |
| `vertical` | Reviewed `frame.vertical_world` and a signed per-marker `axis_world` | Parallel vectors, with the sign explicitly supplied per marker |
| `sagittal` | Reviewed `frame.sagittal_normal_world` and a signed per-marker `axis_world` | Axis lies in that sagittal plane |
| `other` or null | No implemented definition | Clear error; no fallback |

A sagittal plane is **not** a unique measurement vector. It does not authorize
assuming an anterior-posterior axis or projecting a normal into the plane.
The operator must provide the direction specified by the actual source protocol.
Vertical also needs an explicit frame and sign. `definition` fields document
these choices and their sources. Checked geometry is not proof that the source
method, cohort or anatomical landmark has been interpreted correctly.

Algebraic parallel/orthogonality checks use `64 * float64 epsilon`, not an
anatomical angle tolerance. Supply full-precision axes from the same frame;
rounded inconsistent vectors are rejected, not silently projected. Normalization
rescales by the largest component before taking the norm, avoiding overflow.

## Prepare the manifest

Export the case CSV v3 first, including bone endpoints. Generate an **unreviewed**
template, copying exact anchors and source hashes without guessing any axes:

```bash
python -m cranio.tissue_directions --input case.csv --table source_table.json --labels Nasion Rhinion --output directions.json
```

Complete the JSON from reviewed case geometry and the supplied source protocol:

- `schema_version: 1`, `units: "mm"`, `coordinate_space: "world"`.
- `table_sha256s`: exact table byte hashes authorized for this manifest. The
  template includes the selected table. For a comparison, explicitly review and
  list every table; selected rows must agree on the declared direction kind.
- `landmarks.LABEL.bone_xyz_mm`: exact CSV bone coordinates. Moving the anchor
  invalidates the entry; regenerate/review instead of rounding it by hand.
- `axis_world`: the signed three-component vector, initially null.
- `measurement_direction`: must match the selected table row. Unknown directions
  must be verified in the source and entered into a new table revision first;
  update its hash only after reviewing that revision.
- `definition`: a nonempty source/direction explanation; replace the generated
  `TODO(verify-source)` text. Set `reviewed: true` after the actual human review.
- `bone_source_geometry_sha256`: copied from the marker if present; it must match
  on application. It stays null when the case has no source hash.
- `frame`: for vertical/sagittal rows, fill the required vector(s), definition and
  review state. Unused frame axes may remain null. For bone-normal rows, no frame
  is inferred or required.

All vectors and anchors are in the **same world-mm coordinate frame as the case**.
Rotate the manifest vectors and anchors with a rotated case; do not reuse stale
world directions. A matching anchor alone cannot detect every mesh/frame edit.
Without a source hash, the audit explicitly records `geometry_hash_bound: false`.
With one, offline checks it against the recorded marker hash; it cannot verify an
unavailable original surface. Blender additionally compares the current evaluated
registered source geometry when a placement hash exists. A geometry/hash change
requires re-placement/review; absent hashes do not imply verified bone geometry.

The template is intentionally unusable until reviewed values are filled. Missing
rows, zero/nonfinite vectors, changed anchors/hashes, unsupported kinds, incompatible
frame geometry and unreviewed definitions fail before any marker is changed.

## Offline

```bash
python gnm_reconstruct.py --input case.csv --npz /models/gnm_head.npz --output out/source-direction.obj --tissue-table source_table.json --tissue-labels Nasion Rhinion --tissue-axis source --tissue-directions directions.json
```

`--tissue-axis source` requires both selected labels and the manifest. Supplying
`--tissue-directions` with another mode is rejected rather than ignored.
`--tissue-axis existing` retains the earlier explicit existing-axis scenario.
The default remains unconfigured: table selection alone never moves targets.
Zero previous depth is supported in source mode because the direction comes from
the manifest, not a zero-length old bone-to-target vector.

The input CSV is never rewritten. The JSON report hashes the direction file and
records its content, each supplied/normalized axis, frame, before/after target,
review state and table row. `source_direction_enforced` means this declared
geometric direction contract was applied to the selected landmarks; **it does
not mean independent source or anatomical validation**. TXT names the mode.
Frozen protocols retain the direction policy and implementation; the manifest
is a case-specific hashed input, like marker coordinates, not a shared constant
frozen across subjects. `--tissue-compare` preflights it for every table and
records whether source mode was used. Changing the scientific direction rule
requires a reviewed new protocol revision; case vectors/anchors naturally vary.

SD weighting remains a separate option. Source direction does not turn scalar SD
weights into a directional covariance or calibrated uncertainty estimate.

## Blender

In **Versioned tissue-table scenario**, select the table and placed markers using
the existing depth checkboxes. Choose **Depth direction → Reviewed source
directions**, select **Direction JSON**, review the manifest/frame and acknowledge
**I reviewed the direction definitions and frame**. Then press
**Replace Selected Depths from Table**. Changing mode, table or file path clears
the acknowledgement. Merely changing settings does not move any markers.

The operation uses the same NumPy planner as the CLI. It updates the selected
skin endpoints, pegs and depths in one rollback-capable main-thread transaction.
Undo/Redo restores geometry and source/audit history. A failure after a partial
mutation restores the original transforms, depths and stored directions.
Re-export CSV afterward. **Run Offline Fit and Import** fits those exported
coordinates without applying the table a second time. Source-direction history
is retained in `marker_depth_adjustments`. An older normal-estimator record may
correctly become stale after reorientation; it is not rewritten as a new estimate.

## Existing dense behavior and scope

Selected-landmark table application does **not** replace dense region/scalp
depths. Those offsets still follow the explicitly reviewed nearest sampled bone
normal in `cranio.geometry.dense_correspondences`, for both fitting and dense TPS.
The current nearest-correspondence rejection and sampling rules are unchanged.
A1.4 may optionally weight dense fit rows by regional SD; that does not change
their depths or directions. Applying table-specific dense depths/directions is
not part of this selected-marker mode and is not claimed as implemented.

Tests establish synthetic coordinate geometry, rigid-transform equivariance,
atomic failure, default regression and Blender integration. They do not establish
source equivalence, CT accuracy or anatomical applicability. Human CT validation
remains separate.

# Marker CSV v3

CSV coordinates are **skin targets** in millimetres in the Blender world frame. Bone landmarks are separate columns. The pipeline does not silently convert units or infer bone positions by subtracting a population average.

```csv
# gnm-marker-csv v3
# {"version":3,"units":"mm","coordinate_space":"world","model_sha256":"<64-character model SHA-256>"}
label,vertex,placed,x,y,z,weight,bone_x,bone_y,bone_z,tissue_depth_mm,tissue_source
Nasion,12319,1,0,100,26,1,0,100,20,6,"Operator-reviewed source and measurement definition"
```

The numeric example is illustrative, **not a recommended tissue depth**.

| Field | Contract |
| --- | --- |
| `label` | Unique nonempty anatomical/operator label |
| `vertex` | Explicit nonnegative vertex index; manual Blender picks survive export |
| `placed` | `1` or `0`; the origin is a valid placed point |
| `x,y,z` | Finite target coordinates; required for placed rows |
| `weight` | Relative influence in `(0,1]`; not a confidence probability |
| `bone_x,bone_y,bone_z` | Either all present and finite, or all absent |
| `tissue_depth_mm` | Optional nonnegative value; when bone coordinates are present, must match target distance within 0.05 mm |
| `tissue_source` | Review note citing study/table/landmark definition or explicit operator assumption |
| `use_for_fit` | Optional `1`/`0`; default `1`. A placed row with `0` is retained in metadata/bone diagnostics but excluded from pose and identity fitting |
| `bone_status` | `observed`, `reconstructed`, `inferred`, or `unspecified` (default); records repaired/mirrored or missing bone |
| `mapping_reviewed` | Optional `1`/`0`; blank means not recorded. `--strict` rejects explicit `0` for included targets |
| `mapping_source` | Candidate-map revision or `operator-selected`; describes the skin correspondence, distinct from tissue provenance |
| `marker_notes` | Operator notes on placement, measurement direction, restoration and assumptions |

The additional columns are backward-compatible additions to v3. Older v3 files remain readable; missing review fields are not invented. New exports include case notes, cranial-modification status, requested marker set and the reference-table metadata. Per-row sources determine which tissue values were actually used.

`model_sha256` identifies the **actual model archive**, including topology. It is checked when supplied and required by `--strict`. The metadata may carry acquisition, observer and tissue-table details; it is copied to the run report. Avoid direct identifiers in shared case metadata.

Suggested case metadata: case pseudonym, scan modality/resolution, source units, known calibration measurement, observer ID, placement date, tissue study DOI/table, measurement direction, cohort applicability, mean vs individual estimate, tissue variance/measurement repeatability, damaged/mirrored regions and manual assumptions. A single free-text citation is not proof that the selected value/landmark is appropriate.

## Validation

The reader rejects duplicate labels or included target vertices, unknown legacy encodings, incomplete/malformed metadata, non-finite coordinates, incompatible units, invalid weights and inconsistent bone/skin distances. The pipeline additionally checks included vertex bounds, at least four usable noncollinear targets, file collisions and the model hash. Documentation-only rows are retained in `marker_metadata.marker_records`; they do not enter the fitting arrays.

Three markers may orient a preview, but do not make a well-constrained approximation. Four is a numerical minimum, not an anatomical sufficiency criterion. Anatomically distributed midline and bilateral points are required for meaningful review.

## Legacy migration

v1/v2 `gnm_landmark_index,x,y,z` remain supported. Encoded indices are decoded using the inherited tables, including the historical Rhinion correction. `(0,0,0)` retains its old unplaced meaning; v1 has no unit metadata and therefore assumes world mm with a warning. These formats cannot preserve arbitrary manual picks or bone coordinates.

For an existing `.blend`, install the new ZIP, select the reviewed model, inspect every target/direction, document tissue sources, then export v3. Do not relabel a v1 file as v3: missing information cannot be recovered reliably. Legacy CSVs cannot drive the offline nasal bone diagnostic.

In add-on 15, **Add Missing Markers** preserves placed objects, manually entered depths and manual vertex selections. The default Pogonion candidate changes from the lower-lip vertex 12284 to chin candidate 12261. Explicit v3/manual indices remain authoritative; review existing cases deliberately. New sites need anatomical review; the PDF does not supply GNM correspondences. See [PDF protocol](PDF_PROTOCOL.md).

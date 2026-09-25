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

`model_sha256` identifies the **actual model archive**, including topology. It is checked when supplied and required by `--strict`. The metadata may carry acquisition, observer and tissue-table details; it is copied to the run report. Avoid direct identifiers in shared case metadata.

Suggested case metadata: case pseudonym, scan modality/resolution, source units, known calibration measurement, observer ID, placement date, tissue study DOI/table, measurement direction, cohort applicability, mean vs individual estimate, tissue variance/measurement repeatability, damaged/mirrored regions and manual assumptions. A single free-text citation is not proof that the selected value/landmark is appropriate.

## Validation

The reader rejects duplicate labels or vertices, unknown legacy encodings, incomplete/malformed metadata, non-finite coordinates, incompatible units, invalid weights and inconsistent bone/skin distances. The pipeline additionally checks vertex bounds, at least four usable noncollinear targets, file collisions and the model hash.

Three markers may orient a preview, but do not make a well-constrained approximation. Four is a numerical minimum, not an anatomical sufficiency criterion. Anatomically distributed midline and bilateral points are required for meaningful review.

## Legacy migration

v1/v2 `gnm_landmark_index,x,y,z` remain supported. Encoded indices are decoded using the inherited tables, including the historical Rhinion correction. `(0,0,0)` retains its old unplaced meaning; v1 has no unit metadata and therefore assumes world mm with a warning. These formats cannot preserve arbitrary manual picks or bone coordinates.

For an existing `.blend`, install the new ZIP, select the reviewed model, inspect every target/direction, document tissue sources, then export v3. Do not relabel a v1 file as v3: missing information cannot be recovered reliably. Legacy CSVs cannot drive the offline nasal bone diagnostic.

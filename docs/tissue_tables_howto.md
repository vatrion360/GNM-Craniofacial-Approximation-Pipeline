# Versioned tissue tables: data exchange (A1.1)

This module validates structure, not scientific accuracy or applicability. It
performs no fitting, table selection in Blender, marker movement, weighting,
direction conversion or uncertainty simulation. A loaded/imported table never
overrides a case's manually recorded depths or coordinates. The existing
explicit **Apply Table 2 Tissue Depths** operation is unchanged.

## Create, inspect and exchange

```bash
python -m cranio.tissue template --id my_table --output my_table.json
python -m cranio.tissue inspect my_table.json
python -m cranio.tissue export-csv --input my_table.json --output my_table.csv
python -m cranio.tissue import-csv --input my_table.csv --output checked_table.json
```

CLI outputs must be new files unless `--overwrite` is explicit. Even with that
flag, replacing the input is forbidden. Writers validate before atomic replacement;
failed writes preserve an existing destination. The Python writer API provides
atomic replacement; its caller is responsible for deciding overwrite policy.

`load_table(Path(...))` reads an explicit local file. A bare string identifier
resolves only to `cranio/data/tissue/<id>.json`; there is no download or remote
schema resolution. The wheel and Blender ZIP include the schema. Runtime uses
standard-library code and existing NumPy helpers, not jsonschema/SciPy/TensorFlow.

## Schema and metadata

The authoritative schema is `cranio/data/tissue/schema.json` (schema version 1,
units mm). Its deliberately restricted JSON Schema subset is evaluated by the
shared module. Unsupported schema keywords/references fail closed. Unknown data
fields fail validation, to catch misspellings rather than silently lose metadata.

Every table contains `id`, `revision`, `provenance`, `citation`, `doi`,
`measurement_method`, `posture`, `sex`, `age_range_years`, `ancestry_label`, `n`,
`notes`, `landmarks` and `regions`. Preserve cohort labels as the source states
them. Enter a full citation when verified; never fabricate bibliographic details.
Unknown scientific fields use JSON `null`, not zero, an empty string or a guessed
value. Use `TODO(verify-source)` notes for unresolved source review. A revision
identifies curated data; changing values requires a new revision by the curator.

Each landmark/region row requires `central_mm` (nullable). Optional fields are:

| Field | Contract |
| --- | --- |
| `estimator` | mean / median / shorth / 75-shormax / null; descriptive, never calculated from another estimator |
| `sd_mm` | nonnegative or null; missing SD warns; zero SD warns that inverse-variance weighting is undefined |
| `p10_mm`, `p90_mm` | nonnegative or null; P10 cannot exceed P90 |
| `n` | positive integer or null; optional row-specific sample count |
| `measurement_direction` | bone_normal / vertical / sagittal / other / null; metadata only in A1.1 |
| `direction_notes` | explain the reference frame/sign or an `other` direction; nullable |
| `provenance` | legacy_hardcoded / source_transcription / user_supplied; inherited from table when absent |
| `notes` | free text |

Directions must eventually be interpreted in a reviewed case frame. Merely storing
`vertical` or `sagittal` here does not define a vector. Missing SD does not produce
a default variance. No range thresholds, tissue depths or source coefficients
are generated. Negative values, NaN/Inf, booleans as numbers, duplicate JSON keys,
duplicate CSV labels and malformed rows are rejected.

## CSV format (not marker CSV)

This is **tissue-table CSV v1**, independent of marker-coordinate CSV v11/v12/v2/v3.
It begins with `# gnm-tissue-table-csv v1`, then `# ` followed by one-line JSON
metadata excluding the row collections. The third line is the header. Exported
columns are `scope,label,central_mm,estimator,sd_mm,p10_mm,p90_mm,n,measurement_direction,direction_notes,notes,provenance`.
`scope` is `landmarks` or `regions`. Blank scientific cells mean null; blank
provenance inherits the table value. Only scope, label and central_mm columns
are mandatory. UTF-8, quoted commas and multiline notes round-trip. Decimal
numbers use a period; convert other spreadsheets explicitly before import.

`inspect` prints the normalized table and an audit record containing its ID,
revision, citation, provenance, exact source-file SHA-256 and warnings. Library
callers must surface `TissueTable.warnings`; validation warnings are returned,
not printed at import time. The hash records source bytes, so a formatting-only
change also changes it. `document` returns a detached copy; writing/reloading an
edited document produces a new record. This infrastructure does not certify
transcription, cohort suitability or anatomical correspondence.

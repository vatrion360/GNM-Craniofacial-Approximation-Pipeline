# Versioned tissue tables: data exchange (A1.1)

The data-exchange module described here does not move markers. The separate
[A1.3 scenario workflow](TISSUE_SCENARIOS.md) now provides explicit selected-marker
application and offline comparison; source-direction enforcement remains pending.

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

## Bundled migration (A1.2)

| ID | Preserved content | Evidence status |
| --- | --- | --- |
| `legacy_hardcoded` | 27 marker depths, five facial region offsets and the scalp offset | Inherited implementation constants; citation, SD, cohort, estimator and direction unknown |
| `var2026_table2` | 32 positions already transcribed in `paper_reference.py` | Existing case-study attribution retained; not a new PDF/source verification |

The 48-marker union, label order, sides, initial source strings, confidence
weights and Table 2 placement definitions remain unchanged. Overlapping legacy
and Table 2 values remain distinct. Dense scalp defaults are now shared by the
CLI, config and Blender; an explicit `--scalp-offset-mm` still takes precedence.
The generic Blender property initializer is not a source measurement and is not
added as an invented table row. Regional offsets retain `legacy_hardcoded`
provenance; no claim of independent region-level measurements is made.

Tables are read once when their registry module loads. Restart/reload the add-on
after a curated package revision; do not edit installed table files during a
case. Importing a table alone is data preparation; the separate explicit
application workflow is described in [A1.3](TISSUE_SCENARIOS.md). Existing saved/manual case
values are retained, and **Apply Table 2 Tissue Depths** remains an explicit
replacement operation. Offline fitting uses the CSV's world-mm targets, never
rebuilds those targets from the bundled catalogue.

The JSON report adds `bundled_tissue_defaults`, explicitly a catalogue, with
IDs/revisions/hashes and all unknown-data diagnostics. It does not assert that
all listed tables were applied. The TXT report provides a summary. Effective
marker targets/source notes remain in `marker_metadata.marker_records`; the
scalp override remains in `config.scalp_offset_mm`. The implementation hash now
includes the schema and both data files. Frozen protocols require a deliberate
new revision after this software/data change, even when the mesh is identical.

### Reproduce the engineering comparison

`tests/fixtures/tissue_defaults_24d3706.json` is a historical implementation
snapshot, not an independently validated tissue table. Tests compare every
migrated marker value/side/order/source and region/scalp value exactly.

For a whole-pipeline comparison, obtain the official model separately, create a
worktree at `24d3706b47d28d660dd700675f6f6e4536a8f886`, and run the **new** helper
against each tree with the same pinned Python runtime and one BLAS thread:

```bash
# Linux/macOS shell; on PowerShell set $env:OPENBLAS_NUM_THREADS='1'
export OPENBLAS_NUM_THREADS=1
python tools/verify_tissue_migration.py --source-tree ../baseline-tree --npz /path/gnm_head.npz --output-dir /outside/repo/before
python tools/verify_tissue_migration.py --source-tree . --npz /path/gnm_head.npz --output-dir /outside/repo/after
```

Compare the two `migration_manifest.json` objects for exact equality. The helper
uses seed 1902, the 48 canonical labels, normalized Gaussian directions, and
synthetic bone positions `mean_vertex - 2 * direction` mm. Targets are
`bone + default_depth * direction`; weights come from the unchanged registry.
It runs adaptive lambda with default identity fitting, then with optional local
correction. Reports retain non-convergence/clipping diagnostics. These artificial
targets exercise software compatibility, not CT reconstruction accuracy or
scientific validity of any tissue default. Derived meshes stay outside Git.

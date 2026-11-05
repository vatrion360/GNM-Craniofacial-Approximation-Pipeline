# Optional age-at-death assessment (A6)

This is a descriptive audit of operator-supplied metadata. It does not estimate
age from a skull, modify GNM identity/expression, simulate ageing, change tissue
depths or select a tissue table. Overlapping age ranges do not establish biological
applicability or reconstruction accuracy. Other source criteria still need review.

## Declare the case assessment

Create an empty case document, without overwriting an existing file:

```bash
python -m cranio.age_context template --output case_age.json
```

The template contains exactly this optional field:

```json
{
  "age_at_death_estimate": {
    "schema_version": 1,
    "range_years": null,
    "method": null,
    "source": null,
    "reviewed": false
  }
}
```

Replace `range_years` with two inclusive, finite, nonnegative bounds only when an
assessment supplies them. Record its method and source (for example, a local
assessment identifier and its methodological reference). Unknowns stay `null`.
No default age, midpoint, distribution, confidence level, adult cutoff or plausible
upper bound is invented. A point estimate can be recorded with equal bounds but
must not be interpreted as certainty. `reviewed: true` requires a range and
non-placeholder method/source; this is operator review, not independent validation.
Additional fields inside the estimate are rejected to catch misspelled inputs.

Pass this document using the existing pipeline option:

```bash
python gnm_reconstruct.py --input markers.csv --npz models/gnm_head.npz --output outputs/face.obj --case-metadata case_age.json
```

A v3 marker CSV can also carry `age_at_death_estimate` in its metadata. If the CSV
and external case document contain different non-null declarations, the run fails
before fitting. Differences in source, method or review status count as conflicts;
no declaration is averaged or silently preferred. An external document with no age
(or a null age) does not erase an existing nested case estimate. Remove/reconcile
an old declaration explicitly when correcting it. Other external case fields keep
their existing precedence. Duplicate JSON keys and non-finite constants in external
case documents are rejected rather than silently accepted.

## Inspect table ranges before choosing a scenario

```bash
python -m cranio.age_context compare --case-metadata case_age.json --tables legacy_hardcoded var2026_table2 --output age_comparison.json
```

`--tables` accepts bundled IDs or local JSON paths in the requested order. The
output includes each table's citation, revision, SHA-256 and reported age range,
the case-file hash, raw declarations, interval intersection and interpretation.
Existing output paths are refused. Equal inputs produce byte-identical comparison
JSON; no timestamp is added. The command does not run any fit or pick a winner.

| Comparison | Meaning |
|---|---|
| `no_estimate` | No case range was supplied |
| `unreviewed_estimate` | Case range retained but not screened against a table |
| `no_table_selected` | A reviewed estimate exists, but no table was selected |
| `table_age_unknown` | Selected table has no supplied age range |
| `within_reported_range` | Entire case interval lies within the table interval |
| `partial_overlap` | Intervals intersect but the case interval is not contained |
| `outside_reported_range` | Intervals do not intersect |

Endpoints are inclusive: touching at one bound is an intersection, not evidence
of applicability. There is no probability score, interpolation or automatic choice.
The bundled `legacy_hardcoded` and `var2026_table2` tables currently have unknown
age ranges. This change does not fill them; source-verified metadata is required.

Selecting `--tissue-table` in a fit adds this comparison to the existing tissue
context. It still requires the existing explicit label/axis controls to replace
any depths. Without a table, the case estimate is reported with
`no_table_selected`. JSON stores `marker_metadata.age_context`; TXT includes the
range, method, source and the limitation that soft-tissue ageing is not modelled.
No age field means no age audit or extra warnings on the legacy/default path.

## Blender

The tissue panel has an optional **Age assessment JSON** file field, empty by
default. Select the case document above. Reading happens only on explicit tissue
**Apply** or marker/offline **Export**, never during redraw or live fitting.
Changing the field/file does not move markers or refit the mesh.

Apply records a snapshot of the age comparison and source-file hash in the
existing marker history. Editing the file later cannot rewrite that history.
A subsequent Apply uses the new file. Exports embed the current assessment and
its source-file hash into v3 CSV, so the offline pipeline does not depend on that
file still being available. A missing/malformed selected file fails the action;
existing marker state and an existing CSV remain intact. The path is stored in
`.blend`; distribute the JSON with the scene if later actions need it, or clear
the field to stop supplying current age metadata. Historical records remain.

No CT validation, automatic age-based table selection, age-conditioned prior or
ageing model is introduced. The numerical fit and its defaults remain unchanged.

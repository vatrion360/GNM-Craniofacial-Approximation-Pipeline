# Explicit tissue-table selection and comparison (A1.3)

This is **sensitivity analysis**, not uncertainty estimation or anatomical
validation. Source-direction application (A1.5) is not implemented here. Existing
bundled tables have unknown measurement directions. Nothing substitutes an
assumed world vertical, GNM normal or statistically inferred direction.

## Preserve or replace case values

All new controls default off. Selecting a table alone changes only reporting:

```bash
python gnm_reconstruct.py --input case.csv --npz /models/gnm_head.npz --output out/selected.obj --tissue-table var2026_table2
```

To replace specific targets, explicitly name the labels **and** accept the
existing-axis scenario:

```bash
python gnm_reconstruct.py --input case.csv --npz /models/gnm_head.npz --output out/scenario.obj --tissue-table var2026_table2 --tissue-labels Nasion Rhinion --tissue-axis existing
```

`--tissue-table` accepts a bundled ID or a local schema-valid JSON file. IDs do
not trigger downloads. The input CSV is never rewritten. Without replacement
labels, every case target and weight remains unchanged. With explicit labels,
those values **including manual/individual measurements** are deliberately
replaced; all other markers retain their values. There is no provenance-based
guess about which manual values should be overridden.

Replacement requires v3, a placed/included marker, explicit bone coordinates,
a nonzero bone-to-target axis and a configured table depth for every selected
label. Missing rows/null depths, legacy CSVs, excluded/unplaced labels and
invalid axes fail before any replacements are made. A small numerical guard is
shared with the inherited Blender axis transaction; it is not an anatomical
threshold. Legacy CSVs remain readable for ordinary fitting without replacement.

For bone point b, current skin target s and table depth d (all mm), the new target
is `b + d * (s-b)/||s-b||`. Source `measurement_direction` is recorded but **not
enforced**, even when known. By choosing `existing`, the operator accepts this
explicit sensitivity assumption; this does not establish equivalence to the
source's measurement method. Review the table cohort, definitions and source
before interpreting a scenario. SD/estimator metadata does not change weights.
Dense facial regions, scalp offset, bone geometry and skin correspondences stay
unchanged. General source-direction support and SD weighting are later tasks.

Unknown/legacy provenance remains `unspecified`/`legacy-unvalidated`; merely
selecting a table does not satisfy strict provenance gates. The TXT report names
the table and citation, explicit labels and axis assumption. JSON includes its
source SHA-256, metadata, every original and replacement row, and preserved
labels in `marker_metadata.tissue_application`. Effective records/targets reflect
the scenario, while the original CSV and its hash remain in the audit trail.
Custom table bytes are included in frozen-protocol checks, not just filenames.
Existing frozen protocols need a reviewed new revision for this implementation.

## Blender

1. Use the left-hand depth selection checkboxes to choose **placed** markers.
2. In **Versioned tissue-table scenario**, choose a bundled table or **Local JSON
   table** and its file. Selection alone preserves the current case.
3. Review the source and marker axes. Enable **Use current axes as an explicit
   assumption** and press **Replace Selected Depths from Table**.

Changing the table/path clears the acknowledgement. The operation preserves
bone positions, weights, mapping and unselected markers; selected manual depths
are replaced. Blender may edit a placed documentation-only marker deliberately;
its Include in fit state does not change. The CLI replacement list must refer
to included fit targets. Invalid selected rows cancel the whole edit. Undo/Redo
restores/reapplies values, source notes and geometry. The existing percentage
operation and this operation share one rollback-capable geometry transaction.

The `.blend` and CSV `marker_depth_adjustments` retain table hash/citation,
assumptions and before/after history. Reusing **Run Offline Fit and Import** fits
the already edited exported targets; it does **not** apply the selected table a
second time. Loading the table/scene alone does not move markers. The older
explicit **Apply Table 2 Tissue Depths** button retains its earlier semantics;
it is not the new selected-marker transaction.

## Offline comparison

```bash
python gnm_reconstruct.py --input case.csv --npz /models/gnm_head.npz --output out/tissue-study.obj --tissue-compare legacy_hardcoded,var2026_table2 --tissue-labels Nasion Rhinion --tissue-axis existing
```

The comma-separated list accepts IDs/local JSON paths (paths containing a comma
are not supported). At least two entries are required; duplicates are allowed
for self-comparison. Every selected label must exist in **every** table. All
variants start from the same original case, not the preceding fitted mesh.

Output is a **new** `out/tissue-study_tissue_compare/` directory:

- Each numbered table folder contains the normal statistical/final OBJ, local
  displacement PLY, TXT and JSON fitting reports.
- `difference_statistical.ply` and `difference_final.ply` compare corresponding
  vertices against the **first** table's respective surface. Numeric
  `vertex_difference_mm` and a common colour-scale maximum are stored in headers.
- `summary.json` lists every table/revision/hash, replacements, report/PLY hashes,
  all-vertex and (when available) skin-exterior statistics, lambda, convergence,
  QC and exclusions. It is published only after all fits/checks succeed.

The difference is computed on exported six-decimal world-mm OBJ coordinates,
without ICP. It includes changes in fitted pose and scale as well as shape; it
is not a surface-distance measurement against a real face. All-vertex metrics
include internal head/eye/teeth geometry; inspect skin-exterior results where
available. A zero self-comparison is a determinism check, not evidence of truth.
Final and statistical comparisons remain separate so local correction is visible.
Non-convergence or automatic exclusions must be reviewed before interpretation.

A fresh comparison directory is mandatory even with `--overwrite`; this avoids
mixing old completion records with new variants. Only `--output` controls the
comparison prefix; per-file output overrides are rejected. Inputs are hashed
across all runs, and a changed input aborts completion. Existing pipeline/QC gates
are retained. A failed run may leave partial per-table outputs but no completed
comparison summary. Frozen protocols must be run individually with their own
reviewed scenario; the multi-table experiment does not silently bypass a freeze.

## Engineering evidence and remaining limits

Synthetic tests cover selection-only exact equality, selective replacement,
unknown provenance, malformed/incomplete rows, different/self comparisons,
independent starts, input modification detection, failure completion boundaries
and custom-table protocol hashes. Actual Blender checks cover RNA geometry,
rollback, persistence, export and Undo/Redo. Default-path replay against the
pre-A1.3 source is recorded in `TISSUE_SELECTION_BENCHMARK.json`.

No subject CT accuracy, cohort applicability, direction equivalence, SD weighting
or calibrated uncertainty is established by these tests. CT validation remains
with the project author. No new anatomical constants or model weights are added.

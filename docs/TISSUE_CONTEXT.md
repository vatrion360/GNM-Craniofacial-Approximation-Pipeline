# Tissue estimator and posture metadata (A1.6)

This is descriptive reporting, not a new fitting model. Declaring a posture does
not move targets, change weights, select a different tissue table or compensate
for gravity. No acquisition posture is inferred from CT modality or skull pose.

## Declare the case acquisition posture

Use the actual documented acquisition/reference posture relevant to the case's
soft-tissue comparison. Do not infer a living person's posture from a historical
skull or confuse world-axis orientation with subject posture. Leave unknowns empty.

- Offline: optional `--case-posture supine` (an example label, not a CT default).
- Marker CSV v3 JSON header: `acquisition_posture`, string or null.
- Embedded `case_metadata` or external `--case-metadata FILE`: the same
  `acquisition_posture` key. The existing external-document precedence replaces
  embedded `case_metadata`; the raw input CSV and external file hashes remain.
- Blender: **Versioned tissue-table scenario → Case acquisition posture**.
  Empty by default, persisted in `.blend` and exported into CSV metadata.

Nonempty CLI, CSV-root and active case-document declarations must agree after
case/whitespace normalization. Conflicts are errors, not silent overrides.
Raw declarations are retained. Posture is case-specific data, so frozen protocol
settings do not require every subject to have the same posture label. Input data
and CLI settings remain in each run record.

## Compare against the selected table

The table's original free-text `posture` is retained. Only whitespace/case are
normalized; no translations, posture synonyms or modality deductions are made.
The comparison reports:

- `matching_labels`: equal normalized known labels; **not** evidence of biological
  equivalence, comparable acquisition methods or correct source applicability.
- `different_labels`: warning naming both labels. Even `seated` and `upright`
  remain distinct until the author reconciles their intended source definitions.
- `unknown`: comparison unavailable; case and/or table posture is unknown.

Null, blank, `unknown`, `unspecified`, `not reported`, `not recorded` and
`unavailable` are treated as missing declarations; original text is preserved.
No table posture is filled in on behalf of the source.

Comparison runs use the same metadata loader/check as individual fits and copy
each table's context into `summary.json`. A conflict fails preflight before the
comparison output folder is created. A mismatch is advisory and never changes
the fit or silently converts the table.

## Estimators and actual use

JSON `marker_metadata.tissue_application.context` and TXT name each table row's
`estimator`, supplied `central_mm` and provenance. The existing allowed labels
are `mean`, `median`, `shorth`, `75-shormax` and null (reported as unknown).

`depth_applied` distinguishes the selected landmark rows whose depths were
explicitly applied from reference-only rows. Selecting a table alone does not
turn its means/estimators into measurements of the case. Dense region depth rows
remain reference-only because selected-marker table application does not replace
dense depths. Regional SD may separately affect weights in A1.4; `depth_applied`
refers to depth replacement, not to that weighting operation.

The implementation consumes a supplied central value directly. It **does not
calculate shorth or 75-shormax from means, SDs or percentiles**, and does not
relabel a mean as another estimator. If the desired raw-derived estimate is not
supplied and source-verified, leave it unknown. Structural validation/labels do
not verify the computation or scientific source; that remains an author task.

Blender shows compact posture and applied-estimator counts after explicit Apply,
with mismatch/unknown warnings. Full context is saved in the operation history,
`.blend` and exported CSV history. Editing the posture field alone does not
reapply a table or rewrite past history. Re-export for a new offline run. Existing
scenarios/default geometry are preserved; no additional source data is invented.

## Evidence and limits

Synthetic tests check missing/conflicting declarations, label comparisons,
verbatim precomputed estimator use, comparison preflight, CLI/TXT/JSON records,
and identical numeric fit/TPS output when only the posture declaration changes.
Actual Blender checks exercise the field, warning display, persistence and CSV
export. These are engineering checks, not a posture correction calibration or
CT/subject-level accuracy validation.

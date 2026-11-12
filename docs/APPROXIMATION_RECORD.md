# Optional derived approximation record (A7.1, first increment)

The existing `face_report.json` remains the canonical pipeline run report. This
command creates a detached view of its evidence. It does not refit a face, alter
any mesh, introduce thresholds, or declare scientific validity. Nothing runs
unless explicitly requested.

```bash
python -m cranio.record build --report outputs/case/face_report.json --output-dir outputs/case/record
```

| Option | Default | Meaning |
|---|---|---|
| `--report` | Required | Completed schema-2 world-mm pipeline report |
| `--output-dir` | Required | New directory; existing destinations are refused |
| `--artifacts` | Report's directory | Directory holding the four unchanged output basenames |
| `--limitations` | Not configured | Optional operator-approved RO/EN wording file |

## Outputs and interpretation

- `approximation_record.json`: deterministic derived record, published **last** as
  the completion marker. Includes settings, model/input hashes, fit coefficients,
  transform, lambda selection, residuals, source warnings/exclusions, metadata and
  fitted-marker provenance. Source values are copied, not recomputed.
- `approximation_record.txt`: concise human-readable summary, including supplied
  limitations. Full numerical evidence remains in the JSON files.
- `provenance.json`: source report hash, original paths and generation timestamp,
  checked output hashes, record-generator module hash, derived-file hashes and
  this export's timestamp.

Unknown marker provenance stays `not_recorded`. No original/mirrored/donor category
is inferred. Tissue, age, mandibular pose, restoration and other case metadata are
preserved if present, not fabricated when absent. Prior presence and its recorded
justification are explicit.

A completed report is not necessarily an approved geometry result: the pipeline
can write a report before returning a required-QC failure. A nonconverged solver or
unmet required geometry gate gives `diagnostic_only`; otherwise the derived status
is `recorded_not_validated`. These labels do not replace source warnings. When
profile refinement was enabled, solver diagnostics are explicitly scoped to the
baseline before profile refinement.

Uncertainty, calibration, validity domain and scientific export authorization
remain `not_assessed`. This increment does not link or validate uncertainty or CT
artifacts, introduce overrides, or infer approval from small marker residuals.
Tissue/prior comparison child run reports can be processed individually; their
aggregate `summary.json` files are not schema-2 pipeline run reports.

## Integrity, moved bundles and failure handling

Before writing, all four source outputs (final OBJ, statistical OBJ, displacement
PLY, diagnostics TXT) must match their recorded SHA-256. Windows and POSIX source
paths are supported: only their basenames are resolved inside the report directory
or explicit `--artifacts` directory. Distinct basenames are required; escaping
symlinks are rejected. Custom outputs in different directories must first be
copied unchanged into one bundle directory.

The source report, approved wording and output contents are checked again before
publishing the completion marker. An interrupted/failed export can leave TXT or
provenance files, but no completed `approximation_record.json`. Inspect the error
and use a fresh destination. The command does not overwrite an earlier record or
modify source files.

Original input/model files are **not opened or revalidated**. Their recorded hashes
are retained with `input_verification: hashes_recorded_not_revalidated`. Output
checks establish consistency with the supplied report, not authenticity of the
report or anatomical correctness. Do not modify the source bundle concurrently.

## Determinism and privacy

The deterministic core excludes runtime input/output paths, generation timestamp
and the hash of the timestamped diagnostics TXT. Those remain in the provenance
envelope, together with the raw source-report hash. The other output hashes remain
in the core. Re-exporting the same report and rerunning the synthetic pipeline with
the same inputs/settings in another directory are tested for byte equality.

User-supplied case metadata (including its own timestamps/paths), software versions,
implementation hashes and numerical results remain evidence. Thus this is not a
promise of cross-platform bitwise fitting or equality after editing metadata. No
recursive metadata scrubbing or anonymization is performed. Review case identifiers
and source paths before sharing either file.

## Operator-approved RO/EN limitations

No scientific wording has been approved for this increment. By default the record
says `not_configured`. To supply wording explicitly:

```bash
python -m cranio.record limitations-template --output limitations.json
```

This writes:

```json
{"schema_version": 1, "revision": null, "approved": false, "ro": null, "en": null}
```

Fill a revision identifier and both language texts after human review, then set
`approved` to true and pass `--limitations limitations.json`. Empty/placeholding or
unapproved files are rejected. The status `operator_declared_approved` describes
the declaration in that file; it is not independent ethical or scientific approval.
The supplied wording and exact file hash are retained.

Remaining A7 work includes explicit linkage to uncertainty/calibration, validated
case domains, export-mode integration and Blender controls. CT validation remains
a separate operator-led protocol.

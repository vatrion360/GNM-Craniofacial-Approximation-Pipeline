# A7.2 — Operator-declared validation domain

This opt-in comparison records whether explicitly reviewed case observations and
a run signature match an **operator-declared** domain. It does not perform a CT
study, verify a publication, infer anatomy or certify a reconstruction. No actual
validation cohort, anatomical thresholds or regional errors are bundled.

## Prepare the domain and case observations

```bash
python -m cranio.validity_domain template --report outputs/case/face_report.json --output validation_domain.json
```

`--report` is optional for this action. If supplied, it fills only the existing
model hash and run signature. The domain remains unreviewed, with null evidence
and empty conditions/results. Without a report all scientific fields remain
empty. Fill definitions, allowed categories and study provenance from reviewed
validation material, then declare `reviewed: true`. This is an operator review
statement, not an independent assessment by the software.

After configuring the domain:

```bash
python -m cranio.validity_domain case-template --report outputs/case/face_report.json --domain validation_domain.json --output domain_case.json
```

The case template is bound to the **exact SHA-256 of that report**. Each domain
condition receives `value: null`, `source: null`, `reviewed: false`. Supply the
case-specific observations and their sources explicitly. Neither marker count nor
missing markers establish skull completeness. Age classes, pathology, preservation
and anatomy are not inferred. Existing age estimates are not silently converted
into an adult/subadult label. Changing the source report requires a new binding
and review, not reuse of observations from another report.

```bash
python -m cranio.record build --report outputs/case/face_report.json --output-dir outputs/case/new_record --validation-domain validation_domain.json --domain-case domain_case.json
```

Both options are required together. In Blender, choose both files in
**Approximation Record (saved fit)**, then use the existing explicit export action.
The comparison banner appears in the text report and panel completion status.
Nothing runs on field changes or panel redraws.

## Domain schema (version 1)

The loader uses a closed schema: unknown fields, duplicate JSON keys, placeholders
in required text, malformed hashes and NaN/Inf are rejected. Unreviewed drafts can
contain null fields; an empty unreviewed template produces `not_configured`.

| Field | Meaning |
|---|---|
| `schema_version` | Integer 1 |
| `id`, `revision` | Operator-supplied identifiers |
| `reviewed` | Boolean operator declaration |
| `model_sha256` | Model asset digest |
| `run_signatures` | Distinct supported signatures from reviewed run configurations; empty only in drafts |
| `evidence` | `reference`, `sha256`, `n_subjects`: declared study reference/hash and independent-subject count |
| `conditions` | Nonempty map for reviewed domains, with definitions, allowed values and sources |
| `regional_errors` | Supplied study estimates; an empty list means none were provided |

Each condition key uses lowercase letters/digits/underscores (starting with a
letter, up to 64 characters). `model_sha256` and `run_signature` are reserved.
Each entry has exactly `definition`, `allowed_values`, `source`. Allowed values
are distinct, nonblank strings. Matching is exact and case-sensitive; leading or
trailing whitespace in values is rejected. These labels must be defined by the
operator's protocol, not treated as anatomical diagnoses by the software.

Each regional result has exactly:

| Field | Meaning |
|---|---|
| `region` | Source-defined ROI/region |
| `metric` | Full source-defined metric; signed bias and unsigned errors must be distinguished |
| `units` | Explicit units; no conversion is inferred |
| `estimate` | Finite supplied value; signed metrics may be negative |
| `n_subjects` | Positive integer, not a vertex count; cannot exceed declared study N |
| `interval` | Null, or `lower`, `upper`, `kind`, `level` |
| `source` | Traceable source/definition for this result |

Intervals have finite ordered bounds. `kind` must state what the interval means;
`level` is null or a fraction strictly between zero and one. The software does not
assume confidence intervals, calculate missing bounds, or require an estimate to
lie inside an interval whose method has not been specified. Region/metric pairs
must be distinct. Missing intervals and missing regional estimates are explicitly
reported. No minimum N is asserted to establish statistical sufficiency.

Case files have exactly `schema_version: 1`, `report_sha256`, `observations`.
Observation keys must belong to the domain. Each row has exactly `value`, `source`,
`reviewed`. A reviewed row needs both non-placeholder value and source. Missing,
null or unreviewed observations are unknown; they never count as matches.

## Run signature and comparison

The signature is SHA-256 of sorted, indented UTF-8 JSON with a trailing newline,
as produced by `cranio.record.canonical_bytes`. Signature schema 1 contains:

- model hash;
- all report config fields except runtime file-path fields in `PATH_SETTINGS`;
- sorted input role names (including presence of skull, profile or craniometry);
- recorded hashes for shared prior/map/protocol/tissue-table/direction inputs;
- implementation source fingerprint;
- pipeline/Python/NumPy/SciPy/trimesh versions and numerical-environment metadata.

Case-specific marker/skull/constraint file contents, runtime paths, timestamps,
Git commit/dirty status and residual values are not hashed into this signature.
This supports comparison between cases under a common recorded configuration;
the separate case-file hash binding prevents silently applying another report's
observations. Required software/fingerprint/environment metadata missing from a
report makes signature comparison unknown. The numerical environment itself is
recorded provenance, not independently verified hardware equivalence.

This contract is conservative: software, source, environment, settings, optional
input presence and shared-asset changes can put a case outside the declared domain.
Even non-numerical config differences retained in the report can change its
signature. Adding a signature requires an explicit domain revision/review; no
automatic compatibility exception is supplied. Matching does not prove that a
study was independently conducted or that correspondence/protocol choices were
appropriate. Source hashes in older reports are not replaced with today's code.

| Status | Meaning / banner |
|---|---|
| `not_configured` | Domain is unreviewed; no applicability comparison is claimed |
| `indeterminate` | No known mismatch, but at least one observation or signature is unknown |
| `outside_declared_domain` | Model/signature mismatch or a reviewed observation outside allowed values |
| `within_declared_conditions` | All declared checks match; **not independent validation** |

A known mismatch takes precedence over unknown observations, while both remain in
the detailed checks. The banner is near the start of the TXT report. It does not
block exporting a diagnostic record, upgrade the fit's status or authorize a
scientific export. Such gating remains separate work.

## Integrity and interpretation limits

Domain/case file hashes and comparison details are retained in the core record;
paths and the comparison module hash are recorded separately in provenance.
Both files are checked again before the completion marker. Repeated exports from
the same files are deterministic; a new source report or edited declaration is
new evidence and need not yield identical bytes. Template writes refuse existing
files and detect source drift/concurrent destination creation before publication.

Study evidence references/hashes and N are **operator-declared and not reopened
or independently verified**. No network request or embedded evidence-file access
is performed. Regional values describe the supplied study; they are not predicted
errors of this face, not a calibrated uncertainty map and not correction limits.
Case observations must also be reviewed against the underlying scan and study's
inclusion criteria. Identifiers and source references may contain sensitive data;
review before sharing.

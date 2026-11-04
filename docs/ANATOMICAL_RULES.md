# Anatomical-rule evidence registry (A3.1)

The registry records evidence metadata for candidate eye, nose, mouth and ear
rules. It does not predict anatomy, load implementations, score a face, choose
weights or modify any fitting result. It is available in the Python package and
Blender addon ZIP; a Blender rule panel and numerical rules are separate tasks.

## Inspect and prepare

```bash
python -m cranio.rules inspect
python -m cranio.rules inspect --input /path/to/local_registry.json
python -m cranio.rules template --id my_review --output local_registry.json
```

Inspection prints the complete metadata, diagnostics, exact input-byte SHA-256
and bundled-schema SHA-256. Output is deterministic for identical bytes/schema.
CLI JSON uses ASCII Unicode escapes on stdout so redirected output remains
UTF-8-compatible under Windows code pages; decoding JSON recovers the original
Unicode strings. Files remain explicitly UTF-8.
Template creation refuses existing outputs and protects bundled data. The blank
template has an empty rule list. To prepare a row through Python:

```python
from cranio.rules import empty_registry, empty_rule, validate_registry
catalogue = empty_registry('my_review')
catalogue['rules'].append(empty_rule('my_rule', 'nose'))
document, warnings = validate_registry(catalogue)
```

These helpers do not write a file or supply a formula. `load_registry(path)` reads
an explicit local UTF-8 JSON path; omitted path selects the bundled catalogue.
No URLs are fetched. `document` returns a detached copy. Edits should be saved to
a new reviewed revision; raw-file hashes intentionally change with formatting.

## Data contract

`cranio/rules/schema.json` describes registry schema 1. The loader uses the same
restricted, standard-library schema evaluator as tissue-table exchange. Duplicate
JSON keys, non-finite values, unknown fields, invalid types and duplicate rule IDs
are rejected. The schema describes field structure; cross-field review consistency
and identifier uniqueness are additional loader checks.

| Field | Meaning |
|---|---|
| `id`, `revision`, `schema_version` | Catalogue identity, operator-maintained revision, schema version |
| Rule `id`, `feature` | Stable identifier; eyes, nose, mouth or ears |
| `reference.citation` | Full citation after verification; null until supplied |
| `reference.doi` | Bare DOI, if supplied; syntax is checked, existence is not |
| `reference.supplied_reference` | Original bibliographic lead; not treated as a verified full citation |
| `status` | `needs_verification`, `unused` or a documented `validated` claim |
| `tested_error` | Null or explicit metric, mean, SD, n, units, cohort and source locator |
| `applicability` | Source-specific sex, ancestry and dentition label lists plus notes; null means unknown |
| `implementation_id` | Identifier only; null until configured, never imported or executed by this loader |
| `verification` | Separate source, implementation and external-evidence records |
| `notes` | Limitations, unresolved details and `TODO(verify-source)` items |

Published error summaries must retain their metric, units, cohort and location in
the source whenever any numeric mean, SD or n is supplied. Signed means may be
negative; SD must be nonnegative and n a positive integer. Unknown statistics
remain null with warnings. No SD is calculated from a mean, no published SD is
converted into per-case uncertainty, and no numerical errors are seeded here.
Each row describes one error metric/cohort; use distinct rule variants when the
same publication has different formulas, cohorts or evaluation metrics.

Applicability labels are preserved verbatim; no sex, ancestry or dentition label
is inferred from the skull, mapped to GNM groups or treated as universally valid.
Unknown applicability is not equivalent to applicability to all cases.

## Three separate review claims

Each verification record has `status`, `reviewer`, `evidence` and `scope`:

- **Source:** `not_verified` or `verified`. Verification needs a full citation and
  documentation of the exact formula/definition and primary-source location.
- **Implementation:** `not_tested` or `tested`. Testing needs an implementation ID
  and evidence identifying the implementation revision and tests.
- **External:** `not_validated` or `documented`. Evidence should identify the
  independent evaluation, its population, conditions, errors and limitations.

Completed records require non-placeholder reviewer, evidence and scope text.
The aggregate status `validated` is rejected unless all three records are
completed. This checks consistency of **declared review metadata**, not the
truth of its content. Even an accepted `validated` record does not certify a
method, establish applicability to a particular case or activate execution.
Reviewers must recheck these claims after formula, implementation or scope changes;
A3.1 does not automatically bind review text to source PDFs or code revisions.
`unused` keeps the feature unspecified by that rule. No traffic-light threshold,
scientific approval badge or automatic anatomy adjustment follows from a status.

## Bundled bibliography and limitations

Six entries preserve only the bibliographic leads supplied in TASKS.md:
Stephan & Davidson (2008), Stephan/Huang/Davidson (2009), Stephan's mouth-width
evaluation, Stephan & Murphy (2008), the supplied nose-projection guideline title,
and Guyomarc'h & Stephan (2012). All remain `needs_verification`, including the ear
entry; ear prediction is unspecified and reserved for an unused execution policy.
Four supplied DOIs are retained. Missing titles, full citations, nose authors/DOI,
formulas, coefficients, tested errors and applicability are not completed from
memory or secondary sources. Primary texts were not verified for this increment.

A3.2 will implement only source-confirmed formulas with hand-computed tests.
A3.3/A3.4 will separately address reviewed model correspondences, comparisons and
Blender display. This registry introduces no GNM indices, anatomical constants,
confidence estimates, tissue updates, new fitting defaults or runtime dependency.
CT validation remains independent and is not replaced by metadata/schema tests.

## A3.2 contract and unavailable-rule handling

This increment supplies **interfaces and stubs only**. No source-confirmed eye,
nose or mouth formula has been supplied for implementation. It does not complete
the numerical-prediction part of A3.2, and it does not validate case observations.

```bash
python -m cranio.rules status
python -m cranio.rules status --rule nose_projection_guidelines
python -m cranio.rules status --input local_registry.json
```

`status` is a case-free availability report. It returns exit code 0 for a valid
report even when all predictions are unavailable; malformed data or an unknown
requested ID returns 2. Check each `execution_status`, not the CLI exit code, to
learn whether a rule is unused or unconfigured. The report retains registry/hash
metadata, references, review claims, missing requirements and null result fields.
No input coordinates, model or scan are needed for this diagnostic.

Declared registry status and execution status are distinct. Five bundled source
leads report `not_configured`; the ear lead reports `unused` and an unspecified
feature while its bibliographic status remains `needs_verification`. A custom
unknown rule ID cannot trigger an import or expression evaluation. An
`implementation_id` or `validated` flag never enables code automatically.

The Python API is `cranio.rules.engine.predict(rule_id, observations=None,
registry=...)`. Eye, mouth and nose stubs raise `NotConfigured`, with `rule_id`
and a tuple of missing requirements. Ear/explicitly unused rules return null
prediction, null SD and unknown applicability. Stubs deliberately do not read,
validate or mutate observations: anatomy-specific input conventions must come
from each verified source before a numerical implementation can be added.
`readiness()` catches only expected `NotConfigured`; invalid metadata and route
conflicts remain errors. No fallback to GNM averages or zero error is performed.

`cranio.rules.contracts` defines immutable, standard-library result types:

- `Prediction`: a finite scalar in mm/degrees/unitless, or three world-mm
  coordinates in an immutable tuple. Other point frames require explicit
  conversion; no unit/axis inference is supplied.
- `RuleResult`: unpackable as `(prediction, sd, applicable, notes)`. A prediction
  requires `applicable=True`; `False` means an assessed inapplicable case and
  `None` means no applicability assessment. An unavailable prediction cannot
  carry an SD or claim applicability.
- SD remains optional. Scalar predictions take scalar SD; point predictions
  require three explicitly supplied marginal coordinate SDs. A scalar source SD
  is never expanded isotropically. SD does not encode covariance or a confidence
  interval. Finite nonnegative values are required when supplied; unknown is
  null, not zero. Published mean error is not automatically an SD.

These representation contracts do not compute scientific estimates. Tests use
synthetic quantities, check invalid units/NaNs/ambiguous SDs, immutable state,
metadata-only activation attempts, and cold-start/Unicode portability. No test
is presented as an anatomical prediction or independent accuracy result.

To replace a stub, a separate reviewed change must supply the exact primary
formula, source locator, coefficient units, observed landmark definitions,
coordinate convention, case-applicability protocol and hand-computed reference
examples. It must define how missing/reconstructed anatomy and absent source
error statistics are handled, and bind execution to the reviewed implementation.
There is no JSON coefficient evaluator, externally loaded Python or guessed
regression in this release. A3.3 comparisons and A3.4 Blender display remain
separate tasks; the ordinary fitting pipeline never calls these stubs.

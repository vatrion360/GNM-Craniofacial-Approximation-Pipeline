# A2.4 — operator-supplied empirical error-limit calibration

This standalone harness consumes **reviewed measurements produced by the
operator**. It does not segment DICOM, align skulls/faces, establish homologous
correspondence or conduct the project's CT study. No CT result is bundled.

It fits a multiplier of the existing ensemble `spread_rms_mm` to a declared
coverage target, then reports coverage on separate subjects without refitting.
The result is an **empirical radial error limit**, not a calibrated coordinate SD,
a Gaussian 95% interval, a posterior probability or an identification score.
It does not change meshes, fitting defaults or the A2.2 raw spread exports.

## Manual preparation and scope

1. Freeze the reconstruction/settings and ROI protocol before examining validation
   outcomes. Use the A2.2 **statistical ensemble mean** and its paired numerical
   `spread_rms_mm` field. Live-only fits and dense/TPS final surfaces are not
   automatically interchangeable with this ensemble.
2. Prepare the reference face and reviewed alignment in the same world-mm frame.
   Document segmentation, posture, exclusions and registration in your protocol.
   Face-based alignment can remove errors and must not be concealed. This tool
   performs no registration and cannot verify the declared alignment.
3. Retain original prediction vertex indices. Assign each retained vertex exactly
   one reviewed region. Exclude openings, scan residues and internal GNM geometry
   according to the frozen ROI, rather than after inspecting distances.
4. Compute an explicitly declared nonnegative error per retained vertex, using
   either reviewed homologous correspondence or unsigned reference-surface
   distance. Supply the paired A2.2 spread for that same vertex. Do not use
   signed distances, correction magnitudes, standard errors or coordinate SDs
   in place of the specified scalar fields.
5. Separate subjects used to fit the multiplier from subjects used to evaluate it.
   One case per subject is supported. Repeated sessions must not be presented as
   independent subjects. CT-conditioned approximations are refused for this
   skull-only error model because they use reference-face information.

Nearest-surface distance is not homologous-point error and can understate shape
error. It is offered only as an explicitly named empirical metric, not silently
substituted for anatomical correspondence. The reference, model, settings and ROI
hashes in the manifest are **declared provenance**; only the manifest, supplied
measurement CSVs and frozen calibration JSON are opened and hash-verified here.
Operators remain responsible for matching those declarations to actual files.

## Configuration with no scientific defaults

```
python -m cranio.calibration template --output case_manifest.json
```

The template leaves the scientific protocol fields null and has no cases.
`TODO(verify-source)`: fill the choices and sources before fitting. Unsupported or
missing choices cause a clear error; no multiplier is guessed. The supported
quantile and pooling methods must be explicitly selected, even though there is
currently only one implementation of each. A request for another estimator
requires a separately reviewed extension, not an undocumented fallback.

Manifest fields are exactly `schema_version` (integer 1), `protocol`, `cases`.

| Protocol field | Required meaning |
|---|---|
| `model_sha256` | Model asset digest |
| `fit_settings_sha256` | Digest of your frozen reconstruction/ensemble settings record |
| `region_definition_sha256` | Digest of the reviewed ROI/region definition |
| `units` | `world_mm` |
| `prediction_kind` | `statistical_ensemble_mean` |
| `error_definition` | `euclidean_correspondence` or `unsigned_surface_distance` |
| `target_coverage` | Explicit number strictly between 0 and 1; e.g. choose 0.95 only if specified in your protocol |
| `quantile_method` | Explicit `higher` |
| `pooling` | Explicit `pooled_vertices` |
| `alignment_protocol` | Documented alignment and coordinate frame, not an inferred transform |
| `source` | Justification/source of the protocol and its choices |

For each case, supply exactly:

| Case field | Meaning |
|---|---|
| `case_id`, `subject_id` | Stable pseudonyms; one case per independent subject |
| `split` | `calibration` or `validation` |
| `measurements` | CSV path, relative to the manifest or absolute |
| `measurements_sha256` | Actual digest of that CSV |
| `ensemble_sha256` | Declared digest of the corresponding A2.1 ensemble record |
| `reference_sha256` | Declared digest of the reference surface |
| `conditioning` | `skull_only`; CT-conditioned predictions are refused |

Digests are lowercase SHA-256. A manifest refuses repeated case/subject IDs or
measurement/prediction/reference hashes. Evaluation also refuses overlap with
training provenance in the frozen calibration file. Different aliases for the
same real person cannot be discovered automatically; pseudonym consistency is
part of the operator protocol. Source paths recorded inside a calibration JSON
are not followed during evaluation.

Measurement CSV header, in exact order:

```
vertex_index,region,error_mm,spread_rms_mm
```

Indices are distinct nonnegative integers. Each row has one nonblank region and
finite nonnegative error and spread. Duplicate indices, missing cells, extra
columns, NaN/Inf and negative values are refused. No row is silently filtered.
The model is not loaded, so correspondence and maximum valid vertex index must
be checked during manual preparation. Empty datasets are refused.

## Fit and frozen evaluation

```
python -m cranio.calibration fit --manifest training_and_holdout.json --output calibration.json
python -m cranio.calibration evaluate --manifest new_validation_cases.json --calibration calibration.json --output validation_report.json
```

Equivalent checkout wrapper: `python scripts/calibrate_uncertainty.py ...`.
Installed distributions use `python -m cranio.calibration`.

| Option | Default | Effect |
|---|---|---|
| Action `template`, `fit`, `evaluate` | Required | Prepare configuration, fit scale, or evaluate frozen scale |
| `--manifest` | None; required for fit/evaluate | Explicit case/protocol input |
| `--calibration` | None; required only for evaluate | Frozen multiplier record; never refitted during evaluation |
| `--output` | Required/new | JSON report; overwrites and input aliases refused |

At least two **distinct calibration subjects** are required by this software
gate. Two subjects are not asserted to be statistically sufficient. A manifest
may additionally contain held-out subjects; they affect evaluation only. With
no held-out subjects the report explicitly states that external validation has
not occurred. `evaluate` accepts only validation cases under an identical
canonical protocol hash. Changing ROI/settings/error metric/target coverage
requires a new protocol and calibration record. Keep validation data out of
those choices; the tool cannot prevent iterative researcher selection.

## Definition and zero-spread behavior

For each calibration vertex, let `d_i` be its declared nonnegative error and `s_i`
the ensemble RMS spread. Let `q` be the explicitly selected target coverage.

```
r_i = d_i / s_i
k = quantile(r, q, method="higher")
limit_i = k * s_i
covered_i = (d_i <= limit_i)
coverage = sum(covered_i) / number_of_retained_vertices
```

For sorted ratios of length n, `higher` uses zero-based index
`ceil((n-1)*q)`. Every retained vertex has equal weight in this pooled estimator.
Large/denser cases therefore contribute more; regional and equal-case coverage
are also reported so this weighting is visible. No surface-area weighting,
bootstrap intervals or independent-vertex assumption is used.

Zero spread and zero error contribute ratio zero. Positive calibration error at
zero spread makes finite multiplicative calibration impossible: fitting stops
rather than inserting epsilon or dropping that vertex. An all-zero spread dataset
also stops. During held-out evaluation, zero-spread positive-error observations
remain in the denominator and are explicitly counted as uncovered. A zero fitted
factor is retained with a warning; it is not proof of certainty.

Reports contain before/after coverage for each case and each observed region,
pooled coverage, equal-case mean coverage, number of contributing subjects,
vertex counts, mean error, limit widths, zero-spread failure counts, the factor,
protocol, provenance and input hashes. Regions absent in a case have reduced
reported subject counts; they are not imputed. The factor is global, not a fitted
per-region correction. `before` uses factor one as a descriptive comparison;
it does not assign a probability to one RMS spread.

All outputs retain `calibration_status: exploratory`. There is no automatic
"validated on N cases" or sufficient-N threshold. In-sample coverage is not
held-out performance. Three CT cases, if used, remain a small exploratory cohort;
this implementation does not establish a validated population or anatomical
applicability domain. Small-N uncertainty needs a separately specified study.

## Reproducibility and safety

Inputs are hash-checked again before atomic output publication. JSON excludes
timestamps and has deterministic ordering. Same inputs/paths/environment produce
identical bytes. Hashes support tracing, not authenticity or scientific approval
of manually edited records. Case pseudonyms appear in reports: do not supply
patient names or identifiers intended to remain private.

A fully synthetic runnable example is included:

```
python -m cranio.calibration fit --manifest examples/calibration_synthetic/manifest.json --output outputs/synthetic_calibration.json
```

Its numbers and non-CSV hashes are synthetic engineering fixtures, not GNM/CT
measurements, recommended thresholds or a clinical calibration. See
[TASK_A2_4.md](TASK_A2_4.md) for actual software verification and remaining work.

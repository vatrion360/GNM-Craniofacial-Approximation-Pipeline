# V19 implementation progress

The roadmap in TASKS_V19_REVIEW.md is a comparison against the audited base,
not a claim that all planned features are available. CT validation remains with
the project author; engineering tests do not establish anatomical accuracy.

## Atomic marker export and source attribution

Base: `6f31258250270f061230ed27f0b053236ee0d767` (PR #12 integrated).

- Changed `cranio/io_csv.py`, `cranio/export.py`, `addon_v13.py`: validate the
  closed temporary v3 file before replacement, retain previous outputs on failure,
  and show actual per-marker sources in the session report. V2 serialization is
  atomic without inventing a legacy mapping for validation.
- Tests: malformed reader fixtures still exercise the reader independently;
  writer tests cover invalid rows/metadata, streaming failures, locked destinations,
  Unicode/multiline notes and unchanged valid serialization. Installed Blender
  verifies failed-export preservation and session-source reporting.
- Before: 216 passed, 1 Windows-only skip; after: 228 passed, 1 Windows-only skip.
  Official GNM asset enabled. Ruff and Blender 4.5.0 Linux ZIP integration passed.
- No anatomical values, numerical defaults or model weights changed. No CT cases
  or interactive Windows acceptance were run. No open scientific choices in this task.

## Opt-in head-only identity fitting

Base: `0a51bd5c6b1fdf77481875e7c0c60ebcf1c10727` (atomic-export task).

- Changed backend metadata, shared identity solver/preview, CLI/config, Blender
  selector/external invocation, diagnostics and holdout evaluation. New
  `cranio/identity.py` verifies the naming contract before selecting components.
- The mode defaults to `all`. `head` fixes eye/teeth coefficients at zero even
  with a prior, solves only active columns and returns full-order coefficients.
  The inactive policy is explicit in docs/IDENTITY_SUBSPACE.md and reports.
- Before: 228 passed, 1 Windows-only skip. After: 251 passed, 1 Windows-only skip;
  official model enabled. Ruff passed. Blender 4.5.0 Linux ZIP integration passed,
  including the live selector/stamp and external CLI/report propagation.
- Tests cover restricted priors, conditional LOO, dense and measurement rows,
  metadata failures, coefficient replay, markerless warm starts and holdout.
- A separate run against the previous commit confirmed byte-identical default
  vertices and OBJ. See HEAD_IDENTITY_BENCHMARK.json for the synthetic scenario,
  seed, settings, timings, metrics and retained non-convergence warnings.
- No CT cases, calibrated uncertainty or anatomical benefit are claimed. The
  version remains unreleased; this task does not introduce new tissue values.
- Next planned lot: versioned tissue tables with provenance and explicit
  precedence for individual/manual case values; no invented SDs or thresholds.

## A1.1 — Versioned tissue-table exchange

Base: `24d3706b47d28d660dd700675f6f6e4536a8f886` (head-only identity task).

- Added `cranio/tissue.py`, the bundled JSON schema, JSON/CSV round-trip tools,
  source-byte hashes, null/unknown diagnostics and strict malformed-input checks.
  Added 62 synthetic tests, installed-ZIP schema checks, package-data entries,
  README command table and `tissue_tables_howto.md`.
- Baseline: 251 passed, 1 Windows-only skip; Blender 4.5.0 Linux installed ZIP
  passed with the reviewed official model and external Python. The local runtime
  uses Python 3.12.14 / NumPy 2.3.5 / SciPy 1.17.0 / trimesh 5.1.0 / pytest 9.1.1.
- After: 313 passed, 1 Windows-only skip. Ruff, installed Blender ZIP and
  wheel/sdist builds passed. The wheel was installed and its schema loaded
  outside the source tree.
- No constants, fit defaults, model data or case values changed. No table
  application, SD weighting or direction interpretation is introduced. Unknown
  fields stay null; schema validity is not scientific source verification.
- CT cases and interactive Windows acceptance remain manual. No new scientific
  choices were made. Next task: migrate existing constants with exact replay
  comparisons, keeping the existing manual-case precedence.

## A1.2 — Preserve defaults as versioned tissue data

Base: `6cbb445812d4b050100a0f285995cc0e4bdb5bdb` (A1.1).

- Added `legacy_hardcoded.json` (27 markers, five facial regions, scalp) and
  `var2026_table2.json` (32 existing transcribed positions). Unknown SD, estimator,
  method, posture, age, sample count and direction remain null. Existing
  attribution/cohort text is preserved, not newly verified against a PDF.
- Registry/paper modules now obtain depths from these files. CLI/config/Blender
  share the scalp default; explicit config overrides and manual marker values
  retain precedence. Anatomical definitions, order, sides, source strings and
  weights remain unchanged. No general table-application control is added yet.
- Implementation manifests include data/schema hashes. JSON/TXT reports label
  the bundled catalogue separately from effective case target/source records.
  A frozen study protocol needs a new revision after implementation changes.
- Before: 313 passed, 1 Windows-only skip, actual Blender 4.5.0 Linux ZIP passed.
  After: 319 passed, 1 skip; Ruff and Blender ZIP passed (official GNM and external
  fitting enabled), including table availability, shared scalp and manual values.
- Wheel/sdist built; installed wheel outside the source tree loaded both tables.
  New historical fixture checks all migrated values/float encodings exactly.
- `tools/verify_tissue_migration.py` replayed the historical and new trees using
  seeded artificial targets derived from their respective defaults. All numerical
  manifest fields and OBJ/PLY byte hashes matched for statistical fitting and
  optional local correction. See `TISSUE_MIGRATION_BENCHMARK.json`. Both runs
  retained non-convergence at the iteration limit; no accuracy claim follows.
- Deviations: existing Table 2 transcriptions are kept separate from unverified
  legacy heuristics instead of conflating their provenance. The task's requested
  real-case comparisons remain with the user; synthetic engineering replay is
  provided here. No new scientific values, weights or thresholds were selected.

## A1.3 — Explicit selected-marker scenarios and table comparison

Base: `6bcf3c81e3f7153725c1b2516fb546cc27b3107d` (A1.2).

- Added shared `tissue_application.py`, offline `tissue_compare.py`, Blender
  adapter/dropdown/Apply operator, CLI/config controls, audit records and custom
  table hashes in frozen protocols. Added `TISSUE_SCENARIOS.md`, command tables,
  30 synthetic pytest cases and actual Blender checks.
- Selection alone preserves all case values. Explicit labels/checkboxes plus
  explicit existing-axis acknowledgement authorize selected replacements,
  including manual measurements. No source frame, anatomical depth or SD is
  invented. Source direction is not enforced and is labelled as an assumption.
- Comparisons refit each table from the same original case, use a fresh output
  directory, keep ordinary QC gates and publish the summary only after success.
  Statistical/final corresponding-vertex differences are separate. Inputs are
  hashed across runs. Dense offsets/weights are unchanged. Frozen multi-table
  experiments require separately reviewed per-scenario protocols.
- Shared Blender geometry transaction preserves Undo/Redo, history and rollback;
  shared target/peg ownership is rejected to avoid moving unselected markers.
  External fitting consumes already edited CSV targets without double application.
- Before: 319 passed, 1 Windows-only skip. After: 349 passed, 1 Windows-only skip,
  official GNM enabled. Ruff passed. Actual installed-ZIP Blender 4.5.0 Linux
  passed including source/geometry history, rollback, persistence, CSV and Undo.
  Runtime: Python 3.12.14 / NumPy 2.3.5 / SciPy 1.17.0 / trimesh 5.1.0 /
  pytest 9.1.1. Wheel/sdist build and installed-wheel import checked separately.
- Default-path replay against the base produced identical numerical manifests
  and OBJ/PLY bytes with/without local correction. Both artificial cases retained
  non-convergence at the iteration limit; see TISSUE_SELECTION_BENCHMARK.json.
- Deviation/limit: A1.3 exposes only explicit existing-axis sensitivity, since
  source-direction enforcement belongs to A1.5 and bundled directions are null.
  Dense tissue-table application is not claimed. Historical Table 2 bulk Apply
  remains unchanged. SD weighting, direction enforcement, uncertainty and CT
  validation are not completed by this task; CT assessment stays with the user.

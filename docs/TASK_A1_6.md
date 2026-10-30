# A1.6 — tissue estimator and posture metadata

Base: `3fb2153fd0bcbff47a2356c30bd3b004c75fa664`,
`feature/tissue-measurement-directions` (PR #19). Both predecessor workflows
completed successfully before this task. This task is a stacked feature branch;
publication does not imply a merge into main.

## Changes

- `cranio/tissue_context.py`: shared case metadata loading, conservative posture
  label comparison, per-row supplied estimator/value/application audit, TXT and
  compact Blender summaries. No tissue values or posture corrections are computed.
- `cranio/tissue_application.py`, `cranio/pipeline.py`, `cranio/tissue_compare.py`:
  context retained in application/JSON records, warnings and TXT output; comparison
  preflight and summaries use the same case metadata as individual runs.
- `cranio/config.py`, `gnm_reconstruct.py`, `cranio/protocol.py`: optional
  `--case-posture`; unknown by default; posture treated as case-specific metadata,
  not a fitting constant frozen to the same value across subjects.
- `addon_v13.py`, `cranio/blender_tissue.py`: optional acquisition-posture field,
  compact summaries after explicit Apply, warning display, persisted history and
  `.blend`/CSV metadata. Field edits alone do not alter geometry or past history.
- `tests/test_tissue_context.py`, `tools/blender_context_checks.py`,
  `tools/blender_smoke.py`: new synthetic and actual Blender checks.
- README options table and `docs/TISSUE_CONTEXT.md`: semantics, workflow and limits.

## Verification (2026-10-30)

Linux, Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, trimesh 5.1.0,
pytest 9.1.1, Ruff 0.17.3; `OPENBLAS_NUM_THREADS=1`.
Official model SHA-256:
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
Blender 4.5.0 Linux archive verified against its official checksum manifest.

| Gate | Before | After |
|---|---|---|
| Pytest with official model | 404 passed, 1 Windows-only skip | 426 passed, 1 Windows-only skip |
| Actual add-on ZIP + model + external Python | `BLENDER_SMOKE_PASS` | `BLENDER_SMOKE_PASS`, including `BLENDER_TISSUE_CONTEXT_PASS` |
| Ruff and diff check | Existing baseline | Pass |
| Wheel/sdist build and installed wheel outside source tree | Existing baseline | Pass; context module and CLI flag checked |

The 22 new Python tests cover matching/different/unknown posture labels, missing
case documents, raw declaration preservation, conflicts and malformed metadata,
no inference from CT modality, direct use of supplied shorth/75-shormax values,
reference-only versus applied rows, CLI/TXT/JSON audit, comparison preflight,
case-specific protocol metadata and compact UI summaries. Posture-only variants
have identical coefficients, transform, lambda, solver diagnostics, metrics and
OBJ bytes, with and without local correction. The original CSV is unchanged.

Blender checks exercise the optional field, no movement on metadata edits,
warning/estimator display after Apply, preservation of past audit history,
`.blend` persistence and CSV export. Existing direction, Undo/Redo, geometry,
external fit/import and other integration checks remain active.

Separate-process official-model default replay using
`tools/verify_tissue_migration.py`, seed 1902, produced identical numeric manifests
and all OBJ/PLY hashes for both statistical and local-correction modes before and
after. The existing synthetic replay still reaches the iteration limit in both
trees (`converged=false`); this is regression evidence, not convergence or
anatomical accuracy evidence. Reports gain metadata; their bytes are not claimed
identical. No CT cases or subject data were analysed or changed.

## Scope and open scientific questions

- A posture label match does not prove comparable acquisition conditions. A
  mismatch is advisory, never an automatic correction or change in table/weights.
- Only whitespace/case normalization is applied; synonyms and translations are
  not inferred. CT modality does not establish posture.
- Precomputed estimator values are consumed as supplied and labelled as such.
  No shorth or 75-shormax calculation from means is implemented. Source/raw-derived
  value verification remains the author's responsibility; structural validation
  cannot certify it.
- Missing posture/estimator data remain unknown. No empirical data, thresholds,
  scientific references or defaults were invented or changed.
- External case metadata retains the existing precedence over embedded nested
  `case_metadata`; conflicting active root/CLI/case posture declarations fail.
- Dense depths/directions and the numerical solver are unchanged. Current table
  region estimators are reference metadata, not applied case depth measurements.
- Local gates are Linux; new-commit Windows checks rely on CI. Human interactive
  acceptance and CT calibration/validation remain separate.

# A6 — Second increment: age-at-death context

Base: `69ad0e09e8da80f884b0bb0fd5a1a7f0fa79f2d7` (merged PR #35).
Branch: `feature/age-context-audit`.

## Implemented

- `cranio/age_context.py`: strict structured assessment, conflict checking,
  inclusive interval audit, unknown template CLI and deterministic multi-table
  comparison CLI. Sources are recorded, not independently verified by the code.
- `cranio/tissue_context.py`, `cranio/pipeline.py`: optional age reporting for
  selected tables and ordinary fits. External metadata cannot silently erase or
  override a recorded age. Malformed/duplicate JSON declarations fail explicitly.
- `addon_v13.py`, `cranio/blender_tissue.py`: optional case JSON path, read only on
  Apply/export; age snapshot and file hash in tissue history and marker CSV.
- `tests/test_age_context.py`: 45 synthetic regressions; packaging assertion and
  `tools/blender_context_checks.py` coverage of RNA, CSV, immutable history,
  malformed source rollback, unchanged targets and save/reload.
- README, changelog, AGE_CONTEXT, prior documentation and roadmap updated.

## Verification — 2026-11-05

| Gate | Base | This change |
|---|---|---|
| Python with official model | 895 passed, 1 Windows-only skip (25.49 s) | 940 passed, 1 Windows-only skip (22.97 s) |
| Blender 4.5.0 Linux ZIP/model/external Python | Passed | Passed, including `BLENDER_AGE_CONTEXT_PASS` |
| Ruff and whitespace | — | Passed |
| Wheel, sdist, addon ZIP | — | Built |
| Installed wheel outside checkout | — | Unknown template and two bundled-table audits passed |

Python 3.12.14; NumPy 2.3.5; SciPy 1.17.0; trimesh 5.2.0; pytest 9.2.0.
Official model SHA-256:
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
Blender archive verified against its official checksum manifest.
The workspace was reset between sessions: code was recovered from the confirmed
base and the previously prepared edits. Both suites were rerun on an isolated
unchanged base as well as the modified checkout in the restored runtime.

The new synthetic regressions verify identical OBJ bytes, coefficients, transform,
lambda, solver diagnostics and numerical metrics with/without age metadata, both
with/without a selected table and local correction. They cover interval endpoints,
unknowns, unreviewed estimates, conflicting sources, invalid numerical inputs,
copy isolation, repeatable CLI output, file hashes and no-overwrite behavior.
The two-table fitting comparison retains the same case audit as a standalone fit.
These tests are software checks, not scientific validation on CT or historical cases.

## Scope and remaining work

This increment supports table-source review, not automatic age-based selection.
The bundled tables still have null age ranges; no scientific values were supplied
or invented. Age bounds have no inferred distribution or confidence level. No age
parameter, ageing simulation, tissue change, fit weight or new numerical default
was added. The metadata path is empty by default and no age audit is emitted when
age is absent. Default mesh behavior is unchanged.

A6 remains partial: prior UI/rationale migration, a source-reviewed table-selection
policy and later canonical A7 record consolidation remain separate. There is no
new CT study, calibrated age model, independent source verification or scientific
applicability guarantee. Windows/interactive behavior is not claimed from local
Linux tests; hosted Windows/Linux CI results are reported separately on the PR.

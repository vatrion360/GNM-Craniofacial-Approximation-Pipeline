# A3.1 — Anatomical-rule evidence registry

Base: `5220a767b9bb6f1197f9d4f6a990631d36c4fb9a` (merged PR #30).
Branch: `feature/anatomical-rule-registry`.

## Changes

- `cranio/rules/__init__.py`: standard-library loader, blank templates, detached
  records, exact input/schema hashes, schema and cross-field consistency checks.
  Reuses the tissue loader's restricted schema evaluator and strict JSON reader;
  no existing evaluator, fitting code or scientific constant changed.
- `cranio/rules/schema.json`, `registry.json`: versioned schema and six supplied
  feature-source leads. All entries remain needs_verification. No formulas,
  numerical errors, applicability labels or implementation IDs are invented.
- `cranio/rules/__main__.py`: explicit inspect/template CLI, safe new-file export.
- `pyproject.toml`, `tools/build_addon.py`: include the rules package/data in the
  wheel, sdist and addon ZIP without new dependencies.
- `tests/test_rule_registry.py`: 46 synthetic engineering tests; malformed
  metadata, incomplete review claims, missing error context, duplicate keys/IDs,
  non-finite numbers, detached records, deterministic output and protected files.
- `tests/test_packaging.py`, `tools/blender_smoke.py`: verify packaged resources,
  actual Blender import and unconfigured execution state.
- README command table, `docs/ANATOMICAL_RULES.md` and this task report.

## Executed verification — 2026-11-04

| Gate | Before | After |
|---|---|---|
| Python suite with official GNM model | 749 passed, 1 Windows-only skip | 795 passed, 1 Windows-only skip |
| Blender 4.5.0 Linux, actual ZIP/model/external Python | Passed | Passed; includes registry load |
| Ruff / whitespace | — | Passed |
| Wheel, sdist, addon ZIP | — | Built |
| Installed wheel outside checkout | — | Module origin, bundled catalogue, inspect and template CLI passed |

Runtime: Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, trimesh 5.2.0, pytest 9.2.0.
Official GNM v3 model hash:
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.

The scratch environment was recreated from the merged base before work. Both
baseline suites ran before source edits. Initial Blender startup failed with a
host bus error; re-extracting regular files in chunks from the checksum-verified
official archive resolved the runtime issue. The subsequent baseline and final
smoke runs passed. This was environment recovery, not an addon code correction.
PR #30's prior Linux/Windows CI runs were also checked and had succeeded.
Local Windows/interactive/anatomical/CT validation was not performed for this task;
new hosted CI results are reported separately.

## Scope decisions / deviations / open questions

The registry is metadata only. It does not introduce a Blender panel, predictions,
feature-to-GNM mappings, rule activation or case-specific confidence. Source
verification, implementation testing and external evidence are separate review
claims. Aggregate validated requires documentation of all three, but structural
acceptance is not independent confirmation or permission to execute a rule.
No automatic code/PDF binding or stale-review detection is claimed for free-text
review records. References/evidence must be re-reviewed when their scope changes.

Bibliographic leads from TASKS.md are preserved in supplied_reference. Full
citation fields stay null until verified; four supplied DOIs are retained and
missing DOIs are not guessed. Only eye/nose/mouth/ear feature leads are seeded;
tissue and overview references are not invented as executable feature rules.
The ear entry stays needs_verification like the other source leads, while its
prediction remains unspecified (unused policy planned for A3.2).

A3.2 requires the exact primary-source formulas, coefficient units, landmark
conventions, source locators, error definitions and applicability evidence.
Unknowns remain TODO(verify-source); no scientific choice is silently resolved.
A3.3/A3.4 comparison and UI remain separate tasks. Default live/offline outputs
and model assets are unchanged. CT evaluation remains with the user.

## PR #31 portability correction — 2026-11-04

Hosted CI at `1ac84194b2d8501d3714cc02dedb9322780a7225` exposed two defects
not caught by the earlier local runs:

- The dependency test prohibited all `urllib` imports. A cold Python startup
  imports `urllib.parse` through `pathlib`; parsing is not network activity.
  Preloaded standard-library modules masked this locally. The corrected test
  starts with `-I -S`, blocks numerical imports and socket audit events separately,
  permits URL parsing, checks both guards with negative controls, and prints
  child stderr on failure instead of hiding the cause in CalledProcessError.
- Registry CLI JSON used the console's encoding for literal Unicode. Windows
  CP1252 produced non-UTF-8 bytes on redirected stdout. JSON now escapes Unicode
  on stdout without changing decoded strings or UTF-8 files. Three regression
  cases exercise ASCII, CP1252 and UTF-8 streams, Unicode source text and paths.

Both failures were reproduced locally before editing: the original import guard
under `python -S` rejected `urllib.parse`, and CP1252 stdout failed UTF-8 JSON
parsing. The ordinary local suite still passed (792 passed, 4 skipped), explaining
why that suite alone was insufficient. After correction: 49 registry tests and
795 full-suite tests passed, with 4 skips (model-dependent and Windows-only tests).
Ruff and whitespace checks passed. Files changed: the registry CLI, its tests,
ANATOMICAL_RULES.md and this report. No fitting, anatomy or registry data changed.
The full Windows/Linux Python and model-backed Blender checks are rerun in CI;
these replace neither interactive Blender review nor CT validation.

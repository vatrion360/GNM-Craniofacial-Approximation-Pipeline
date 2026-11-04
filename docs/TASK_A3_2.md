# A3.2 — Rule contracts and unavailable-rule infrastructure

Base: `1c8ac3fa6b729d9243e274ba289c746b7293d062` (merged PR #31).
Branch: `feature/anatomical-rule-contracts`.

## Implemented scope

This increment implements the source-missing framework portion of A3.2. It does
**not** implement numerical eye, mouth or nose predictions, and does not claim
the complete A3.2 formula task is finished. No supplied primary-source formula
or hand-computed anatomical example was available for this increment.

- `cranio/rules/contracts.py`: immutable Prediction/RuleResult contracts, explicit
  units, tri-state applicability, optional SD and descriptive NotConfigured errors.
  Missing values remain null; point SD is never inferred from a scalar.
- `eyes.py`, `mouth.py`, `nose.py`, `ears.py` in that package: pure entry points.
  Source-missing predictors refuse execution; ear prediction remains unused and
  unspecified. No observations are read, validated or modified by these stubs.
- `cranio/rules/engine.py`: static code-owned routing and readiness reports.
  Registry review flags and implementation IDs cannot activate predictions or
  dynamically import code. Bad metadata/conflicting routes remain explicit errors.
- `cranio/rules/__main__.py`: optional status command with registry/rule filters;
  portable JSON stdout. Valid reports return 0 even when all predictions are
  unavailable; this is not a successful reconstruction or applicability verdict.
- `tests/test_rule_contracts.py`: 40 engineering regressions for representation,
  finite values/units, unknown SD/applicability, immutability, missing formulas,
  metadata-only activation attempts, CLI encodings and isolated Python startup.
- `tests/test_packaging.py`, `tools/blender_smoke.py`: package contents and actual
  ZIP import/readiness checks alongside the existing addon integration suite.
- README controls and `docs/ANATOMICAL_RULES.md`: API, states and explicit limits.

## Executed verification — 2026-11-04

| Gate | Before | After |
|---|---|---|
| Python suite with official model | 798 passed, 1 Windows-only skip | 838 passed, 1 Windows-only skip |
| Blender 4.5.0 Linux ZIP/model/external Python | Passed | Passed; includes rule contracts/readiness |
| Ruff / whitespace | — | Passed |
| Wheel, sdist and addon ZIP | — | Built |
| Installed wheel outside checkout | — | CP1252 status output and direct NotConfigured/unused behavior passed |

Runtime: Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, trimesh 5.2.0, pytest 9.2.0.
The official model checksum was verified before tests:
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
The Blender archive was checked against its official SHA-256 manifest. Both
baseline suites ran before source edits. Hosted Windows/Linux CI is reported
separately; no local Windows, interactive or CT assessment is claimed.

## Deviations and pending source-dependent work

There are no implemented anatomical formulas to validate against hand calculations
in this change. Synthetic result-contract tests are not substitutes for those
future reference tests. The result contract permits explicit unknown error
statistics; published mean error is never converted to an SD or per-case interval.

The five non-ear bibliographic leads remain needs_verification/not_configured.
The ear lead remains bibliographically needs_verification with execution unused.
Unknown registry IDs cannot run arbitrary code; known IDs map only to stubs.
There is no case input schema yet: exact anatomical observations, coordinate
conventions and applicability checks must be defined with each verified formula.
No automatic ancestry/sex/dentition inference or case validation is supplied.

To complete numerical A3.2: supply exact primary-source formulas and locators,
coefficient values/units, landmark conventions, applicability evidence and
hand-computed reference cases. Add each implementation in a separate reviewed
change, including missing/reconstructed-anatomy behavior and error semantics.
A3.3/A3.4 remain separate comparison/UI work. Default fitting, model assets,
registry source values and existing review states are unchanged. CT validation
remains with the user.

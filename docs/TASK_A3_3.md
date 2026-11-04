# A3.3 — Measurement and comparison foundation

Base: `6b137eb2f46f462c66abdb2894f08565c4613f3b` (merged PR #32).
Branch: `feature/anatomical-rule-comparison`.

## Implemented scope

This increment implements the native-mesh measurement and residual API portion
of A3.3, not its complete anatomical QC/constraint integration. No verified
anatomical mapping, predictor formula, SD or cutoff was supplied for this task.

- `cranio/rules/comparison.py`: model-bound mapping templates, reviewed point and
  feature definitions, strict topology/index checks, Euclidean widths/world-mm
  positions, explicit unavailable states, signed residuals and optional sourced
  threshold policies. The core uses NumPy only; CLI mesh reading uses trimesh.
- `tests/test_rule_comparison.py`: 32 regressions covering measurement, partial
  mapping, duplicate/bad indices, review/source requirements, geometry errors,
  signed scalar and vector residuals, unknown/zero SD, threshold gates, rigid
  transforms, deterministic CLI output, overwrite protection and real-model OBJ
  topology preservation. Synthetic indices are not anatomical correspondences.
- `tests/test_packaging.py`, `tools/blender_smoke.py`: addon ZIP includes and
  imports the core; exercises missing mappings and standardized residuals.
- README and `docs/RULE_COMPARISON.md`: command table, schema, units, formulas,
  interpretation and explicit pending integration.
- This task report records scope, tests and deviations.

## Executed verification — 2026-11-04

The unpublished files from an earlier attempt were lost on workspace reset. This
implementation was recreated on the merged base and tested again; results below
belong to this version, not merely to the earlier attempt.

| Gate | Before edits | After edits |
|---|---|---|
| Python suite with official model | 838 passed, 1 Windows-only skip (21.89 s) | 870 passed, 1 Windows-only skip (19.71 s) |
| Blender 4.5.0 Linux ZIP/model/external Python | Passed | Passed, including `BLENDER_RULE_COMPARISON_PASS` |
| Ruff / whitespace | — | Passed |
| Wheel, sdist, addon ZIP | — | Built |
| Installed wheel outside checkout | — | Model-bound template and residual API passed; import location verified |

Runtime: Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, trimesh 5.2.0, pytest 9.2.0.
Official model SHA-256 checked before tests:
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
Blender archive checked against its official SHA-256 manifest. Both baseline
suites ran before source edits. Hosted Windows/Linux CI is reported separately;
no local Windows, interactive Blender or CT validation is claimed.

## Deviations and remaining work

No legacy feature map is promoted to reviewed status. An empty template leaves
all anatomical points unknown. Operators must verify definitions and actual
native vertices; features without a suitable surface vertex remain unavailable.
The mesh-count/topology checks do not prove the anatomical validity of a mapping
or detect arbitrary coordinate permutations with unchanged triangle indices.

All source-missing eye/mouth/nose rules remain unconfigured. Binding a rule keeps
the measurement but cannot yield a prediction or a green light. The standalone
residual API can compare supplied compatible results; its synthetic traffic-light
tests establish only configured arithmetic, not clinical/forensic thresholds.
Future executable rules need case-input adapters and definition compatibility
checks; the engine refuses unexpected numeric prediction until then.

Pending: verified mappings and formulas, compatible skull-input adapters,
integration into the normal pipeline report, optional soft constraints, and the
A3.4 Blender UI. No default fitting, identity coefficients, tissue depths, model
asset, dependency requirement or geometry is changed. Independent CT evaluation
remains with the user. A3.3 is not claimed complete as a whole.

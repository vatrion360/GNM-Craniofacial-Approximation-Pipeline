# A3.4 — Blender anatomical-rule inspection panel

Base: `fc4546d3d343fb4327a3d28d7fc60b597d5e8616` (merged PR #33).
Branch: `feature/anatomical-rule-panel`.

## Changes

- `cranio/blender_rules.py`: closed-by-default panel, explicit catalogue refresh,
  blank mapping creation and measurement/snapshot export. Displays source/DOI,
  review and execution status, bound features and measurement/unavailable states.
  Calls the A3.3 NumPy engine; no fitting/geometry mutation or redraw I/O.
- `addon_v13.py`: register/unregister the separate panel module.
- `tools/blender_rule_checks.py`: headless integration scenarios for six catalogue
  entries; synthetic native mapping creation; exact shared-core parity; world-mm
  transform; unconfigured predictors; partial mapping; invalid units, presentation
  copies, modifiers and model mismatch; safe output/input handling; cached draw
  without file/model/measurement calls; input-change clearing; unchanged scene
  geometry/fit metadata/marker count.
- `tools/blender_smoke.py`: run the new checks and assert panel properties are
  added/removed in repeated register/unregister cycles.
- `tests/test_packaging.py`: verify the new Blender module is in the addon ZIP.
- README, `docs/RULE_COMPARISON.md`, `docs/BLENDER_RULE_PANEL.md`: control table,
  requirements, provenance and historical-snapshot semantics.

## Verification — 2026-11-04

Before source edits: 870 Python tests passed, one Windows-only skip (17.17 s),
and Blender 4.5.0 Linux ZIP/model/external-Python integration passed.

After: 870 Python tests passed, one Windows-only skip (17.11 s). The new tests
are Blender integration scenarios rather than additional pytest cases. Blender
integration passed, including `BLENDER_RULE_PANEL_PASS` and repeated lifecycle
checks. Ruff and whitespace checks passed. Wheel/sdist/addon ZIP were built;
installed-wheel contents and existing rules CLI were checked outside the checkout.

Runtime: Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, trimesh 5.2.0, pytest 9.2.0.
Official GNM model SHA-256:
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
No local Windows, interactive UI usability or CT/anatomical validation is claimed.
Hosted Windows/Linux CI reports separately. The synthetic panel test's point
indices are engineering fixtures only, not proposed anatomical correspondences.

## Scope and deviations

This completes the read-only panel for the currently available infrastructure.
Current predictors cannot produce a numerical anatomical comparison. Accordingly,
the SD-deviation/light fields explicitly remain unavailable/not assessed. Numeric
traffic lights are not fabricated to make the panel appear complete. Source
verification, numerical A3.2 formulas, compatible case adapters, verified GNM
correspondences, soft constraints and normal pipeline-report integration remain
pending; the complete anatomical-rule milestone is not claimed finished.

Measurements are explicit snapshots, not current-scene certification. Geometry,
units or external file edits require another export; no automatic polling or
continuous hashing is added. Source/map selection changes and new actions clear
the case display; prior export files are preserved. The neutral fit must be
selected, with presentation copies and evaluated geometry rejected.

No scientific values, assets, dependencies or numerical fitting defaults change.
No network access is added. CT validation remains with the user. Further UI
conveniences such as interactive correspondence picking are outside this task.

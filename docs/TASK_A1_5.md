# A1.5 — selected-marker tissue measurement directions

Base: `5b80f3c413405d281bd99af2d8567a800481f90a` (A1.4,
`feature/tissue-sd-weighting`). Predecessor PR #18 completed both GitHub Actions
workflows successfully before this task. This is another stacked feature branch,
not a claim that predecessor PRs have merged into main.

## Delivered

- `cranio/tissue_directions.py`: explicit reviewed direction manifest, exact table
  hashes and bone anchors, signed-vector normalization, vertical/sagittal algebraic
  checks, and an unreviewed-template generator from CSV v3. No inferred axes.
- `cranio/tissue_application.py`: common atomic planner supports existing/source
  modes; source mode records supplied vectors, frames and before/after targets.
- `cranio/config.py`, `gnm_reconstruct.py`, `cranio/pipeline.py`, `cranio/report.py`,
  `cranio/tissue_compare.py`, `cranio/protocol.py`: opt-in CLI, input/output path
  protection, direction-file hashing/change detection, comparison preflight,
  accurate mode reporting. Direction files are case inputs; frozen protocols
  retain the source-direction policy without freezing one subject's anchors for
  every subject.
- `addon_v13.py`, `cranio/blender_tissue.py`, `cranio/blender_marker_depths.py`:
  opt-in source-direction UI and shared rollback-capable transaction. Current
  source geometry is checked when a placement hash exists. Evaluation is cached
  only within this explicit operation, once per surface/flip combination.
- `tests/test_tissue_directions.py`, `tools/blender_direction_checks.py`,
  `tools/blender_smoke.py`: 33 new Python cases plus actual Blender UI/operator,
  geometry, rollback, Undo/Redo, CSV history and changed-source checks.
- README and direction/scenario/normal-placement documentation updated. Detailed
  configuration and limitations: [TISSUE_DIRECTIONS.md](TISSUE_DIRECTIONS.md).

## Verification (2026-10-30)

Linux; Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, trimesh 5.1.0,
pytest 9.1.1, Ruff 0.17.3; single OpenBLAS thread. Official GNM v3 model hash:
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
Blender 4.5.0 Linux archive was checked against the official checksum manifest.

| Gate | Baseline | Changed tree |
|---|---|---|
| Full pytest with official model | 371 passed, 1 Windows-only skip | 404 passed, 1 Windows-only skip |
| Actual ZIP integration with model and external Python | `BLENDER_SMOKE_PASS` | `BLENDER_SMOKE_PASS`, including `BLENDER_TISSUE_SOURCE_DIRECTIONS_PASS` |
| Ruff and diff whitespace check | Existing baseline | Pass |
| Wheel/sdist and installed wheel outside source tree | Existing baseline | Built; direction module and CLI/template entry points checked |

Synthetic tests exercise all three configured directions on sphere anchors,
rigid-transform equivariance, sign choice, exact anchor/hash bindings, invalid
or unsupported source definitions, missing/zero/nonfinite axes, arithmetic
extremes, reviewed flags/placeholders, malformed JSON, atomic planning, old
zero-length target axes, CLI reporting, comparison, frozen-policy separation,
input-file protection and mutation during fitting. They are not anatomical data.

`tools/verify_tissue_migration.py` ran in separate processes against the base and
changed trees with the official model and seed 1902. Both `statistical_default`
and `local_correction` produced identical numeric manifests and all OBJ/PLY
hashes with new options off. As before, the synthetic replay reaches the iteration
limit (`converged=false`): numerical regression evidence, not proof of convergence
or reconstruction accuracy. No CT cases were run or altered.

## Scientific decisions deliberately left explicit

- A sagittal plane does not specify a unique vector. Source mode requires a
  reviewed in-plane vector per marker, not an assumed anterior-posterior line.
- Vertical requires a reviewed case frame and a signed marker vector. Scene axes
  are never silently treated as anatomical axes.
- `bone_normal` consumes a supplied reviewed surface normal; this module does not
  estimate it or independently certify perpendicularity/exterior orientation.
  Existing local-normal estimation remains a separate, documented placement tool.
- Source mode rejects unknown/unsupported directions. Both bundled tissue tables
  retain unknown direction metadata. Source definitions must be supplied/reviewed
  before those rows can use this mode. No empirical constants/references were added.
- Geometry binding is weaker when the case has no source hash; the audit explicitly
  records that. Offline checks recorded hashes, not an unavailable original mesh.
- Scope is selected landmark table application. Dense region/scalp offsets continue
  to use their existing reviewed nearest-sample bone normals. No table-specific
  dense depth/direction override is implemented or claimed by this task.
- New behavior defaults off. `gnm_head.npz`, CSV compatibility and ordinary fitting
  are unchanged. No network/scipy/TensorFlow calls were added inside Blender.
- Local verification is Linux. New-commit Windows outcomes depend on CI; human
  interactive acceptance and CT/scientific validation remain separate.

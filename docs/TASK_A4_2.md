# A4.2 — reference frame and standardized orientation

Branch `feature/anatomical-reference-frame`, based on A4.1 merge
`3beebd9bf1ce9351fd8af9e21c01247c116d4f17` in
`feature/uncertainty-calibration-harness`. This is a separate roadmap task/PR.
No model assets or dependencies were added. Package/addon versions remain
5.0.0rc10 / 19.0.0; this does not revert numbering to the historical V14 plan.

## Files and behavior

- `cranio/reference_frame.py`: NumPy-only three-point Frankfort geometry,
  independent cranial midline SVD plane, proper world/frame transforms, explicit
  configuration and provenance gates, optional seeded placement sensitivity,
  camera axes, safe offline template/compute CLI.
- `cranio/blender_reference_frame.py`: manual computation and viewport actions,
  Scene record, configuration path, stale snapshot checks, opt-in capture switch.
  No bpy work occurs in a numerical worker or in the shared core.
- `cranio/blender_craniometry.py`: optional snapshot in existing JSON/CSV metadata;
  no key added when no frame exists.
- `addon_v13.py`: registration and capture integration; anatomical camera roll,
  conservative framing/clipping, retained frame metadata and camera restoration
  on render failure. Old orientation remains the default.
- `tests/test_reference_frame.py`: 24 synthetic geometry/provenance/CLI tests,
  deterministic conditional noise propagation, and byte-identical default fit
  outputs with/without frame metadata.
- `tools/blender_reference_frame_checks.py`, `tools/blender_smoke.py`: actual
  Blender RNA, placement, source/review invalidation, JSON/CSV, viewport action and
  capture-camera integration checks.
- README options, `REFERENCE_FRAME.md`, extended-reference/marker-format notes,
  and this execution report.

## Executed checks (2026-11-02)

| Check | Baseline | Changed code |
|---|---|---|
| Python suite with official GNM model | 603 passed, 1 Windows-only skip | 627 passed, 1 Windows-only skip |
| Blender 4.5.0 Linux, actual ZIP/model/external Python | Pass on unchanged base checkout | Pass, including `BLENDER_REFERENCE_FRAME_PASS` |
| Ruff and whitespace checks | — | Pass |
| Wheel/source distribution/addon ZIP build | — | Pass |
| Installed wheel outside checkout | — | Reference module import and template CLI pass |
| Default statistical/final OBJ and displacement PLY | — | Byte-identical with/without frame metadata on synthetic fixture |

Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, pytest 9.2.0, Linux x86_64.
Model SHA-256:
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
The official Blender archive checksum was verified. Initially two extracted
runtime files were truncated, causing Blender to fail even at `--version` before
loading Python/addon code. Re-extracting those files restored operation. The
baseline Blender gate was then rerun on an isolated unchanged base checkout;
the changed ZIP passed separately. No addon change was needed for that runtime
failure.

New Blender checks cover: default off/no metadata, registration cleanup through
the main smoke gate, arbitrary tilted source frame, preserved object matrices,
reference movement, definition edits, source mesh edits, configuration edits,
reconstructed Porion rejection, current/stale metadata, CSV/JSON preservation,
three camera rotations, and camera restoration after a deliberate renderer error.
The synthetic renderer-error traceback in the log is expected and asserted.

The capture renderer is stubbed in the new test: actual operator/RNA/camera
geometry is tested, **not PNG pixels or lighting**. Interactive UX, `.blend`
reload-specific tests, local Windows execution and anatomical/CT validation were
not performed. CI results are reported separately for the published commit.

## Choices and scope boundaries

- No automatic anatomical selection, scientific thresholds, missing tissue
  values or placement SDs are introduced. Porion/Orbitale definitions and the
  selected protocol still require expert review. L/R rejection is a consistency
  check, not a guarantee against all labelling errors.
- Midline references explicitly exclude the mandible. Missing/reconstructed
  references are not silently filled; partial skulls without this protocol's
  observed inputs remain unsupported by this frame action.
- Residual RMS is exported separately from optional conditional error summaries.
  No RMS-as-confidence claim or implicit placeholder SD is made. Nonzero SDs
  must be supplied with sources; all invalid Monte Carlo draws abort the analysis.
- Orientation changes viewport/camera state only. Automatic rotation of skull,
  face or marker coordinates is deliberately not performed. Transforms are
  exported for explicit downstream use, preserving same-segmentation coordinates.
- Existing restoration planes and face fitting remain separate, unchanged paths.
  Reference-frame metadata alone neither adds constraints nor changes lambda.
- No new definition source/PDF or CT data was required to implement geometry;
  configuring anatomical choices and validation remains the operator's task.
  No anthropometric feature/classification result is claimed. A4.3 remains next.

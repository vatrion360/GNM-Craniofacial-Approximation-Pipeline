# Validation and release gates

## Evidence obtained for this revision

Local execution on 2026-09-25, Linux x86_64, Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, trimesh 5.1.0.

| Check | Evidence / status |
| --- | --- |
| Automated numerical/input/pipeline/packaging tests | 59 passed, including the official model integration test; see commands below |
| Official GNM asset identity | SHA-256 matches the pinned asset; 17,821 vertices, 253 identity dimensions |
| Complete reconstruction from official mean-model synthetic markers | Passed; produces statistical/final OBJ, displacement PLY, TXT and JSON |
| Direct neutral-model parity with upstream GNM NumPy implementation | Three seeded coefficient vectors; maximum coordinate deviation below 0.000016 mm; [machine-readable result](upstream_parity.json) |
| Outer holdout evaluation on synthetic official-model markers | Executed; software sanity check only |
| Reconstruction without network | Socket connection entry point blocked in the end-to-end test; runtime fitting contains no downloader |
| Python build and complete add-on ZIP | Built; vendored Python sources compile; final wheel checked outside the source tree |
| Blender runtime/headless test | **Not executed here**: no Blender executable; package/download installation attempts were unavailable in this environment |
| Interactive Blender Windows/macOS/Linux acceptance | **Pending** |
| Independent paired skull/face accuracy or recognition | **Not performed; no subject data supplied** |

A synthetic test with targets derived from the same statistical model is expected to fit closely. It is not an empirical accuracy study. The parity result only checks neutral identity evaluation against upstream, not anatomical validity.

## Reproduce engineering tests

```bash
python -m pip install '.[dev]'
# Set GNM_MODEL_PATH to the reviewed official model to include integration.
python -m pytest -q
python -m ruff check cranio addon_v13.py gnm_reconstruct.py tools tests
python -m build
python tools/build_addon.py
```

Optional direct upstream parity (only for development; adds upstream dependencies):

```bash
python -m pip install absl-py 'etils[enp,epath]'
python tools/check_upstream_parity.py --upstream vendor/GNM --npz models/gnm_head.npz --output outputs/parity.json
```

With the model environment variable set, run:

```bash
blender --background --factory-startup --python-exit-code 1 --python tools/blender_smoke.py
```

The ordinary Python test suite does not import `bpy`; passing it cannot establish Blender compatibility. CI includes a Python matrix and a Blender 4.5.0 Linux integration job. The latter verifies the official model checksum and exercises the ZIP, marker exchange, external fitting/import and cancellation. Configured jobs are not evidence of an executed run; record successful run URLs with a release. Set `GNM_EXTERNAL_PYTHON` to the external environment's Python executable to include fitting/import/cancellation in the local Blender script.

## Blender manual acceptance checklist

Run this on each advertised Blender/OS pair and record exact versions, asset hash and outcomes:

- Install only the ZIP; enable/disable/re-enable; ensure no missing `cranio` imports or duplicate handlers.
- Import mm, cm and metre copies of a known mesh; compare calibrated world-mm measurements and source orientation.
- Place/move/delete markers, edit a tissue depth, modify a vertex correspondence, undo/redo, save/reload; confirm marker geometry and v3 export agree.
- Verify v3 round trip preserves bone position, target, manually selected vertex and tissue source; test a legitimate origin point.
- Load model and inspect ghost locations, dual viewports and side convention. Document anatomical correspondence review separately.
- Run external fitting in paths containing spaces and Romanian characters; verify new case folder, successful log/report and imported world-mm mesh alignment.
- Cancel a long run, close/reload the file, and disable the add-on while a run is active. Check process termination, released logs and no stale result import.
- Stop optional preview; confirm timer/handler cleanup and expected UI pauses for expensive previews.
- Repeat with partial skulls, missing mandible, reversed normals, malformed marker data and missing model/dependencies. Failure must be explicit; originals must remain intact.

## Independent scientific validation programme

1. Define intended population, age range, preservation state and use case before testing. Separate method development from a locked external subject test set. Keep subjects disjoint; do not split vertices of the same subject across train and test and call it independent validation.
2. Acquire appropriately governed, paired skull/face data in a consistent physical frame. Document segmentation, pose, expression, imaging resolution, tissue compression, dental status and missing anatomy. No additional scanning is implied by this software.
3. Have independent specialists annotate predefined bone/skin landmarks with documented definitions. Quantify repeatability/interobserver error and distinguish measured from inferred/mirrored points.
4. Lock correspondence map, tissue sources/directions, regularisation, dense masks, exclusion rules and optional correction settings before evaluating the external subjects. Include rigid-mean and marker-only baselines; perform ablations for each refinement.
5. Evaluate anatomically corresponding landmarks plus region-specific surface distances in mm, with a declared alignment protocol. Separate fitting error from held-out error. Do not permit unconstrained post-hoc registration that erases clinically/anatomically meaningful shape or scale errors.
6. Report subject-level distributions, mean/median/RMSE/p95, signed regional bias where meaningful, failures and uncertainty intervals for aggregate statistics. Use subject-level resampling. Investigate systematic subgroup differences and underrepresented cases without unsupported generalisation.
7. Quantify sensitivity to landmark placement, FSTT choice/direction, missing bone, model/prior selection and scan resolution. Only call a range calibrated uncertainty after testing empirical coverage on unseen subjects.
8. If recognisability is an objective, use a separately designed blinded protocol with distractors and appropriate chance/baseline comparison. Geometric closeness alone does not establish identification performance.
9. Publish the protocol, provenance, exclusions, software/model versions and results. Report unsuccessful cases. Define acceptance thresholds prospectively for the intended application rather than inventing a universal millimetre guarantee.

Until these gates are completed, this is a **release candidate for supervised research**, not a validated forensic identification system or a certified clinical product.

# A7.1 increment 3 — Blender saved-fit record export

Base: `29954b39a2b8cdd08dfec73f3b23100f04d75c6b` (PR #39 merged).
Target: `feature/uncertainty-calibration-harness`.

## Changes
- `cranio/blender_record.py`: closed-by-default panel, explicit saved-report
  selection/active-object shortcut, optional artifacts/limitations/ensemble fields,
  external job, cancellation and scene/file/unregister cleanup.
- `cranio/record_job.py`: request/source hash snapshot, safe fixed CLI bootstrap
  from the installed ZIP, completion-file integrity and source identity checks.
- `addon_v13.py`: registration, unregister and file-load stop hooks only.
- `tests/test_record_job.py`: 19 synthetic tests, including actual external Python,
  Unicode/metacharacter paths, stale/corrupt/incomplete results and diagnostic status.
- Packaging assertions, actual-ZIP Blender checks and workflow documentation.

No fitting/default/mesh/marker/CSV changes. The report is about saved fit files;
the UI explicitly excludes later scene edits. Optional A2.1 evidence retains its
existing uncalibrated scope; no CT result, scientific value or threshold is added.

## Verification
- Baseline: **1054 passed, 1 skipped**, 48.70 seconds.
- Final Python suite: **1073 passed, 1 skipped**, 51.84 seconds.
- Focused launcher/packaging tests: **21 passed**.
- Ruff and wheel/sdist/Blender ZIP builds passed.
- Official model SHA-256:
  `e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
- Linux, Python 3.12; NumPy 2.3.5, SciPy 1.17.0, trimesh 5.2.0,
  pytest 9.2.0; OPENBLAS_NUM_THREADS=1.
- One host pytest-plugin CallSpec2 deprecation warning, unrelated to this change.
- Base hosted runs 43183792015 (Python/packaging) and 43183791904 (Blender)
  succeeded. Local Blender startup remains unavailable; no local Blender pass
  is claimed. Feature Windows/Linux Blender and Python CI results are tracked
  on the PR.

The added actual-ZIP Blender check exercises explicit report selection, missing
options/interpreter rejection, external export and new text display, immutable
source meshes/markers/files, corrupt output rejection, cancellation, and deletion
of the owning scene followed by replacement with the same name. Existing smoke
registration/unregistration cycles exercise the new module too.

## Scope, safety and remaining work
Source-report reading and the interpreter probe occur only on explicit export.
Mesh hashing and optional ensemble checks run in the external child; panel redraws
perform neither. No background thread touches bpy. A fixed bootstrap imports the
ZIP's own cranio.record, rather than relying on an older installed module.

The original report identity is captured at submission and checked before display.
Optional files are pinned by the child when read. Result paths embedded in JSON
never choose executable code or mesh loads. Cancellation retains files, including
a completed result if the process already finished; it does not claim deletion.

This makes the existing saved-fit record usable in Blender. It is not live-scene
recording, calibration application, validity-domain validation or a scientific
export-mode gate. Those remain separate increments; CT evaluation stays manual.

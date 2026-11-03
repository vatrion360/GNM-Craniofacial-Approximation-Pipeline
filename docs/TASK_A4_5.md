# A4.5 — Explicit mandibular articulation

Base: `23c100ecdbecee7c99a297fccfcb2804ef2f8600` (merged PR #28).
Branch: `feature/mandible-articulation`.

## Changes

- `cranio/articulation.py`: NumPy rigid world transform validation, paired point
  distances, necessary edge-incidence closure check. No jaw joint or pose inferred.
- `cranio/blender_articulation.py`: main-thread wireframe preview with native
  controls, Apply/Cancel transaction, association by registered source IDs,
  explicit review, stale signatures and session pose/history export. Previous
  reviews and collision overrides remain archived within each pose event.
- `cranio/blender_occlusion.py`: on-demand BVH overlap, conditional parity
  containment (including nested surfaces), sampled vertex gaps and optional
  configured contact threshold. Missing/open anatomy stays explicit.
- `addon_v13.py`, `cranio/blender_craniometry.py`: register panel, gate sessions
  using the new tool, attach pose records to CSV/craniometry/session reports.
  No new default fitting behavior or change to `fit_identity`.
- `tests/test_articulation.py`: 8 synthetic tests covering transforms, partial
  references, open surfaces and offline metadata/mesh parity.
- `tools/blender_articulation_checks.py`, `tools/blender_smoke.py`: actual Blender
  mixed-fragment motion, associated markers, cancellation, invalid scale, stale
  placement/pose/geometry gates, metadata, registration persistence, collision
  override, transaction rollback, Undo/Redo, BVH overlap/nesting/open surfaces.
- README options and `MANDIBLE_ARTICULATION.md` document workflow and limits.

## Executed verification — 2026-11-03

| Gate | Before | After |
|---|---|---|
| Python suite with official GNM model | 707 passed, 1 Windows-only skip | 715 passed, 1 Windows-only skip |
| Blender 4.5.0 Linux ZIP/model/external Python | Passed | Passed, including articulation and Undo/Redo |
| Ruff / whitespace | — | Passed |
| Wheel, sdist, addon ZIP | — | Built |
| Installed wheel outside checkout | — | Pure NumPy articulation transform passed |
| Identical targets with/without pose metadata | — | Offline OBJ byte-identical; metadata retained |

Runtime: Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, trimesh 5.2.0, pytest 9.2.0.

The workspace reset during implementation. The base was freshly cloned and
baseline checks rerun before restored changes were applied; this report refers
to that restored implementation. The official Blender archive checksum was
verified. Model SHA-256 remains
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
No scan, model asset, non-commercial dependency or anatomical default was added.
Tests use synthetic geometry only. Local Windows/interactive/anatomical/CT
validation was not performed; hosted CI is reported separately.

## Scope decisions / deviations / open work

Native controls act on independent wireframe copies, then Apply transforms the
original fragments and source-bound observations together. This keeps cancellation
non-destructive and makes pose changes explicit. Existing scene hierarchies,
constraints, animated objects and modifiers are refused, not silently rewritten.
Live fitting stops during preview and must be restarted by the operator.

Condyle/fossa measurements are explicit point-reference distances, not inferred
joint centres or a claim about joint congruence. Dental BVH intersection pairs
include contact; conditional parity requires appropriate closed surfaces and can
be ambiguous. No exact penetration volume, continuous collision detection,
non-penetration certificate or physiological occlusion verdict is supplied.
No tolerance is treated as an anatomical norm. Missing sides are not completed.

A reviewed pose is a human assumption with evidence/limitations recorded. It
is not an automatically validated configuration. New point-definition review is
required after movement, even when source-bound positions were rigidly propagated.
Other inherited unassociated markers are not guessed or moved by label.

A4.6 pose-sensitivity sampling, automatic occlusal optimization, broad hierarchy
support and interactive assessment on real partial specimens remain separate
work. CT validation remains with the user. None is claimed complete by this PR.

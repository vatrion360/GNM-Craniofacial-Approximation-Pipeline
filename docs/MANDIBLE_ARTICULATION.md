# Explicit mandibular articulation (A4.5)

This optional Blender tool applies an **operator-chosen rigid pose** to one or
several preserved mandibular fragments. It does not infer physiological occlusion,
complete a missing jaw, change the GNM identity/expression directly or introduce
a GNM jaw joint. Default fitting is unchanged until the operator uses the tool.

## Workflow

1. Work in Metric scale 0.001 (one world coordinate = one mm). Register the
   preserved fragments and mark their source anatomy **MANDIBLE**. Select only
   the fragments to move together. Independently aligned fragment groups can be
   articulated in separate operations; no bilateral completeness is assumed.
2. In **Mandible Articulation**, optionally select separate observed lower/upper
   dental meshes. The lower mesh moves with the selected fragments. Supply point
   empties for the left and/or right condyle and corresponding fossa if these
   observations exist. Condyle empties move; fossa empties remain stationary.
   Object selection/labels are operator declarations, not anatomical certification.
3. Place the 3D cursor at the desired manipulation pivot and press **Articulate
   Mandible: Wireframe Preview**. Use G/R or the native translation/rotation
   handles on the new control. Wireframe mesh copies show the proposed position;
   original surfaces/markers have not moved. Copies have independent mesh data.
   Scaling, shear and reflections are rejected. Live fitting is stopped.
4. **Check** computes the current proposed reference distances and dental
   diagnostics. Results appear in the panel status and `GNM_Mandible_Checks`
   Blender text. Checks run only on explicit actions, never on viewport redraw.
5. Enter a **Pose assumption / justification**, then **Apply**. All selected
   fragments, optional lower dentition/condyle points and source-bound marker
   bone/skin/peg objects move by the same world transform. Source-bound cranial
   point empties also move. Marker tissue depths are unchanged. **Cancel** deletes
   the preview without moving originals or overwriting intervening user edits.
6. Re-review moved cranial point definitions. **Record Reviewed Pose** explicitly
   acknowledges the operator assumption and stores fresh geometry diagnostics.
   If collision flags exist, a documented override reason is required. Missing
   teeth or reference pairs stay `unavailable`; review does not certify them.
7. Restart fitting if desired. **Export Pose Session JSON** writes history and
   current/stale review status without overwrite. Marker CSV metadata, craniometry
   JSON and the session text include the pose record. The offline pipeline retains
   this metadata and consumes the already transformed world-mm coordinates; it
   does not apply the transform again.

Until a newly applied pose is reviewed, fitting and marker export are blocked
for sessions using this tool. A checked legacy articulation checkbox alone does
not bypass this gate. Existing sessions that have never used the tool retain
legacy behavior. A new preview also blocks fit/export until cancelled or applied
and reviewed. Undo/Redo restores geometry, pending preview and record state.

## Ownership, provenance and stale data

Objects must be static and independent: Object Mode, no parenting/children,
constraints, animation/drivers or mesh modifiers. Prepare copies with an explicit
modifier workflow if needed; this tool does not silently apply modifiers or
rewrite hierarchies. Mesh data are not modified by Apply. The transform is rigid
within a recorded-code float32 numerical tolerance (`RIGID_ATOL=2e-5`), not an
anatomical plausibility range. World matrices use Blender's finite precision.

Only markers associated by registered source ID move automatically. Anatomical
names alone cannot establish ownership. Review any unassociated observations and
attach/re-place them on the correct source before using the tool. Shared objects
belonging to different sources are refused. Bone/source hashes must match at the
start; stale placements cannot be legitimized by a new articulation. A known rigid
move updates placement hashes, while moved cranial definitions lose review and
previous marker-orientation estimates may become stale. Recheck these separately.

During preview, changes to originals, associated object membership, reference
selection, control scale or preview geometry stop Apply. A transaction failure
restores moved object matrices and modified provenance/history. On successful
Apply the preview is removed and an append-only pose event is stored in the scene.
Each event records the assumption, delta transform, before/after matrices and
geometry hashes, affected source manifests and selected reference objects.
A separate latest-review record stores diagnostics and any collision override.

Review signatures include all registered bone sources and the referenced objects.
Subsequent transform/reference/registry/assumption changes invalidate review.
Fit snapshots check transforms and registry; explicit export also checks geometry
hashes. Geometry edited outside this workflow requires renewed articulation/review.
The panel's last status is not a continuously recomputed diagnostic.

## What the geometric checks mean

- **Condyle–fossa:** Euclidean distance between the two explicitly chosen point
  empties, in world mm, reported separately for each available side. This is not
  minimum joint-surface distance or an anatomical pass/fail criterion. A missing
  opposite side is not synthesized, mirrored or assumed symmetric.
- **Surface intersections/contact:** number of triangle-pair overlaps returned by
  Blender's BVH. Contact/coplanar overlap and crossing surfaces are not reliably
  distinguished by this count; it is a review flag, not penetration volume.
- **Containment:** bidirectional vertex-in-surface parity checks catch nested
  surfaces that have no triangle crossings. Closed edge incidence is required.
  Three ray directions must agree; disagreements are reported as ambiguous.
  Near-boundary vertices are reported separately. Open surfaces report this
  metric as unavailable. Edge closure does not certify absence of self-intersection
  or valid anatomy, so these results are explicitly conditional.
- **Gaps/contact:** minimum bidirectional vertex-to-triangle distance and number
  of sampled vertices within an optional explicitly enabled tolerance. The
  tolerance is unconfigured by default. These metrics depend on tessellation and
  do not give the exact triangle-to-triangle minimum gap or a physiological contact
  tolerance. Record the rationale for a selected tolerance in the pose assumption.

BVH computations use float32. The boundary/ray step epsilon is recorded as
`64 * float32_epsilon * max(1, maximum absolute coordinate)` in mm. It is numerical,
not anatomical. Very small structures or large world-coordinate offsets can
make containment ambiguous or resolve nearby surfaces poorly. Inspect the
reported epsilon, boundary counts and original surfaces. Degenerate triangles
are rejected. Self-intersecting/nonmanifold dental scans need repair or an
explicitly limited assessment. **No flags in performed checks is not proof of
non-penetration or correct occlusion.**

No scientific tissue value, plausible joint distance, contact threshold or jaw
pose distribution is supplied. The operator retains responsibility for fragment
assembly and the anatomical interpretation. These software checks are not CT
validation, and do not replace inspection of the fitted face after articulation.

# Propose bone landmarks on one observed fragment (B2.2)

Use this optional Blender tool when you have a reviewed bone atlas, homologous
preserved anatomy and existing observed anchors. It proposes additional **bone**
positions. It neither estimates tissue depths nor completes missing anatomy.
There is no bundled atlas, automatic placement, fit update or export gate.

1. Prepare the [reference skull](PLACEMENT_ATLAS.md) in a different scene,
   including its source and single-vertex `ATLAS_REVIEWED:<label>` groups.
   Choose an independent working mesh registered as **preserved bone**. Use
   Object Mode, static geometry without modifiers or shape keys, and the
   addon's metric scene convention (1 Blender coordinate = 1 mm).
2. On each mesh explicitly select the **same anatomical surface** and assign
   its vertices with positive weight to `ATLAS_PATCH:<name>`. Include only
   intact homologous exterior bone on the target. Only triangles with all three
   vertices assigned are used. Use one connected patch at a time. For a right
   vault, nasal fragment and left mandibular fragment, name/run each separately.
   Do not assign the other side, an internal sheet or a mirrored repair under
   the same name. The program cannot verify anatomical homology from a name.
3. Place and check at least four matching, noncoplanar bone anchors on the
   registered patch. The tool uses case marker-list labels, observed status,
   source ID and placement geometry hash; the skin end of a peg is never an
   anchor. Stale source hashes require fresh verification and placement on the
   current bone. Too little intact anatomy for those anchors means no proposals
   for that fragment. Complete any pending articulation review first.
4. In **GNM Scientific Markers → Fragment landmark proposals**, choose the
   reference skull, activate the target object and enter the patch name without
   its prefix. Supply three positive distances (mm): permitted surface gap
   for correspondences and snapping, maximum distance to a local anchor,
   and maximum similarity residual at any anchor. No preset values have been
   validated. Click **Propose Landmarks (Review Only)**.
5. Open the new **GNM Landmark Proposals.json** text in Blender's Text Editor
   (numbered on subsequent runs). Each `needs_review` row contains a candidate
   in the case world-mm frame. Inspect it against the observed bone; place it
   manually only if justified. Other rows give reasons with null coordinates.
   The text is a historical snapshot, not a live overlay. Re-run after editing
   sources, anchors or patch membership. Failures do not create or update a
   snapshot; older ones remain. Treat saved text as case data.

## Registration and interpretation

Reference local geometry is aligned to target world mm by proper similarity on
named, equally weighted anchors. Negative/singular anchor cross-covariance,
degenerate or duplicate anchors, and anchor discrepancies above the operator's
limit stop registration. Distance-gated ICP refines that similarity using
target triangles and at most 256 deterministic area-stratified triangle-centroid
samples. Up to 12 iterations are accepted only if the sum of mean squared anchor
error and mean truncated squared surface distance decreases and the anchor
residual limit still holds. These are computational budgets. The system then
interpolates anchor residuals with the existing NumPy 3-D linear polyharmonic
spline (affine tail, zero smoothing), and projects held-out sites to the patch.
Blender's native BVH supplies closest triangle points on the main thread.

Sites too far from anchors on either mesh, too far from observed triangles, or
landing on an open cut edge receive no coordinates. For supported sites the
geometric score is one minus the larger of two ratios: pre-snap gap / maximum
gap and local anchor distance / maximum radius. It measures proximity under
the chosen limits, **not** anatomical accuracy or a calibrated probability.
A small gap cannot distinguish neighboring anatomical sites. Four nearly
planar anchors, incorrectly named anchors, missing bone close to surviving
bone or a locally distorted warp may lead to rejection or misleading proposals.
Mesh resolution and triangle ordering can affect ICP sampling. Inspect every
candidate. No general biomechanical, fold-free or laterality guarantee is made.

The JSON includes input geometry and patch hashes, reviewed vertex IDs, reference
source, observed anchor locations, limits, similarity, ICP counts, spline
diagnostics and per-site support. It does not replace the scientific fit record.

## Compare independent manual placements

Keep reference/registration anchors separate from test labels. An independent
operator should place the test labels without seeing the proposals. Save the
proposal text and a second JSON object mapping manual labels to coordinates
in **the same target world-mm frame**. No re-alignment is performed:

```shell
python -m cranio.landmark_proposals snapshot.json manual.json
```

The command refuses anchor labels, prints Euclidean errors and their median in
mm, and lists unassessed sites alongside the denominator. Report availability
as well as error. In the nonlinear synthetic regression fixture, two of three
held-out sites were supported (median error **0.0447 mm**); the distant third
site was withheld. The Blender synthetic fixture also exercises a cut edge and
stale input. These are software checks. No human skull or CT placement accuracy,
runtime on clinical scans, or inter-observer repeatability was measured here.

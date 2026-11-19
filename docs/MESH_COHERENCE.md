# T0.3 · Facial vertices inside a reviewed bone volume

Use this offline comparison on a facial surface and bone segmentation already registered in the same world coordinate frame, in millimetres. The primary result is the percentage of eligible facial vertices strictly inside the operator-reviewed bone volume. The report also gives the minimum triangle angle across the complete saved face using the existing mesh-quality calculation.

## Inputs and commands

1. Use the saved pipeline face OBJ with its original vertex order. For the skull supply a triangulated STL, PLY or pipeline OBJ. The restricted OBJ reader accepts positive vertex-only triangle indices. A face patch can be open.
2. Generate the inventory below. Standard output contains JSON with SHA-256 hashes and the face mesh angles. Without a review, the volume metric is `not_assessed`.

   ```sh
   python -m cranio.coherence --skull bone.stl --face fitted.obj
   ```

3. In the mesh editor, review the eligible facial skin group. Exclude internal surfaces, dentition, eye interiors and natural openings as appropriate for the case. Export its **zero-based vertex indices in the saved OBJ order**. Record which group, exclusions and segmentation revision you reviewed. Confirm that the bone mesh represents the intended bone material as closed, non-self-intersecting boundaries, including any cavities. A watertight outer scalp or cranial envelope would measure the wrong volume. For an open fragment or uncertain solid, set `bone_solid_reviewed` to false.
   For a Blender mesh whose vertex order you have verified against the saved OBJ, this Console expression copies the indices from a reviewed vertex group to the clipboard. Replace the group name with your own. Positive group weights include a vertex once.

   ```python
   import bpy, json
   obj = bpy.context.active_object
   group = obj.vertex_groups["Reviewed facial skin"]
   ids = [v.index for v in obj.data.vertices if any(g.group == group.index and g.weight > 0 for g in v.groups)]
   bpy.context.window_manager.clipboard = json.dumps(ids)
   ```

4. Create a review file using the two printed hashes. Replace the illustrative IDs and source text with the reviewed data.

   ```json
   {
     "schema": "gnm.coherence-review.v1",
     "skull_sha256": "<SHA-256 of the skull file>",
     "face_sha256": "<SHA-256 of the face OBJ>",
     "review_source": "<segmentation revision, skin group, exclusion and frame review>",
     "bone_solid_reviewed": true,
     "eligible_face_vertices": [2, 5, 12]
   }
   ```

5. Install the optional spatial index in the offline Python environment, then run the reviewed comparison.

   ```sh
   python -m pip install ".[coherence]"
   python -m cranio.coherence --skull bone.stl --face fitted.obj --review review.json > coherence.json
   ```

## Reading the result

Each eligible vertex counts once. `percent` equals 100 times the inside count divided by the eligible count. Boundary vertices remain in the denominator. The counts distinguish inside, outside, boundary and ambiguous. The output lists the original indices classified as inside or ambiguous. The result depends on the selected vertices and their density.

The skull reader welds exact coincident coordinates to reconstruct triangle adjacency in STL. Open edges, inconsistent winding, duplicate triangles and degenerate triangles prevent a volume score. These checks cannot establish that the segmentation encloses the correct anatomical material or rule out every self-intersection. The operator's review is required.

For the numerical test, the longest side of the skull bounding box is scaled to one. Points within the trimesh merge tolerance of the surface count as boundary. The output records this numerical tolerance converted to mm. Two fixed directions, each traced forward and backward, must agree on even/odd intersection parity. Nested nonintersecting shells therefore preserve cavities. Any disagreement makes the overall percentage unavailable. Changes to either input invalidate the review.

Exit 0 means the diagnostic completed. Read `skin_in_bone.status` to distinguish a measurement from an unavailable result. Malformed inputs or a mismatched review return exit 2. The program emits deterministic JSON for the same files and runtime. It performs no alignment, surface repair, clinical scoring or fitting.

The reverse measurement of uncovered bone surface requires an area denominator, a coverage definition and a tolerance. Regional tissue thickness requires measurement directions and profile error requires homologous reference points. These are separate T0.3 outcomes. Existing per-fit contacts and deformation diagnostics are available in [saved-fit consistency](POSTFIT_CONSISTENCY.md).

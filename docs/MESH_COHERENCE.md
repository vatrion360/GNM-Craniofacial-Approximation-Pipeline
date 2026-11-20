# T0.3 · Measuring coherence between bone and skin

Use this offline comparison on a facial surface and bone segmentation already registered in the same world coordinate frame, in millimetres. Supply a vertex review to measure facial vertices inside bone, a facet review to measure bone surface without skin coverage, or both in one command. The report also gives the minimum triangle angle across the complete saved face using the existing mesh-quality calculation.

## Facial vertices inside a reviewed bone volume

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

## Bone surface without skin coverage

Select the **external bone facets where skin coverage can be evaluated**, plus the corresponding cutaneous facets in the saved face. Review both in the same world-mm frame. An open bone fragment is eligible when its outward normals can be established. Exclude cut surfaces, cavities, natural openings and regions outside the face scan. For mixed remains, identify observed, mirrored and donor regions in the review and run separate selections if their results are to be reported separately.

For each point on a selected bone triangle, follow its outward facet normal from the bone surface up to the operator's `max_distance_mm`. The point counts as covered if this closed segment intersects any selected skin triangle. Contact and the far endpoint count. A skin surface behind the bone or beyond the specified distance leaves that point uncovered. Choose and document the distance for the case before comparing fits. It is a search limit with no universal anatomical default.

1. Run the inventory command above for the exact skull and face hashes. Review the **zero-based triangle indices in each saved file**, with the outward orientation given by the bone triangle winding. For a triangulated Blender mesh whose polygon order matches the saved facets, select the polygons in Edit Mode, return to Object Mode, and copy their indices with the Console expression below. Repeat on the other object. Verify the facet order after export, including STL/PLY import and any triangulation or modifier application.

   ```python
   import bpy, json
   mesh = bpy.context.active_object.data
   assert all(len(p.vertices) == 3 for p in mesh.polygons)
   bpy.context.window_manager.clipboard = json.dumps([p.index for p in mesh.polygons if p.select])
   ```

2. Prepare a coverage review. The following numbers refer to a synthetic two-patch test. Replace both selections, hashes, source and distance with the values for your case.

   ```json
   {
     "schema": "gnm.bone-coverage-review.v1",
     "skull_sha256": "<skull hash>",
     "face_sha256": "<face hash>",
     "review_source": "Synthetic open bone patches, complete skin field, 1 mm search from the fixture design",
     "outward_normals_reviewed": true,
     "skin_extent_reviewed": true,
     "eligible_bone_triangles": [0, 1],
     "skin_triangles": [0, 1],
     "max_distance_mm": 1.0
   }
   ```

3. Install the coherence extra and run the command. Add `--review review.json` to include skin-in-bone in the same report.

   ```sh
   python -m pip install ".[coherence]"
   python -m cranio.coherence --skull bone.stl --face fitted.obj --coverage-review coverage.json
   ```

Read `bone_without_skin_coverage.percent` as **100 × uncovered area / selected bone area**. The report gives all three areas (eligible, covered, uncovered) in mm², both facet counts, the search limit, and the coverage review hash. For example, a skin patch covering 2 mm² of a 10 mm² selection leaves 8 mm² uncovered, or 80%. A second selected layer over the same patch adds no coverage.

The calculation clips candidate skin triangles to each bone triangle's outward distance interval, projects them onto the facet plane, and measures the union of their intersections with the bone facet. This includes partial triangles. For floating-point roundoff at each endpoint the implementation snaps heights within 32 machine epsilons times the larger of the search limit and the maximum absolute bone-facet coordinate in mm. The result depends on bone normals, registration, both masks and the search limit. Compare runs with the same protocol.

Unreviewed normals or incomplete skin extent, degenerate selected facets, and duplicate or inconsistently oriented bone facets yield `not_assessed` and a null percentage. File-hash mismatches and invalid indices return exit 2. The operator verifies the skin extent and normal direction for each component, including isolated triangles. Anatomical interpretation and accuracy against an independent reference require additional evidence.

Regional tissue thickness requires documented measurement directions and profile error requires homologous reference points. Existing per-fit contacts and deformation diagnostics are available in [saved-fit consistency](POSTFIT_CONSISTENCY.md).

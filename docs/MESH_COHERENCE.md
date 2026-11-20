# T0.3 · Measuring coherence between bone and skin

Use this offline comparison on a facial surface and bone segmentation already registered in the same world coordinate frame, in millimetres. The command accepts independent reviews for facial vertices inside bone, bone surface without cutaneous coverage, regional directional thickness and error at homologous profile points. You can supply any combination in one run. The report also gives the minimum triangle angle across the complete saved face using the existing mesh-quality calculation.

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

## Regional thickness along documented directions

Measure the distance from a point on an external bone triangle to the selected cutaneous surface, along an explicitly signed world-space direction. The result for a fitted OBJ describes the **approximation**. To measure CT-derived thickness, use the corresponding bone and skin segmentations from that subject in the same world-mm frame. A segmented open patch can be used on either side.

Use the inventory command to obtain both file hashes. For each region, select the skin facets that correspond to the bone sites and verify their extent in the mesh editor. Teeth, folded internal surfaces and scan residues can create additional crossings. Give each sampled site a name. Record the source bone triangle in saved file order, its outward winding, and the three barycentric weights locating the site within it. The weights correspond in order to the first, second and third corners of the triangle and must sum to one. For example, `[1, 0, 0]` selects its first corner. A site can be away from all three vertices. Use the same sampling sites, axes, search distance and masks when comparing runs on the same geometry. Update the hashes and review the masks for each new mesh.

For a placed marker, use its bone endpoint. If you have the three saved world-mm triangle corners `a, b, c` (in file order) and the original world-mm endpoint `p`, the following gives candidate barycentric weights. Check the reconstructed point against the endpoint at the precision of your stored coordinates and verify the weights lie inside the triangle before saving them. A substantial discrepancy requires reviewing the triangle, frame or endpoint.

```python
import numpy as np
a, b, c, p = np.asarray([a, b, c, p], dtype=float)
uv, _, rank, _ = np.linalg.lstsq(np.column_stack((b - a, c - a)), p - a, rcond=None)
assert rank == 2
w = np.array([1.0 - uv.sum(), *uv])
print(w.tolist(), "reconstructed endpoint error (mm)", np.linalg.norm(w @ np.array([a,b,c]) - p))
```

Supply the signed bone-to-skin vector as `axis_world`. For a reviewed marker axis with a positive length you can use tip minus bone in world mm. For a source-defined direction, record the protocol and its signed orientation in this case's anatomical frame. The command normalizes that vector. Set `reviewed` to true only after checking the anchor, winding, direction definition and corresponding skin selection. Use false and null direction fields to keep a pending site in the counts. The search limit is supplied by the operator.

This synthetic review describes an oblique ray through parallel planes 3 mm apart. Replace the geometry, mask, source text and distance with your case values.

```json
{
  "schema": "gnm.thickness-review.v1",
  "skull_sha256": "<skull hash>",
  "face_sha256": "<face hash>",
  "review_source": "Synthetic planes in a common world-mm frame",
  "max_distance_mm": 10,
  "regions": {
    "patch": {
      "skin_triangles": [0],
      "sites": {
        "A": {
          "bone_triangle": 0,
          "barycentric": [0.5, 0.25, 0.25],
          "axis_world": [3, 0, 4],
          "direction_source": "Synthetic outward 3:4 axis in the world XZ plane",
          "reviewed": true
        }
      }
    }
  }
}
```

```sh
python -m pip install ".[coherence]"
python -m cranio.coherence --skull bone.stl --face fitted.obj --thickness-review thickness.json
```

Read `regional_thickness.regions` for the individual sites, measured and requested counts, and the minimum, median and maximum in mm over measured sites. Each named site counts once, so these statistics depend on sampling and carry no area or population weighting. A partial region retains successful measurements and identifies every omission. If all sites are unavailable, the summary is null.

The synthetic example gives **3.75 mm** along the oblique vector. One distinct cutaneous crossing is required within the finite forward segment, including its endpoints. Contact gives zero. Hits from adjacent facets at the same point are grouped. Distinct skin layers, an intervening skull surface, a grazing unresolved intersection, an inward direction or a miss give a null thickness with a reason. Each measured site records its origin, unit axis, endpoint and original skin triangle IDs for inspection. Its numerical tolerance in mm is 64 machine epsilons times the larger of the search limit and the maximum absolute source-facet coordinate. The whole skull is checked for an intervening surface on the segment. Interpretation still depends on the completeness of the segmentation.

## Profile error against a withheld skin reference

Use a measured skin surface from the **same subject** that was withheld from the fitting operator, including any facial depths derived from that reference. Preserve the registered skull frame and scale in mm. The evaluator records the segmentation and registration sources, identifies the midsagittal section on the skull and locates the planned homologous skin sites on both faces. Choose the site definitions and the tolerance around the plane before inspecting errors. Exclude non-skin geometry, including lateral scan residues. For a missing or ambiguous landmark, keep its name and record a reason.

1. Supply the saved approximation and reference to obtain the hashes of all three meshes. The reference accepts triangulated STL, PLY or the restricted OBJ format described above.

   ```sh
   python -m cranio.coherence --skull bone.stl --face fitted.obj --profile-reference reference_skin.stl
   ```

2. For each site, record the zero-based triangle index and its three barycentric weights on **each** surface. The meshes may have different vertex counts and triangle orders. The marker example above shows how to compute weights from a selected world-mm point. Verify corner order against each saved file. For an exact vertex, assign weight 1 to its corner. Declare the midsagittal plane with its origin, normal and permitted absolute point-to-plane distance in mm. The normal can have either sign.

   The following illustrates the review format. Replace the example facet IDs, plane and tolerance with the reviewed case data.

   ```json
   {
     "schema": "gnm.profile-error-review.v1",
     "skull_sha256": "<skull hash>",
     "face_sha256": "<approximation hash>",
     "reference_sha256": "<reference hash>",
     "reference_source": "<subject skin segmentation revision and evaluation record>",
     "reference_access": "withheld",
     "registration_source": "<shared skull-based world-mm registration record>",
     "plane": {
       "origin_mm": [0, 0, 0],
       "normal_world": [1, 0, 0],
       "source": "<reviewed skull-based plane definition>",
       "tolerance_mm": 1
     },
     "sites": {
       "Gl": {
         "approx": {"triangle": 12, "barycentric": [0.5, 0.25, 0.25]},
         "reference": {"triangle": 43, "barycentric": [0, 1, 0]}
       },
       "Pg": {"reason": "Cutaneous chin landmark outside the reference scan"}
     }
   }
   ```

3. Run the calculation. The other coherence reviews can be included in the same command.

   ```sh
   python -m cranio.coherence --skull bone.stl --face fitted.obj --profile-reference reference_skin.stl --profile-review profile_review.json
   ```

Each measured site reports its two original world coordinates, their signed offsets from the plane, the **3D Euclidean distance** and the **distance projected into the sagittal plane**. For example, a discrepancy of 3 and 4 mm along orthogonal in-plane axes gives a profile error of 5 mm. An additional 1 mm perpendicular to the plane gives a 3D distance of √26 mm (about 5.10 mm), provided both points meet the declared plane tolerance. The command performs no ICP or other fit. The outcomes describe sampled homologous sites, not distances along the intervening contour.

Read `profile_error.measured_count` alongside `site_count`. Both summaries give MAE, median, RMSE and P95 in mm, with equal weight per measured site. The 3D summary uses the C3 paired-point calculation. Inspect `sites` for explicit omissions, degenerate facets or off-plane anchors. A partial result summarizes only eligible sites. Zero eligible sites yield null summaries.

`reference_access` describes access during fitting. Use `seen` for a previously inspected reference and `used` for a conditioned fit. Both leave the independent outcome unassessed. Byte-identical reference and fitted face or skull files also leave it unassessed. The evaluator is responsible for verifying subject identity, homology and independence. The [C3 study protocol](validation_protocol.md) records blinding, retrospective and conditioned arms, frozen runs and subject-level results. Historical approximations without a measured reference have no independent profile score.

For recorded per-fit contacts and deformation diagnostics see [saved-fit consistency](POSTFIT_CONSISTENCY.md).

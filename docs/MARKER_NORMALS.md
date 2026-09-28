# Perpendicular marker placement — 5.0.0rc5 / add-on 17.1

The default **Stabilized local normal** estimates a tangent plane near the clicked
bone point. The marker follows its perpendicular, rather than the normal of one
small, possibly noisy triangle. The bone point is **not moved**, the tissue depth
is retained, and the skull is not smoothed, snapped, deformed or resampled.
This is a geometric placement aid; a tissue reference may prescribe a different
anatomical measurement direction. Review each landmark accordingly.

## Blender workflow

1. Register each preserved bone fragment and review its exterior normal direction.
   Use world millimetres: Metric, scale 0.001. The source's **Flip normals** flag is
   respected; normals never turn automatically toward the viewer or skull centre.
2. In **GNM Markers → Perpendicular marker placement**, choose **Stabilized local
   normal** and set **Local radius (mm)** (default 3 mm; range 0.25–20 mm).
   This radius is an engineering starting point, not a published tissue standard.
3. New placements use this setting. Existing placements remain unchanged. Select
   an existing marker in the list and click **Preview Normal** to display an arrow
   and a tangent circle of the requested radius at its bone point. The circle
   indicates scale, not a segmentation boundary or the exact accepted patch.
4. Inspect the arrow, support count, angular change from the seed face and warnings.
   Near the orbit, nasal aperture or a fracture, compare smaller radii and review
   the tissue measurement protocol. The preview is a snapshot; repeat it after
   scene edits. Changing radius/mode/selection clears it. **Hide** removes it.
5. **Reorient Selected** recomputes from the current evaluated surface and applies
   the direction, retaining the bone point, depth, mapping, weight and inclusion
   settings. Only the selected marker's target and peg change. Blender Undo is
   available. The normal is retained even at zero depth. A live refit is requested.
6. If support is inadequate, the operation fails before replacing the marker.
   Adjust the radius, reconsider the site, or explicitly choose **Face normal**.
   There is no automatic fallback to another fragment or an unreported face normal.

Parents/constraints/animation on target or peg must be detached before reorientation.
If source geometry, evaluated modifiers or world transforms have changed since
placement, review and re-place the marker. There is no automatic bone-point snap.
The old source binding and placement hash are checked. Legacy markers without a
source binding must be re-placed. Inferred patches remain explicitly inferred and
new placements on them remain excluded from the fit/plane by default.

## Estimator and safeguards

`cranio.surface_normals.estimate_normal` needs NumPy only. Blender reads evaluated
triangles in world coordinates on the main thread, including determinant parity
and the explicitly selected normal flip. It does not use shaded/smoothed display
normals. There is no persistent geometry cache or background Blender data access.

- A triangle AABB broad phase and exact point-to-triangle distances find local
  surface candidates. The ray's evaluated polygon selects the initial triangle;
  subsequent orientation retains its recorded seed when source and bone point match.
  The bone point must be within 0.05 mm of the chosen surface.
- Only edge-connected faces within the Euclidean radius can contribute. A nearby
  disconnected fragment, including another component of the same mesh, cannot
  enter the patch. Nonmanifold edges are barriers. Faces beyond 60 degrees from
  the seed and edges with dihedrals above 50 degrees are also barriers.
- Three symmetric barycentric quadrature points per triangle carry area/3 weights,
  multiplied by `exp(-2 * distance² / radius²)`. Samples outside the radius are
  discarded. This reduces vertex-density bias; it is not an exact integral over
  the radius-clipped surface, especially on coarse triangles.
- The eigenvector of the smallest weighted covariance eigenvalue supplies the
  normal. Three Huber reweighting updates use residual cutoff `1.5 * scale`, with
  `scale = max(1.4826 * median(abs(residual)), 0.01 * radius)`. The final normal's
  sign follows the seed triangle's winding. No camera-facing sign correction is used.
- Fewer than 3 connected faces or 9 samples, tangent spread below 0.02, or smallest/
  middle covariance eigenvalue ratio above 0.3 causes explicit failure. A direction
  change above 60 degrees also fails. Large changes (>25 degrees), curvature/noise
  (eigenvalue ratio >0.1) and barriers within 0.75 radius produce review warnings.

All these cutoffs are **engineering heuristics**, recorded with method version
`connected-area-pca-v1`; they have not been calibrated against CT ground truth.
Small radii can follow scan noise; large radii can blur real anatomy. Connectivity
does not identify bones, guarantee exterior winding, or repair bad topology.
A gradual fold connected within the radius may remain in the patch; inspect
concavities and reduce radius. Coarse, narrow, highly curved or very damaged
surfaces may not support a plane at the requested scale. Boundary warnings can
also reflect coarse sampling of the radius rim and require inspection.

The tangent-plane/PCA construction and scale/sign limitations follow the
[PCL normal-estimation documentation](https://pointclouds.org/documentation/tutorials/normal_estimation.html).
Our connectivity, quadrature, robust weighting and rejection rules are implementation
choices, not a verbatim PCL algorithm or a validated craniofacial protocol.

## Traceability and offline use

The bone object stores `gnm_normal_record` only when a direction is applied, not on
preview. It contains method/version, radius, actual normal, bone point, seed
triangle, surface distance, support count, covariance diagnostics, warnings,
source hash/ID, inferred/observed status, normal review/flip state and UTC time.
The applied depth is recorded separately from later tissue-depth edits.

CSV v3 metadata includes `marker_orientation` for each placed marker. It records
the applied estimate and actual current direction, and flags
`matches_current_marker=false` if the point/direction has since been manually
changed. Older/manual placements are labelled `legacy_or_manual_unrecorded`.
The existing offline pipeline retains this metadata in `*_report.json` and fits
the exported target coordinates. It does **not** recalculate the directions or
require a changed solver. Re-export CSV after applying a new direction.

The regression suite covers noisy planes, curved surfaces, nearby disconnected
fragments, fractures, sharp and nonmanifold edges, narrow support, winding,
rigid transforms/scaling, invalid data and explicit failure. Actual Blender
checks exercise placement, preview/apply, exact source preservation, zero-depth
edits, negative/nonuniform transforms and stale-source rejection. These are
engineering checks, not anatomical or blind CT accuracy measurements.

## Ghid scurt

În panoul **GNM Markers**, alege **Stabilized local normal** și raza locală, inițial
3 mm. Markerii noi folosesc această direcție. Pentru unul deja plasat: selectează-l
în listă → **Preview Normal** → verifică săgeata și avertismentele → **Reorient
Selected**. Punctul de pe os și grosimea tisulară rămân aceleași. Se schimbă direcția
tijei și poziția țintei. Reexportă CSV-ul pentru următoarea rulare offline.
La margini și pe os foarte subțire verifică o rază mai mică; normala geometrică
trebuie să respecte și direcția de măsurare cerută de protocolul anatomic.

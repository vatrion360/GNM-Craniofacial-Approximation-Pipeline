# Mixed fragments, duplicate audit and adaptive lambda (5.0.0rc3 / add-on 16)

## Landmark audit

The pinned official GNM asset has **48 registry labels and 48 distinct skin-vertex candidates**. There are no exact registry duplicates. The 32 paper positions overlap with 11 of the original 27; these shared labels are stored once, producing 48 entries, not 59. The [machine-readable audit](landmark_audit.json) records the model hash and a reproducible proximity search:

```bash
python tools/audit_landmarks.py --npz models/gnm_head.npz --output outputs/landmark_audit.json
```

Within 2 mm, the only pair is **Nasospinale_BazaNas / Acanthion**, 1.5 mm apart on the neutral skin template (12298 / 12297). Different skin vertices are not proof of different bone sites. In this registry, Nasospinale means the intersection of the midsagittal plane with the line joining the inferior nasal-aperture margins; Acanthion means the anterior nasal-spine tip. Nomenclature is inconsistent between published protocols, so check the definitions used for the case and exclude one if the protocol treats them as the same measurement. Do not count two clicks on the same bone site as independent evidence.

The nearby candidates remain available for compatibility; this revision does not invent a replacement skin correspondence. Suborbitale / Infraorbitale-foramen, LateralOrbit / lateral canthus, Menton / Gnathion and Infradentale / Pogonion also retain separate definitions. Proximity alone does not justify merging them. A definition reference is Caple (2018), *Elliptical Fourier analysis of lateral skull profiles as a tool to assist in human identification*, University of Queensland, [thesis](https://espace.library.uq.edu.au/view/UQ%3A726654/s4342843_final_thesis.pdf); the supplied paper's definitions remain documented in [PDF_PROTOCOL](PDF_PROTOCOL.md).

**Audit Landmark Duplicates** writes `GNM_Landmark_Audit` in Blender's Text Editor. Included placements are checked for repeated labels, repeated resolved GNM vertices and coincident skin targets (within 0.000001 mm). Such collisions stop preview/offline fitting and require correcting the correspondence or excluding a row. Bone sites within 0.1 mm produce a review warning, without silently merging distinct anatomical landmarks. Manual picks are included in this audit. Unplaced and documentation-only markers do not count as fitting constraints.

## Lambda uses the actual included count

The preview and Blender's offline button now share:

`lambda = clamp(lambda_base * 48 / N_used, lambda_min, lambda_max)`

`N_used` is the number of distinct, placed, mapped markers with **Include in fit** enabled. The reference of 48 is fixed; changing the marker-set dropdown does not change a fit with the same data. With base 1 and default bounds:

| Included landmarks | Lambda |
| ---: | ---: |
| 4 | 12 |
| 6 | 8 |
| 12 | 4 |
| 24 | 2 |
| 32 | 1.5 |
| 48 | 1 |

Dense surface samples never increase this count. Dense-only preview uses `lambda_max` instead of pretending to have 24 anatomical markers. Fewer than four landmarks cannot start the offline pipeline. This schedule is an explicit engineering heuristic; neither 48 nor base 1 is an empirically calibrated anatomical optimum. Weights, spatial coverage, correlated sites and uncertainty still matter. This changes the old `base * 24 / N` preview schedule and removes the ICP path's artificial minimum count of 24. Review prior cases accordingly; halving the base reproduces the old formula for an otherwise identical marker-only preview.

Optional **Conditional LOO tuning** uses the current vertices, coordinates and weights. Its cache is invalidated when those data or the loaded model change, even if the count stays constant. It uses the pipeline's fixed-pose tuning grid; the adaptive base/min/max do not override LOO's choice. LOO runs on Blender's main thread and can pause the UI. It is a tuning score, not independent reconstruction accuracy. Changing lambda settings requests a new preview fit.

The offline button passes the selected adaptive/LOO mode explicitly. Standalone CLI still defaults to conditional LOO for compatibility; select the count rule with:

```bash
python gnm_reconstruct.py --input markers.csv --npz models/gnm_head.npz \
  --output outputs/case/face.obj --regularization adaptive \
  --lambda-base 1 --lambda-min 0.3 --lambda-max 1000
```

CLI exclusions and optional automatic outlier exclusion update the count before each adaptive fit. JSON records the configuration, final landmark list and lambda.

## Why global half-skull mirroring was replaced

The previous function selected one globally intact side, cut away the opposite side from a copy, mirrored the retained half, joined/welded it and hid the source. With a preserved right cranium, nasal fragment and left mandible, either global choice loses valid observed anatomy from the working reconstruction. Its plane also mixed mandibular and cranial points, including inferred positions, and did not reject nearly collinear references.

The replacement creates **separate inferred patches for explicitly defined donor regions**. It never cuts, joins, welds, moves, hides or recolors the preserved sources during generation. A later explicit recenter command moves all registered fragments, reference planes and markers together. Generated patches remain distinguishable and carry source/plane/provenance metadata.

Existing `.blend` files keep their source objects, previous outputs and markers. The old global intact-side setting is not automatically converted into anatomical regions: register them explicitly. Previous landmarks with unspecified provenance must be reviewed and marked Observed before contributing to an automatic cranial plane, or use a reviewed manual plane.

## Workflow for right cranium + nasal bone + left mandible

Register **every preserved fragment**, including central anatomy, so its surface is protected. Sources can be separate objects or distinct vertex groups in a single composite mesh. Apply active geometry modifiers on a working copy first. In Object Mode, select a source and press **Add Active Fragment**; repeat for each region. For a vertex group, only complete faces whose vertices all have weights above 0.5 are donors.

| Region | Anatomy | Action | Donor side | Reference |
| --- | --- | --- | --- | --- |
| Right cranial fragment | Cranium | Mirror selected region | Right | Reviewed cranial plane |
| Nasal fragment | Nasal / central | Keep preserved | Not used | Not mirrored |
| Left mandibular fragment | Mandible | Mirror selected region | Left | Separate mandibular plane, or reviewed articulation |

A donor that extends more than the overlap tolerance onto **both sides** of the plane is rejected. Restrict its vertex group or separate its fragments. This prevents accidentally mirroring a composite skull/mandible object as though it were one intact half. Central-only donors are also rejected; use **Keep preserved**. The donor-side label documents the anatomical interpretation; the geometric reflection follows the plane and selected mesh, not an automatic anatomical classifier.

For the cranial plane, either select a reference object whose **local XY plane** is the intended symmetry plane, or place at least three spatially distributed cranial midline bone landmarks. Automatic references must be marked **Observed**, enabled with **Use observed cranial point for plane**, and non-collinear. Mandibular landmarks and repaired/inferred bone are excluded from this automatic cranial plane. A fit RMS above 1.5 mm blocks automatic patch generation pending review; this is an engineering guard, not a clinical acceptance threshold.

An unarticulated mandible **requires its own reference-plane object**. Otherwise, explicitly confirm **Mandible articulated with cranium** after reviewing its pose/occlusion. A separate plane supports restoring a detached mandibular fragment in its current frame; it does not articulate it into the correct facial pose. Complete and review articulation before placing the mandibular constraints used for face fitting. Unarticulated mandibular points are omitted from the cranial asymmetry report and automatic contralateral placement ghost.

Press **Generate / Update Region Patches**. All regions are checked before output changes. Repeating the command updates each region's managed output without creating another overlapping copy. Regeneration replaces that generated patch; keep an independent copy if manually editing it. Removing a region also removes its managed patch and keeps the source. Undo is supported through Blender's operator stack.

Original registered surfaces take precedence: generated triangles whose vertices and centre are all within the overlap tolerance of preserved surfaces are suppressed. Partial contacts are counted and retained for inspection. This is a conservative proximity filter, **not an exact Boolean intersection test**; small intersections between sample points can remain. Inspect seams and contacts manually. No watertight result or lost anatomical detail is invented or guaranteed. Keep dense fitting disabled until the actual observed/inferred geometry and its applicability have been reviewed.

Markers placed on inferred patches automatically receive **Digitally repaired** provenance, are disabled for fitting and do not enter the cranial-plane fit. Include them only after review; mirrored constraints are correlated with their donor and do not provide independent observations. Regenerating or articulating fragments does not automatically reposition existing markers: recheck them afterwards. Region choices, plane parameters, donor hash and output counts are exported in CSV metadata and the offline JSON report.

## Verification

Pure Python tests cover exact/near duplicates, exclusion-aware lambda, cache keys, degenerate planes and reflection in rotated frames. The Blender regression uses a **single mesh containing right cranial, central nasal and left mandibular regions**, a translated/rotated/scaled object and a separate mandibular plane. It verifies source coordinates/faces/transform/visibility, reflected patch positions and normals, idempotent generation, rejection of a mixed-side donor, protection of an observed opposite fragment and inferred-marker provenance. See [VALIDATION](VALIDATION.md) for executed results.

Blender implementation references: [BMesh operators](https://docs.blender.org/api/current/bmesh.ops.html), [BVHTree](https://docs.blender.org/api/current/mathutils.bvhtree.html). These geometry operations do not validate bilateral symmetry, articulation, missing anatomy or final facial accuracy for a specimen.

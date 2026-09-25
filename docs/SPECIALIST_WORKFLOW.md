# Specialist workflow

## Case preparation

1. Keep the unedited scan and acquisition metadata. Work on a copy. Record scan modality/resolution, surface extraction threshold if known, source units and repairs. This software begins with an existing skull mesh; it does not validate segmentation.
2. Import into Blender with explicit mm/cm/m. Check at least one known length and the right/left labels. The scene contract is metric scale 0.001, with world coordinates in millimetres.
3. Preserve true asymmetry. If a partial skull is mirrored, mark the repaired regions and distinguish measured landmarks from inferred ones. Do not treat both mirrored sides as independent observations. Keep an original scan copy: the inherited reconstruction tool can remove the selected half.
4. Load the reviewed GNM model. Check correspondence positions on the neutral skin mesh. A topology hash verifies model identity, not anatomical homology.

## Marker and tissue review

Place well-distributed midline and bilateral landmarks on stable, preserved bone. The automatic normal-based offset is an initial construction, not an anatomical rule. Review local normals around sharp ridges, orbital margins, thin nasal bones and openings. Local curvature or reversed normals can send the target in the wrong direction.

For each placed marker, document the tissue source/table/definition and why it applies. Adjust the tissue distance and inspect the resulting target. Depth edits update existing target/peg geometry; manually moving the target inconsistently with the recorded depth prevents export. The active marker's **Tissue source / method** field is exported. The defaults remain explicitly unvalidated until reviewed.

Do not conflate bony and soft-tissue landmark names. Review especially the inherited orbit/canthus, nasospinale/subnasale, prosthion/lip, alare and piriform correspondences. Use **Pick GNM Vertex** only after deciding the desired homologous target; v3 preserves that choice.

Export v3. Check the list of used/skipped markers and the bone and skin coordinates. A `0,0,0` target is valid in v3. Four landmarks are a solver minimum, not an acceptable anatomical protocol by themselves.

## First fit

Use the default statistical fit with no local correction and no dense constraints. In Blender, configure the external Python environment and run **Run Offline Fit and Import**, or use:

```bash
python gnm_reconstruct.py --input case/markers.csv --npz models/gnm_head.npz --output case/run01/face.obj --strict
```

The strict option checks provenance fields only. It cannot determine whether the cited tissue values, anatomy or case protocol are sound.

Inspect the fit in frontal, lateral and three-quarter views, together with the skull. Check laterality, scale, chin/mandibular angle, nasal bridge, orbital region, lips, ears, internal anatomy and exposed bone. The solver does not provide a complete collision/self-intersection check. Compare the mesh with the actual markers; do not use the colour of confidence ghosts as an empirical confidence interval.

## Diagnose before adding flexibility

Read the TXT and JSON reports. Review high residuals, clipped coefficients, few landmarks and consistency warnings. A distance from the population mean is not by itself a placement error: inspect the specimen before changing an unusual observation.

Use explicit `--exclude LABEL` only for documented reasons. `--exclude-outliers` is a residual-based numerical heuristic that can remove real atypical anatomy; it is disabled by default. The report retains excluded labels and errors. Do not select exclusions to improve a reported performance score.

Evaluate landmark generalisation separately:

```bash
python -m cranio.evaluation --input case/markers.csv --npz models/gnm_head.npz --output case/holdout.json --regularization 30
```

With `--regularization auto`, tuning is repeated within each training fold. This can take longer. The outer held-out target never determines that fold's pose, identity or tuning. Holdout still tests imposed target positions, not accuracy against the deceased individual's face.

## Optional refinements

**Dense constraints:** export a copy of the skull in the same world-mm coordinates as the markers, without axis conversion. `--skull` uses sampled nearest-surface constraints and fixed regional offsets. Start with `--no-face-dense` for damaged facial bone. Check all normals and retained correspondence counts. A partial or hollow skull can match an unintended surface. These heuristics require their own validation.

**Local correction:** `--local-correction` enables a bounded 3-D radial deformation after the fit. Compare `face_statistical.obj` with `face.obj`. Large changes or a visually smoother fit do not establish accuracy. Coplanar or duplicate centres fail explicitly; do not bypass the check. The displacement map exposes how much local correction was applied, not uncertainty.

**Nasal tangent diagnostic:** requires five explicit bone landmarks. It is informational only and uses pose-aligned axes. Its fallback direction is exploratory. Neither a plausible pronasale nor a small deviation from the fit validates the nose shape.

## Archive and review

Keep the original scan, edited `.blend`, exported skull used for dense fitting, v3 CSV, five output artifacts, run log, environment/model provenance, tissue sources, exclusions, observer notes and all manual edits made after fitting. An OBJ modified after export is a new derived artifact and will no longer match the manifest hash.

Have a second specialist review the landmark definitions, correspondence map, tissue sources, damaged/reconstructed regions and plausible alternative appearances. Before operational forensic use, complete the independent paired-data and interobserver programme in [VALIDATION](VALIDATION.md). A claim of identity requires an appropriate separate identification method; this approximation alone is not that evidence.

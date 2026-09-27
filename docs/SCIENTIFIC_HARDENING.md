# Numerical contract and scientific traceability (5.0.0rc4)

This release implements the numerical/code-review corrections. It prepares the software for a paired-data study; it does not supply that study or establish publication-grade forensic accuracy. Primary mathematical and anatomical references remain in [SCIENCE](SCIENCE.md) and [PDF_PROTOCOL](PDF_PROTOCOL.md).

## Shared fit

Marker-driven preview and offline fitting both call `cranio.optimize.fit_identity`. `cranio.preview` adapts snapshots without duplicating the solver. Both use the same dense correspondence selector, regional sampling and weight normalization. Tests compare nonzero identity fits, including automatic lambda, using identical arrays and nearest-point results. Different sampled scans, Blender's float32 model and differing settings can still produce numerical differences; matching the objective does not promise bitwise equality between installations.

The similarity transform has a proper rotation. Weighted rank checks reject effectively collinear source or target sets; noncollinear planar points remain admissible. Planarity alone is not an error or evidence that left/right labels were swapped. Near rank loss and effective point counts appear in the report. Huber weights use **world-mm residuals**, threshold 10 mm, and the original confidence weights. One IRLS layer freezes these weights for the pose and identity blocks of each sweep. The ridge block operates in **model mm**. Convergence requires coefficient, translation, rotation, scale and robust-weight stability, with a common default limit of 30 iterations. A stopped iteration budget is reported explicitly.

This alternating, clipped algorithm with changing nearest-surface matches is a block-coordinate heuristic. Neither global joint MAP convergence nor a globally minimizing bounded least-squares solution is claimed. The hard coefficient limit remains ±3 by default; changing it changes the protocol. Conditional fixed-pose landmark LOO uses the existing grid 0.3–1000, with boundary warnings. It is a tuning procedure, not independent face validation, and does not optimize every optional prior/dense term inside each held-out fold.

Adaptive lambda remains `clip(base * 48 / n_used, min, max)`, with the maximum at zero markers. Dense samples never increase `n_used`. Automatic LOO runs through the shared solver; it is no longer reused from a marker-only cached fit when dense/prior settings differ.

Dense rows are quadrature-like constraints. Their weights sum to `dense_weight * sum(original_marker_weights)`; the default ratio is 0.5. Increasing the sample budget does not multiply the total attraction. Regional multipliers are normalized within this total, and nasal weight zero removes those rows. Face/scalp rows share a deterministic 50/50 budget, redistributing unused capacity. Fewer than ten accepted rows do not enter the identity solve; diagnostics identify this.

Markerless ICP remains experimental: coarse yaw search assumes an approximately upright skull. Candidates are compared using cost divided by coverage. With fewer than three markers, pseudo-observations determine pose and outer updates refresh matches; with no markers, the explicit reference weight mass is 48, multiplied by the dense ratio. This regime is distinct from anatomically anchored fitting and does not validate missing anatomy.

## Observed fragments and normal orientation

Blender's **Observed bone sources** is a positive source list. Import preserves separately named objects and their mesh coordinates, applies one common mm calibration, and records file hash, source units and transform. Register pre-existing meshes explicitly. Dense preparation evaluates visible modifiers and all enabled sources, sampling in proportion to area. Classify cranium, nasal, mandible or mixed sources. Review exterior normals per source; explicit reversal is available. Mixed/unclassified sources require articulation review or more precise classification before dense use.

No coverage threshold automatically reverses skull normals. Inward surfaces can otherwise create inward skin targets that look numerically consistent. Open fragments have no reliable global inside/outside inference. Offline `--skull` requires `--skull-normals-reviewed`; `--skull-flip-normals` is an explicit whole-file reversal. For a file with heterogeneous winding, fix/review components separately in Blender before exporting.

Ray placement accepts registered observed bone and explicit restoration patches. Generated face meshes, marker pegs and other scene objects are excluded. Markers on inferred patches remain labelled reconstructed and excluded from fitting by default. The original selective restoration of right cranium + nasal fragment + left mandible remains available; each donor region and reference plane is independent. Restoration and dense source lists serve different purposes. Neither automatic mirroring nor dense nearest-point correspondence establishes anatomical homology or correct mandibular articulation.

Prepared samples are invalidated after source geometry/transform/settings changes. Full evaluated hashes also check changes made while preview was stopped. Scene/case binding and geometry generations reject stale results and reset the prior, model and coefficients on loading another `.blend`. Live fitting is serialized on Blender's main thread; there is no fitting worker race with Blender APIs. It can pause the interface. Use the external process for long fits.

## Mapping and marker exchange

There are 48 unique built-in candidates and **17 bilateral pairs**, including internal and external orbital labels. Exact mirror **indices** are tested independently of spatial mirror equality. The pinned neutral asset has genuine small asymmetry: the largest bilateral landmark deviation is approximately 0.2341 mm. The official-model regression bounds Euclidean deviation below 0.25 mm with a fixed asset hash; it does not alter the template or pretend the coordinates agree within 0.05 mm.

A reusable reviewed map contains `schema_version: 1`, the exact `model_sha256`, and canonical `landmarks` entries with `vertex_index` and `reviewed: true`. Precedence is per-marker manual override, reviewed map, built-in candidate. Legacy generated candidate JSON supplies confidence annotations only; legacy manual maps without a model hash require re-export from the original scene. Explicit v3 CSV indices remain authoritative offline. `--landmark-map` also permits a reviewed map for legacy decoding.

CSV parsing rejects duplicate headers and malformed quoted records and preserves multiline notes beginning with `#`. New optional columns record bone source ID, evaluated geometry hash at placement, anatomy and articulation review. These extend v3 without changing world-mm coordinates. Moving/editing a source after placement does not silently move markers: inspect and re-place them. Frozen protocol checks reject stale placement hashes.

## Geometry checks and reports

Default `--geometry-qc basic` reports new collapsed faces, relative normal reversal, area and edge distortion at statistical and final stages. `--geometry-qc full` additionally checks nonadjacent exterior triangle contacts, including coplanar overlaps, and compares them with contacts already in the posed neutral asset. An incomplete broad-phase search cannot pass. Shared-vertex triangle pairs are excluded; existing template contacts and excluded adjacency require review. A reversed reference normal is a diagnostic, not a volumetric Jacobian.

When observed bone samples are available, full QC also measures closest-surface displacement along their reviewed outward normals at up to 5,000 deterministic samples, before and after local correction. Negative clearance beyond 0.1 mm is flagged. This is a local sampled check, not watertight skull containment or an anatomical guarantee. Without bone input the report explicitly says clearance was not assessed. Small TPS caps cannot guarantee absence of folding or penetration.

`--require-qc --geometry-qc full` returns exit code **3** for review-required geometry or nonconvergence, retaining the artifacts and completed report. Input failures return **2**. Normal completion returns **0**. JSON `status=completed` denotes a completed run, while `geometry_quality.status` denotes the scope-limited check outcome.

Report schema 2 includes actual source file fingerprints, git commit/dirty state when available, Python/library versions, NumPy build/BLAS details and selected thread settings, solver convergence and singular values, final IRLS weights, dense matches/targets/weights/rejections, optional-input hashes and bone-source manifests. Coefficients and similarity transform permit replay of the statistical mesh; local-correction centers/vectors and settings support replay of the correction. The displacement heatmap remains displacement, not uncertainty.

## Prepare a blinded CT protocol

Freeze acquisition/segmentation rules, pseudonymous subject IDs, subject-level development/held-out split, tissue table/direction definitions, landmark definitions, missing-region strategy, articulation procedure, dense/TPS/clip settings, demographics policy and stopping/QC rules **before** revealing held-out faces. Separate operators preparing skull markers from evaluators holding the reference skin. Related scans of one subject must remain in one split. No landmark, threshold or lambda-grid change may be selected from held-out face errors.

After a development run with full QC:

```bash
python -m cranio.protocol --development-report development/face_report.json --protocol-id ct-study/r1 --split-manifest study/subject_split.csv --output study/protocol.json
python gnm_reconstruct.py --input case/markers.csv --npz models/gnm_head.npz --output case/frozen/face.obj --geometry-qc full --protocol study/protocol.json --case-metadata case/case.json
```

Use the same numerical flags as the development run. The freeze checks source/model/runtime hashes, numerical settings, prior/map hashes, presence of bone input and placement provenance. The case metadata must contain nonempty `case_id`, `observer_id`, `protocol_id`, `split_sha256`, `acquisition_sha256`, `segmentation_revision`, and `coordinate_frame`. The two SHA-256 fields are hashes of actual archived inputs. Archive scan modality/resolution, segmentation threshold/manual edits, source-to-world transforms, software environment and observer/session identities alongside these fields. The protocol validates consistency of recorded fields; it cannot verify that an observer truly remained blinded.

Keep reconstruction and CT skin in an independently defined CT/skull frame. Do not use unconstrained ICP against the held-out face as the primary registration: it can conceal reconstruction errors. Predeclare exterior facial ROIs, missing-surface masks and the handling of internal cavities. Report area-weighted symmetric point-to-triangle distances (mean, RMSE, median, p95, Hausdorff with coverage), signed distances only where orientation is well-defined, independent landmark errors, and uncertainty across **subjects**, not across densely correlated vertices. Record failed cases and coverage instead of silently dropping them. Stratify intact/mixed-side fragments, mandibular availability, cranial modification and relevant cohort factors; compare mean-template, marker-only, dense and TPS variants. Include repeat placement/interobserver error and sensitivity to tissue depths and registration. Calibrated uncertainty requires empirical coverage on independent data; this software does not estimate it.

`cranio.evaluation` supplies outer landmark holdout with refitted pose/identity. It tests target generalization only. No paired CT validation or recognition study has been performed for this release.

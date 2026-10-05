# 5.0.0rc8 / add-on 18.0.2

- Replace the combined craniometry marker error with field-specific diagnostics for both endpoints of a rejected pair, shared by live and offline fitting.
- Expose the existing endpoint marker review/source fields directly in the Craniometry panel, with metadata-only checks and no draw-time geometry/model reads.
- Reject whitespace-only, non-text and reserved tissue-source placeholders. Preserve case metadata and all source/anchor checks; do not automatically certify existing markers.
- Add numeric and installed-Blender regressions for the reported legacy-marker failure and inline review controls.

# 5.0.0rc6 / add-on 18.0.0

- Table 3 catalogue: 22 bone references, 14 case-specific chords, observed/reconstructed/missing status and placement/source review.
- Dedicated Blender panel, bone placement/linking, selected-chord display, custom reviewed skin controls and standalone JSON/CSV export.
- Optional shared live/offline skin-distance fitting, with explicit bone-to-skin correspondence and target construction. No specimen values or bone-to-skin multipliers are supplied.
- Distance-aware scale updates, tolerance/Huber weighting, excluded-endpoint filtering and unchanged adaptive-lambda counting.
- Before/statistical/final skin residuals and cranial measurements in reports; control policy included in frozen protocols.
- Numeric and installed-ZIP Blender regressions added to existing Windows/Linux CI.

# 5.0.0rc5 / add-on 17.1.0

- Stabilized local tangent normals from connected, area-weighted surface patches; configurable radius and explicit face-normal alternative.
- Preview arrow/tangent circle and selective reorientation preserve bone point, tissue depth and source mesh.
- Evaluated geometry, winding/transform handling, fragment/edge guards and explicit insufficient-support errors.
- Per-marker direction provenance in CSV v3 and offline JSON, including detection of later manual direction changes.
- Numeric and actual Blender regressions added to existing Windows/Linux CI.

# 5.0.0rc4 / add-on 17.0.0

- Shared live/offline dense objective, single Huber layer, pose-aware convergence and weighted-rank diagnostics.
- ICP coverage-score fix, explicit exterior-normal review, multiple observed bone sources and case-state invalidation.
- Reviewed model-bound maps, orbital bilateral-pair coverage, multiline CSV validation and placement source hashes.
- Geometry QC at both stages, report schema 2 and an enforceable numerical freeze for planned blinded CT studies.
- Hashed Python 3.12 runtime, expanded Blender regressions, official-model CI and dependency audit.

# 5.0.0rc3 / Blender add-on 16.0.0

- Audit runtime duplicate labels, model vertices and coincident skin targets; preserve distinct anatomical sites and flag near bone placements.
- Share the base * 48 / actual included count lambda rule between preview and Blender-launched offline fitting. Remove artificial 24-marker counts from dense/ICP paths; invalidate LOO cache on changed data, not just count.
- Replace global half-skull cutting with per-region inferred patches that preserve mixed-side original fragments. Support vertex-group donors and independent mandibular planes, and reject mixed-side donor selection.
- Fit automatic cranial planes only to stable observed cranial references; keep unarticulated mandibular/inferred landmarks out. Record inferred-surface placement and exclude it from fit by default.
- Add mixed-fragment and lambda/duplicate regression coverage; document methods and limitations in FRAGMENT_RESTORATION.md.

# 5.0.0rc2 / Blender add-on 15.0.0

- Extend to 48 unique marker sites; selectable 32-position paper and 27-position legacy sets.
- Transcribe and cite Table 2 of Rangel-de Lazaro et al. (2026), with explicit case/population applicability and anatomical definitions.
- Preserve existing placements, tissue edits and manual correspondences when adding missing markers; provide an explicit tissue-profile application action.
- Correct the default Pogonion skin candidate from lower-lip vertex 12284 to chin vertex 12261. Explicit v3 and manual picks remain authoritative; review previous cases.
- Record observed/repaired/inferred bone, placement notes, operator correspondence review and documentation-only markers across Blender, CSV and offline reports.
- Exclude documentation-only markers from preview/offline fitting; apply CLI exclusions before strict review checks.
- Check external Python executable type, version, bitness and imports before creating case output. Reject wrong scripts/installers, copied foreign-platform environments and Blender itself, with actionable Windows 193 diagnostics.
- Isolate child Python paths from Blender's embedded environment; preserve virtualenv symlinks, Unicode paths, logs and cancellation.
- Add regression tests and Windows Blender integration to the existing Linux and Python CI checks.

# 5.0.0rc1 / Blender add-on 14.0.0

- Installable Python package/CLI and complete Blender ZIP with a namespaced numerical core.
- Explicit v3 marker labels, placed flag, manual vertex indices, bone/skin coordinates, tissue provenance and model hash. v1/v2 remain readable with documented limitations.
- Safe numeric model loading without pickle; topology, dimensions and finite-value checks; offline doctor.
- Proper-rotation Umeyama including planar sets; degenerate-input rejection; correct RMSE; sagittal reflection in symmetry loss; soft-prior IRLS gradient correction; final pose re-estimation.
- Local 3-D polyharmonic correction is now opt-in, uses the dimension-appropriate radial kernel, rejects singular configurations and preserves an unwarped output.
- Separate outer landmark holdout evaluation, with no held-out target in pose/identity fitting.
- JSON reproducibility manifest and per-file atomic exports; deterministic skull sampling; output collision protection; true red maximum in the displacement heatmap.
- Nasal diagnostics use explicit bone positions in pose-aligned axes, never legacy skin-target coordinates.
- Explicit skull import units; editable tissue depths update placed targets; final fitting in a cancellable external Python process. No persistent background fitting thread inside Blender.
- Synthetic tests, real GNM integration check, packaging CI, headless Blender acceptance script, installation guide and scientific validation protocol.

## Changes requiring attention

Local correction is disabled by default. Its kernel and the numerical fixes can change previous results. Revalidate existing research protocols before comparing runs across versions. v3 export requires a selected model and a metric scene scale of 0.001. Unknown legacy vertex encodings now fail instead of being silently discarded.

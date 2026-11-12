# GNM Craniofacial Approximation
[![DOI](https://zenodo.org/badge/1306404052.svg)](https://doi.org/10.5281/zenodo.23333534)

A Blender marker add-on and an offline, auditable fitting pipeline for **supervised craniofacial approximation research**. Fits a neutral GNM Head identity model to operator-defined skin targets derived from a scanned skull.

**Software 5.0.0rc10 / add-on 19.0.0.** Blender adds [post-fit presentation copies](docs/POSTFIT_PRESENTATION.md): native GNM UVs, expression components, teeth/eye shape offsets and eye rotation, with bounded displacement from the frozen final surface. The original neutral fit remains available for validation. It retains [manual percentage changes to selected tissue depths](docs/MARKER_DEPTH_ADJUSTMENT.md), endpoint-marker diagnostics, redraw/refit performance fixes, 22 bone references, 14 Table 3 measurements and reviewed skin-distance controls shared by live and offline fitting. These controls do **not** establish forensic accuracy, infer BMI or recover a uniquely determined face. See [performance evidence](docs/PERFORMANCE.md), the [craniometry protocol](docs/CRANIOMETRY.md), [scientific basis](docs/SCIENCE.md) and [audit](docs/AUDIT.md).

## Start here

- [Install, obtain model assets, prepare an offline workstation](docs/INSTALL.md)
- [Specialist workflow, anatomical review and output interpretation](docs/SPECIALIST_WORKFLOW.md)
- [Ghid rapid în română](docs/GHID_RO.md)
- [Post-fit expressions, teeth, eyes and GNM UV textures](docs/POSTFIT_PRESENTATION.md)
- [Marker v3 specification and migration](docs/MARKERS.md)
- [PDF Table 2, 48-marker set and correspondence changes](docs/PDF_PROTOCOL.md)
- [Scientific rationale and primary references](docs/SCIENCE.md)
- [Perpendicular marker placement and local normals](docs/MARKER_NORMALS.md)
- [Table 3 cranial measurements and reviewed skin-distance controls](docs/CRANIOMETRY.md)
- [Optional extended bone references and definition review](docs/EXTENDED_BONE_REFERENCES.md)
- [Opt-in anatomical reference frame and standardized views](docs/REFERENCE_FRAME.md)
- [Protocol-defined cranial features and conditional intervals](docs/CRANIAL_FEATURES.md)
- [Mixed fragments, duplicates and adaptive lambda](docs/FRAGMENT_RESTORATION.md)
- [Validation protocol and current evidence](docs/VALIDATION.md)
- [Optional derived approximation record and provenance](docs/APPROXIMATION_RECORD.md)
- [Export a saved-fit approximation record from Blender](docs/BLENDER_APPROXIMATION_RECORD.md)
- [Numerical corrections, geometry QC and frozen CT protocol](docs/SCIENTIFIC_HARDENING.md)
- [Reviewed tissue measurement directions](docs/TISSUE_DIRECTIONS.md)
- [Explicit tissue scenarios and comparison](docs/TISSUE_SCENARIOS.md)
- [Optional age-at-death assessment and tissue-range audit](docs/AGE_CONTEXT.md)
- [Versioned tissue tables: JSON/CSV exchange](docs/tissue_tables_howto.md)
- [Contributing and CI](CONTRIBUTING.md)
- [Optional head-only identity fitting](docs/IDENTITY_SUBSPACE.md)
- [Opt-in marker-error propagation and its limits](docs/UNCERTAINTY.md)
- [V19 task comparison and revised implementation plan (Romanian)](docs/TASKS_V19_REVIEW.md)
- [Change log](CHANGELOG.md)

## Quick start

Python 3.10+; the current local test environment is Python 3.12 on Linux.

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --require-hashes --only-binary=:all: -r requirements-tested-py312.txt  # Python 3.12
python -m pip install --no-deps .
```

Obtain `gnm_head.npz` from the official Google GNM repository using the pinned instructions in [INSTALL](docs/INSTALL.md). The full GNM model weights are **not included** in this repository, wheel or add-on ZIP. Eight small legacy experimental demographic-prior NPZs are tracked under `priors/`; they are excluded from the wheel and ZIP and have no independent cohort validation. They are local files at reconstruction time; there is no runtime download, cloud inference or telemetry.

```bash
python -m cranio.doctor --npz models/gnm_head.npz
python gnm_reconstruct.py --input markers.csv --npz models/gnm_head.npz --output outputs/case01/face.obj
```

Outputs:

| File | Meaning |
| --- | --- |
| `face_statistical.obj` | Neutral GNM fit before any local correction |
| `face.obj` | Final fit; identical to the statistical mesh by default |
| `face_heatmap.ply` | Local displacement, with numeric `displacement_mm` and colour scale; **not uncertainty** |
| `face_statistici.txt` | Human-readable diagnostics and warnings |
| `face_report.json` | Completion record, input/output SHA-256, full settings, coefficients, transform, software versions, residuals and provenance |

All exported coordinates are **world millimetres**. Existing outputs are refused unless `--overwrite` is explicit. `--strict` requires v3 markers, matching model checksum, non-default tissue source notes and no explicitly unreviewed skin correspondences among included targets; it is a provenance check, not scientific approval.

Strict, frozen-protocol and craniometry checks reject blank tissue-source notes and the placeholders `unspecified` / `legacy-unvalidated`, ignoring surrounding whitespace and letter case. The original source text is retained for auditing. The JSON report distinguishes fixed lambda, the adaptive marker-count heuristic (including its count and bounds), and conditional fixed-pose landmark LOO; none is an independent validation result.

Local correction is opt-in (`--local-correction`). Dense skull constraints are experimental and require a skull exported in the **same world-mm frame** (`--skull skull.obj --skull-normals-reviewed`). Read the workflow before enabling either.

## Blender

Marker CSV exports validate a closed temporary file before replacing the destination;
failed exports preserve the previous file. Session reports list each marker's recorded
tissue source and do not attribute project tissue-depth values to the GNM model.

```bash
python tools/build_addon.py
```

Install `dist/gnm_cranio-5.0.0rc10.zip` through Blender's **Install from Disk** and enable **GNM Scientific Markers**. The ZIP includes `cranio`; installing `addon_v13.py` alone is no longer the recommended route. Blender 4.5.0 headless integration runs on Windows and Linux; see [revision-specific results](docs/VALIDATION.md). Blender **4.2+ remains the broader target**; interactive and other version checks remain pending.

Select the local model, import the skull with explicit source units, place/review markers, and export v3 CSV. For **Run Offline Fit and Import**, select the external Python executable from the environment above and a case output folder. The add-on runs the CLI in a separate process, records a log, then imports the completed world-mm OBJ. Each run gets a new case subfolder. The default button uses marker-only statistical fitting with lambda based on the actual included marker count; explicit dense and local-correction switches are available in the panel and CLI. Register all preserved bone sources, review their normals and confirm mandibular articulation before including mandibular constraints.

Use **Extended 48**, **Paper 32** or **Legacy 27**, then **Add Missing Markers**. Existing placements, tissue values and manual picks are retained. The paper's normal-female reference can be applied explicitly with **Apply Table 2 Tissue Depths**; review applicability before case use. Sites marked **Include in fit = off** remain documented but do not affect pose or identity fitting. The default Pogonion candidate is corrected from lower-lip vertex 12284 to chin candidate 12261; review previous cases.

The craniometry panel also offers **Add Extended Bone References (+12)**:
34 bone positions instead of the standard 22, while the 48 tissue markers and
14 chords remain unchanged. This opt-in catalogue adds Subspinale, mandibular
references, Porion, orbital-rim references, Condylion and Zygomaxillare. Known
counterparts reuse existing marker labels; unconfigured definitions require
operator text and source before confirmation. No new tissue depths, GNM indices
or fitting constraints are guessed. See [placement, review and compatibility](docs/EXTENDED_BONE_REFERENCES.md).

| Bone-reference control | Default | Effect |
|---|---|---|
| Add 22 Bone References / 14 Measurements | Existing initialization | Original reference set, current case work preserved |
| Add Extended Bone References (+12) | Off until clicked | Add the optional references without new skin targets |
| Case landmark definition / Definition source | Empty when unconfigured | Required before confirming a new reference; edits invalidate review |

For a manual depth scenario, check one or more rows using the **left-hand adjustment checkboxes**, enter **Change (%)**, choose **Increase** or **Decrease**, and press **Apply to Selected Depths**. The operation changes the current mm values in that same list and moves existing skin targets along their current axes. Selection is independent of **Include in fit**. Repeated applications compound; use Undo to revert. Only Blender provides this control; an exported CSV contains the edited targets without any additional offline multiplier.

After the final live/offline fit, open **Post-fit Presentation / GNM UV**, select the fitted source and **Create Presentation Copy**. This preserves the final surface, including local correction, and hides the retained original. Choose native statistical controls, then **Apply Preview**; **Reset to Frozen Neutral** restores the saved neutral coordinates. The default maximum combined displacement is 3 mm, an engineering limit rather than an anatomical threshold. Select a texture region and **Load GNM UV Texture** to apply an image matching the native UV layout. Read the [workflow and limitations](docs/POSTFIT_PRESENTATION.md) before editing: no separate jaw joint, named emotion presets, collision guarantee or scientifically inferred appearance is supplied.

On Windows select **`.venv\Scripts\python.exe`** (or the Windows-created `.venv` folder), then **Check Python Environment**. Selecting the pipeline `.py`, Blender itself, an installer or a copied Linux interpreter is rejected before fitting. See [Windows troubleshooting](docs/INSTALL.md#windows-interpreter-check-and-winerror-193).

Optional previews wait **0.35 s after the last edit** before reading the latest positions and fitting; adjust **Refit after idle (s)** if needed. Panel redraws perform no fit snapshots or source/model hashing. Bone-only measurements do not trigger face fitting while skin-distance strength is zero. A fit still runs on Blender's main thread and can pause the UI, particularly with dense constraints or LOO; these NumPy calculations do not use GPU VRAM. Use external fitting for expensive jobs. See [performance troubleshooting](docs/PERFORMANCE.md).

## Reproducible demonstration

Optional identity fitting controls (defaults preserve the previous path):

| Option | Default | Effect |
| --- | --- | --- |
| `--identity-subspace all` | Selected | Fit the complete identity basis |
| `--identity-subspace head` | Off | Fit 170 named GNM head components; eye/teeth coefficients remain zero, even with a prior |

Blender exposes the same choice as **Identity fit** and forwards it to external
fitting. This constrains coefficients, not all movement of eye/teeth vertices.
See [the numerical contract and checks](docs/IDENTITY_SUBSPACE.md).

The supplied `examples/synthetic_markers.csv` is generated from the GNM mean. It demonstrates software operation, **not reconstruction accuracy**.

```bash
python gnm_reconstruct.py --input examples/synthetic_markers.csv --npz models/gnm_head.npz --output outputs/demo/face.obj --regularization 30 --strict
python -m cranio.evaluation --input examples/synthetic_markers.csv --npz models/gnm_head.npz --output outputs/demo/holdout.json --regularization 30
```

`cranio.evaluation` holds out each landmark and refits pose and identity without it. Its scores are distinct from the conditional fixed-pose LOO used to tune regularisation. Neither is a substitute for evaluation on paired skull/face subjects.

## Tissue-table data exchange

`python -m cranio.tissue` provides opt-in data preparation; it does not apply a
table to a case or overwrite manual marker values. Unknown SD/source metadata
remain null with diagnostics. Bundled `legacy_hardcoded` and `var2026_table2`
retain the previous depths and their distinct provenance; JSON/TXT reports
identify the catalogue separately from actual case values. See [format and commands](docs/tissue_tables_howto.md).

| Command | Purpose |
| --- | --- |
| `template --id ID --output FILE` | Create an empty JSON template, without tissue values |
| `inspect ID_OR_FILE` | Validate structure; print metadata, SHA-256 and warnings |
| `export-csv --input ID_OR_FILE --output FILE` | Export lossless tissue-table CSV |
| `import-csv --input FILE --output FILE` | Validate CSV and write JSON |
| `--overwrite` | Explicitly replace an output; never replace an input |

Selected-table reports name the supplied estimator for each row and compare
recorded posture labels. No posture is inferred from CT and no shorth/75-shormax
is derived from a mean. See [posture/estimator reporting](docs/TISSUE_CONTEXT.md).

For explicit scenarios in fitting, see [selection/application and comparison](docs/TISSUE_SCENARIOS.md).
Selecting a table alone preserves case values. Replacing selected values requires
explicit labels and either acceptance of existing axes or a reviewed source-direction
manifest. Blender offers both policies on checked, placed markers with
Undo and audit history. Existing manual values change only through explicit Apply. Dense offsets still
follow reviewed sampled bone normals and are not replaced by selected-marker tables.

| Fit option | Default | Effect |
| --- | --- | --- |
| `--case-posture TEXT` | Unknown | Declared acquisition posture; selected-table mismatch/unknown warnings only, no geometric correction |
| `--case-metadata FILE` | None | Case JSON; optional reviewed `age_at_death_estimate` is reported and compared with the selected tissue range, without changing geometry |
| `--depth-weighting {none,sd}` | `none` | Offline only: optional `1/SD_mm²` multipliers from the selected table; missing SD retains base weight with warning; sensitivity, not calibrated uncertainty |
| `--tissue-table ID_OR_JSON` | None | Select/report a table; does not by itself replace targets |
| `--tissue-labels LABEL ...` | Empty | Explicit authorization to replace these case depths/targets |
| `--tissue-axis {existing,source}` | Unconfigured | Preserve current axes explicitly, or use reviewed world-frame source directions |
| `--tissue-directions FILE` | None | Manifest required for source mode; normal, vertical or explicit in-sagittal-plane vectors; no inferred frame |
| `--tissue-compare ID1,ID2,...` | None | Independent per-table fits, corresponding-vertex difference PLYs and summary; fresh output prefix required |

## Marker-error propagation

Optional A2.1 simulations use `python -m cranio.uncertainty`; they refit the shared
marker-only statistical solver with explicitly supplied placement/depth errors.
No missing SD is invented and no calibrated confidence is claimed. JSON retains
convergence/clipping diagnostics and paired prior scenarios. Existing fitting
defaults are unchanged; this is a separate command, not an uncertainty overlay
for a dense/TPS final fit. See the full
[options table, input schema and limitations](docs/UNCERTAINTY.md).

| Sampling option | Default | Effect |
|---|---|---|
| `--samples`, `--seed` | 200, 0 | Reproducible PCG64 perturbations |
| `--max-iter` | 30 | Explicitly adjustable iteration budget; unchanged convergence tolerances |
| `--placement FILE` | Unconfigured | Supplied per-coordinate placement SDs and sources |
| `--allow-partial` | Off | Conditional sensitivity with unknown errors held fixed and listed |
| `--depth-labels LABEL ...` | Empty | Selected table mean/SD depths with explicit axis policy |
| `--prior-variants off on` | off | Separate paired scenarios; `on` requires `--prior` |

Export a **converged** A2.1 record with
`python -m cranio.uncertainty_export --ensemble marker_ensemble.json --npz models/gnm_head.npz --output-dir outputs/spread`.
Each prior scenario gets a world-mm mean OBJ, numerical SD/spread PLY and actual
representative sample OBJs. The JSON summary preserves provenance and warnings;
these are uncalibrated simulated dispersions, not confidence bounds or CT accuracy.
See [definitions, regions and export rules](docs/UNCERTAINTY_EXPORTS.md).

| Ensemble export option | Default | Effect |
|---|---|---|
| `--variants {3,4,5}` | 3 | Select actual replay samples in beta space; fewer if insufficient distinct samples |
| `--regions FILE` | None | Explicit model-hash-bound vertex sets; otherwise only all vertices, including internal geometry |
| `--output-dir DIR` | Required/new | Separate completed bundle; no overwrite or sample realignment |

## Conditional linear covariance diagnostic

`python -m cranio.linear_uncertainty` compares analytic covariance with independent
Monte Carlo least-squares draws under an explicitly fixed pose and Gaussian model.
It distinguishes posterior covariance from repeated-data estimator variation;
it does not calibrate the nonlinear fit or alter existing defaults.
See [required assumptions, formulas and limits](docs/LINEAR_UNCERTAINTY.md).

| Diagnostic option | Default | Effect |
|---|---|---|
| `--input`, `--npz`, `--assumptions`, `--output` | Required | Case/model, documented noise/prior/pose, new JSON output |
| `--draws`, `--seed` | 10000, 0 | Independent reproducible Gaussian least-squares checks |
| `--identity-subspace {all,head}` | `all` | Explicit active coefficients; others remain zero |

## Empirical error-limit calibration (manual reference measurements)

`python -m cranio.calibration` consumes your reviewed per-vertex error/spread
CSVs. It fits an explicitly configured multiplier on calibration subjects and
reports coverage on disjoint validation subjects. No CT processing or anatomical
validation is inferred, and no mesh or original SD field is changed. Results
remain exploratory. See [protocol, input schema and limitations](docs/UNCERTAINTY_CALIBRATION.md).

| Calibration option | Default | Effect |
|---|---|---|
| `template`, `fit`, `evaluate` | Required action | Empty configuration, empirical scale fitting, or frozen-scale evaluation |
| `--manifest` | Unconfigured | Reviewed inputs; coverage/quantile/pooling choices must be explicit |
| `--calibration` | None | Frozen record, required only for evaluate |
| `--output` | Required/new | Deterministic report; no overwrite |

## Development

```bash
python -m pip install '.[dev]'
python -m pytest -q
python -m build
python tools/build_addon.py
```

Set `GNM_MODEL_PATH` to include the real-model integration test. Run the Blender gate separately:

```bash
blender --background --factory-startup --python-exit-code 1 --python tools/blender_smoke.py
```

[Validation status](docs/VALIDATION.md) distinguishes executed tests from pending interactive Blender and independent scientific validation. No unexecuted test counts or forensic performance badges are advertised.

## License and credit

Project code: Apache-2.0, original project by VATRION. GNM assets/code: Google and contributors, under their own Apache-2.0 distribution. See [NOTICE](NOTICE) and [references](docs/references.bib). No human-subject data or demographic priors are bundled.

## Optional anatomical reference frame (A4.2)

Observed/reviewed Porion L/R, a selected Orbitale and explicit cranial median
references define a frame for views and captures. The fit and world-mm coordinates
remain unchanged. See [configuration, assumptions and stale-frame checks](docs/REFERENCE_FRAME.md).

| Control / command | Default | Behavior |
|---|---|---|
| Frame configuration JSON | Blank template, no computed frame | Explicit protocol, side, superior cue and median points |
| Compute Reviewed Frame | Manual action | Validate observation/review/source hashes; save transforms and residuals |
| Front / 3/4 / Right / Left | Manual action | Orient viewport only |
| Use reviewed frame for standardized captures | Off | Anatomical camera axes and superior roll; stale frames refused |
| `placement_error` in frame config | `null` | Optional sourced SDs, sample count and seed; conditional sensitivity only |
| `python -m cranio.reference_frame template` | Explicit command | Write blank config, refuse overwrite |
| `python -m cranio.reference_frame compute` | Explicit command | `--input` craniometry JSON, `--config`, `--output` frame JSON |

## Optional cranial features (A4.3)

Bone measurements are exported separately from face fitting. Definitions,
projection choices, mandibular assumptions, placement SDs and thresholds require
explicit configuration/review. [Workflow and geometric conventions](docs/CRANIAL_FEATURES.md).

| Control / command | Default | Behavior |
|---|---|---|
| Add Feature Bone References | Not initialized | Extend 22/34 bone rows to 38; reuse pr/pg/go skin-marker associations without new targets |
| Cranial Features → Write Blank Protocol | Explicit action | Null definitions, no norms/error values |
| Compute / Export Reviewed Features | Explicit action | Write fresh JSON and Blender text; unavailable features remain explicit |
| `python -m cranio.features template` | Explicit command | `--output` blank configuration |
| `python -m cranio.features compute` | Explicit command | `--input` craniometry JSON, `--config`, `--output` results JSON |
| `uncertainty` / `thresholds` | `null` / `null` | Conditional placement intervals / sourced descriptive labels only when configured |

## Optional sagittal profile refinement (A4.4)

An explicitly reviewed, segmented bone profile can refine identity at the baseline
pose through the offline CLI or Blender's external fit/import action. Live preview
is unchanged. [Manifest, objective, acceptance gates and limits](docs/SAGITTAL_PROFILE.md).

| Control / command | Default | Behavior |
|---|---|---|
| Reviewed sagittal profile offline | Off | Opt-in fixed-pose identity refinement; currently marker-only |
| Profile JSON | Empty | Reviewed model/case/source hashes, plane, segmented path, depths and positive SDs |
| `python -m cranio.profile --template PATH` | Explicit command | Write blank manifest; refuse overwrite; no guessed scientific data |
| `--profile-constraint PATH` | Absent | Same NumPy refinement as Blender's external pipeline; manifest copied by addon |
| Acceptance gates | Explicit manifest limits | Reject candidate if any profile point worsens, marker limit or plane band fails |

No automatic gap completion, anatomical mapping or depth/SD imputation. Incompatible
losses/TPS/frozen protocols fail clearly. Reports distinguish baseline solver
history from final profile-refined coefficients and residuals. This is experimental
constraint fitting, not validated reconstruction accuracy.

## Optional mandibular articulation (A4.5)

Blender can preview and apply a rigid pose to selected registered mandibular
fragments and their source-bound markers. Pose assumptions, geometry diagnostics
and provenance are recorded explicitly. [Workflow and limits](docs/MANDIBLE_ARTICULATION.md).

| Control | Default | Behavior |
|---|---|---|
| Articulate Mandible: Wireframe Preview | Explicit action | Independent copies, native G/R handles; cursor-defined pivot |
| Lower/upper dentition and condyle/fossa objects | Unset | Observed references selected by operator; absent sides stay unavailable |
| Check | Explicit action | Point distances, BVH intersection candidates, conditional containment, sampled gaps |
| Explicit contact tolerance | Off | Optional user-set mm threshold; no anatomical default |
| Apply / Cancel | Explicit actions | Rigid move with provenance and rollback / discard preview |
| Record Reviewed Pose | Required after Apply | Assumption and fresh checks; collision flags need an override reason |
| Export Pose Session JSON | Explicit action | Pose history/current review; safe no-overwrite export |

Source-bound bone/skin targets move together; depths remain unchanged. Review is
invalidated by subsequent changes. Pose records accompany CSV, craniometry JSON
and session reports. No automatic occlusion, missing-jaw completion or GNM jaw
joint is introduced; ordinary fitting is unchanged when the tool is unused.

## Optional mandibular pose sensitivity (A4.6)

Explore explicitly configured rigid-pose scenarios without changing the skull or
face. The shared NumPy engine recomputes bone-reference positions, configured
cranial features and optional profile targets. [Configuration and interpretation](docs/POSE_SENSITIVITY.md).

| Control / command | Default | Behavior |
|---|---|---|
| Mandibular Pose Sensitivity panel | No run | Explicit configuration and export only |
| Write Blank Configuration / `python -m cranio.sensitivity template --output PATH` | Explicit action | Null ranges/pivot/axes/sample count; no invented scientific settings |
| `python -m cranio.sensitivity compute --input BONES --config CONFIG --output JSON` | Explicit action | Same scenario engine as Blender; no geometry mutation or face refit |
| Translation/rotation intervals, moving source IDs/hashes | Unconfigured | One rigid mandibular group, baseline + corners + seeded uniform scenarios |
| `feature_config.thresholds` | Null | Missing norms reported; threshold-crossing ranges labelled `indeterminate` |
| `profile` | Null | Optional sourced bone-normal offsets; derived targets only, no gap filling |

Ranges describe sampled scenarios, not confidence or validated accuracy. Failed
scenarios remain explicit and withhold dependent ranges. CT validation remains
separate; default live/offline fitting is unchanged.

## Anatomical-rule evidence registry (A3.1)

Eye, nose, mouth and ear rule metadata can be inspected offline. The bundled
bibliographic leads are **unverified and unimplemented**; missing formulas,
errors and applicability remain null. The registry does not change the face or
activate constraints. [Schema, review states and limitations](docs/ANATOMICAL_RULES.md).

| Command / field | Default | Behavior |
|---|---|---|
| `python -m cranio.rules inspect` | Bundled unverified catalogue | Print metadata, warnings and content/schema hashes |
| `inspect --input PATH` | No external file | Validate one explicit local JSON; no network access |
| `template --id ID --output PATH` | Explicit action | Write an empty catalogue; refuse overwrite |
| `status` / `verification` | `needs_verification` / unreviewed | Distinguish source verification, implementation testing and external evidence |
| `implementation_id`, `tested_error`, applicability | Unconfigured | No execution, imputed errors or presumed case applicability |

Registry/schema data ship in both the wheel and addon ZIP. The optional Blender
panel below exposes their status; numerical rule predictions remain pending.

## Anatomical-rule contracts (A3.2 infrastructure)

The rule API now distinguishes unconfigured formulas, unused features and unknown
case applicability. No numerical anatomical predictor is enabled. [Contracts and
remaining source requirements](docs/ANATOMICAL_RULES.md#a32-contract-and-unavailable-rule-handling).

| Command / API | Behavior |
|---|---|
| `python -m cranio.rules status [--input PATH] [--rule ID]` | Case-free readiness JSON; five bundled leads unconfigured, ear prediction unused |
| `cranio.rules.engine.predict(...)` | Source-missing stubs raise `NotConfigured`; unused rules return null predictions/SD/applicability |
| `Prediction` / `RuleResult` | Explicit units, finite values, immutable results and tri-state applicability; no SD imputation |

A valid status report exits successfully even when no predictions are available.
Changing registry review flags cannot activate a formula. Source-confirmed
formulas and their numerical reference tests are still required to complete A3.2.

## Optional native-mesh feature measurements (A3.3 core)

Reviewed model-bound correspondences can be measured on the fitted world-mm OBJ.
Missing mappings, predictors, SDs or threshold policies remain explicitly
unevaluated. No anatomical indices or traffic-light cutoffs are supplied.
[Mapping, API and limitations](docs/RULE_COMPARISON.md).

| Command / field | Default | Behavior |
|---|---|---|
| `python -m cranio.rules.comparison template --npz MODEL --output MAP` | Explicit action | Bind empty mapping to model hash/count; no overwrite |
| `python -m cranio.rules.comparison measure --npz MODEL --face FACE.obj --mapping MAP --output JSON` | Explicit action | Native-topology measurements and input hashes; no mesh changes |
| Point/feature `reviewed` | False | Require documented definitions and correspondences before measurement |
| `rule_id`, `thresholds` | Null | No prediction or traffic light inferred |

The shared NumPy core ships in the addon ZIP. Numerical anatomical rules, case
adapters and fitting constraints remain separate work.

## Blender anatomical-rule panel (A3.4)

**Anatomical Rules / Feature Snapshot** shows the bundled source leads and
execution states, with optional measurements on a selected neutral fitted mesh.
[Workflow, input gates and snapshot semantics](docs/BLENDER_RULE_PANEL.md).

| Control | Default | Behavior |
|---|---|---|
| Show / Refresh Rule Catalogue | Explicit action | Read-only source/DOI, review and execution states; no case assessment |
| Neutral fitted mesh / Reviewed feature map | None / unconfigured | Require native topology, matching model and reviewed mapping |
| Write Blank Feature Map | Explicit action | Model-bound null correspondences; no overwrite |
| Measure / Export Snapshot | Explicit action | Shared NumPy measurements, provenance JSON and historical display |

No model reads, geometry checks or fitting occur during panel redraw. Displayed
values are **last snapshots**, requiring recomputation after changes. Numerical
rules are still unavailable: SD deviation remains unavailable and the light
remains **not assessed**. No anatomical threshold or formula is invented.

## Experimental identity-prior audit (A6, opt-in)

Run the same case without an external prior and with the chosen prior, retain
both fits and export corresponding-vertex difference maps. The operator rationale
is recorded; the result describes sensitivity, not anatomical accuracy.
[Commands, outputs and limitations](docs/PRIOR_COMPARISON.md).

| Option | Default | Behavior |
|---|---|---|
| `--prior-compare` | Off | Paired neutral/prior fits under a fresh `<output stem>_prior_compare/` directory |
| `--prior-justification TEXT` | None | Required with comparison; recorded verbatim in the summary and prior child reports |
| `--prior FILE` | Existing none | Explicit experimental prior archive; no category inferred |

The ordinary no-prior fit is unchanged. Existing standalone/Blender prior controls
remain available without this new audit. Structured age handling and dedicated
Blender comparison controls are pending. No prior values or age effects are invented.

## Age-at-death metadata (A6, optional)

Use `python -m cranio.age_context template --output case_age.json` to create an
unknown assessment. Supply documented bounds, method and source, then pass it
via `--case-metadata` or Blender's **Age assessment JSON** field. The standalone
`compare --case-metadata FILE --tables ID_OR_PATH ... --output FILE` command audits
reported table ranges. No age, scientific threshold or tissue value is imputed;
no table is selected automatically and soft-tissue ageing is not modelled.
See [format, statuses and Blender workflow](docs/AGE_CONTEXT.md).

## Blender prior audit (A6, explicit action)

The offline panel offers **Prior rationale** and **Compare Neutral / Selected
Prior**. Select an existing local experimental prior and document the rationale;
the button runs the same paired CLI audit in external Python. Both checked
surfaces are imported separately (neutral initially hidden), with their report
links. Existing objects and marker coordinates are preserved. **Cancel Offline
Fit** handles either mode. Difference PLYs stay in the case output directory.
The ordinary fit button remains a single fit; a supplied rationale is recorded
when a prior is selected. See [controls and limitations](docs/PRIOR_COMPARISON.md#blender-paired-comparison).

## Derived approximation record (A7.1, optional)

After a completed fit, run `python -m cranio.record build --report path/to/face_report.json --output-dir path/to/new_record`.
The command checks the four output artifacts and writes a deterministic JSON view,
a summary TXT and a separate provenance envelope. It preserves the canonical run
report and all mesh files. Unknown uncertainty/calibration/validity-domain fields
remain `not_assessed`; operator-approved RO/EN limitations can be supplied explicitly.
See [options, integrity checks and determinism limits](docs/APPROXIMATION_RECORD.md).


To associate an existing A2.1 Monte Carlo report, add the following explicit options:

| Record option | Default | Effect |
|---|---|---|
| `--uncertainty FILE` | Absent | Link related uncalibrated marker-only evidence after checking recorded model/CSV hashes |
| `--uncertainty-scenario off/on` | Required with the file | Choose the scenario matching the run prior state; `on` also requires matching prior hash |

This records source warnings, omitted errors and numerical failures; it does not
apply SDs or calibration to the final mesh. Settings/target comparisons remain
descriptive, with fit equivalence explicitly unestablished. See the
[association contract](docs/APPROXIMATION_RECORD.md#explicit-association-of-an-a21-monte-carlo-analysis).


In Blender, **Approximation Record (saved fit)** now exposes the same export.
Select the saved fit report explicitly or use **Use Active Fit Report**, then
**Export Approximation Record**. The existing external Python performs the checks;
Blender displays a new text report after verified completion. Cancel, file-load
and unregister cleanup are supported. This records saved fit files, not current
scene edits. See [controls, defaults and limitations](docs/BLENDER_APPROXIMATION_RECORD.md).

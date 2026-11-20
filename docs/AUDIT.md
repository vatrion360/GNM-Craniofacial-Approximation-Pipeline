# T0.1 audit of the Blender and offline fit

Audited on 20 November 2026 at [`af97f88`](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/tree/af97f884e91e75faed57d90829f841a0d4173fdd), the integration branch after PR #63. This revision packages add-on 19.0.0 and offline software 5.0.0rc10. The eight findings below describe the implementation and its synthetic regression tests. Accuracy against an individual's CT face requires a separate paired evaluation.

## 1. Which markers enter the fit?

Blender defaults to Extended 48 (14 midline positions and 17 bilateral pairs). Paper 32 and Legacy 27 overlap at 11 positions. Each set controls which rows **Add Missing Markers** creates. Existing rows and case-specific edits survive a change of set. A live fit uses the world position of the skin endpoint of each placed, included marker with a resolved GNM vertex. Scenario and provenance rules can exclude additional rows. Duplicate checks run on the snapshot, and mandibular markers require articulation review. Offline CSV v3 records placement and inclusion separately. [addon_v13.py:345](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/addon_v13.py#L345) · [addon_v13.py:525](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/addon_v13.py#L525) · [addon_v13.py:1918](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/addon_v13.py#L1918) · [addon_v13.py:2537](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/addon_v13.py#L2537) · [cranio/io_csv.py:87](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/io_csv.py#L87)

The bone registry has 22 core references for 14 Table 3 chords, with 12 extended and four additional feature references (38 available codes in total). Their role is measurement, frame construction or anatomical description. Skin-distance controls require explicit bindings to eligible skin endpoints. A raw bone chord alone supplies no fitted skin length. [cranio/craniometry.py:18](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/craniometry.py#L18) · [cranio/craniometry.py:42](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/craniometry.py#L42) · [cranio/craniometry.py:70](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/craniometry.py#L70) · [cranio/craniometry.py:239](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/craniometry.py#L239) · [cranio/landmarks.py:225](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/landmarks.py#L225) · [cranio/landmarks.py:253](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/landmarks.py#L253)

The official-model registry check found 48 distinct mapped vertices and zero duplicate errors. At the 2 mm proximity screening distance, it returned one pair. `Nasospinale_BazaNas` and `Acanthion` map to vertices 12298 and 12297, 1.499703 mm apart on the neutral template. Their distinct definitions and the direction chosen for each need operator review. [tools/audit_landmarks.py:15](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/tools/audit_landmarks.py#L15) · [cranio/landmarks.py:181](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/landmarks.py#L181)

## 2. Where do tissue depths and dense offsets come from?

The table lists **initial depths for newly created Blender rows** in mm. On shared sites, Extended 48 preserves the legacy value, while Paper 32 initializes from its own transcription. For example, adding Nasion to an empty case gives 6 mm in Extended 48 or 7 mm in Paper 32. Selecting Paper 32 after Nasion already exists preserves the current case value. A dash means the site is absent from Paper 32. The row-level metadata and original transcription notes are in the versioned JSON tables. [addon_v13.py:525](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/addon_v13.py#L525) · [cranio/landmarks.py:170](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/landmarks.py#L170) · [cranio/data/tissue/legacy_hardcoded.json:16](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/data/tissue/legacy_hardcoded.json#L16) · [cranio/data/tissue/var2026_table2.json:15](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/data/tissue/var2026_table2.json#L15)

| Marker label(s) | Extended 48 (mm) | Paper 32 (mm) | Source of Extended 48 default |
| --- | ---: | ---: | --- |
| `Nasion` | 6 | 7.0 | Legacy |
| `Rhinion` | 3 | 2.5 | Legacy |
| `Glabella` | 5 | 4.5 | Legacy |
| `Pogonion` | 10 | 13.0 | Legacy |
| `Gnathion` | 10.5 | — | Legacy |
| `Gonion_Dr` / `Gonion_St` | 13 | 10.5 | Legacy |
| `Orbita_Dr_Ext` / `Orbita_St_Ext` | 8 | — | Legacy |
| `Orbita_Dr_Int` / `Orbita_St_Int` | 6 | — | Legacy |
| `Supraorbitale_Dr` / `Supraorbitale_St` | 7 | 8.5 | Legacy |
| `Infraorbitale_Dr` / `Infraorbitale_St` | 7 | — | Legacy |
| `Zygion_Dr` / `Zygion_St` | 8.5 | 7.0 | Legacy |
| `Alare_Dr` / `Alare_St` | 4.5 | — | Legacy |
| `Eurion_Dr` / `Eurion_St` | 5 | — | Legacy |
| `Vertex_VarfCap` | 5.5 | — | Legacy |
| `Nasospinale_BazaNas` | 11 | — | Legacy |
| `Prosthion_BuzaSup` | 12 | 11.0 | Legacy |
| `Acanthion` | 10 | — | Legacy |
| `Piriform_Dr` / `Piriform_St` | 6.5 | — | Legacy |
| `Supraglabella` | 4.5 | 4.5 | Table 2 |
| `Midphiltrum` | 10 | 10.0 | Table 2 |
| `Infradentale_BuzaInf` | 12.25 | 12.25 | Table 2 |
| `Supramentale` | 10 | 10.0 | Table 2 |
| `Menton` | 8 | 8.0 | Table 2 |
| `FrontalEminence_Dr` / `FrontalEminence_St` | 4 | 4.0 | Table 2 |
| `Suborbitale_Dr` / `Suborbitale_St` | 6.25 | 6.25 | Table 2 |
| `InferiorMalar_Dr` / `InferiorMalar_St` | 12 | 12.0 | Table 2 |
| `LateralOrbit_Dr` / `LateralOrbit_St` | 11.5 | 11.5 | Table 2 |
| `Supraglenoid_Dr` / `Supraglenoid_St` | 6.25 | 6.25 | Table 2 |
| `SupraM2_Dr` / `SupraM2_St` | 18 | 18.0 | Table 2 |
| `Midmasseter_Dr` / `Midmasseter_St` | 17.5 | 17.5 | Table 2 |
| `SubM2_Dr` / `SubM2_St` | 17 | 17.0 | Table 2 |

The five dense facial offsets are `brow_median` 5, `punte_nazala` 3, `zigomatic` 8.5, `infraorbital` 7 and `barbie` 10 mm. The scalp starts at 5 mm and has a separate case setting. These are inherited engineering values. Relative landmark weights live in the registry. Offline SD-based weighting is an explicit option. The bundled tables leave unknown SDs unpopulated, and the weighting code records a neutral factor when an applicable SD is missing. [cranio/landmarks.py:57](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/landmarks.py#L57) · [cranio/landmarks.py:130](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/landmarks.py#L130) · [cranio/geometry.py:85](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/geometry.py#L85) · [cranio/config.py:32](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/config.py#L32) · [cranio/depth_weighting.py:10](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/depth_weighting.py#L10)

## 3. In which direction is depth applied?

A Blender marker starts along a signed normal estimated from the evaluated bone mesh. The default is a connected local-plane estimate with a 3 mm radius. Single-facet normal is an explicit alternative. The target is the bone point plus the unit direction times tissue depth in world mm. For an explicit table replacement in the offline pipeline, `existing` keeps the case's bone-to-skin axis. `source` uses a signed axis declared for that site and checks the manifest, table, anchor and any required frame. Dense targets use the accepted sampled **bone** normal and regional offset. The fit consumes the resulting coordinates. [addon_v13.py:367](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/addon_v13.py#L367) · [cranio/blender_marker_normals.py:24](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/blender_marker_normals.py#L24) · [cranio/blender_marker_normals.py:83](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/blender_marker_normals.py#L83) · [cranio/tissue_application.py:60](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/tissue_application.py#L60) · [cranio/tissue_directions.py:66](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/tissue_directions.py#L66) · [cranio/geometry.py:134](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/geometry.py#L134)

## 4. Which identity coefficients are solved and counted at the clip limit?

The verified GNM v3 archive has 17,821 vertices and 253 named identity components. In file order these are head 0–169, eyes 170–172 and teeth 173–252. Default `all` solves all 253. In `head` mode, selection uses component names, the solver operates on 170 components and it returns a full vector with the 83 inactive coefficients set to zero, including when a prior is active. The default clip is ±3. The reported saturation count includes only active coefficients at or within `1e-9` of the limit, so eye and tooth coefficients can contribute in `all` mode. [cranio/identity.py:5](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/identity.py#L5) · [cranio/config.py:42](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/config.py#L42) · [cranio/config.py:85](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/config.py#L85) · [cranio/optimize.py:300](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/optimize.py#L300) · [cranio/optimize.py:443](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/optimize.py#L443) · [cranio/optimize.py:486](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/optimize.py#L486) · [addon_v13.py:2690](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/addon_v13.py#L2690)

## 5. How is global scale estimated and bounded?

Weighted Umeyama estimates one isotropic scale, a proper rotation and a translation. The implementation rejects a nonfinite scale or a scale ≤ `1e-12`. With reviewed skin-distance controls active, it updates scale and translation at fixed rotation using both point and distance terms. The last pose update uses the final coefficients. The solver imposes no anatomical scale interval. Both input unit conversion and skull registration therefore matter before interpreting millimetre errors. [cranio/optimize.py:58](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/optimize.py#L58) · [cranio/optimize.py:331](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/optimize.py#L331) · [cranio/measurement_fit.py:72](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/measurement_fit.py#L72) · [cranio/optimize.py:482](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/optimize.py#L482)

## 6. How large can the local correction be?

The offline fit skips local correction by default. When enabled, the default smooth displacement cap is 8 mm outside the scalp mask and 15 mm on the scalp. The solver uses a 3D linear polyharmonic kernel (−r), an affine tail and zero smoothing. It applies the cap to displacement magnitude with `tanh`, then multiplies displacements in protected eye, eye-interior, mouth-sock and lip groups by 0.25. These limits describe the change from the statistical surface during this stage. They do not establish a bound on final anatomical error. [cranio/config.py:50](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/config.py#L50) · [cranio/local_correction.py:145](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/local_correction.py#L145) · [cranio/landmarks.py:125](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/landmarks.py#L125) · [cranio/optimize.py:549](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/optimize.py#L549) · [cranio/optimize.py:565](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/optimize.py#L565) · [cranio/pipeline.py:540](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/pipeline.py#L540)

## 7. Which entry point produced the result?

| Entry point | Marker and regularization behavior | Output and correction |
| --- | --- | --- |
| Blender live preview | Three noncollinear markers support a marker-based pose. With fewer than three, the preview needs prepared bone geometry and at least ten accepted dense rows. Adaptive lambda is the default. Conditional LOO is available from four markers. | Statistical face in the scene. [cranio/preview.py:9](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/preview.py#L9) · [addon_v13.py:2676](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/addon_v13.py#L2676) · [addon_v13.py:3568](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/addon_v13.py#L3568) |
| Blender **Finalize Local Fit (New Mesh)** | Fresh fit from at least four included markers using current live settings. The correction also requires at least four noncoplanar centres. | Separate corrected float32 mesh, NumPy spline and basic geometry QC. [cranio/finalize.py:14](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/finalize.py#L14) · [cranio/local_correction.py:147](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/local_correction.py#L147) · [cranio/blender_finalize.py:87](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/blender_finalize.py#L87) |
| Blender **Run Offline Fit and Import** | Launches external Python with exported markers and the selected adaptive or conditional-LOO setting. Forwards the subspace, clip and enabled options including dense fit, craniometry weight and prior. | Offline artifacts and imported result. Local correction depends on the offline checkbox. [addon_v13.py:3981](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/addon_v13.py#L3981) · [addon_v13.py:4015](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/addon_v13.py#L4015) · [addon_v13.py:4040](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/addon_v13.py#L4040) |
| Direct offline CLI | At least four retained targets. Defaults to conditional LOO (`auto`), with fixed or adaptive lambda available. | Statistical and final artifacts with run report. Optional SciPy local correction and full geometry QC. [cranio/config.py:41](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/config.py#L41) · [cranio/pipeline.py:240](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/pipeline.py#L240) · [cranio/pipeline.py:403](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/pipeline.py#L403) · [cranio/pipeline.py:540](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/pipeline.py#L540) · [cranio/pipeline.py:604](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/pipeline.py#L604) |

Live and offline use the same identity solver. For adaptive regularization, the unbounded value is `base × 48 / included marker count`, clamped to the configured minimum and maximum. A zero-marker preview uses the maximum. Dense rows are excluded from that count. With default settings, eight included markers give λ = 6. [cranio/regularization.py:7](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/regularization.py#L7) · [cranio/preview.py:34](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/preview.py#L34) · [cranio/pipeline.py:424](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/pipeline.py#L424)

## 8. When does a demographic prior affect the fit?

The default is a neutral, zero-centred ridge penalty. Direct CLI requires a prior file to activate demographic shrinkage. Blender initializes both demographic selectors to `NONE` and requires both selections to load a prior. For a selected prior, the squared penalty uses precision `lambda × prior_weight / prior_scale²` around the recorded component mean. The head-only restriction still applies. Blender copies the selected file and verifies its hash before passing it to external Python. The optional neutral/prior comparison requires an operator rationale. The bundled demographic priors remain experimental. [cranio/config.py:72](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/config.py#L72) · [cranio/optimize.py:413](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/optimize.py#L413) · [cranio/prior.py:6](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/cranio/prior.py#L6) · [addon_v13.py:3165](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/addon_v13.py#L3165) · [addon_v13.py:3573](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/addon_v13.py#L3573) · [addon_v13.py:4039](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/blob/af97f884e91e75faed57d90829f841a0d4173fdd/addon_v13.py#L4039)

## Verification at the audited revision

Linux, Python 3.12.14, Blender 4.3.2, official model SHA-256 `e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`. Pytest passed **1,641 tests** with one Windows-only skip. The installed Blender ZIP reached `BLENDER_SMOKE_PASS`. Both T0.2 cases exactly matched the published numerical snapshot in this environment.

| Synthetic regression | Retained markers | Lambda | Scale (rounded) | Final marker RMSE (mm, rounded) |
| --- | ---: | ---: | ---: | ---: |
| Mean model | 48 | 20 (fixed) | 1.000000 | < 1e-12 |
| Sparse Rhinion perturbation with local correction | 8 | 6 (adaptive) | 0.993754 | 0.009168 |

For the eight-marker case, marker RMSE was 0.684855 mm on the statistical face and 0.009168 mm after local correction. Both use the same eight fitting targets. For independent subject-level accuracy, use withheld reference surfaces under the [paired CT protocol](validation_protocol.md). Instructions for reproducing the two synthetic comparisons are in the [baseline runner guide](OFFLINE_BASELINE.md).

To reproduce the registry check and test results from the repository root with the reviewed model and offline environment prepared:

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python -m tools.audit_landmarks --npz "$GNM_MODEL_PATH" --output /tmp/gnm-landmark-audit.json
python -m pytest -q
python tools/build_addon.py
GNM_EXTERNAL_PYTHON="$(command -v python)" blender -b --factory-startup --python-exit-code 1 --python tools/blender_smoke.py
python scripts/run_baseline.py --suite examples/regression/suite.json --model "$GNM_MODEL_PATH" --compare baseline/5.0.0rc10
```

## Historical repository audit — 2026-09-25

Baseline: `b72fb73` from `vatrion360/GNM-Craniofacial-Approximation-Pipeline`.

The repository had a useful numerical skeleton and a substantial Blender interface, but its original distribution did not support the advertised installation, historical test counts or publication-grade readiness. No scanned subject or paired skull/face validation dataset was present.

| Finding | Consequence | Change / remaining work |
| --- | --- | --- |
| No committed test suite or package metadata; README referenced absent files/model/venv | Clean installation and claimed test badges could not be reproduced | Added packaging, tests, build scripts and honest installation steps |
| Single-file add-on imported an adjacent `cranio` not included by Blender installation | Installed add-on could not find its numerical core | Build a complete ZIP; use a private package namespace |
| `allow_pickle=True` for numerical model loading | Unnecessary execution surface for untrusted archives | Disabled pickle; check dimensions, numeric values, topology and mirror mapping |
| CSV export had only encoded index and skin coordinates | Manual vertex picks, bone positions and tissue provenance lost | Explicit v3; retain legacy decoding with warnings |
| Zero coordinates used as universal unplaced sentinel | Valid origin markers disappeared | v3 has a separate placed flag |
| Missing validation of units, NaN, duplicates and weights | Silent corruption or opaque numerical failures | Strict input contracts and CLI error return codes |
| Negative SVD determinant rejected unconditionally | Valid planar configurations could fail | Proper-rotation Umeyama with rank checks |
| Mean Euclidean distance displayed as RMS | Understated/incorrectly named metric | True RMSE; report mean/median/p95/max separately |
| Symmetry penalty compared opposite-side coordinates without reflecting x | Symmetric shape changes could be penalized | Geometric sagittal reflection before differences |
| Soft latent-prior IRLS multiplier squared an extra ratio | Incorrect gradient surrogate | Corrected the ratio and documented heuristic clipping |
| Final pose could lag behind final coefficients | Residuals used an outdated pose | Re-estimate pose for final coefficients |
| Fixed-pose LOO labelled like independent validation | Optimistic interpretation of tuning errors | Explicit conditional label; separate outer pose-refitting holdout utility |
| Local deformation defaulted on, used 2-D TPS kernel, lacked input guards | Uncontrolled interpretation and singular systems | Opt-in 3-D polyharmonic kernel, rank/cap checks, separate statistical OBJ |
| Nasal offline diagnostic used skin targets and arbitrary world axes | Anatomically wrong tangent inputs | Bone-only v3 positions; rotate to pose-aligned frame; unavailable when missing |
| Skull import guessed units from bounding-box size | Fragment size could cause a thousandfold scale error | Explicit source-unit choice; no bounding-box heuristic |
| Tissue edits did not update existing targets | Displayed depth differed from fitted geometry | Update target and peg; refuse inconsistent export |
| Persistent Python fitting thread in Blender | Unsupported threading model and shared-state hazards | Serialized optional preview; external process for final fitting |
| File outputs silently overwrote and lacked machine-readable provenance | Weak reproducibility and case tracking | Distinct paths, explicit overwrite, atomic individual files, completion manifest |
| Colour scale's maximum returned yellow | Misleading displacement visualization | Correct red endpoint and numeric displacement/scale |
| Legacy depths/mapping confidence asserted scientific validity without row-level evidence | Unsupported precision and homology claims | Clearly label inherited assumptions; specialist review remains required |

### Limitations recorded in September 2026

- Anatomical validation of all 27 bone-to-skin correspondences, including definition/direction of each measurement.
- Tissue tables with appropriate study/cohort/measurement provenance and calibrated individual uncertainty.
- Independent paired-subject accuracy, repeatability, interobserver error, subgroup performance and uncertainty coverage.
- Interactive Blender compatibility, undo/file-load behavior, viewports and external-process UX on the intended OS.
- Guaranteed skull containment, collision-free local warps, anatomically independent eye/lip/nose modelling or recovery of a person's identity.

See [VALIDATION](VALIDATION.md) for acceptance criteria and the distinction between implemented checks and unexecuted validation. The legacy demographic-prior generator and map-builder remain experimental; their historical output claims are not certified by this revision.

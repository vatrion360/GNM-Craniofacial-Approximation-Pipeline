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
- [Mixed fragments, duplicates and adaptive lambda](docs/FRAGMENT_RESTORATION.md)
- [Validation protocol and current evidence](docs/VALIDATION.md)
- [Numerical corrections, geometry QC and frozen CT protocol](docs/SCIENTIFIC_HARDENING.md)
- [Reviewed tissue measurement directions](docs/TISSUE_DIRECTIONS.md)
- [Explicit tissue scenarios and comparison](docs/TISSUE_SCENARIOS.md)
- [Versioned tissue tables: JSON/CSV exchange](docs/tissue_tables_howto.md)
- [Contributing and CI](CONTRIBUTING.md)
- [Optional head-only identity fitting](docs/IDENTITY_SUBSPACE.md)
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

For explicit scenarios in fitting, see [selection/application and comparison](docs/TISSUE_SCENARIOS.md).
Selecting a table alone preserves case values. Replacing selected values requires
explicit labels and either acceptance of existing axes or a reviewed source-direction
manifest. Blender offers both policies on checked, placed markers with
Undo and audit history. Existing manual values change only through explicit Apply. Dense offsets still
follow reviewed sampled bone normals and are not replaced by selected-marker tables.

| Fit option | Default | Effect |
| --- | --- | --- |
| `--depth-weighting {none,sd}` | `none` | Offline only: optional `1/SD_mm²` multipliers from the selected table; missing SD retains base weight with warning; sensitivity, not calibrated uncertainty |
| `--tissue-table ID_OR_JSON` | None | Select/report a table; does not by itself replace targets |
| `--tissue-labels LABEL ...` | Empty | Explicit authorization to replace these case depths/targets |
| `--tissue-axis {existing,source}` | Unconfigured | Preserve current axes explicitly, or use reviewed world-frame source directions |
| `--tissue-directions FILE` | None | Manifest required for source mode; normal, vertical or explicit in-sagittal-plane vectors; no inferred frame |
| `--tissue-compare ID1,ID2,...` | None | Independent per-table fits, corresponding-vertex difference PLYs and summary; fresh output prefix required |

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

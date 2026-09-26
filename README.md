# GNM Craniofacial Approximation

A Blender marker add-on and an offline, auditable fitting pipeline for **supervised craniofacial approximation research**. Fits a neutral GNM Head identity model to operator-defined skin targets derived from a scanned skull.

**Software 5.0.0rc2 / add-on 15.0.0.** This revision adds 48 markers, a cited 32-position reference from the supplied paper, bone/restoration provenance and external-Python checks for Windows. It does **not** establish forensic accuracy or recover a uniquely determined face. Tissue applicability and GNM correspondences require anatomical review. See the [PDF-based protocol](docs/PDF_PROTOCOL.md), [scientific basis](docs/SCIENCE.md) and [audit](docs/AUDIT.md).

## Start here

- [Install, obtain model assets, prepare an offline workstation](docs/INSTALL.md)
- [Specialist workflow, anatomical review and output interpretation](docs/SPECIALIST_WORKFLOW.md)
- [Ghid rapid în română](docs/GHID_RO.md)
- [Marker v3 specification and migration](docs/MARKERS.md)
- [PDF Table 2, 48-marker set and correspondence changes](docs/PDF_PROTOCOL.md)
- [Scientific rationale and primary references](docs/SCIENCE.md)
- [Validation protocol and current evidence](docs/VALIDATION.md)
- [Change log](CHANGELOG.md)

## Quick start

Python 3.10+; the current local test environment is Python 3.12 on Linux.

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install .
```

Obtain `gnm_head.npz` from the official Google GNM repository using the pinned instructions in [INSTALL](docs/INSTALL.md). The weights are **not included** in this repository, wheel or add-on ZIP. They are local files at reconstruction time; there is no runtime download, cloud inference or telemetry.

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

Local correction is opt-in (`--local-correction`). Dense skull constraints are experimental and require a skull exported in the **same world-mm frame** (`--skull skull.obj`). Read the workflow before enabling either.

## Blender

```bash
python tools/build_addon.py
```

Install `dist/gnm_cranio-5.0.0rc2.zip` through Blender's **Install from Disk** and enable **GNM Scientific Markers**. The ZIP includes `cranio`; installing `addon_v13.py` alone is no longer the recommended route. Blender 4.5.0 Linux/Windows integration is exercised by CI; see [revision-specific results](docs/VALIDATION.md). Blender **4.2+ remains the broader target**; interactive and other version checks remain pending.

Select the local model, import the skull with explicit source units, place/review markers, and export v3 CSV. For **Run Offline Fit and Import**, select the external Python executable from the environment above and a case output folder. The add-on runs the CLI in a separate process, records a log, then imports the completed world-mm OBJ. Each run gets a new case subfolder. The default button uses marker-only statistical fitting; advanced dense/correction options are available through the CLI.

Use **Extended 48**, **Paper 32** or **Legacy 27**, then **Add Missing Markers**. Existing placements, tissue values and manual picks are retained. The paper's normal-female reference can be applied explicitly with **Apply Table 2 Tissue Depths**; review applicability before case use. Sites marked **Include in fit = off** remain documented but do not affect pose or identity fitting. The default Pogonion candidate is corrected from lower-lip vertex 12284 to chin candidate 12261; review previous cases.

On Windows select **`.venv\Scripts\python.exe`** (or the Windows-created `.venv` folder), then **Check Python Environment**. Selecting the pipeline `.py`, Blender itself, an installer or a copied Linux interpreter is rejected before fitting. See [Windows troubleshooting](docs/INSTALL.md#windows-interpreter-check-and-winerror-193).

Optional legacy previews run serially on Blender's main thread and may pause the UI. No persistent Python fitting thread is started inside Blender.

## Reproducible demonstration

The supplied `examples/synthetic_markers.csv` is generated from the GNM mean. It demonstrates software operation, **not reconstruction accuracy**.

```bash
python gnm_reconstruct.py --input examples/synthetic_markers.csv --npz models/gnm_head.npz --output outputs/demo/face.obj --regularization 30 --strict
python -m cranio.evaluation --input examples/synthetic_markers.csv --npz models/gnm_head.npz --output outputs/demo/holdout.json --regularization 30
```

`cranio.evaluation` holds out each landmark and refits pose and identity without it. Its scores are distinct from the conditional fixed-pose LOO used to tune regularisation. Neither is a substitute for evaluation on paired skull/face subjects.

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

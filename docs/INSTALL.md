# Installation and offline preparation

## Tested versus targeted

The Python pipeline is tested locally on Linux / Python 3.12.14 with the exact versions in `requirements-tested-py312.txt`. CI covers Python 3.10/3.12 on Windows/Linux and headless Blender 4.5.0 on both systems, including model loading, marker export, external fitting/import and cancellation; see the revision-specific results in [VALIDATION](VALIDATION.md). Blender 4.2+ remains the broader target; other versions/platforms and interactive workflows need their own acceptance checks. The earlier README's Blender 3.6–5.0 and historical test badges were not supported by committed test evidence.

## 1. Prepare the Python environment

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell alternative:
# .venv\Scripts\Activate.ps1
python -m pip install .
```

No TensorFlow, PyTorch, CUDA, GNMImporter purchase or complete GNM Python installation is needed for neutral identity fitting. The optional legacy demographic-prior generator has separate dependencies and is outside the tested fitting workflow.

## 2. Acquire and verify the official model (connected preparation)

```bash
git clone https://github.com/google/GNM.git vendor/GNM
git -C vendor/GNM checkout 915aa356c6a2247083e69a06e40dfe909d42435a
python tools/prepare_model.py --source vendor/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz --destination models/gnm_head.npz
python -m cranio.doctor --npz models/gnm_head.npz
```

Keep the upstream license/notices beside transferred assets. `prepare_model.py` only copies an existing file after verification; it performs no network access. The reviewed asset's SHA-256 is:

```text
e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de
```

The reviewed model has 17,821 vertices and 253 identity dimensions. The float32 identity basis occupies about 54 MB (decimal). Asset identity is verified by hash; dimensions alone cannot establish topology identity or anatomical validity. The Blender built-in map requires this exact asset. Explicit v3 mappings can be used for experimental compatible archives in the CLI, with independent review.

Use `--npz` for every command, or set `GNM_MODEL_PATH` to an absolute filename. Do not place downloaded models in Git.

## 3. Install the Blender ZIP

```bash
python tools/build_addon.py
```

In Blender: Preferences → Add-ons → Install from Disk → select `dist/gnm_cranio-5.0.0rc3.zip` → enable **GNM Scientific Markers**. The sidebar is **GNM Markers**. Disable previous copies to avoid duplicate operator registrations.

Select `gnm_head.npz`. Import a skull and explicitly select mm/cm/m according to the source file. The resulting scene uses **one Blender coordinate = one millimetre**, represented by metric scale `0.001`. Check a known anatomical/scanner measurement after import; STL/OBJ do not reliably carry physical units.

To run the pipeline from Blender, set **Python executable** to `.venv/Scripts/python.exe` on Windows or `.venv/bin/python` on Linux/macOS. Select a case output folder. The add-on invokes its bundled CLI with that interpreter; required dependencies must already be installed in the environment. Blender's own Python does not need SciPy or trimesh for marker placement/preview.

### Windows interpreter check and WinError 193

`[WinError 193] %1 is not a valid Win32 application` is Windows loader error `ERROR_BAD_EXE_FORMAT`: the selected executable could not be started. It occurs before the numerical fit. Earlier add-on versions checked only that the selected file existed, allowing a `.py` script, a foreign-platform interpreter or another unsuitable file to reach `CreateProcess`. The message alone cannot identify which file was selected on a particular workstation. [Microsoft error-code reference](https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--0-499-).

Prepare the environment on the Windows workstation from the repository directory (PowerShell):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m cranio.doctor --npz models\gnm_head.npz
(Resolve-Path .\.venv\Scripts\python.exe).Path
```

Paste the last command's output into Blender's **Python executable / venv folder** field. The field takes one interpreter path, without script names or command arguments. Click **Check Python Environment**: it must show Python 3.10+ / 64-bit and `numpy/scipy/trimesh OK`. Select a case folder, place/review at least four included markers, then run the offline fit. For an air-gapped workstation, use the wheelhouse instructions below in place of the connected `pip install` step.

Add-on 15 rejects scripts, activation files, installers, `blender.exe`, `pythonw.exe` and non-Windows binary signatures. It also checks the actual Python version/bitness and imports the required packages, with actionable dependency/DLL errors. Child processes receive a clean Python environment rather than Blender's `PYTHONHOME`/`PYTHONPATH`. Arguments stay separate with `shell=False`, including paths with spaces and Romanian characters. The run log records the interpreter and argument list.

Create each virtualenv on its target operating system; copying a Linux/macOS `.venv` onto Windows cannot make its interpreter a Windows executable. If a binary-format error persists after choosing the correct interpreter, use the full path and diagnostic shown by **Check Python Environment** to check that installation and CPU/OS compatibility.

The default **Run Offline Fit and Import** creates a unique subfolder, exports v3 markers, runs the marker-only statistical fit, writes `run.log`, and imports the resulting OBJ without axis conversion. Cancellation terminates the process and retains partial files. A completed JSON report is the completion marker. Advanced CLI settings do not silently carry over from the preview controls.

Add-on 16 explicitly shares the regularization choice with this button: adaptive `base * 48 / included marker count`, or conditional LOO when selected. It passes the adaptive base/min/max values to the CLI. Other advanced preview options are not implicitly applied to the offline run. See [FRAGMENT_RESTORATION](FRAGMENT_RESTORATION.md) for duplicate checks and mixed-fragment restoration.

## 4. Build an air-gapped installation kit

On a connected machine with the **same OS, CPU architecture and Python minor version** as the target:

```bash
python -m pip install build
python -m build --wheel
python -m pip download --only-binary=:all: --dest wheelhouse -r requirements-tested-py312.txt
```

Copy the project wheel, wheelhouse, model + upstream notices, add-on ZIP and this documentation to the offline workstation. For Python versions other than 3.12, resolve/test an appropriate dependency set instead of using the 3.12 pins. Do not copy a virtualenv between different operating systems.

On the offline workstation, create/activate a fresh virtualenv, then:

```bash
python -m pip install --no-index --find-links wheelhouse dist/gnm_craniofacial-5.0.0rc3-py3-none-any.whl
python -m cranio.doctor --npz models/gnm_head.npz
```

If no compatible wheel is found, rebuild the kit on the matching target platform. Reconstruction itself never calls a network service. Record hashes for the kit and keep it with your local validation record. Bitwise identity across different BLAS/OS builds is not guaranteed; seeds, versions, assets and numerical tolerances must be recorded.

## 5. Acceptance checks

```bash
python -m pip install '.[dev]'
python -m pytest -q
python tools/build_addon.py
blender --background --factory-startup --python-exit-code 1 --python tools/blender_smoke.py
```

Set `GNM_MODEL_PATH` for both commands to exercise real asset integration. The Blender script checks ZIP loading, registration/unregistration, marker initialization, depth updates and v3 export. Set `GNM_EXTERNAL_PYTHON` to the external interpreter to also test fitting/import/cancellation. Interactive viewport, selection, undo and operating-system behavior still require the manual checklist in [VALIDATION](VALIDATION.md).

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `cranio` missing in Blender | Install the complete ZIP, not the standalone Python file |
| Model missing or checksum mismatch | Verify local asset with `gnm-doctor`; do not rename an incompatible archive |
| CSV units rejected | Convert explicitly; export v3 from a scene with metric scale 0.001 |
| Bone-to-target depth mismatch | Review the moved marker; edit depth or re-place it before export |
| Degenerate markers/correction centres | Add spatially distributed landmarks; disable local correction if only coplanar points exist |
| Output exists | Choose a new case folder, or deliberately use `--overwrite` |
| Offline fit failed in Blender | Read the case's `run.log`; verify external interpreter dependencies |
| Preview pauses the UI | Stop preview and use the external offline fit button |

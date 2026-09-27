# Contributing

Use a feature branch and a pull request. Keep numerical changes, anatomical assumptions and measured validation evidence distinct. Do not redistribute GNM model weights or subject scans in a PR.

For the reviewed Python 3.12 runtime:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --require-hashes --only-binary=:all: -r requirements-tested-py312.txt
python -m pip install '.[dev]'
python -m ruff check cranio addon_v13.py gnm_reconstruct.py tools tests
python -m pytest -q
python -m build
python tools/build_addon.py
```

Set `GNM_MODEL_PATH` to the reviewed official v3 asset to enable the integration test. For Blender 4.5, set `GNM_EXTERNAL_PYTHON` to that environment's Python executable and run:

```bash
blender --background --factory-startup --python-exit-code 1 --python tools/blender_smoke.py
```

CI runs Python 3.10/3.12 on Windows/Linux, the official-model suite and actual Blender ZIP integration on Windows/Linux, and a vulnerability audit of the pinned runtime. Python 3.10 is a compatibility range test; Python 3.12 consumes the hash lock. macOS and interactive workflows require separate acceptance evidence. Hash-lock updates are deliberate changes using `tools/lock_runtime.py`, followed by both runtime gates; do not silently update versions while evaluating blinded cases.

Changes to fit weighting, mm conversion, IRLS, lambda, normal orientation or region sampling need regressions that compare observable results. Preserve the shared solver; put Blender data access on its main thread and numerical code in `cranio/`. Use synthetic known transforms, explicit malformed inputs and mixed-side fragment fixtures. Tests must not treat an attractive face or a low training residual as anatomical validation.

For anatomical changes, cite the primary source and exact landmark definition/table, direction, units, cohort and applicability. Distinguish source facts from implementation choices. Label legacy candidates and synthetic checks explicitly. Keep the report schema, CLI help, defaults and workflow docs consistent. Any study protocol change after freezing needs a new revision and transparent reporting; see [scientific hardening](docs/SCIENTIFIC_HARDENING.md).

Before release, build and install the wheel outside the source tree, install the ZIP in actual Blender, review warnings and skipped gates, and record commit-specific CI links in `docs/VALIDATION.md`. Interactive acceptance and independent paired-data accuracy cannot be inferred from CI success.

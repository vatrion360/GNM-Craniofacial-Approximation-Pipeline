# Replaying an offline fit baseline

Use `scripts/run_baseline.py` from a source checkout to detect changes in offline fit results. The supplied suite contains two synthetic inputs to GNM Head v3.0. The first fits the existing 48 mean-model targets with fixed regularization. The second takes the first eight targets, adds 3 mm to the world Y coordinate of Rhinion, and uses adaptive regularization plus local correction. Its iteration budget is 150. These cases exercise software behavior. Anatomical accuracy requires independent reference data.

## Replay the published snapshot

Run from the repository root. Set the numerical libraries to the same thread counts as the reference run. In PowerShell use `$env:OPENBLAS_NUM_THREADS='1'` and `$env:OMP_NUM_THREADS='1'`.

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python scripts/run_baseline.py --suite examples/regression/suite.json --model /path/to/gnm_head.npz --compare baseline/5.0.0rc10
```

The checked-in snapshot uses the solver at commit `25aed352`, Linux x86-64, Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0 and trimesh 5.1.0. Comparison is exact. OS line endings, numerical libraries, CPU and thread settings can affect file hashes or the last digits of a metric. Read the per-case diff before attributing a difference to the solver. The program does not assign an anatomical tolerance.

## Record a local suite

Create a UTF-8 JSON object. Each key names a replay case. Each value is an array of arguments accepted by the offline CLI. For example, the value `["--input", "case/markers.csv", "--skull", "case/skull.stl", "--regularization", "adaptive"]` requests one case. Relative input paths resolve beside the suite JSON. Use the shared `--model` on the runner. Leave all output paths to the runner. Represent each prior or tissue-table scenario as a separate single fit.

```sh
python scripts/run_baseline.py --suite /path/to/suite.json --model /path/to/gnm_head.npz --record /path/to/new-baseline
```

All fits must return success before the new directory is created. Each fit writes into a temporary directory that is removed after its report is read. The snapshot retains the effective settings, input and geometry file hashes, marker and displacement metrics in mm, selected lambda, scale and convergence flag. The software and numerical environment from the first fit are saved separately in `environment.json`. Keep baselines with real case identifiers or operator-supplied settings private.

Exit code 0 means the baseline was recorded or matched. Code 1 prints a diff for changed, added or missing cases. Code 2 reports a configuration, fit or file error. Record to a new directory to review a candidate baseline alongside the old one.

# A2.4 — empirical calibration harness execution report

## Scope

Implemented on `feature/uncertainty-calibration-harness`, based on A2.3 commit
`e18ebdbd881d895d357a0fa24f53b91a26c57ef9`. PR #23's Python/packaging and Blender
GitHub checks were verified successful before starting this task.

The user's independent CT assessment remains manual. This task supplies
configuration, input loading, empirical multiplier fitting, frozen evaluation
and auditable reports. It does **not** claim to complete CT validation.

## Changes

- `cranio/calibration.py`: NumPy core and `template`, `fit`, `evaluate` CLI.
- `scripts/calibrate_uncertainty.py`: source-checkout wrapper.
- `tests/test_calibration.py`: 43 synthetic checks, including CLI integration.
- `tools/blender_uncertainty_checks.py`: packaged NumPy numerical check.
- `examples/calibration_synthetic/`: three synthetic cases, two calibration and
  one held-out, with valid measurement-file hashes. No human surfaces or data.
- `MANIFEST.in`: include the wrapper in source distributions.
- `.gitattributes`: preserve the hash-pinned example CSV LF bytes on Windows checkouts.
- `docs/UNCERTAINTY_CALIBRATION.md`, this report, README options and links in
  the earlier uncertainty documents.

There are no edits to the existing solver, marker values, model asset, uncertainty
exporter or their default behavior. No new interactive Blender operator is added.
The module can be imported inside Blender without SciPy or network use.

## Mathematical and scientific choices

The manifest explicitly selects target coverage, metric, pooled-vertex weighting
and the empirical `higher` quantile estimator. Missing choices stay null in the
template and cannot run. No tissue SDs, anatomical thresholds or empirical errors
are supplied by the implementation. Test values are explicitly synthetic.

The fitted quantity is a multiplier defining `error_limit_mm = factor *
spread_rms_mm`. It is **not** a calibrated coordinate SD or a Gaussian confidence
interval. Covariance, bias, correspondence and posture effects are not inferred.
All reports remain labelled exploratory, with actual subject and vertex counts.

The fit requires at least two independent calibration cases as a software gate,
not as a sufficient statistical sample. Held-out cases never affect the factor.
Repeated subject/case IDs and measurement/prediction/reference hashes are refused;
CT-conditioned inputs are refused for skull-only calibration. Further evaluations
must preserve the protocol hash and use subjects independent of training.
The operator must keep validation data out of protocol/ROI/hyperparameter choices.

## Verification executed on 2026-11-02

| Check | Before | After |
|---|---|---|
| Pytest with official GNM model | 535 passed, 1 Windows-only skip | 578 passed, 1 Windows-only skip |
| Actual Blender 4.5.0 Linux ZIP/model/external-Python integration | Pass | Pass, including BLENDER_CALIBRATION_NUMPY_PASS |
| Ruff including scripts and whitespace/diff check | — | Pass |
| Wheel and sdist build | — | Pass |
| Source CLI, checkout wrapper, installed wheel outside checkout | — | Byte-identical synthetic calibration reports |

Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, trimesh 5.2.0, pytest 9.2.0;
Linux x86_64. No Windows or interactive checks were executed locally. PR CI
provides subsequent platform evidence; successful local tests are not scientific
validation or a guarantee for every platform.

Synthetic CLI example inputs: training errors `[1,2]` and `[3,4]` mm, each spread
1 mm; test errors `[5,6]` mm with spread 1 mm. Explicit target coverage is 0.75.
The higher quantile of `[1,2,3,4]` is 4, so factor=4. Training coverage rises from
1/4 to 4/4. Held-out coverage remains 0/2. The negative held-out result is retained;
it does not trigger refitting or removal of observations. These are software
fixtures, not measured craniofacial performance.

Additional tests cover zero spread, positive errors that cannot be repaired by a
finite multiplier, exact inclusive boundary, differing case sizes, regional N,
missing/invalid configuration, malformed CSV, nonfinite/negative values, duplicate
subjects and provenance, frozen-protocol mismatch, deterministic reports, source
hash changes and refusal to overwrite inputs or existing outputs.

## Deviations, pending work and limitations

- The original request for a "95% interval" requires a definition of the error
  variable and sampling/coverage model. No Gaussian factor such as 1.96 is
  silently assigned to radial RMS spread. This implementation exposes a declared
  empirical metric and target as configuration instead.
- Applying the multiplier is explicit in a separate error-limit evaluation report.
  The original raw spread PLY/SD values are preserved; no export is relabelled
  "calibrated" merely because a factor was fitted.
- Actual CT calibration/held-out validation and the >=2 real-case acceptance
  requirement remain the operator's responsibility. Only synthetic end-to-end
  cases were executed here. There is no populated validation domain.
- The estimator pools vertices. Reports also show equal-case coverage and actual
  regional subject counts. Spatial dependence and sampling density are not
  corrected by treating vertices as independent observations.
- Model/settings/ROI/reference/ensemble hashes are declared metadata; the manifest,
  CSV and calibration input bytes are verified. The tool does not load those
  geometric assets or infer/verify correspondence. It cannot detect renamed
  aliases for the same person or concealed use of CT-face information.
- Scope is the A2.2 statistical ensemble mean. Calibration of live-only fits,
  dense/TPS surfaces or the separate A2.3 conditional Gaussian diagnostic requires
  its own explicit protocol and implementation.
- No universal sufficient-N cutoff, population coverage guarantee or confidence
  interval is claimed. Cohort design and anatomical applicability remain open.

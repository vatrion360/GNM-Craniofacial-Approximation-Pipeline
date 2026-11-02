# A2.3 execution report — conditional linear covariance

## Status and scope

Implemented locally on `feature/linear-covariance-check`, based on A2.2 commit
`782450d9b5afcaea20d8d66f389157ab4c4ae95a`. This report records the **newly
executed 2026-11-02 verification**, after the prior transient workspace was lost.
It does not reuse the previous unarchived implementation's test results.

At initial local verification, GitHub publication was pending: the first create-tree
request was not executed because automatic approval review reached its usage limit.
Publication and subsequent CI status are tracked in GitHub. No merge is performed
by this task.

The standalone diagnostic conditions on a fixed pose and explicit SPD noise/prior
covariances. It separates Gaussian posterior covariance from repeated-data MAP
variation, propagates each to world-mm vertex SD and cross-checks independent
augmented least-squares simulations. Existing fit defaults and paths are unchanged.

## Files

- `cranio/linear_uncertainty.py`: NumPy numerical core and standalone CLI.
- `tests/test_linear_uncertainty.py`: hand calculations, correlated covariance,
  ridge parity, independent MC, world transforms, invalid inputs, deterministic
  CLI and publication safeguards.
- `tools/blender_uncertainty_checks.py`: packaged NumPy diagnostic smoke checks.
- `docs/LINEAR_UNCERTAINTY.md`: formulas, input schema, options and exclusions.
- `README.md`, `docs/UNCERTAINTY.md`, `docs/UNCERTAINTY_EXPORTS.md`: discovery and scope.
- This report. No model, fit solver, CSV reader or default option is changed.

## Executed checks

| Check | Before | After |
|---|---|---|
| Pytest with official GNM model | 501 passed, 1 Windows-only skip | 535 passed, 1 Windows-only skip |
| New focused suite | Not present | 34 passed |
| Actual Blender 4.5.0 Linux ZIP/model/external-Python smoke | Pass | Pass, including `BLENDER_LINEAR_COVARIANCE_PASS` |
| Ruff and whitespace/diff validation | — | Pass |
| Wheel and sdist build | — | Pass |
| Installed-wheel CLI outside checkout | — | Same official-model report bytes as source run |

The first baseline without the official model had 498 passed and 4 skips; it was
rerun with the downloaded, hash-verified model before source edits. Blender's
archive was checked against its official checksum manifest. No Windows execution
or interactive UI testing was performed in this environment. There is no new UI.
No independent CT or anthropological validation was performed.

Execution environment: Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, trimesh 5.2.0,
pytest 9.2.0; Linux x86_64, 9 logical CPUs. Timings are environment-specific.

Model SHA-256:
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
The model was obtained from Google GNM commit
`915aa356c6a2247083e69a06e40dfe909d42435a` and was not modified.

## Reproducible synthetic evidence

The low-dimensional check uses:

```
A = [[1,2,0], [0,1,1], [2,0,-0.5], [1,-1,1]]
y = [1,2,3,4]; C = 2 I_4; m = [0,0.5,0]; P = diag(2,3,4)
N = 50000; PCG64 seed = 17
J = default_rng(33).normal(size=(20,3,3))
```

Relative covariance error is `||Q_MC-Q||_F / ||Q||_F`; vertex SD error uses the
same Frobenius ratio on the (vertices,3) coordinate SD arrays. Mean error is the
Euclidean norm of empirical mean minus analytic mean.

| Quantity | Posterior | Repeated-data estimator |
|---|---:|---:|
| Relative covariance error | 0.0071416531 | 0.0106295107 |
| Mean error norm | 0.0044903629 | 0.0042630861 |
| Relative vertex SD error | 0.0026366471 | 0.0042317205 |

The unit test's 0.03 relative-error limit is an engineering tolerance for this
seeded synthetic experiment only. It is not an anatomical threshold.

The real-model *software integration* uses the repository's 48 synthetic mean
markers, all 253 identity components and 17,821 vertices. Pose is identity,
coordinate noise SD is explicitly synthetic 0.2 mm, coefficient prior mean zero
and SD one. These values are test inputs, not recommended human error estimates.
At 5,000 draws, seed 17, the diagnostic took approximately **3.34 s**, with
`OPENBLAS_NUM_THREADS=1`; augmented condition number was 116.02335.

| Quantity | Posterior | Repeated-data estimator |
|---|---:|---:|
| Relative covariance error | 0.1960222578 | 0.1050168001 |
| Relative vertex SD error | 0.0094080140 | 0.0089136496 |

**Limitation:** the full 253-dimensional covariance comparison does not meet the
low-dimensional 3% test tolerance at 5,000 draws. This finite-sample discrepancy
is reported, not hidden by substituting a vertex SD score or declaring a universal
pass. There is no production pass/fail threshold. No inference about CT accuracy
follows from these numerical comparisons.

## Deviations and open work

- A2.3 is a conditional Gaussian diagnostic, not a posterior covariance asserted
  for the alternating robust/clipped A2.1 solver. The two methods have different
  assumptions; documentation makes the distinction explicit.
- Singular observation covariance is unsupported; no arbitrary jitter is added.
- Placement error, pose variability, lambda selection, model bias, dense/TPS
  correction and correspondence error are not calibrated by this task.
- No claim of calibrated 95% coverage, anatomical plausibility or scientific
  validity is made. A2.4 and case-level CT checks remain operator work.
- GitHub CI had not run at the time of local verification. Consult the PR checks
  for subsequent results. Local Linux verification is not a cross-platform certification.
- Default numeric code was not edited. Existing tests passed; this task did not
  repeat a case-level baseline mesh-hash study.

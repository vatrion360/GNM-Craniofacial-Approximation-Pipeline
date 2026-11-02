# A2.3: conditional linear covariance cross-check

This is an **opt-in numerical diagnostic**, not a calibrated facial accuracy
estimate. It does not change the existing fit, the A2.1 perturbation engine or
A2.2 mesh exports. It requires a fixed pose and explicitly supplied observation
and coefficient-prior covariances. Missing noise scales are not guessed.

## Statistical contract

At a fixed world-mm similarity transform, the selected landmark coordinates obey

```
y = A beta + epsilon, epsilon ~ N(0, C), beta ~ N(m, P)
S = inverse(A.T inverse(C) A + inverse(P))
mean = S (A.T inverse(C) y + inverse(P) m)
K = S A.T inverse(C)
```

`y` is the skin target minus the posed mean model; rows of `A` are the posed
identity basis in landmark-major x/y/z order. `C` has world-mm squared units;
`P` is in squared coefficient units. Both must be finite, symmetric and strictly
positive definite. Full correlated matrices are supported. A singular depth-only
error model is refused; no arbitrary jitter supplies missing tangential error.

Two different covariances are reported:

- **Posterior:** `S`, conditioned on the supplied model, pose, data covariance and
  prior. Unobserved coefficient directions can retain prior variance.
- **Estimator:** `K C K.T`, the variation of the MAP estimate when new data noise
  is added with the prior and pose fixed. This is generally smaller than `S` and
  may be singular. It is not an alternative name for posterior covariance.

The formulas above are definitions, not the numerical implementation. The code
Cholesky-whitens the observation and prior systems, then solves the augmented
system with SVD. It rejects numerical rank loss instead of silently truncating
components. It does not form or invert normal equations. Numerical symmetry and
rank tolerances derive from machine precision. The rotation tolerance `1e-10`
and vertex processing block size 256 are engineering choices, not anatomical
thresholds.

The world-frame vertex Jacobian is `J_v = scale * rotation * B_v`. For either
coefficient covariance `Q`, coordinate SDs are
`sqrt(diag(J_v Q J_v.T))`, and `spread_rms_mm` is
`sqrt(trace(J_v Q J_v.T))`. The latter is an RMS Euclidean displacement about the
mean under this model, not an SD bound or a 95% interval. Every model vertex is
reported, including internal eye/teeth geometry; no facial region is inferred.

## Independent Monte Carlo check

Let `M` and `b` be the whitened augmented design and target. Each posterior draw
solves `lstsq(M, b + z)`, where every entry of `z` is independently standard
normal. Perturbing both data and prior targets gives covariance `S` algebraically.
The estimator check sets the prior-target perturbations to zero before solving;
its covariance is `K C K.T`. The same data noise is paired across the checks.
Neither uses the computed covariance factor to generate the test samples.

A local PCG64 generator preserves global random state. Empirical covariance uses
`ddof=1`. Reports include the relative Frobenius covariance error, mean error
norm, and relative error of the propagated coordinate SD field. A zero reference
norm produces zero if the difference is zero, otherwise null (undefined relative
error). No universal acceptance tolerance or anatomical calibration is inferred.
Finite-sample full-matrix error depends on dimensionality and the number of draws.

This check is not a direct validation of A2.1: A2.1 refits pose, includes robust
weighting and coefficient clipping, and can perturb depths with truncated normal
draws. These are different statistical models. It also does not compare or mix
demographic prior scenarios.

## CLI and required assumptions

```
python -m cranio.linear_uncertainty --input markers.csv --npz models/gnm_head.npz --assumptions assumptions.json --output outputs/linear_check.json
```

| Option | Default | Meaning |
|---|---|---|
| `--input`, `--npz`, `--assumptions` | Required | Case CSV, unchanged model, explicit assumptions JSON |
| `--output` | Required/new | JSON record; existing files and input aliases refused |
| `--draws` | 10000 | Number of MC draws, integer at least 2 |
| `--seed` | 0 | Nonnegative PCG64 seed |
| `--identity-subspace` | `all` | `head` requires the verified named GNM component contract |

The JSON contains exactly these top-level fields:

| Field | Required value/shape |
|---|---|
| `schema_version` | Integer 1 |
| `model_sha256` | Actual SHA-256 of the supplied NPZ |
| `units`, `coordinate_space` | `mm`, `world` |
| `source` | Nonblank documented origin and justification of assumptions |
| `labels` | Included CSV labels in exact order |
| `pose` | `scale` positive scalar, `rotation` proper 3x3 matrix, `translation_mm` length 3 |
| `observation_covariance` | Exactly `sd_mm` with 3L positive entries, or `matrix_mm2` with shape (3L,3L) |
| `prior_mean` | Length p vector in the selected component order |
| `prior_covariance` | Exactly `sd` with p positive entries, or `matrix` with shape (p,p) |

Here L is the included landmark count and p the active identity component count.
Inactive components are fixed at zero, not at another unrecorded prior mean.
No populated scientific template is bundled: a supplied SD must represent a
justified assumption or measured error, and must be labelled accordingly.
CSV weights are retained for traceability but are **not** interpreted as error
covariance. Mapping review and anatomical applicability remain operator duties.
Duplicate vertex indices, invalid pose, NaN/Inf, inconsistent model hashes,
unknown assumptions fields and changed inputs during analysis are refused.

Output contains the conditional mean coefficients, both coefficient covariance
matrices, per-vertex coordinate SD and RMS spread, empirical MC summaries, full
assumptions, CSV metadata/exclusions, input hashes, implementation hash, software
versions and warnings. Timestamps are omitted. JSON is written through a temporary
file; previous files are not intentionally replaced. Repeated runs in the same
environment with identical paths/inputs/settings are byte-identical. Floating-point
results need not be byte-identical across BLAS implementations or platforms.

## Relation to ridge fitting

For the *fixed, unclipped* objective in model millimetres,
`sum_i w_i ||residual_i||^2 + lambda ||beta||^2`, an explicitly chosen residual
scale `tau` gives equivalent means with world covariance
`C = diag(scale^2 * tau^2 / repeat(w,3))` and
`P = (tau^2/lambda) I`, `m=0`. With the diagonal demographic penalty, the analogous
prior variance is `tau^2 * prior_scale_i^2 / (lambda * prior_weight)`.
Positive lambda and positive variances are required. The solver weights and
lambda alone do not determine `tau`; the program does not infer it.
The tests check equivalence of the fixed ridge means, not equivalence of all
stages of `fit_identity`.

## Scope and pending validation

There is no uncertainty for pose estimation, landmark correspondence errors,
model inadequacy, Huber/IRLS selection, lambda selection, ±3-sigma clipping,
profile/dense constraints, local TPS or tissue-table applicability. These omissions
can dominate the real error. Unconstrained Gaussian coefficient draws are not
anatomically approved face variants. The module does not export such meshes.

A2.4 calibration on independent CT cases remains separate and is to be performed
by the project operator. Neither this diagnostic nor its synthetic tests establish
coverage or facial identification performance. See [execution report](TASK_A2_3.md).

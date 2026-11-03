# A4.4 — Reviewed segmented sagittal profile refinement

Base: `a5f29017e6867b360c2965ebc853cdfba0feb14c` (merged A4.3 / PR #27).
Branch: `feature/reviewed-profile-constraint`. This task does not change a default
fit option or scientific constant. No CT case was assessed.

## Files and behavior

- `cranio/profile.py`: blank manifest, explicit evidence/topology/plane checks,
  fixed-pose active-identity ridge increment and three acceptance gates. Segments
  permit documented missing intervals without automatic completion.
- `cranio/config.py`, `gnm_reconstruct.py`, `cranio/pipeline.py`: optional manifest
  path, input/output collision and hash protection, preflight, shared refinement,
  final geometry/metrics and complete record. Incompatible stages fail explicitly.
- `cranio/report.py`: per-point baseline/candidate/final mm residuals; baseline
  shared-solver diagnostics clearly distinguished from final coefficients.
- `cranio/protocol.py`: no freezing a profile-refined run until a profile-specific
  cross-case protocol policy is implemented; no silently incomplete freeze.
- `addon_v13.py`: off-by-default checkbox/path, early combination checks,
  immutable-per-run manifest copy and shared external CLI invocation.
- `tests/test_profile.py`: 51 synthetic checks, including hand-computed ridge,
  world transforms, active subspace, clipping, missing evidence, rank deficiency,
  non-worsening guards, gaps, CLI/config/report/replay and disabled-path parity.
- `tools/blender_profile_checks.py`, `tools/blender_smoke.py`: real Blender
  registration, default controls, incompatible modes, official-model external
  refinement, manifest copy and mesh import. Constraints are synthetic.
- README options and `SAGITTAL_PROFILE.md`: equations, units, evidence requirements,
  limitations, supported combinations and operator workflow.

## Executed checks (2026-11-03)

| Gate | Baseline | Changed code |
|---|---|---|
| Python suite, official model enabled | 656 passed, 1 Windows-only skip | 707 passed, 1 Windows-only skip |
| Blender 4.5.0 Linux, installed ZIP + official model + external Python | Pass | Pass, including PROFILE_OPTIONS and PROFILE_EXTERNAL |
| Ruff / whitespace | — | Pass |
| Wheel, sdist, addon ZIP | — | Built successfully |
| Wheel installed outside checkout | — | Profile template CLI and argument parsing pass |
| Profile disabled, historical baseline replay | — | OBJ/PLY byte-identical in statistical and local-correction modes |

Environment: Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, pytest 9.2.0,
Linux x86_64. Model SHA-256:
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
Blender archive verified against the official checksum manifest. Model unchanged.
Windows and interactive visual assessment were not executed locally; hosted CI
is separate. No inference about CT accuracy follows from these tests.

Historical replay used a detached checkout at the base above, the same official
model and 48 artificial targets. NumPy `default_rng(44)` generated 253 identity
coefficients from `normal(0, .03)`, followed in the backend mapping's insertion
order by 3-D `normal(0, .1)` noise added to each generated landmark. These are
engineering perturbations, not scientific error/depth values. Both CLI trees ran
with fixed lambda 30 and `OPENBLAS_NUM_THREADS=1`, with profile absent, first
without and then with `--local-correction`. Final/statistical OBJ and displacement
PLY hashes, transform, coefficients, lambda and metric dictionaries matched
exactly. Small derived evidence: `PROFILE_DEFAULT_BENCHMARK.json`. No model mesh
or scan is included in that file.

## Deviations, limits and remaining inputs

This is a conservative first A4.4 implementation, not full anatomical automation.
The requested ordered median path is supplied and reviewed by the operator;
self-mirror indices/mesh edges validate topology only. Automatic extraction and
bone sampling were not added without verified correspondences. Missing intervals
are explicit segments; missing complete-profile endpoints or mandible prevent
use. Positive source-backed SDs are required; legacy means without SDs do not
become calibrated constraints. Sources/directions must be independently reviewed.

Instead of modifying the baseline nonlinear alternating optimizer, an explicit
fixed-pose identity increment is fitted and tested against baseline per point.
This avoids altering existing fitting behavior and exposes tradeoffs in the
record. SDs weight the objective; they are not confidence bands. Incompatible
losses/TPS are refused, not discarded. Live preview is unchanged; final refinement
is available through Blender's existing offline fit/import route. Other regions
can change and need full-face review; no joint-optimality or non-penetration claim.

Operator-supplied inputs still needed: a reviewed anatomical segmented path,
case bone samples/normals and source hashes, applicable depth SDs, midsagittal
plane/tolerance, regularization/strength and marker displacement policy. CT
comparisons, parameter selection on development cases and held-out validation
remain with the user. Frozen profile protocols and profile-aware uncertainty
propagation require a later increment; they are not claimed complete here.

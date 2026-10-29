# Identity fitting: all components or head only

This opt-in feature restricts which identity coefficients the statistical fit
may adjust. It does not establish an anatomical improvement or freeze a region
of the mesh in world space. Default `all` retains the previous numerical path.

## Controls

| Interface | Setting | Default |
| --- | --- | --- |
| Offline reconstruction | `--identity-subspace all\|head` | `all` |
| Blender live panel | **Identity fit → Head only** | All components (legacy) |
| Blender Run Offline Fit and Import | Uses the same Identity fit selection | `all` |
| Independent marker holdout | `python -m cranio.evaluation --identity-subspace head ...` | `all` |

Example:

```bash
python gnm_reconstruct.py --input markers.csv --npz models/gnm_head.npz --output outputs/head/face.obj --identity-subspace head
```

The selector persists in `.blend`. CSV metadata records the requested selection;
the CLI's explicit setting controls a run and is recorded in its config. CSV
coordinates do not change when a fitting subspace is selected. Switching the
Blender selector schedules a refit through the existing debounce mechanism.

## Component identification and inactive policy

The reviewed official v3 archive contains these `identity_names`:

| Group | Names | Official array indices | Head-only action |
| --- | --- | --- | --- |
| Head | `head_000` … `head_169` | 0–169 | Fit 170 coefficients |
| Eyes | `eyes_000` … `eyes_002` | 170–172 | Exactly zero |
| Teeth | `teeth_000` … `teeth_079` | 173–252 | Exactly zero |

The loader validates optional name metadata and the selector resolves by names,
not a guessed column count. Head-only mode refuses missing/unsupported naming;
unnamed legacy/custom models remain usable in `all` mode. The GNM archive is
never changed. Its reviewed SHA-256 is
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.

Inactive policy is **zero**, including when a demographic prior is supplied.
Only the active coefficients receive that prior's corresponding means/scales.
This explicit engineering policy prevents eye/dental priors from silently
changing a skin fit. It is not an inferred dentition or eyeball measurement.

The solver operates on the selected basis using the same pose, ridge, Huber,
conditional LOO, dense and measurement machinery, then returns the full
253-component vector in original model order. It does not solve all components
and erase some afterwards. Markerless preview also clears inactive coefficients
from its correspondence warm start. Clip diagnostics count active coefficients.

Head variation and the fitted similarity transform can still move eye/dental
geometry. Optional local correction is a separate surface operation. Post-fit
presentation remains available on the separate copy and may intentionally add
eye/dental offsets after fitting; this does not change the stored neutral fit.

## Records and reproducibility

JSON `config.identity_subspace` records the selected mode.
`solver.identity_fit` records total and active counts, active indices, inactive
policy and clipped-active count. TXT diagnostics include the same summary.
The live fit stamp preserves this diagnostic block for presentation/replay.

These additive settings and changed implementation hashes require a new frozen
protocol revision. An older frozen protocol must not silently certify this code.

## Executed engineering checks

Tests cover invalid metadata/indices, full-vector replay, prior isolation,
fixed and conditional-LOO fitting, dense rows, skin-distance controls,
markerless warm starts, live/offline parity and independent marker holdout.
Actual Blender ZIP tests exercise the selector, timer, fit stamp and external
process argument/report propagation. No subject CT cases were used.

`HEAD_IDENTITY_BENCHMARK.json` records a deterministic synthetic comparison:
the 48 mapped mean landmarks in dictionary order, plus independent coordinate
perturbations from `numpy.random.default_rng(1901).normal(size=(48, 3))` mm;
weights all one, lambda 3, other solver settings unchanged, one BLAS thread.
Compare using `fit_identity`, with head indices supplied only for head mode.

Against baseline commit `0a51bd5`, default/all coefficients and vertex coordinates
were unchanged; exported OBJ hashes matched exactly. Head/all marker RMSE was
approximately 1.316196 mm in this fixture and the maximum vertex difference was
approximately 1e-12 mm. The eye/teeth coefficients were already numerically near
zero in the unrestricted skin-marker fit. Thus this scenario demonstrates the
restriction and compatibility, not better reconstruction. Both modes reached
30 iterations without meeting all convergence criteria; that negative result
is retained in the benchmark. Single timing observations are not a speed claim.

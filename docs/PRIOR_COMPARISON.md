# Experimental identity-prior comparison (A6, first increment)

The default fit already uses **no external demographic prior**. This change does
not alter that default or the shared solver. The optional audit runs the same
case twice, first without an external identity prior and then with the selected
prior file. It writes a paired record and corresponding-vertex differences.

```bash
python gnm_reconstruct.py --input markers.csv --npz models/gnm_head.npz --output outputs/case01.obj --regularization 30 --prior local_prior.npz --prior-compare --prior-justification "Operator-recorded rationale for this sensitivity scenario"
```

The example regularization is an explicit software setting, not a recommended
anatomical value. Use the case's intended settings. No demographic category,
ancestry, sex, age or suitable prior is inferred from the skull or filename.
Prior coefficients and scales are read from the supplied local archive with
`allow_pickle=False`, using the existing loader; model/coefficients are unchanged.
Legacy prior archives are not independently validated cohort distributions.

## Controls and compatibility

| Option | Default | Effect |
|---|---|---|
| `--prior FILE` | None | Existing experimental identity prior selection |
| `--prior-compare` | Off | Two independent full pipeline fits and a comparison bundle |
| `--prior-justification TEXT` | None | Required for comparison; optional audited rationale for a normal prior-enabled run |
| `--prior-weight` | Existing 1.0 | Existing prior precision multiplier, recorded without reinterpretation |
| `--identity-subspace` | Existing `all` | Existing full/head-only policy; inactive coefficients stay zero in head mode |
| `--output PREFIX.obj` | Existing input-based prefix | Comparison writes `<PREFIX>_prior_compare/`, not the prefix OBJ itself |
| `--overwrite` | Existing off | Does not permit reuse of a comparison directory |

A justification must be nonempty documented text, not an unknown/TODO placeholder.
It is recorded verbatim; this is operator provenance, not evidence of biological
applicability. Supplying a reason without a prior is an error. The reason is case
metadata rather than a frozen numerical setting; prior weight and other numerical
settings remain part of protocol settings.

For compatibility, standalone `--prior` and ordinary Blender prior fits still
work without a rationale when its field is empty. The separate Blender paired
comparison requires one. Mandatory justification for older live/ordinary flows
would be a separate compatibility change.
The numerical default is unchanged; JSON configuration records now include the
two new fields. Timestamped/provenance reports are not promised byte-identical.

Comparison owns its child output paths: do not combine it with `--output-json`,
`--output-stats`, `--output-error-mesh` or `--output-statistical`. It rejects frozen
protocols, profile refinement, nested tissue comparisons and automatic outlier
exclusion. Explicit exclusions and a single tissue-table scenario may be shared
by both runs. Enabled dense constraints and local correction retain the existing
pipeline behavior and checks. No QC requirement is skipped.

## Bundle contents

| Path | Meaning |
|---|---|
| `neutral/face.obj` and normal pipeline outputs | No external identity prior; existing regularization remains active |
| `prior/face.obj` and normal pipeline outputs | Selected prior, same original case inputs and settings |
| `difference_statistical.ply` | Corresponding-vertex differences before local correction |
| `difference_final.ply` | Corresponding-vertex differences after the enabled processing stages |
| `comparison.txt` | Rationale, convergence, lambda and difference summary |
| `summary.json` | Completion marker, input/child-report hashes, prior values, scenario diagnostics and difference metrics |

The prior-enabled child also stores the rationale in its ordinary JSON config and
TXT report. Summary metadata includes prior mean/scale, weight, reported sample
count (null if absent), active components and inactive policy. Array dimensions
are checked, but the code cannot infer the model/component-order provenance of
an otherwise compatible legacy archive. Verify this externally.

The original marker/model/prior files are never rewritten. Inputs are hashed
before fitting and checked across both runs. Completed child files are checked
against their run reports. The compared marker labels, vertices, targets and
weights must agree. A failure/nonzero child exit produces no completed summary;
any partial outputs remain diagnostic material in the new directory. Exit 3 from
required QC is preserved. Use another output prefix after a failed attempt.

If both child processes finish but either solver did not converge, the summary
is explicitly `diagnostic_only_nonconverged`. Numeric differences are retained for
inspection but are not a stable sensitivity estimate. Converged runs still carry
their QC findings, warnings, clipping information and residuals; convergence alone
does not establish anatomical correctness.

## Definitions and interpretation

Let `v0[i]` be vertex `i` in the no-prior output and `v1[i]` the same indexed vertex
in the prior output. All coordinates are world millimetres. The stored distance is

```text
d[i] = ||v1[i] - v0[i]||_2
RMS = sqrt(sum(d[i]^2) / N)
```

Distances use the actual six-decimal OBJ coordinates. There is no ICP or post-hoc
alignment, and the vertices are compared by native model index, not by nearest
surface point. Each PLY uses the prior-run surface and stores `vertex_difference_mm`.
Both PLYs share the maximum difference as their colour scale; a zero maximum is
valid when both outputs agree. The summary reports all-vertex metrics and separate
`skin_exterior` metrics when that model group is present; otherwise skin metrics
are null. All-vertex values include internal teeth/eye geometry.

Each scenario refits independently from the original targets. Pose, global scale,
conditional LOO lambda, dense correspondences and local correction can therefore
change. These are effects of the configured prior workflow, not isolated
fixed-pose coefficient displacement. Both actual lambdas and transforms are
recorded. Identical seeds do not remove genuine pose/correspondence differences.

The comparison measures **sensitivity to an experimental prior**. It does not
identify which face is more accurate, estimate uncertainty, validate a population
assignment or supply an age model. GNM's neutral/zero-centred regularization is
still a model assumption; “neutral” does not mean a face without statistical bias.

## Remaining A6 work

Structured age-at-death metadata and descriptive range comparisons are available
in the [age audit](AGE_CONTEXT.md). No tissue depth is changed based on age.
Automatic table selection is not implemented. A dedicated Blender comparison
control is available below; mandatory rationale for legacy live/ordinary prior
fits and complete A7 record integration remain separate work. CT validation remains with
the user. Tests use synthetic targets/priors and the official model topology;
they do not constitute a demographic or subject-level validation study.

## Blender paired comparison

Use the existing experimental prior selectors and local **Priors Folder**. These
labels are inherited GNM categories, not demographic estimates derived from the
case. Archives are not included in the addon ZIP; supply and review a local prior.
No generation, download, TensorFlow or network call is introduced in Blender.

In **Offline fit (external Python)**:

1. Configure the Python interpreter, case directory and the intended offline fit
   options, as for an ordinary offline run.
2. Enter **Prior rationale**, describing why this sensitivity scenario is being
   examined. Empty/placeholder text cannot start a comparison.
3. Click **Compare Neutral / Selected Prior**. This is a distinct action; the
   ordinary fit button retains its previous default mode.

| Control | Default | Behavior |
|---|---|---|
| Prior rationale | Empty | Required for paired comparison; optional for an ordinary prior-enabled run; stored verbatim |
| Compare Neutral / Selected Prior | Explicit click only | Run the existing CLI `--prior-compare` workflow in the external process |
| Run Offline Fit and Import | Existing ordinary fit | One fit; carries a supplied rationale when a prior is selected |
| Cancel Offline Fit | Existing control | Cancel either mode; retain diagnostic partial files without importing incomplete results |

Comparison uses the offline button's settings: included markers, regularization,
identity subspace, clip, measurement weight and explicitly enabled dense/local
correction options. It does not clone the last preview or transfer every preview
control. Profile refinement remains incompatible. No existing validation is
skipped. A selected prior that cannot be loaded blocks the run; a copied prior
whose hash changed during export also blocks launch.

Every invocation receives a fresh case directory. Within it, `face_prior_compare/`
has the bundle layout above. The selected prior is copied beside the exported
markers for replay; the original prior/model are never modified. The rationale
is captured before launch and cannot be changed in an already running process.
Editing the rationale does not request a live refit or move any target. If running
a neutral-only fit, clear a previous rationale: intent without a selected prior
is rejected rather than silently discarded.

After a successful process, Blender checks the completion record, both child
reports and all expected artifact hashes using fixed paths. It checks triangle
indices, finite vertices, matching topology and consistent convergence status.
It reads only the pipeline's triangle OBJ dialect, without axis/unit conversion.
No Blender objects are created until the full bundle passes these checks. Object
creation is rolled back if an import step fails. A nonzero process exit or missing
summary never imports a single successful child as a completed comparison.

Two new objects are imported; existing live/offline faces remain unchanged:

- `GNM_Audit_<run>_prior`: shown initially.
- `GNM_Audit_<run>_neutral`: hidden in viewport and render initially, to avoid
  overlapping surfaces. Toggle visibility in the Outliner to compare them.

Each object records its scenario, child report path, comparison summary path and
convergence status. The difference PLY files remain available in the output
folder; this increment does not automatically load their colours into Blender.
The status explicitly says sensitivity, not accuracy. A nonconverged pair is
labelled `diagnostic_only_nonconverged` even though its completed diagnostic
surfaces can be inspected. Neither convergence nor file integrity validates the
prior scientifically. No automatic ranking or preferred-face claim is made.

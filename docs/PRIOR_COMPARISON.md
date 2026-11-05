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

For compatibility, the existing standalone `--prior` flow and Blender prior
selection still work without the new audit or rationale. Mandatory justification
for those older flows and a dedicated Blender comparison control remain pending.
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
Automatic table selection is not implemented. Blender prior controls/justification migration and
complete A7 record integration also remain pending. CT validation remains with
the user. Tests use synthetic targets/priors and the official model topology;
they do not constitute a demographic or subject-level validation study.

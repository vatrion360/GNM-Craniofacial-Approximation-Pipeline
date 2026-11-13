# A5.1 — explicit saved-report checks

This opt-in increment introduces a shared `pass | warn | block | not_assessed`
contract for a **saved offline fit**. It does not fit a face, re-open original
scans, alter markers, or authorize scientific export. Current scene edits are
not part of the saved report. CT validation remains manual.

## Workflow

```bash
python -m cranio.check_policy template --output check-policy.json
# Supply and review the policy; the template contains no anatomical values.
python -m cranio.check_policy assess --report face_report.json --policy check-policy.json --output checks.json
python -m cranio.record build --report face_report.json --check-policy check-policy.json --output-dir record
```

The assessment command writes deterministic JSON before returning **3** when
checks are held (`block` or `not_assessed`), **0** when the configured gate permits
continuation, and **2** for invalid input or I/O failure. `--allow-blocked "reason"`
records an explicit exception and returns 0 while preserving every finding and
the original aggregate status. It is not scientific approval. Existing outputs
are refused; sources and destination are rechecked before atomic publication.
The result contains the source report, policy and implementation SHA-256 hashes.
No paths embedded inside the report select additional files to open.

For the derived approximation record, optional `--check-policy FILE` and
`--check-override "reason"` embed the assessment, policy hash and exception. A
blocked/incomplete assessment yields `diagnostic_only`, even with an override.
The record command still exports diagnostics and returns 0 on successful record
creation; its return code is **not** the standalone assessment's gate decision.
Original fitting commands, their exit codes, outputs and defaults are unchanged.

In Blender, use **Approximation Record (saved fit)** → **Check policy (optional)**
and, if appropriate, **Check override reason (optional)**. Computation runs in
the existing external Python process. The resulting status and text block show
`CHECK POLICY: ...`. Redraw performs no fitting or mesh hashing. With the fields
empty, existing record output is unchanged.

## Policy schema

The closed top-level schema contains `schema_version: 1`, `id`, `revision`,
`reviewed` and `rules`. The blank template has null identifiers, false review and
an empty list. Reviewed policies require supplied non-placeholder identifiers.
Every rule requires a distinct `id`, a `kind`, a documented `source`, and explicit
`on_fail: "warn"` or `"block"`. No threshold is inferred from a cited title.

| Kind | Additional fields | Observation and limits |
|---|---|---|
| `bone_range` | `measurement`, `minimum_mm`, `maximum_mm` | Canonical Table 3 chord key; positive inclusive bounds in world mm. Recomputed from embedded observed, definition-reviewed, source-current endpoints. Missing/reconstructed endpoints are not assessed. |
| `marker_count` | `region`, `labels`, `minimum` | Explicit distinct label list and integer minimum, from 1 to its length. Counts fitted labels with positive base weights; no automatic anatomical region assignment. |
| `midline_rms` | `maximum_mm` | Nonnegative maximum plane residual. Requires a current A4.2 snapshot with matching observation/configuration signature; recomputes geometry from embedded bone positions. |

Unknown fields/kinds, invalid booleans/numbers, duplicate IDs/labels, reversed
ranges and undocumented sources are rejected. Labels are literal and
case-sensitive. An absent label counts as absent; no alias or mirrored substitute
is guessed. A reconstructed left mandibular fragment cannot supply a missing
left cranial endpoint. An absolute chord outside a supplied interval may reflect
morphology, placement or units; it does **not** diagnose a scale mistake.

A marker count does not measure independent information, regional coverage or
placement correctness. Multiple labels may refer to dependent constraints. The
midline RMS describes agreement among selected references, **not anatomical
confidence**, and it does not replace calibrated placement-error analysis. Frame
geometry is recomputed without rerunning the optional Monte Carlo engine.
Snapshot source hashes establish internal consistency only, not current scan
freshness or authenticity.

## Built-in diagnostics and aggregation

- **Convergence:** records the existing statistical solver boolean; failure is
  `block`. For profile refinement this remains explicitly the baseline solver.
- **Proper transform:** finite positive scale and proper orthonormal rotation.
  Reflection/nonorthogonality is `block`. The orthogonality tolerance is 64
  float64 machine epsilons, a numerical test rather than an anatomical threshold.
  Scale plausibility is not inferred from this test.
- **Side labels:** reuses the existing GNM model-space 5 mm heuristic
  (`provenance: legacy_hardcoded`), with stable inverse-transform normalization.
  Suspect labels are `block`; no lateral labels means `not_assessed`. A pass
  cannot certify all possible swaps, correspondence mistakes or reflections.
- **Recorded geometry QC:** existing degeneration, normal reversal, new contact
  or negative local clearance findings are `block`. Basic-only success is
  `warn`; absent/incomplete contact or bone-clearance data are `not_assessed`.
  Full success retains the original restricted scope: sampled local clearance,
  excluded adjacent triangles and baseline contacts. It is not a watertight
  containment certificate. Existing geometric thresholds remain legacy values.

The aggregate precedence is `block`, then `not_assessed`, then `warn`, then
`pass`. Each rule remains visible. Missing configuration for any of bone ranges,
regional counts or midline residual produces its own `not_assessed` row, so a
partially configured policy never produces an overall green result. Unreviewed
policies are retained but not applied. No threshold is supplied by the software.

`gate.proceed` is a workflow decision for callers of this API. An override never
changes the checks, hides warnings or sets scientific authorization. A policy
pass is not independent validation. A7.2 domain matching is a separate check;
this increment does not implicitly combine it with the gate.

## Scope remaining

A5 is **not complete**: the ordinary CLI and Blender mesh exports are not yet
controlled by this policy. A7.3 must wire the gate to explicit scientific versus
illustrative export operations and preserve diagnostic outputs. These policies
also do not supply population ranges, minimum-marker recommendations, automatic
anatomical inference, calibrated midsagittal confidence, or live-scene checks.

Software tests use synthetic values explicitly labelled as such; no CT results
are shipped or inferred. See [task evidence](TASK_A5_1.md).

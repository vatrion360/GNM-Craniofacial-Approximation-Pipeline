# B1.2 — Shared preparation of local correction

`cranio.local_correction.prepare_local_correction` now prepares the same centres,
prescribed vectors, regional caps and protection indices for either numerical
backend. The offline pipeline uses it whenever `--local-correction` is enabled.
The stage is still off by default; SciPy remains its default solver.

This increment removes the offline-only centre assembly. It does **not** add a
Blender Finalize button. The shared preparation and NumPy application are tested
inside the installed Blender ZIP; scene transactions, source freshness and the
Finalize UI remain a separate increment.

## API and responsibilities

```python
from cranio.local_correction import prepare_local_correction

plan = prepare_local_correction(
    vertices=statistical_vertices_mm,
    marker_indices=included_marker_vertex_ids,
    targets=included_skin_targets_mm,
    confidence=original_confidence_multipliers,
    scalp_indices=scalp_vertex_ids,
    protected_indices=protected_vertex_ids,
    face_cap_mm=config.face_cap_mm,
    scalp_cap_mm=config.max_correction_mm,
    protect_damping=config.protect_damping,
    seed=config.seed,
    scalp_centres=config.tps_scalp_centres,
    face_centres=config.tps_face_centres,
    dense_indices=accepted_dense_vertex_ids,
    dense_targets=accepted_dense_targets_mm,
    dense_regions=accepted_dense_region_names,
)
final_mm, displacement_mm, prescribed_magnitudes_mm = plan.apply(backend="numpy")
selection_record = plan.record()
```

All inputs must use the **same world-mm frame**. No conversion or alignment is
inferred. Omit all three `dense_*` arguments for marker-only correction; an empty
accepted dense set is also allowed. Markerless preparation is possible only when
the supplied dense rows provide enough distinct, full-rank centres. This does not
change the offline pipeline's minimum-marker requirements.

| Input / action | Requirement / behavior |
|---|---|
| Marker indices, targets, confidence | Only included fit rows, in matching order; no excluded/reference-only landmarks |
| `confidence` | Original nonnegative displacement multipliers; not SD precision or final IRLS weights; no normalization |
| Dense indices, targets, regions | Already accepted correspondences; provided together, no skull query or inferred missing regions |
| Scalp/protected vertex indices | Distinct in-range integer IDs from the caller's model masks |
| Caps/damping | Explicit positive mm caps and damping in [0, 1]; no tissue-band values inferred |
| Seed/scalp budget/face budget | Explicit nonnegative integers; preserved RNG and sampling order |
| `plan.apply()` | Default SciPy; always applies to the captured statistical vertices |
| `plan.apply(backend="numpy")` | Explicit NumPy backend, no SciPy/trimesh/TensorFlow/bpy numerical imports |
| `plan.record()` | Detached deterministic preparation audit; does not certify anatomy or run QC |

The caller remains responsible for model/case binding, anatomical correspondence
review, source provenance, mandibular articulation and normal review. Dense
acceptance still occurs in `geometry.dense_correspondences` before preparation.
This API cannot establish whether a source is original, mirrored or a donor.

## Preserved selection and arithmetic

1. Keep supplied markers first. Their vectors are `(target - statistical vertex)
   multiplied by original confidence`, including existing fractional weights.
2. Exclude dense centres at distance **less than or equal to 3 mm** from any
   statistical marker position. Targets are not the separation reference. This
   is the existing `legacy_hardcoded` numerical heuristic, not a new anatomical
   tolerance. NumPy computes distances in query batches without a SciPy tree.
3. Sample eligible `scalp` rows first, then all other region rows, using the
   existing seeded `default_rng` sequence and separate supplied budgets. Sort
   selected row positions as before. Empty regions remain empty.
4. Dense vectors are `target - statistical vertex`, without an additional marker,
   SD or IRLS multiplier. Do not interpret the historical name `face` for the
   non-scalp bucket as automatic anatomical classification.
5. Build scalp/other caps and use the existing bounded solver, with the same
   one-time tanh limit and protected-region damping.

For valid float-valued settings, the legacy SciPy outputs are checked with exact
equality. One Python-API edge case is corrected: an integer-valued face cap no
longer creates an integer cap array that truncates a fractional scalp cap. CLI
caps were already parsed as floats. No default values change.

Malformed arrays, nonfinite values, duplicate/out-of-range vertex indices and
invalid budgets are rejected. Coincident selected centres (including different
vertex IDs at the same location), fewer than four centres and deficient 3-D
rank fail explicitly. No missing centre is invented, silently merged or jittered.
The selected backend still performs its own numerical checks.

Inputs are copied into read-only numerical snapshots. Caller mutations do not
change a prepared operation, and repeated `apply` calls do not accumulate a
second correction. These snapshots are not a substitute for Blender's pending
scene-freshness and Undo/rollback integration.

## Saved report and replay

Enabled offline runs add `marker_metadata.local_correction_preparation` to the
existing JSON report. It records ordered marker IDs/confidence, supplied dense
candidate IDs/regions, rejected-near-marker rows, selected dense rows, ordered
centre IDs/kinds/counts, seed/RNG, budgets, caps and protected indices/damping.
The existing `local_correction_centres_world_mm` and
`local_correction_prescribed_vectors_mm` remain available and unchanged.

Dense row indices refer to the **supplied accepted candidate array**, not skull
triangle IDs or raw bone sample indices. The report's configuration/input hashes
and the separately stored centre/vector arrays must accompany this selection
record. No timestamp or mutable scene handle is added to the preparation record.
Disabled runs do not create this new record. Existing geometry QC remains after
local correction and before export.

## Evidence and limits

`tests/test_local_correction.py` compares against the frozen pre-extraction
SciPy-KDTree algorithm. Tests cover marker-only and mixed/absent regions,
zero/oversized budgets, strict separation boundaries, synthetic fragment labels,
determinism, immutable snapshots, invalid inputs, pipeline routing/reporting,
and the official model with synthetic targets. Neither synthetic labels nor
these fixtures constitute incomplete-skull validation.

The installed-ZIP Blender integration compares preparation arrays/records exactly
and final NumPy/SciPy vertices at `1e-6 mm` engineering tolerance, using identical
frozen model arrays. It emits `BLENDER_LOCAL_PREPARATION_PASS`. This does not
claim equality between independently acquired Blender/offline fits or different
bone samples, precisions and settings. Actual CI outcomes are linked from the PR.

See [task evidence](TASK_B1_2.md) and [solver mathematics and limitations](NUMPY_LOCAL_SPLINE.md).
Manual CT evaluation remains separate. No new tissue values, anatomical
thresholds, runtime dependencies, model assets or performance claims are added.

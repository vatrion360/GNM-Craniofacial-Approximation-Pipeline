# Manual tissue-depth scenarios (Blender 18.1.0)

This editor applies an operator-chosen percentage to one or more current marker
depths. It does not accept BMI in kg/m², infer body mass, select a demographic
model or implement a validated relationship between BMI and regional tissue
thickness. Document why a percentage and anatomical subset were chosen.

## Workflow

1. Open **GNM Markers** and initialize or load the marker list.
2. Check the leftmost checkbox on each desired row. **Select All** and
   **Clear Selection** are available below the list. These checks are independent
   of the active row, object selection and **Include in fit**.
3. In **Manual tissue-depth adjustment**, enter **Change (%)** and select
   **Increase** or **Decrease**.
4. Click **Apply to Selected Depths**. The same list's mm values are overwritten;
   placed targets and pegs update while bone positions and current axes remain
   fixed. Unplaced rows are also editable; later placement uses the new depth.
5. Inspect the result, use Blender Undo if necessary, and save the `.blend`.
   If Live is enabled, one settled refit is requested for the batch. With Live
   disabled, the face is refreshed only when fitting is explicitly resumed.
6. Export a fresh CSV if the edited scenario will be used offline. Existing
   CSVs and running offline jobs are snapshots and are not changed retroactively.

The rule is `new_mm = current_mm × (1 ± percent / 100)`. For example, increasing
10 mm by 20% gives 12 mm; decreasing that 12 mm by 20% gives 9.6 mm, not 10 mm.
Repeated applications compound. Undo, rather than the opposite percentage,
restores the previous edit. Zero percent is a no-op. Decrease is limited to
100%; that endpoint yields zero and retains the axis for a subsequent direct
depth edit. Increasing an already zero depth leaves it zero. This mathematical
endpoint is not a recommendation for tissue thickness.

## Integrity and traceability

The complete selected batch is validated before mutation. Negative/non-finite
values, decreases above 100%, incomplete placements, non-mm placed scenes,
linked marker data and target/peg constraints, parents or animation are rejected.
An adapter failure rolls back depths, geometry and provenance. No GNM model is
required to edit marker depths. The ordinary model/export checks still apply.

Each changed marker retains its source text under `manual-percentage; base
source: ...`. Its `.blend` audit history stores UTC time, percentage, direction,
previous and resulting mm values and previous tissue source. CSV v3 metadata
exports these entries as `marker_depth_adjustments`, also for unplaced edited
rows. The existing offline report carries that metadata. Audit values record
Blender's stored float precision. Later direct depth edits or a tissue-table
reset do not erase history; history entries describe past percentage operations,
not a guarantee that the current value still equals the last entry.

Fit inclusion, weights, correspondence review, observed/reconstructed status,
vertex overrides, skull meshes and raw cranial measurements do not change.
Skin-distance controls derived from the edited targets can change on the next
fit, as they do after a direct mm edit; explicitly predicted skin distances remain
their own constraints. The offline solver and CLI have no percentage/BMI option.

## Verification

`tests/test_marker_depths.py` checks arithmetic and rejected numeric inputs.
`tools/blender_depth_checks.py`, called by the installed-ZIP smoke suite, checks
selected versus untouched rows, unplaced and excluded rows, world-space targets
and pegs, unchanged bone coordinates, batch refit coalescing, rejected edits,
rollback, zero-depth direction retention, persistence and export provenance.
Headless tests do not establish anatomical validity or interactive usability.

# Two manual placements on the same observed bone (B2.4)

Use this optional study to ask **how far apart two placements of the same bone
landmark were for this operator on this case**. It does not assess the face,
estimate error against ground truth, compare different observers, or establish
a transferable placement SD. No GNM model or CT data is required for capture.

## Blender: collect A, then B

1. Set up the marker catalogue and register the preserved bone sources in a
   metric case (scene scale 0.001). Use a stable pseudonymous case ID and
   observer ID. Save a clean copy **before placing any fit markers**. For
   comparison with a later fit, fork both files from that setup: do not import
   the meshes twice or recreate the registry. Source IDs and evaluated world
   geometry hashes, not just filenames, must agree.
2. In **GNM Scientific Markers → Manual placement repeatability (A/B)**, close
   the placement atlas and proposals. Remove visual cues left by other tools
   (including labels, a cursor left at a candidate, reference faces and
   overlays). The software cannot establish observer blinding or independence.
3. Choose **Start A**, select a label in the ordinary marker list, choose
   **Pick Selected Bone Site**, then left-click the visible bone in the same
   single 3D viewport. Esc cancels. Only a direct hit on an enabled registered
   observed bone counts. No peg, skin target, ghost or other scene object is
   created. The next unmeasured row is selected; you can change the selection.
   Use Undo to reverse a mistaken pick. Leave absent landmarks unmeasured.
4. **Finish A** freezes the measured rows. At least one measurement is needed.
   At a separately scheduled session, **Start B** and repeat without consulting
   A. The B list starts at its first label; no A coordinates or per-label A
   feedback are shown. Complete **Finish B**. Save the blend to resume between
   sessions; no mandatory delay is imposed. Record session timing and any
   visual cues in the study log. Case, observer, labels and registered sources
   must remain the same; moving a fragment invalidates the comparison.
5. **Export Repeat Placement Report** writes a new `placement_error.json`.
   Choose a new filename if one already exists. **Discard A/B Study** clears
   the scene's active study, not an exported file. Both the blend and JSON
   contain case coordinates and should be handled as case data.

The report includes the two session IDs, coordinate inputs, source hashes,
B minus A displacement vector and Euclidean distance in millimetres for each
same-source pair. The median is **across paired sites**; report the paired and
requested counts alongside it. Missing A, missing B, missing both and hits on
different fragments are distinguished. None is assigned zero error; the
summary can be empty. There is no alignment, reflection or tissue-depth
correction between the two sessions.

## Optional A2 sensitivity scenario

A2 expects the SD of **one Cartesian coordinate for a single placement**.
The repeatability report does not supply a validated SD. If an analyst elects
to assume independent, unbiased A/B errors with equal isotropic coordinate
variance, then for one site `E[||B−A||²] = 2 × 3 × σ²`. The opt-in
method uses `||B−A||/sqrt(6)` as a single-pair plug-in scale. One pair cannot
test the assumptions, quantify systematic error, or calibrate this scale. A
surface-constrained click need not have isotropic or independent errors.

```shell
python -m cranio.uncertainty --input case_markers.csv --npz models/gnm_head.npz --repeatability placement_error.json --paired-iid-isotropic-reason "REPLACE with your case-specific sensitivity rationale" --output marker_ensemble.json
```

Use a v3 CSV with the same observer, case and observed source geometry. The
reader verifies the stored summaries against the raw A/B observations and
selects labels included in this fit. Absent or unmatched pairs, coincident
repeat clicks, and proposal-assisted or non-observed sites have unknown SD.
The normal A2 missing-input policy applies: a partial scenario requires
`--allow-partial` and at least one configured error term. Compare the source
and warnings in the ensemble before interpretation. The operator's rationale
and input SHA-256 are retained. Without the explicit model and rationale,
the file is descriptive only. Existing `--placement` JSON files with documented
per-coordinate SDs remain an alternative; do not supply both inputs.

Headless Blender tests use two fresh rays on a synthetic triangle with a
known 5 mm separation, check refusal after changes to observer or pose, and
check missing sites, no fit-marker creation and safe file export. Numerical
tests cover different fragments and propagation through the A2 CLI. These are
software tests, not empirical measurements on human skulls.

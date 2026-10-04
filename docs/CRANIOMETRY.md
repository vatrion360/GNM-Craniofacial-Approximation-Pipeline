# Cranial measurements and reviewed skin-distance controls

Version: **5.0.0rc7 / add-on 18.0.1**. Interchange protocol: `table3-chords-v1`.

The catalogue follows Table 3 in the supplied article,
[DOI 10.4995/var.2024.24796](https://doi.org/10.4995/var.2024.24796), which attributes
definitions to White, Black & Folkens (2012), *Human Osteology*, third edition.
The article's numbers describe its specimen, which has intentional cranial
modification. **None is a default, population mean or fitting target.**

The full White text has not been independently verified for this implementation.
The operator must select and record the osteometric convention before casework.
[CoRA's public measurement protocol](https://docs.coracore.org/en/latest/print_cora_docs/)
was used to cross-check names and to identify convention differences below.

## Catalogue and anatomical limits

All values are **3-D straight-line endpoint distances in world millimetres**.
The operator localizes extrema, reviews the midsagittal plane and ensures that
caliper/breadth endpoints follow the chosen protocol. The software does not find
extrema on broken surfaces, enforce a caliper orientation, or infer missing bone.

| Key | Measurement | Bone endpoints |
| --- | --- | --- |
| ec-ec | Biorbital breadth | Right/left ectoconchion |
| d-d | Interorbital breadth | Right/left dacryon |
| ba-n | Cranial base length | Basion–nasion |
| g-op | Maximum cranial length | Glabella–opisthocranion |
| eu-eu | Maximum cranial breadth | Right/left eurion |
| zy-zy | Bizygomatic breadth | Right/left zygion |
| ba-b | Basion–bregma | Basion–bregma |
| al-al | Nasal aperture breadth | Right/left bony alare |
| n-ns | Nasal aperture height, endpoint-chord variant | Nasion–nasospinale |
| fmt-fmt | Upper facial breadth | Right/left frontomalare temporale |
| ft-ft | Minimum frontal breadth | Right/left frontotemporale |
| n-b | Frontal chord | Nasion–bregma |
| b-l | Parietal chord | Bregma–lambda |
| l-o | Occipital chord | Lambda–opisthion |

There are 22 unique reference points. `R` and `L` mean the individual's right
and left. The article's `ftm-ftm` spelling is accepted as an alias of `fmt-fmt`;
duplicate alias/canonical entries are rejected. **Opisthion (`o`) differs from
opisthocranion (`op`); bregma differs from vertex; nasospinale differs from
acanthion.** Dacryon and ectoconchion are bone references, not eye canthi.

The nasal-height convention deserves explicit attention: CoRA describes an
average of the two nasion-to-inferior-aperture distances. This release instead
reports the selected `n`–`ns` endpoint chord. Those constructions are not
interchangeable on asymmetric anatomy. The `ns` reference requires a localization
note when reviewed in Blender. Do not label this value as a validated implementation
of every published nasal-height protocol. Sutural chords should use bone-surface
level rather than a depression in the suture.

Each measurement records preservation (`observed`, `reconstructed`, `unspecified`
or `missing`), anatomical review, source-hash currency and degeneracy separately.
A measurement on reconstructed bone is retained as documentation. Its value
does not become observed evidence. A missing endpoint produces a null distance,
with the missing codes listed. No contralateral completion takes place.

## Blender workflow

1. Install the complete release ZIP. Use Metric scale **0.001**, register the
   preserved bone meshes, and record case/observer/protocol identifiers.
2. Open **GNM Markers → Cranial Measurements (Table 3)** and choose
   **Add 22 Bone References / 14 Measurements**. Repeating this preserves placements.
3. Select a reference and use **Place Bone Reference**, then click the registered
   bone. Alternatively select an existing marker in the main panel and choose
   **Link Selected Marker**. Linking reuses its bone point and requires anatomical
   review; names alone never establish equivalence.
4. Check its definition, preservation and localization notes, then choose
   **Confirm Definition / Position**. Moving the point invalidates that position's
   review. A changed source mesh/transform requires re-placement and review.
5. Read distances in the list. **Show / Hide Selected Chord** displays the selected
   segment and follows its current endpoints. **Export Measurements JSON** works
   without a loaded GNM asset for measurement-only work. Existing files require
   explicit replacement. The JSON contains raw points, source hashes and all 14
   recomputed measurements. Marker CSV export also embeds the raw document.

For an optional skin-distance control, select a measurement and enable **Use
skin-distance control**. Bind both endpoints to included skin markers anchored
at the corresponding bone references (0.1 mm tolerance). Each marker requires a
reviewed GNM vertex, a tissue source and observed bone. Both cranial references
must have current source hashes and reviewed definitions. Enter the method,
tolerance and influence; explicitly confirm the bone-to-skin mapping. The global
**Skin-distance strength** starts at **0**, so measurement alone does not change
the face. Tolerance defaults to 2 mm as an editable engineering setting, not a
population-derived uncertainty estimate.

New anatomy without an existing skin marker can use **Create a custom skin
control**. Supply an explicit GNM skin vertex, positive tissue depth and source.
The new `Cranio_<code>` marker uses the current local-normal estimator and starts
excluded and unreviewed. Inspect its direction and skin correspondence in the
main marker panel before inclusion. No built-in correspondence or depth is
invented for bregma, lambda, etc. Custom controls require preserved external
bone; basion/opisthion controls are unsupported.

Two target modes are available:

- **Distance between reviewed skin targets:** calculated from the existing skin
  targets. This emphasizes their mutual separation but supplies no independent
  observation. Review depth and normal direction first.
- **Documented skin-distance prediction:** an explicit case-specific predicted
  *skin* distance. Record the equation/reference, applicability and tolerance in
  the method field. The software does not supply a skull-to-skin prediction model
  or a universal multiplier.

The three measurements involving basion/opisthion (`ba-n`, `ba-b`, `l-o`) remain
bone-only because this release has no defensible exterior-skin correspondence.
All other controls are conditional on operator review, not prevalidated anatomy.
This is a skin SSM, not a joint skull–face model. A genuinely joint approach needs
additional skull-shape information and a validated relationship to the face;
see [Madsen et al. (2018)](https://shapemodelling.cs.unibas.ch/gravis-site-archive/publications/2018/2018_Madsen_Probabilistic_Joint_Face-Skull_CVPR_2018.pdf).

## Offline interface and reproducibility

The Blender offline button forwards the same global strength and embeds the
same point/control snapshot. CLI usage, after the above review:

```bash
python gnm_reconstruct.py --input case/markers.csv --npz models/gnm_head.npz \
  --output case/face.obj --regularization adaptive --measurement-weight 0.5
```

`0.5` is an example experiment setting, not a validated recommendation. A separate
`--craniometry case/craniometry.json` may be supplied when the CSV has no embedded
document. Conflicting embedded/external documents are rejected. Case IDs must
agree when provided; an active fit requires the same model SHA-256 and current
source hashes in the marker CSV. Units are never guessed or converted silently.
For documentation-only runs omit `--measurement-weight` (default 0).

JSON `craniometry` contains all bone measurements, active/skipped controls and
skin residuals after initial alignment, statistical fit and final local correction.
TXT provides the bone table and final skin residuals. The raw document remains
under `marker_metadata.craniometry`; input file hashes, model identity, coefficients,
transform, version and settings are recorded by the existing report. Source
changes invalidate the control. Manual or automatic marker exclusion removes
dependent controls before refitting. Frozen protocols include control selection,
endpoint labels, target mode, method, tolerance and influence, while subject
coordinates and predicted values remain case observations.

## Shared numerical contract

`cranio.craniometry.resolve_controls` is the shared anatomical/provenance gate.
`cranio.optimize.fit_identity` is the only fit implementation used by preview
and offline. For each approved pair, the scalar residual is

\[
r_k = s\|v_{a_k}(\beta)-v_{b_k}(\beta)\|-d_k^{skin}.
\]

With block strength \(\alpha\), marker confidence sum \(W\), \(N\) included
pairs, influence \(q_k\), and operator tolerance \(\sigma_k\) in mm, the base
row mass is \(\alpha W q_k/(N\sigma_k^2)\). A Huber factor clips influence beyond
\(2.5\sigma_k\) in world mm. All tolerances/influences are exported. Increasing
the number of equally weighted pairs does not multiply the block's total mass.
Increasing a tolerance weakens its control; it is not a calibrated uncertainty.

Distances are linearized with a Gauss–Newton Jacobian. The identity block uses
model-mm targets \(d_k^{skin}/s\), matching the existing marker/ridge convention.
Rotation and translation remain marker-derived. Scale includes the distance rows
at **every pose update, including the final update**. Scalar IRLS updates scale
and pair weights at fixed rotation. This extends the existing block-coordinate
surrogate with clipping; it is not a globally optimal joint probabilistic fit.

Adaptive lambda still uses the actual included **skin-marker count**, never
`count + 14`. Conditional fixed-pose LOO still tunes marker rows only; it does
not validate or cross-validate the augmented distance objective. Independent
subject-level validation and sensitivity analysis are needed before fixing
weights for a blinded protocol. Pair targets derived from markers are dependent
data and must not be counted again as independent evidence.

Local correction remains opt-in and may change pair residuals; both statistical
and final values are exported. The skull mesh and the original bone observations
are not deformed by this feature. No facial-accuracy improvement is established
by the software regressions.

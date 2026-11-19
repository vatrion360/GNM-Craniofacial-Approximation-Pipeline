# C2 — Observed teeth vs the neutral fitted dentition

This optional comparison answers two questions: **where does a reviewed point on a fitted GNM tooth lie relative to the corresponding point on preserved dentition?** And, if a corresponding lip vertex is supplied, **how much does the tooth-to-lip chord change when the observed tooth point replaces the modeled one, holding the fitted lip fixed?** It does not predict how the living lip would move.

Work from a completed offline fit in world millimetres with a case ID, saved statistical and final OBJ files, and the model used for the fit. The saved fit can have been launched from Blender. A live preview, a different registration or a textured presentation copy is not a compatible substitute. The command only reads existing fit artifacts; it does not change the face, fit the 80 dental identity components, register the dentition, or use a CT face.

## Operator workflow in Blender

1. In **Approximation Record (saved fit)**, select the saved report JSON. If the OBJ files were moved together, select their directory under **Moved artifacts folder**. Select the same model file under the live-fit GNM model setting. Enable **Observed vs fitted dentition**. Set **Dental sites JSON** to a new filename in an existing directory and choose **Write New Dental Sites Template**.
2. Inspect each preserved tooth. There are 12 possible sites: central incisor, lateral incisor and canine on each anatomical side of each arch. Record one reproducibly defined point per tooth and its exact counterpart on the GNM tooth. A group mask checks arch and side, not which tooth or which part of the tooth you chose. Do not assign the nearest model vertex across the arch and call it a correspondence.
3. To obtain a scan point directly from Blender, register the static preserved fragment in the same mm scene and [tag its faces as original](FACE_ORIGIN.md). Select **one vertex** on the observed tooth in Edit Mode, then return to Object Mode with that object active. **Read Selected Preserved Tooth Point** creates a new Text Editor entry with its world-mm coordinate, case ID, source ID and evaluated geometry hash. Do not stamp mixed repaired bone as original to obtain a pick.
4. Edit the new JSON. For each preserved site, set `state` to `observed`, paste the Text Editor object into `observation`, and fill `correspondence` as described below. Record an absent tooth as `absent`, a repaired tooth as `reconstructed`, and an undocumented or uninspectable site as `unknown`. Keep `observation: null` for these three states. A missing lower hemimandible says nothing about tooth absence on that side.
5. Set **New dental comparison JSON** to a different new filename and choose **Compare Saved Dental Positions**. The status shows the number of sites measured. The Text Editor summary and the JSON file give both stages and the reason for each unavailable site. Geometry and files are read only on the explicit button click.

Use zero-based GNM vertex indices from the original GNM topology. In an unmodified GNM mesh in Blender, vertex indices can be inspected in Edit Mode with vertex indices displayed. A conventional OBJ face list uses one-based indices; do not copy them as if they were zero-based. Do not use indices from a mesh that was welded, split, simplified or remeshed.

| Field in a reviewed correspondence | Required value |
|---|---|
| `reviewer` | Operator identifier. |
| `definition` | Reproducible description of the homologous observed and GNM tooth point; if reporting the lip proxy, identify its lip site here too. |
| `tooth_vertex` | Integer vertex in the GNM teeth, correct arch and anatomical side groups. No site mapping is bundled. |
| `lip_vertex` | Optional integer on the matching exterior upper or lower lip and side, otherwise null. Tooth discrepancy can be reported without it. |

A manual measurement in another mesh tool can supply the same observation fields: `case_id`, `source_id`, `geometry_sha256`, `xyz_mm` (three numbers). The geometry hash is the **registered source geometry hash in the fit export**, not the STL file checksum. Verify the coordinate frame and the tooth on the actual preserved source before entering data. Hash matching binds the declared inputs, but does not verify the operator's anatomical identification or independently authenticate a manual measurement.

## Offline commands

```bash
python -m cranio.dental_consistency template --report outputs/case/face_report.json --output sites.json
# Review and fill sites.json, then:
python -m cranio.dental_consistency compare --report outputs/case/face_report.json --npz models/gnm_head.npz --sites sites.json --output dental_comparison.json
```

Use `--artifacts DIR` if the saved OBJ files have moved. The template is tied to the report, case and model. A different report requires a new template and review. The comparison checks both saved OBJ checksums, vertex count and triangle order against the NPZ. Site observations must match the registered source in the fit. A changed source or unreviewed mandibular articulation gives a site-specific reason; missing sides are never mirrored. Existing output files are refused.

## Reading the result

For each stage let **G** be the selected fitted tooth point, **O** the observed tooth point and **L** the optional vertex on the same stage's fitted lip. All coordinates and distances are world mm; no best-fit realignment is applied.

- `model_minus_observed_mm` is **G − O**, expressed in the case's world axes. `tooth_distance_mm` is its Euclidean norm. These axes need not be anatomical axes.
- `observed_minus_model_mm` is **‖L − O‖ − ‖L − G‖**. A positive value means that the observed tooth point is farther from this fixed lip point than the model tooth is. A zero difference can occur even if the tooth positions differ. This chord is not soft-tissue thickness, contact, pressure or an estimate of true lip error.
- Each stage reports the number of measured sites, their arithmetic mean 3D discrepancy and their maximum. Missing sites do not enter the denominator. With no measured sites, both distances are null. Do not compare means across cases without examining which teeth were measured.
- Keep the JSON alongside its reviewed site file and saved fit. It records the source hashes, indices, coordinates, saved-fit convergence and warnings. No acceptance thresholds or empirically validated interpretation are supplied.

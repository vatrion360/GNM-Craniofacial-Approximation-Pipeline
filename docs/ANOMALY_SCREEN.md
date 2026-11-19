# C1 — Descriptive bone screens in an offline fit

Use this opt-in screen to document geometry that merits review before interpreting a fit. It uses case measurements and operator observations. It does not classify a skull as pathological, culturally modified, taphonomically distorted or edentulous. It neither deforms the bone nor derives thresholds from the GNM mean face.

**Start with scores only.** In Blender, review the definitions and place the bone references on preserved fragments; export the v3 marker CSV with its case ID, craniometry and registered source manifest. Copy [the empty policy](anomaly_policy_template.json) and replace its null case ID with the exact ID from the CSV. Leave `rules` empty to obtain measurements without altering the fit:

```bash
python gnm_reconstruct.py --input markers.csv --npz models/gnm_head.npz --output screened/face.obj --anomaly-policy case_policy.json
```

A separate `--craniometry` document must agree with the embedded evidence and case ID. Each bone point must be observed, definition-reviewed and carry a geometry hash that matches the source manifest in the marker export. Missing sides are never filled by reflection. A failed prerequisite gives `not_assessed` for the dependent score; valid measurements without bounds say `no_thresholds_configured`. Neither status means normal. The screen checks consistency with the exported inputs, not the physical specimen.

| Score ID | Definition and units | Interpretation limits |
|---|---|---|
| `axis_obliquity` | Absolute dot product of the unit right-to-left eurion chord and glabella–opisthocranion chord, unit `absolute_cosine`. | Responds to some shears; cannot separate deformation from original shape or placement error. |
| `vault_breadth_length` | Distance(eu_R, eu_L) / distance(g, op), unit `ratio`, **not** multiplied by 100. | Sensitive to relative width/length changes, not uniform scaling. No causal attribution to compression or intentional vault modification. |
| `vault_side_difference` | Absolute difference of the two bregma–eurion distances, `mm`. | Describes one aspect of vault asymmetry. No suture assessment or diagnosis of craniosynostosis. |
| `jaw_transverse_offset` | Absolute projection of midpoint(eu_R, eu_L)→menton onto the eurion axis, `mm`. | Requires reviewed cranium–mandible articulation. Includes vault asymmetry and pose; not a Frankfurt or midsagittal-plane measurement. |
| `anterior_mandible_chord` | Distance(infradentale, menton), `mm`. | Describes a local chord, not direct measurement of how much alveolar bone was lost. |
| `absent_reviewed_sites` | Absent / (absent + present) over explicitly inspected tooth sites, `fraction`. | Unknown/unexamined sites are outside the denominator; tooth absence does not establish timing or cause. |

For the last score, optionally supply `--case-metadata` (or the CSV's embedded `case_metadata`) with the same `case_id` and a `dentition_observation` object. It requires `source_id`, `source_geometry_sha256`, `observation_source` (the inspection record and site notation), and `sites` (map of distinct site IDs to `present`, `absent` or `unknown`). Use one reviewed source per inventory and do not count parts of the same site twice. With no current inventory or no sites of known status, the score is unavailable.

**To apply a reviewed policy**, add a rule keyed by an exact score ID. Each rule requires its matching `units`, lower and upper inclusive bounds (`low`, `high`; one may be null), a non-placeholder `source` documenting the basis and applicability, and the following fields:

| Action | labels | factor |
|---|---|---|
| `flag` | Empty list | null |
| `reduce` | Explicit affected marker labels from the CSV | Operator-supplied multiplier strictly between zero and one |
| `exclude` | Explicit affected marker labels from the CSV | null |

Only measured scores **outside** the stated bounds trigger actions. The software verifies the rule structure, not the scientific validity of its source or the choice of affected markers. No reference bounds, multipliers or region-to-marker mappings are bundled. When actions overlap, exclusion wins; otherwise the smallest multiplier is applied once to the current marker weight. Previously excluded/unplaced rows stay excluded. Local marker-dependent computations use the resulting targets; dense surfaces are not masked, tissue depths do not change, and the Blender live fit and separate A2 ensemble are not rerun by this option. Fewer than four surviving fit targets prevents the fit. Frozen protocols and batch prior/tissue comparisons do not support the option.

A completed run includes the screen in the text statistics and at `marker_metadata.anomaly_screen` in the JSON report (also retained in the derived approximation record). Inspect each score, units, source rule, availability and per-marker decisions; the input policy has its own SHA-256. The pre-fit log also prints the screen if subsequent fitting cannot proceed. These are engineering-tested descriptors; they have not been validated as detection tests on the project's CT or archaeological cases.

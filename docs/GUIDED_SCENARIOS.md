# Guided marker scenarios (B3)

Use this optional guide to specify which placed tissue markers may contribute
to the marker fit and which findings the saved scientific export must satisfy.
Choosing a scenario describes your case; it does not classify a skull.

In **GNM Scientific Markers → Guided skull scenario**, select a profile, enter
a case-specific preservation/review note and optionally select a local case
rules JSON. Choose **Preview Marker Rules** to inspect the proposed settings.
Choose **Apply Previewed Rules** to activate them. A change to the inputs
between these actions requires another preview. The chosen rules are saved
in the blend file; the case rules file is not opened during redraw or fitting.

All four profiles require recorded observed bone for eligible marker targets.
The existing **Include in fit** checkboxes retain their manual meaning. An
unchecked or unplaced marker cannot be re-enabled by a scenario weight. The
list displays the effective weight or exclusion reason alongside the manual
checkbox. The guide does not create, delete or move markers. Clear it to
return to the *current* manual settings, including any later edits.

| Profile | Operator review | Additional required findings |
|---|---|---|
| Complete | Document preserved anatomy and review articulation where relevant. | Proper transform. No claim of completeness is inferred. |
| Partial / mixed fragments | Document each preserved region and side. Select suspect or missing sites individually. | Proper transform and a pass on the existing side-label check. |
| Mandible absent | Exclude the existing mandibular-marker catalogue. Classify the enabled bone sources. | Proper transform; a source labelled mandible contradicts the scenario; mixed or unknown sources cannot establish its absence. |
| Deformed | Record affected regions and explicitly exclude or weight sites as appropriate. | Proper transform and a pass on the existing geometry check. Basic-only QC does not satisfy this requirement. |

For example, for right cranial vault + nasal bone + left mandibular fragment,
choose **Partial**. A left mandibular marker may be observed even if the left
vault is absent. A mirrored right mandibular site is not observed. The guide
does not use one global left/right mask. For a scan combining repaired and
observed surfaces in a single object, you must review the provenance of each
site: a source hash does not prove a surface is original.

## Case rules (optional)

The bundled `cranio/data/scenarios.json` has no new numerical weights. It
labels weight configuration **calibrate**. With no case file, the guide uses
existing manual or legacy base weights. A case file can add exclusions,
absolute weights in (0, 1] and IDs of additional reviewed A5 policy rules
that must pass. Provide the matching case ID, scenario and a source or
justification. Example **structure** without numerical recommendations:

```json
{
  "case_id": "example-case",
  "scenario": "partial",
  "source": "Example structure only; replace with the actual protocol and review.",
  "exclude": [],
  "weights": {},
  "required_policy_ids": []
}
```

Keys in `weights` and entries in `exclude` are exact labels from the active
marker list. A weight cannot be assigned to a site excluded by this protocol.
Custom rule IDs refer to rules in the **separate** A5 policy for the saved
report. The guide does not create a validated policy or supply ranges,
regional minima or deformation cutoffs.

## Offline use and scope of the gate

Export the normal v3 marker CSV **after applying** the guide, then run the
normal CLI fit on that CSV. The effective selection and base weights are in
its rows. Metadata records case, profile, catalogue revision/hash, required
checks, note and customization. Live marker previews and local Finalize use
the same marker filter. A later change to a guide in Blender does not change
a previously saved fit. Base weights are distinct from subsequent IRLS or
optional SD reweighting.

For a **[scientific saved-fit bundle](SAVED_FIT_EXPORT.md)**, supply the
usual [A5 policy](CHECK_POLICY.md). In addition to existing checks, A5 reads
the scenario from the saved report, verifies its case note and compares the
actual fitted labels, observed status, source IDs/hashes and specified CSV
base weights with the declared rules. A required warning or failure blocks
the bundle; a missing finding holds it as not assessed. As with all A5
checks, an explicit override reason is recorded and does not erase findings.
An unsupported catalogue revision requires the matching software; the current
version does not silently reinterpret archived rules.

This gate applies to the explicit scientific bundle. Ordinary fit outputs
and illustrative exports retain their existing purpose. The guide scopes
**marker targets**: it does not mask dense scan triangles, infer fragment
provenance, diagnose deformation, change the craniometry protocol or disable
priors. Review those inputs separately, or leave them off when their
applicability is unknown. Tests use software fixtures, not CT validation.

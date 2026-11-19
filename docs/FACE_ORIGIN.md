# Track which bone surface supplied a landmark

Use **Fragment restoration (originals preserved) → Face provenance and donor regions** when a case combines preserved fragments and repairs. For example, a preserved right cranial fragment, nasal bone and left hemimandible can all be original; their sides do not determine origin. A reflected copy of the case's own bone is *mirrored*. A patch from another individual is *donor*. The operator establishes which geometry belongs to the case; the add-on cannot authenticate a fragment.

1. Register the preserved fragments. In Object Mode, select one verified original mesh and choose **Mark All Faces of Active Preserved Bone as Original**. This labels every polygon. Use a single-user static mesh without modifiers or shape keys. Do not apply this to a combined skull containing repairs or unknown surfaces; keep reviewed working fragments separate.
2. To label new reflected geometry, enable **Tag faces on generated mirror patches**, then generate/update the region. To use external bone instead, prepare the aligned static donor region in a separate scene with the same metric scale (0.001). Choose **Aligned external donor region**, document the source and alignment, then **Copy Aligned External Donor Region**. This creates a separate tagged copy in case coordinates. It does not perform registration or modify the external mesh.
3. Place or re-place the marker on the tagged surface. A repair starts excluded from the fit and reference plane. Review it before enabling **Include in fit**. A guided scenario restricted to observed bone continues to exclude it. Existing placements do not acquire provenance retroactively. After editing or moving a source or bone point, re-place any marker reported as stale.
4. Save the Blender scene and export the v3 CSV. The native mesh attribute `gnm_bone_origin` is an integer on the face domain: 1 original, 2 mirrored, 3 donor. An untagged face is unclassified. STL does not preserve this attribute. The CSV carries the picked polygon, world point in mm, source ID and geometry/lineage hashes in metadata. A downstream record retains these receipts; a CSV alone cannot reconstruct the source mesh.

## Optional case factors

The labels can be used without a weighting policy. To study a specified policy, create a JSON file with this structure, fill in the actual case ID and documented source/rationale, then select **Case sensitivity factors → Load Case Factors**:

```json
{
  "schema": "gnm.origin-factors.v1",
  "case_id": "<exact case ID>",
  "source": "<documented source or sensitivity rationale>",
  "status": "calibrate",
  "mirrored": {"weight_factor": null, "placement_sd_factor": null},
  "donor": {"weight_factor": null, "placement_sd_factor": null}
}
```

The file is a case-specific sensitivity assumption, not a calibrated anatomical estimate. No factor is supplied by the add-on. The loaded values are stored in the scene; reload to apply file edits. **Disable Factors** removes the policy and retains the surface labels and receipts.

| While the policy is active | Effect |
|---|---|
| Original | Use the existing marker weight and placement SD. |
| Mirrored or donor, explicitly included | Effective fit weight = existing case weight × configured weight factor in (0, 1]. A null weight factor excludes it. Previously excluded markers are never re-enabled by a factor. |
| Placement uncertainty on a repair | A2 multiplies the supplied per-coordinate placement SD by the configured factor (at least 1). If either value is missing, placement uncertainty is unknown; the normal missing-input rules apply. Tissue depth and its SD do not change. |
| Untagged placement | Cannot supply fit evidence under this policy. Re-place on reviewed, tagged bone to include it. |

The v3 CSV keeps base weights, effective row weights and the policy so offline fitting can validate the exported weights without applying the factors twice. These checks document the evidence used. They do not establish that any particular weight, uncertainty factor or donor placement improves agreement with a CT reference.

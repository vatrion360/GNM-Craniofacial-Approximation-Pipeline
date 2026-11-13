# B4.1 — saved-fit consistency summary

This explicit diagnostic action collects existing geometric QC and measures
triangle angles on the saved statistical/final OBJ files. It never fits, corrects
or approves a face. It is the first B4 increment, not complete anatomical QC.

## Usage

```bash
python -m cranio.consistency build --report outputs/case01/face_report.json --output-dir outputs/case01/consistency
```

In Blender, open **Approximation Record (saved fit)**, select the saved report and
click **Summarize Saved-fit Consistency**. The external Python selected in Offline
fit performs the work; Blender displays the status and a new Text Editor report.
It shares the existing bounded cancellation, scene-removal and unregister cleanup.
The working mesh, markers and earlier files are preserved.

| Input/control | Default | Effect |
|---|---|---|
| `--report FILE` / Saved fit report JSON | Required | Completed canonical schema-2 world-mm run |
| `--output-dir DIR` | Required/new | Refuse an existing directory |
| `--artifacts DIR` / Moved artifacts folder | Report folder | Optional explicit location of the four saved output basenames |
| Summarize Saved-fit Consistency | Explicit click | Separate external-process diagnostics, no automatic fit-time work |
| Output parent folder (Blender) | Report folder | Unique job directory containing `run.log` and `consistency/` |

Other optional record-panel fields (policy, prior-related ensemble, domain,
limitations, capture settings) do not configure this action. It inspects saved QC
only and does not silently apply a policy or start additional geometric searches.
Current Blender edits are not reflected in the saved report; produce a new fit
when those edits should be assessed.

## Measured versus recorded

**New measurements:** minimum triangle angle and degenerate-face indices, for
both serialized OBJ meshes. All exported triangles are included, including eye
and teeth groups; this is not a skin-only metric. Per-triangle edge scaling and
`atan2(norm(cross(a,b)), dot(a,b))` provide angles in degrees. Numerically zero
cross products identify collinear/collapsed triangles. There is no invented
minimum acceptable angle. Rounding during OBJ serialization can differ from the
unrounded vertices used by the original fit QC.

**Recorded diagnostics:** reference degeneracy, new degeneracy, normal reversals,
contact counts/completeness and new contacts, plus sampled bone clearance from
`geometry_quality`. Contact searches are not repeated. Original contact pair
indices refer to the selected exterior subset; new-contact indices refer to the
full mesh. The original A7 record remains available for detailed source data.
Incomplete searches are explicitly marked, and shared-vertex contacts remain
outside the original search scope. Normal reversal is relative to the aligned
reference, not a volumetric Jacobian or a guaranteed flipped surface.

For recorded local clearance samples `c_i` and their recorded tolerance `t`, the
summary gives the minimum, median, P10/P90 (NumPy linear percentile convention),
and `100 * count(c_i < -t) / N`. The denominator is the **number of samples**;
the fraction is neither an area percentage nor the percentage of face vertices
inside bone. The existing tolerance is retained with `legacy_hardcoded`
provenance, not replaced with a new scientific threshold. Contradictory counts,
nonfinite samples and invalid indices are rejected.

Local clearance projects the closest skin displacement on recorded bone normals.
It is not tissue thickness, a source-table measurement direction or global signed
distance. For incomplete skulls and unreviewed/open surfaces, it cannot establish
inside/outside, complete skin coverage or absence of penetration.

## Status and limits

The existing A5 geometry summarizer supplies the recorded geometry status without
promoting basic QC to full QC. The overall diagnostic summary is:

- **red / block** when an existing recorded defect/nonconvergence or a newly
  measured degenerate serialized triangle requires review;
- **gray / not_assessed** otherwise, because this increment does not assess all
  anatomical consistency checks. A passed recorded check is not a green overall
  approval.

Unassessed checks remain listed: closed-volume skin-in-bone, bone-area coverage,
regional tissue-table bands, and independent reference-face profile error. No
automatic correction is implemented. No tissue values, normative ranges or CT
validation results are supplied. CT evaluation remains manual.

These diagnostic statuses do not alter existing export gates. CLI exit 0 means
the diagnostic package completed, even if its status is red; invalid inputs or
failed integrity checks return an error. Scientific export remains the separate
[explicit gated action](SAVED_FIT_EXPORT.md).

## Files and integrity

- `consistency.json`: deterministic measured/recorded metrics and source hashes;
- `consistency.txt`: readable report, with unassessed checks and source warnings;
- `record/`: verified A7 record, its text and separate runtime/path provenance;
- `consistency_manifest.json`: completion marker written last, with fixed-file
  hashes and implementation identity.

The source report and all four saved artifacts are hash-checked using the A7
record workflow and rechecked before completion. The restricted pipeline OBJ
reader never follows embedded material/file directives. Statistical/final meshes
must have matching topology. Input/model hashes are recorded, not reread as proof
of authenticity. Original source bone normals and scans are not revalidated.

Repeated identical inputs produce identical metric JSON/text; the provenance
envelope has runtime timestamps, so whole-package byte identity is not promised.
Interrupted exports may retain diagnostic files but lack a final completion
marker. Blender verifies fixed outputs and the submitted report identity before
displaying success. See [task evidence](TASK_B4_1.md).

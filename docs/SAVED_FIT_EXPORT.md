# A7.3.1 — gated, labelled saved-fit mesh export

This optional workflow exports the **saved final neutral OBJ** from a completed
offline run. It adds scientific/illustrative labelling, an explicit A5 check gate,
a neutral gray material and a hashed decision manifest. It does not refit,
realign, infer anatomical validity or include current Blender scene edits.

The original pipeline and record commands remain unchanged. Existing mesh exports
are still available with their previous behavior. This is the first explicit
export-mode increment, not completion of every A7.3 requirement.

## CLI

```bash
# Create and then supply/review criteria; the template contains no thresholds.
python -m cranio.check_policy template --output checks.json
python -m cranio.review_export build --report face_report.json --mode scientific --check-policy checks.json --output-dir scientific-export

# Labelled illustrative export of the SAME saved neutral geometry.
python -m cranio.review_export build --report face_report.json --mode illustrative --output-dir illustrative-export
```

| Option | Default | Effect |
|---|---|---|
| `--report FILE` | Required | Completed schema-2 saved run report, world mm |
| `--mode {scientific,illustrative}` | Required | No implicit choice |
| `--output-dir DIR` | Required/new | Existing destinations refused |
| `--check-policy FILE` | None | Required for scientific; optional diagnostic linkage for illustrative |
| `--allow-blocked REASON` / `--check-override REASON` | Off | Explicit exception retained in record, OBJ, decision and README |
| `--artifacts DIR` | Report directory | Explicit location of relocated saved artifacts; original basenames retained |
| `--limitations FILE` | None | Existing approved RO/EN limitations mechanism |
| `--uncertainty FILE`, `--uncertainty-scenario {off,on}` | None | Existing A2.1 record linkage; not final-mesh uncertainty |
| `--validation-domain FILE`, `--domain-case FILE` | None | Existing domain comparison; not automatically added to the A5 gate |

Scientific mode applies the existing A5.1 assessment. A `block` or `not_assessed`
aggregate stops mesh export unless a reason is explicitly supplied. Missing
policy is a configuration error even if an override reason is given. An empty
policy file is allowed as diagnostic input but cannot pass silently. The original
findings remain visible after an override, and the derived record remains
`diagnostic_only`. Passing the configured checks does not grant scientific
validation or human approval.

Illustrative mode always carries `ILLUSTRATIVE — NOT VALIDATED`. It may export a
finite, structurally valid saved mesh despite diagnostic findings; these remain
in the included record and README. This distinction is deliberate and visible.
No mode bypasses file integrity, OBJ validation or input-change checks.

Exit codes: **0** for a completed mesh bundle, **3** for a scientifically held
export with complete diagnostics, **2** for invalid input/I/O failure. A completed
ordinary approximation record is not sufficient to infer a completed mesh bundle:
inspect `export_decision.json` and its `status`.

## Blender

In **Approximation Record (saved fit)** select the saved fit report and the
external Python as before. Choose **Mesh export mode**, initially **Not selected**,
then click **Export Labelled Saved-fit Mesh**. Scientific mode also requires the
**Check policy** field. **Check override reason** supplies an explicit exception.
The original **Export Approximation Record** button retains its previous purpose.

The job shares the existing external-process lifecycle, cancellation and scene
ownership checks. Blender displays a distinct blocked/overridden/illustrative
status and creates a new explanatory text block. Code 3 is displayed as a held
export, not an unexplained process error. Later changes to the selected mode or
input fields cannot change a submitted request.

No object is added, deleted or changed. No geometry work happens during redraw.
The source-report read and interpreter check occur on the explicit action;
export work is external. On completion Blender reads and hashes the fixed bundle
files, including the OBJ, before displaying the result; this is bounded by the
saved files' size, not asynchronous background hashing of the live scene.
Earlier reports are preserved. Cancellation leaves files for inspection and does
not claim that a bundle completed. The same applies after a deleted scene or
add-on unload.

## Bundle contract

A successful export contains:

- `face.obj`: unchanged vertex/triangle numeric tokens from the saved final mesh,
  world mm, with mode, source hashes and any override recorded as comments;
- `face.mtl`: one neutral gray material, no textures or external image references;
- `README.txt`: mode/decision, limitations and full derived-record text;
- `record/`: existing approximation JSON/TXT and separate runtime provenance;
- `export_decision.json`: written last; status, mode, gate, source hashes, geometry
  counts, implementation hash and hashes of all bundle files except itself.

A held export contains only the README, record and decision (`status: blocked`).
It contains **no face OBJ/MTL**. An I/O/input-change failure may leave partial files
but does not publish a decision marker. Consumers must not treat orphaned mesh
files as a completed export. Existing destinations and concurrently created
output files are refused.

The restricted input OBJ parser accepts only pipeline vertices, triangular
positive vertex-only faces, comments and blank lines. Non-finite values, invalid
indices, repeated triangle indices and empty geometry are rejected. Input
materials, texture/normal indices, command directives and other OBJ variants are
rejected rather than followed. No file mentioned by an input OBJ is opened.
Materials are generated locally, so source textures cannot leak into scientific
mode. The saved OBJ already has the pipeline's decimal precision; the exporter
does not introduce further coordinate rounding or change vertex order.

Source artifacts, optional record inputs and written output hashes are rechecked
before the decision marker is published. Hashes establish byte consistency, not
authorship, data rights or anatomical truth. Runtime timestamps in the existing
record provenance can differ between exports; identical source geometry and
mode produce the same OBJ/MTL, not necessarily a byte-identical entire bundle.

## Remaining scope

Both modes currently export a **neutral, untextured saved face**. Existing post-fit
presentation controls remain available inside Blender, but their current meshes,
UVs/textures and expressions are not exported by this command. A live-only preview
must first produce a canonical offline fit/report to use this workflow.

Standardized Frankfort captures and scale bars are available through the separate
[A7.3.2 saved-bundle capture action](STANDARDIZED_CAPTURES.md), requiring a reviewed
frame in the saved report. The original mesh-bundle manifest still says captures
are not exported: it is not rewritten. A new capture manifest links the images to
that bundle by hash. Final-mesh uncertainty remains unassessed; no displacement
heatmap or related marker-only Monte Carlo ensemble is relabelled as final-mesh
confidence. The existing A4.2 live-scene capture workflow remains separate.

This software change does not add CT validation, scientific thresholds or an
independent validity domain. The operator remains responsible for policy sources,
applicability and any override. See [task evidence](TASK_A7_3_1.md).

# Approximation records from Blender (explicit saved-fit export)

The **Approximation Record (saved fit)** panel in **GNM Markers** exports the
existing [A7.1 record](APPROXIMATION_RECORD.md). It records files from a completed
offline run. It does not refit, export current marker positions, change meshes,
texture the face, or provide scientific validation.

## Workflow

1. Select a completed offline fitted object and click **Use Active Fit Report**,
   or explicitly choose its `face_report.json`. The button copies the object's
   recorded `gnm_report` path only; it does not infer a report for a live-only fit.
2. Use the installed external Python selected in **Offline fit (external Python)**.
   The same interpreter checks apply, including the Windows executable check.
3. Optionally choose an output parent directory. Each export creates a unique
   `record_<timestamp>_<id>` job folder; an empty parent uses the report's folder.
4. Supply any optional moved-artifact directory, reviewed limitations file or
   existing A2.1 ensemble. Choosing an ensemble requires an explicit matching
   prior scenario; no scenario is guessed and sampling is not started.
5. Click **Export Approximation Record**. This launches the bundled record CLI in
   the external Python process. Blender polls completion without a worker thread
   using `bpy`; panel redraws do not hash geometry or start computation.
6. On success, inspect the JSON path and the named `GNM_Approximation_Record_...`
   text block in Blender's Text Editor. Each successful export creates a new text
   block, preserving earlier reports. `recorded_not_validated` and
   `diagnostic_only` retain their existing meanings.

| Control | Default | Effect |
|---|---|---|
| Saved fit report JSON | Empty | Explicit canonical schema-2 run report |
| Use Active Fit Report | Explicit click | Copy the active object's stored offline-report path |
| Output parent folder | Empty | New job folder beside the source report |
| Moved artifacts folder | Empty | Use the report folder unless explicitly overridden |
| Approved RO/EN limitations | Empty | No unapproved scientific wording inserted |
| Existing A2.1 ensemble | Empty | No linked analysis or automatic Monte Carlo computation |
| Declared validation domain | Empty | Optional operator-declared conditions and study results |
| Bound domain observations | Empty | Required with domain; bound to the exact report hash |
| Ensemble prior scenario | Not selected | Explicit `off`/`on` is required with an ensemble |
| Export Approximation Record | Explicit click | Check the interpreter and launch one record job |
| Cancel Record Export | Available while running | Stop the child process; retain files for inspection |

One record job can run at a time. Starting during an active offline fit is disabled.
The submitted request is independent of later field edits. The source report's
hash is captured on submission; a changed source is refused at display time.
Optional source files are pinned by the CLI when it reads them, as documented in
A7.1. Heavy artifact checks and optional ensemble validation run outside Blender.
The interpreter probe and initial source-report read occur only on the explicit
export action.

## Output and failure handling

The job folder contains `run.log` and, on success, a `record/` directory with
`approximation_record.json`, `approximation_record.txt` and `provenance.json`.
The JSON completion marker is written last by the existing CLI. Before creating
a Blender text block, the add-on verifies the fixed result files against their
manifest and checks the submitted source-report hash. It does not follow file
paths embedded in the resulting JSON to load other objects or execute code.

Failed jobs show their log path and do not display a successful result. Earlier
text blocks and source files remain intact. Cancellation can race with a job
that has already finished: retained files must be inspected, not automatically
classified as incomplete or deleted. Opening another blend file, unregistering
the add-on or deleting the owning scene stops the job. A new scene with the same
name cannot inherit the deleted scene's completion. Result/status UI fields are
transient; source/settings fields are saved with the blend file.

The record describes the **saved fit files**, not the current Blender scene.
Editing or replacing the imported object, moving markers, or applying presentation
controls does not update that saved run. Produce a new fit/report when those
changes should be recorded. A live-only preview lacks the canonical offline report
needed by this exporter. For prior comparisons choose one scenario's child
`face_report.json`; the aggregate comparison summary is not a run report.

Integrity hashes are not authentication or proof of anatomical accuracy. Linked
Monte Carlo evidence remains uncalibrated and is not assigned as uncertainty of
the final mesh. CT evaluation remains manual. The optional [labelled mesh-export action](SAVED_FIT_EXPORT.md)
shares this panel and process lifecycle but has its own explicit decision file.
[Declared-domain comparison](VALIDITY_DOMAIN.md) is optional; its banner appears
in the completion status and text report without certifying validity. Review
identifiers and file paths before sharing reports.

Optional [saved-report check policies](CHECK_POLICY.md) add configured findings and
explicit override reasons. Held checks remain diagnostic even with an override;
this does not authorize scientific mesh export. Empty policy fields preserve
the prior record path.

For mesh bundles choose **Mesh export mode** explicitly (default **Not selected**)
and **Export Labelled Saved-fit Mesh**. Scientific mode requires a check policy;
blocked jobs retain diagnostics without a face OBJ. See [details and remaining scope](SAVED_FIT_EXPORT.md).

After a completed mesh export, **Capture Reviewed Saved-fit Bundle** uses the
matching saved report/frame to render three orthographic views with scale bars in
a separate CPU Blender process. It shares cancellation/lifecycle handling but
does not require the external Python interpreter. See [settings, inputs and
limits](STANDARDIZED_CAPTURES.md). The original bundle and working scene remain
unchanged; images have their own source-bound completion manifest.

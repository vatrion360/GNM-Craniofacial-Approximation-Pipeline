# C3: Manual paired-face evaluation and inter-observer protocol

Use this harness **after generating the approximations**. It freezes the protocol and case meshes; the evaluator then inspects the CT reference, chooses the documented mask, performs the external comparisons, and imports measurements. It does not segment a CT, register a face, run ICP, rerun a fit, judge likeness or calibrate the add-on. No subject data or success threshold is included.

## 1. Enrol subjects and agree on the comparison

One study directory has **one arm**. Use separate directories and lock hashes for:

| Arm | Case run's reference_access | Meaning |
|---|---|---|
| blind_ct | withheld | Reference face and CT-derived facial depths withheld from fit operators; evaluator distinct from all fit operators. |
| paired_ct_unblinded | seen | The reference was already seen; paired retrospective geometry comparison, without deliberately imposing CT-specific facial depths. |
| ct_conditioned | used | The approximation used case-specific facial measurements from the same CT. This characterizes the conditioned fit, not independent prediction. |
| historical | no_reference | Keep an inventory of the approximations and failures. No paired accuracy metrics, even if another reconstruction exists. |

If a fit operator has already inspected a case's reference face, generating a fresh mesh does not restore blinding. The software records declarations; it cannot establish independence, prior access or the time of unblinding. One pseudonymous subject per folder. Related/repeated scans of the same person are not additional subjects. Work outside the repository and keep the local ID key separate.

Start in a **new** workspace; initialization does not overwrite existing case folders. Stage authorized working copies of your meshes there. Run IDs identify distinct methods, stages, observers or sessions. Register a rigid-template/marker-only baseline as a separate run if your question is whether another fit improves on it.

```bash
python scripts/validate_cases.py init --root paired-study --arm blind_ct --subjects S01 S02 S03 --runs live offline --outcomes face_roi profile_Gl
```

Installed packages use `python -m cranio.validation_cases` with the same arguments. For the historical arm omit `--outcomes`.

- In **study.json**, set `protocol_file` to the relative path of your fixed protocol; set each run's `stage` (`blender_live`, `blender_finalize`, `offline_statistical`, `offline_final` or `baseline`), `observer` and `session`. Fix Blender/addon/model versions, tissue table, skull registration, masking, sampling, exclusions, comparison direction, stopping rules and subject-level inclusion/split before interpreting errors. Record all distances in mm.
- Define each outcome in advance. For a surface: e.g. `{"quantity":"surface_unsigned","direction":"approx_to_reference","definition":"See facial ROI and sampling rule in protocol, section 2","sites":null}`. For a signed field select `surface_signed` and document sign convention, normal quality and which reference side is positive. For an opposite-direction measurement create a **different** outcome with `reference_to_approx`. For anatomical pairs: e.g. `{"quantity":"profile_point_distance","direction":"paired_points","definition":"Reviewed homologous glabella skin points on the prespecified midline section","sites":["Gl"]}`. `landmark_distance` uses the same paired-coordinate format. Use separate outcomes for sites that may be independently missing.
- In each **case.json**, set `skull` to the actual skull mesh and `runs.<id>.mesh` to that exact saved approximation (STL, OBJ or PLY), with the arm's `reference_access`. All paths are relative to that subject's folder. For a failed/missing fit leave the mesh and access null and give a reason. Optional `fit_report` binds an offline statistical or final mesh to its exact saved-stage checksum and case ID. The lock retains the report hash, convergence and available mesh QC counts. These describe mesh quality, not facial accuracy; the full [post-fit consistency report](POSTFIT_CONSISTENCY.md) remains separate.
- Optional `strata` in case.json: e.g. a reviewed preservation category as `{"preservation":{"value":"partial","source":"Case assessment revision A"}}`. Use skeletal class or asymmetry only if a reviewed, sourced classification exists; the harness does not derive it. Missing strata remain unknown.

```bash
python scripts/validate_cases.py freeze --root paired-study --lock-dir paired-lock
```

Record the **printed SHA-256** independently (study log) before the evaluator reveals reference information for a blind study. Archive the lock and inputs. For paired arms the lock directory also contains one editable `S01.review.json` etc. The lock itself is not a signed attestation or an access control.

## 2. Measure manually and complete the review sheets

Keep the skull and skin surfaces from the same segmentation in their original case coordinate frame and metric scale. Where applicable, document the acquisition posture (including supine CT), scanning resolution, expression, jaw pose, segmentation revision and exclusions; do not infer posture from a filename. If two disconnected lateral plates flank the skin segmentation, archive the original, record the removed components and the resulting ROI, and apply the **same eligibility rule** to every approximation. Do not remove high-error regions after looking at distance maps.

For the primary analysis keep the prespecified skull-based alignment. A separately justified face-based ICP/similarity analysis answers a different question and must be reported separately. Do not silently optimize away pose, scale or face-shape error. Choose the surface direction, sampling area/density and normal/sign rule before looking at results. Use identical case coverage across methods or explicitly report failures or different coverage; the harness does not inspect the geometry to verify these choices.

For each review JSON set `evaluator`, `reference_face` (the actual scored reference mesh) and `roi_alignment_record` (separate archived record or file describing ROI, transform, exclusions, sampling and software/version). Store these files under the subject folder. For each planned run/outcome, supply exactly one of:

- **Surface field:** a CSV exported from the external comparison, with a header and one raw scalar value in mm per sampled point. Set e.g. `{"file":"live_roi.csv","column":"Distance_mm","separator":"comma","reason":null}`. Enter the actual scalar field name, without the optional leading `//` on the first header. Comma, tab and semicolon delimiters and decimal points are supported. Do not use a histogram, displayed colour range, per-bin means or a clipped field. Nonfinite rows and negative unsigned values are refused rather than discarded. Sampling points are not independent subjects.
- **Landmark/profile points:** use `{"file":"live_Gl.csv","column":null,"separator":"comma","reason":null}`. Required columns: `site,approx_x_mm,approx_y_mm,approx_z_mm,ref_x_mm,ref_y_mm,ref_z_mm`. Each prespecified site appears exactly once, in the same frame. The harness computes Euclidean distance; a profile point is **not** a signed projection or curve-to-curve distance. Document which landmarks were used in fitting vs independently assessed.
- **Not evaluated:** set file, column and separator to null and give a reason. A missing reference, fit, ROI, or landmark is not zero error.

The tool verifies hashes and explicit assignments, not what the evaluator clicked in CloudCompare. Maintain the CloudCompare project or export log linking the input meshes and selected scalar field to that run/outcome.

## 3. Summarize and interpret

```bash
python scripts/validate_cases.py summarize --root paired-study --lock-dir paired-lock --expected-sha256 YOUR_RECORDED_LOCK_HASH --output-dir paired-results
```

| Output | Interpretation |
|---|---|
| cases.csv | One row per subject/run/outcome with status, omission reason, sample count, MAE, median absolute distance, RMS, P95 absolute distance and (signed fields only) signed mean. Historical rows are inventory only. |
| paired_sites.csv | Individual anatomical site distances; empty if no paired points were evaluated. |
| cohort.csv | For each run/outcome and available stratum: number eligible, number measured and mean of **subject MAEs**, each measured subject weighted once. Never pools vertices, repeated operators or sessions. |
| summary.md | Exploratory interpretation and measured/enrolled counts. Compare methods on the same measured subjects; different denominators do not establish improvement. |
| manifest.json | Frozen study, input/review/output hashes, evaluator attribution and external field assignments. |

For signed values d, MAE = mean(abs(d)), RMS = sqrt(mean(d²)), bias = mean(d). Median and P95 use absolute distances and linear percentile interpolation. Paired sites use the norm of the difference between the two 3D coordinates. The point-count mean is not area-weighted unless the sampling design justifies it. There are no automatic confidence intervals, clinical acceptability limits or independence claims. With three CT subjects, show the individual results and omissions; report study results as exploratory. Do not combine them with historical cases or treat the number of sampled vertices as N. A reviewed study may inform an operator-authored [validity domain](VALIDITY_DOMAIN.md); this command never populates or approves one.

## Inter-observer and repeat-session design

Use 2–3 operators and independent sessions on the same cases, predefined anatomy and geometry frame. Give each operator a clean setup without earlier markers or reference skin; save observer and session IDs, deviations, missing sites and artifact hashes. Keep the evaluator independent for blinded fits. Register each operator/session as a run (including missing runs); compare like stages and use within-subject paired differences for any later method/observer analysis. For placement repeatability, use [A/B manual placement](PLACEMENT_REPEATABILITY.md) to retain site-level 3D differences; tooth, landmark and face discrepancies are distinct outcomes.

The individual inter-session distance is not a calibrated per-coordinate placement SD. Follow the documented A2 repeatability assumptions if exporting a sensitivity scenario. [A2 uncertainty calibration](UNCERTAINTY_CALIBRATION.md) separately requires paired reference errors **and** matching predicted spread on the specified skin sites, a subject-level split and independent holdout. Do not feed per-case means, historical meshes or CT-conditioned fits into that calibration. This harness applies no factor and makes no changes to any fit.

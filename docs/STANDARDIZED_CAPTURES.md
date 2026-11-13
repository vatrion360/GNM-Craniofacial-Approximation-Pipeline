# A7.3.2 — standardized captures of a saved neutral fit

This explicit action documents an existing [labelled mesh bundle](SAVED_FIT_EXPORT.md).
It creates frontal, right three-quarter and right-profile orthographic PNGs,
using the reviewed Frankfort reference frame embedded in the saved fit report.
All views use anatomical superior as image up and the same scale. It does not
refit, orient by guesswork, export current presentation edits or validate a face.

## Blender workflow

1. Review the observed bone references and compute the A4.2 frame **before**
   exporting markers and running the offline fit. The saved `face_report.json`
   must contain the current frame and its reviewed observations. A frame computed
   only later in the live scene does not update the saved report.
2. In **Approximation Record (saved fit)** select that report and export a
   labelled saved-fit mesh bundle. Scientific mode retains its A5 check gate;
   an explicit override stays visible. Blocked/no-mesh bundles cannot be captured.
3. **Capture source export_decision.json** is filled after a successful bundle
   export. To use an earlier bundle, select its decision file and matching report
   explicitly. Moving a complete bundle is allowed; editing its files is not.
4. Choose image size, bar length and CPU samples. Click **Capture Reviewed
   Saved-fit Bundle**. This starts the current Blender executable in a separate
   background process with a factory-startup scene and the package's fixed script.
5. Read `run.log` if the action fails. On completion the panel gives the
   `capture_manifest.json` path and a new Text Editor summary. **Cancel Record
   Export** also stops a running capture. Earlier outputs are retained.

| Control | Default | Meaning |
|---|---|---|
| Capture source export_decision.json | Empty; set after bundle export | Explicit completed bundle matching the report hash |
| Capture size (px) | 1024 | Square PNG, 128–4096 pixels per side |
| Scale bar (mm) | 50 | Positive display length; refuse bars exceeding the reserved layout |
| CPU samples | 16 | Cycles samples per pixel, 1–128; controls rendering cost/noise |
| Capture Reviewed Saved-fit Bundle | Explicit click | No automatic render after fit or marker movement |
| Output parent folder | Empty | New capture job folder beside the bundle if unspecified |

These are display/engineering settings, not anatomical thresholds. Rendering is
CPU-only for portability and can take time; the graphics card is not required.
No external Python, SciPy, TensorFlow or network access is needed for this action.
The numerical input validation uses NumPy; Blender APIs execute only in the child
process's main thread. The parent's mesh, markers, cameras and rendering settings
remain untouched. The existing A4.2 live-scene capture command remains separate.

## Coordinate and scale contract

Inputs are the saved world-mm OBJ and schema-2 report. Frame geometry is recomputed
from the reviewed snapshot observations after verifying its input signature;
cached camera axes are not trusted. Missing, stale, unreviewed or reconstructed
reference points are rejected. There is no inferred frame for an incomplete skull.

Let `r` be the greatest vertex distance from the anatomical frame origin. The
common orthographic scale is `s = 2.8 r`, with square pixels. The camera sits at
`3 r` along each view's backward axis. These layout factors reserve space for
annotations. A bar of length `L` mm has projected length `L * resolution / s`
pixels in every view. The manifest records camera matrices, clipping distances,
bar endpoints in world mm and pixels, plus the pixel coordinate convention.
Millimetres are scene-coordinate units; Blender's metric display scale is 0.001.

## Outputs and integrity

A fresh `captures_<timestamp>_<id>/` contains `run.log` and a `captures/` folder:

- `front.png`, `3quarter.png`, `profile.png`: neutral gray, no textures, labels
  stating scientific/illustrative mode and a visible override when applicable;
- `capture_manifest.json`: source report/decision/mesh and bundle artifact hashes,
  reviewed frame, exact camera/bar settings, image hashes, renderer version and
  implementation hashes. Written last, after source and image integrity checks.

Source changes or partial failures prevent a completion manifest. The panel also
checks request hashes before accepting the result. It reads only fixed expected
output filenames. Existing destinations are refused. These hashes establish
file consistency, not authenticity or anatomical validity.

The original mesh bundle is immutable. Its `standardized_captures: not_exported`
describes that original bundle; the separate capture manifest binds the new
images back to it by hash. Source check findings/override remain in that bundle
and the capture manifest. Do not discard the record when sharing the images.

## Limits and verification

Smooth shading changes surface appearance, not coordinates. Rendered pixels may
differ across Blender/platform versions despite fixed seed/settings; numerical
camera plans are deterministic for identical inputs. No pixel-identical portable
render claim is made. A scale bar describes projection in the stored mm frame;
it does not prove that the source scan was correctly scaled.

No final-mesh uncertainty heatmap, textured/expressive scene export or new CT
validation is supplied. `final_mesh_uncertainty` remains `not_assessed`. The
illustrative/scientific label does not certify accuracy or release suitability.

Unit tests cover camera geometry, rigid transformations, source binding and
rejected frames. Hosted Windows/Linux Blender tests render actual PNGs from the
installed ZIP, decode pixels, check bar length and parent-scene immutability.
Synthetic fixture references are software tests, not anatomical evidence. See
[task evidence](TASK_A7_3_2.md) and the PR for actual run outcomes.

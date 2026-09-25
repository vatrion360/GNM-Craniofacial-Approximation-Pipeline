# 5.0.0rc1 / Blender add-on 14.0.0

- Installable Python package/CLI and complete Blender ZIP with a namespaced numerical core.
- Explicit v3 marker labels, placed flag, manual vertex indices, bone/skin coordinates, tissue provenance and model hash. v1/v2 remain readable with documented limitations.
- Safe numeric model loading without pickle; topology, dimensions and finite-value checks; offline doctor.
- Proper-rotation Umeyama including planar sets; degenerate-input rejection; correct RMSE; sagittal reflection in symmetry loss; soft-prior IRLS gradient correction; final pose re-estimation.
- Local 3-D polyharmonic correction is now opt-in, uses the dimension-appropriate radial kernel, rejects singular configurations and preserves an unwarped output.
- Separate outer landmark holdout evaluation, with no held-out target in pose/identity fitting.
- JSON reproducibility manifest and per-file atomic exports; deterministic skull sampling; output collision protection; true red maximum in the displacement heatmap.
- Nasal diagnostics use explicit bone positions in pose-aligned axes, never legacy skin-target coordinates.
- Explicit skull import units; editable tissue depths update placed targets; final fitting in a cancellable external Python process. No persistent background fitting thread inside Blender.
- Synthetic tests, real GNM integration check, packaging CI, headless Blender acceptance script, installation guide and scientific validation protocol.

## Changes requiring attention

Local correction is disabled by default. Its kernel and the numerical fixes can change previous results. Revalidate existing research protocols before comparing runs across versions. v3 export requires a selected model and a metric scene scale of 0.001. Unknown legacy vertex encodings now fail instead of being silently discarded.

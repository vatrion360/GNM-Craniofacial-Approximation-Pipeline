# Repository audit — 2026-09-25

Baseline: `b72fb73` from `vatrion360/GNM-Craniofacial-Approximation-Pipeline`.

The repository had a useful numerical skeleton and a substantial Blender interface, but its original distribution did not support the advertised installation, historical test counts or publication-grade readiness. No scanned subject or paired skull/face validation dataset was present.

| Finding | Consequence | Change / remaining work |
| --- | --- | --- |
| No committed test suite or package metadata; README referenced absent files/model/venv | Clean installation and claimed test badges could not be reproduced | Added packaging, tests, build scripts and honest installation steps |
| Single-file add-on imported an adjacent `cranio` not included by Blender installation | Installed add-on could not find its numerical core | Build a complete ZIP; use a private package namespace |
| `allow_pickle=True` for numerical model loading | Unnecessary execution surface for untrusted archives | Disabled pickle; check dimensions, numeric values, topology and mirror mapping |
| CSV export had only encoded index and skin coordinates | Manual vertex picks, bone positions and tissue provenance lost | Explicit v3; retain legacy decoding with warnings |
| Zero coordinates used as universal unplaced sentinel | Valid origin markers disappeared | v3 has a separate placed flag |
| Missing validation of units, NaN, duplicates and weights | Silent corruption or opaque numerical failures | Strict input contracts and CLI error return codes |
| Negative SVD determinant rejected unconditionally | Valid planar configurations could fail | Proper-rotation Umeyama with rank checks |
| Mean Euclidean distance displayed as RMS | Understated/incorrectly named metric | True RMSE; report mean/median/p95/max separately |
| Symmetry penalty compared opposite-side coordinates without reflecting x | Symmetric shape changes could be penalized | Geometric sagittal reflection before differences |
| Soft latent-prior IRLS multiplier squared an extra ratio | Incorrect gradient surrogate | Corrected the ratio and documented heuristic clipping |
| Final pose could lag behind final coefficients | Residuals used an outdated pose | Re-estimate pose for final coefficients |
| Fixed-pose LOO labelled like independent validation | Optimistic interpretation of tuning errors | Explicit conditional label; separate outer pose-refitting holdout utility |
| Local deformation defaulted on, used 2-D TPS kernel, lacked input guards | Uncontrolled interpretation and singular systems | Opt-in 3-D polyharmonic kernel, rank/cap checks, separate statistical OBJ |
| Nasal offline diagnostic used skin targets and arbitrary world axes | Anatomically wrong tangent inputs | Bone-only v3 positions; rotate to pose-aligned frame; unavailable when missing |
| Skull import guessed units from bounding-box size | Fragment size could cause a thousandfold scale error | Explicit source-unit choice; no bounding-box heuristic |
| Tissue edits did not update existing targets | Displayed depth differed from fitted geometry | Update target and peg; refuse inconsistent export |
| Persistent Python fitting thread in Blender | Unsupported threading model and shared-state hazards | Serialized optional preview; external process for final fitting |
| File outputs silently overwrote and lacked machine-readable provenance | Weak reproducibility and case tracking | Distinct paths, explicit overwrite, atomic individual files, completion manifest |
| Colour scale's maximum returned yellow | Misleading displacement visualization | Correct red endpoint and numeric displacement/scale |
| Legacy depths/mapping confidence asserted scientific validity without row-level evidence | Unsupported precision and homology claims | Clearly label inherited assumptions; specialist review remains required |

## Not solved by code alone

- Anatomical validation of all 27 bone-to-skin correspondences, including definition/direction of each measurement.
- Tissue tables with appropriate study/cohort/measurement provenance and calibrated individual uncertainty.
- Independent paired-subject accuracy, repeatability, interobserver error, subgroup performance and uncertainty coverage.
- Interactive Blender compatibility, undo/file-load behavior, viewports and external-process UX on the intended OS.
- Guaranteed skull containment, collision-free local warps, anatomically independent eye/lip/nose modelling or recovery of a person's identity.

See [VALIDATION](VALIDATION.md) for acceptance criteria and the distinction between implemented checks and unexecuted validation. The legacy demographic-prior generator and map-builder remain experimental; their historical output claims are not certified by this revision.

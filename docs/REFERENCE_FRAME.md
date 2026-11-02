# A4.2 — explicit anatomical reference frame

This opt-in workflow defines a three-point Frankfort plane from **observed,
reviewed Porion right/left and one explicitly selected Orbitale**. An independently
selected superior cranial median reference disambiguates the orientation. A
separate plane is fitted to at least three selected cranial median references.
No face-fit target, depth, weight, model coefficient or object coordinate changes.

Definitions, Orbitale side, median-point selection and error assumptions require
case-specific expert review. The software does not decide a universal anatomical
protocol. The [extended reference catalogue](EXTENDED_BONE_REFERENCES.md) retains
its unresolved source/definition gates. Do not substitute infraorbital-foramen
markers for the orbital-rim references.

## Configure and compute

In Blender, initialize the extended bone references, place the required points on
registered preserved surfaces and confirm their definitions and positions. Open
**Anatomical Reference Frame (opt-in)**, choose a configuration path and press
**Write Blank Template**. This refuses existing files. Edit the JSON externally,
then press **Compute Reviewed Frame**. For example, the following is a configuration
shape, not a prescribed anatomical protocol:

```json
{
  "schema_version": 1,
  "orbitale": "or_L",
  "superior_code": "b",
  "midline_codes": ["n", "b", "op"],
  "source": "REPLACE with the reviewed case protocol and its source",
  "placement_error": null
}
```

The blank template actually has null Orbitale/superior choices and an empty
midline/source; it cannot compute a frame until configured. Allowed median codes
are `n, g, ba, b, l, o, op, ns, ss`; select a spatially distributed subset appropriate
to preserved anatomy. The superior reference must lie above the selected Frankfort
plane. Mandibular `sm/id/me` cannot determine the cranial midline. Missing,
reconstructed, unreviewed or source-stale references are refused, never mirrored
or replaced automatically. A partial skull without both observed Porion sites
cannot use this protocol. Existing restoration-plane tools remain separate.

Offline, the same NumPy core reads the exported craniometry JSON:

```bash
python -m cranio.reference_frame template --output frame-config.json
# Fill and review frame-config.json before computing.
python -m cranio.reference_frame compute --input craniometry.json --config frame-config.json --output frame.json
```

Output/input collisions and existing output files are refused. Input/configuration
SHA-256 hashes are checked before/after calculation and stored in CLI output.
The implementation hash and NumPy version support numerical traceability.
Coordinates remain world mm throughout.

## Geometry and interpretation

Let `O=(Po_R+Po_L)/2`. The right axis `R` is the unit vector from `Po_L` to `Po_R`.
Remove the component along `R` from `Orbitale-O` and normalize it to give anterior
`A`; superior is `S=R×A`. The independently declared superior control must have a
positive projection on `S`. This rejects an incompatible orientation, including
a simple Porion L/R swap. It cannot certify every possible labelling error.

The frame has right/anterior/superior columns, with origin `O`. The stored 4×4
`frame_to_world` maps frame-mm homogeneous coordinates into world mm;
`world_to_frame` is its inverse. It is a rigid transform, not a similarity fit.
These RAS axes do not change the catalogue's unrelated scalar side labels
(-1 right / +1 left), nor assume a particular orientation of an imported scan.

The midsagittal plane minimizes squared orthogonal distances to the selected
cranial median points using SVD. It is **not forced perpendicular to Frankfort**.
The record reports plane origin/normal, residual RMS in mm, singular values and
the angle between its normal and the frame's right axis. Three Frankfort points
have exactly zero plane residual by construction. Neither that zero nor the
midline RMS estimates anatomical accuracy or a calibrated confidence interval.

Degeneracy checks reuse the existing `fit_reference_plane` engineering gates
(0.1 mm and relative 1e-3 minimum second singular value, provenance:
`legacy_hardcoded`, plus the existing rank check). New vector/singular-gap tests
use 64 machine epsilons solely for numerical degeneracy. They are not published
anatomical plausibility thresholds; close-to-degenerate accepted cases can still
be unreliable and require review.

## Optional placement-error propagation

`placement_error: null` means **not assessed / uncalibrated**, with no invented SD.
To assess conditional sensitivity, provide `samples` (integer ≥2), `seed`
(nonnegative integer), and `points`, an object containing **every used point**.
Each point has `sigma_mm` (finite, nonnegative) and a documented `source`.
The same point used in multiple roles is perturbed only once in each draw.

The model is independent, isotropic Gaussian noise with SD per coordinate in mm.
It is not a radial-distance SD: repeat-placement distances must not be copied
into this field without an explicitly justified conversion. The engine uses a
local PCG64 generator and leaves global random state untouched. It reports origin
coordinate sample SD (ddof=1), the 95th percentile of each axis's angular change,
and the 95th percentile of the midsagittal normal's angular change. These are
conditional perturbation summaries, not empirical 95% coverage claims. If any
sample is invalid the analysis aborts; it does not discard difficult draws and
report a deceptively narrow distribution. All-zero supplied SDs trigger a warning.

No systematic landmark/segmentation error, covariance between placements,
protocol-choice uncertainty or population calibration is inferred. Error inputs
and clinical/anatomical validation remain the operator's responsibility.

## Views, captures and persistence

**Front / 3/4 / Right / Left** orient the 3D view only. The optional **Use reviewed
frame for standardized captures** switch defaults off. When enabled, the existing
capture operator uses the frame, including anatomical superior as camera up, even
when the scan is tilted relative to world axes. Camera framing uses a bounding
sphere about the frame origin. The camera stores the frame JSON for audit.
The previous scene camera is restored if rendering fails. With the switch off,
the existing marker-based capture orientation remains in use.

The cached record persists in the `.blend` Scene property and is embedded under
`reference_frame` in craniometry JSON and CSV v3's `craniometry` metadata. It does
not change CSV skin rows or fit mathematics. Used positions, review/definition,
source geometry hashes and configuration file contents are checked when exporting
or using a view/capture. Changed inputs mark the exported snapshot `stale`; views
and captures refuse it until recomputed. Keep the configuration JSON alongside
the scene; moving/removing it requires updating the path. **Clear Frame** removes
the cache and disables its capture switch. No frame key is added when none exists.
Panel redraw does not compute a frame or hash meshes.

An exported JSON is a snapshot, not a live reference to the original skull.
The offline pipeline preserves it for auditing and does not apply its transform
or independently certify its freshness against a later scan. Recompute through
the frame CLI using a fresh reviewed craniometry export when observations change.

See [task evidence and limitations](TASK_A4_2.md). Synthetic tests verify software
geometry and persistence, not landmark localization or forensic accuracy.

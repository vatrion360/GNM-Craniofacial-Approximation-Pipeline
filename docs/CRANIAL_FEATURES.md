# A4.3 — protocol-defined cranial features

This opt-in workflow exports `skull_features.json`. It measures reviewed bone
observations in world millimetres; it never changes the face, adds fit constraints,
selects population norms or infers a diagnosis. Missing anatomy invalidates only
dependent measurements. The sources and definitions must be reviewed by the operator.

## Blender and offline workflow

The original reference initialization remains **22** rows; extended initialization
remains **34**. **Add Feature Bone References** explicitly initializes **38** by
adding `pr` (Prosthion), `pg` (Pogonion), `go_R` and `go_L`. These reuse bone-site
text already in `paper_reference.py` (Table 2), still requiring case review.
They associate with existing Prosthion_BuzaSup, Pogonion, Gonion_Dr and Gonion_St
markers. They do not add tissue targets or guess GNM vertices. The original
48 tissue sites and 14 chord definitions/skin controls are unchanged.

Place or link bone references using craniometry, then confirm definitions and
positions. Registered source hashes and observed/reconstructed status remain
explicit. Old CSV formats still load; new bone codes require an updated reader.
Do not substitute reconstructed/donor/mirrored observations for preserved bone.

Open **Cranial Features (explicit protocol)**, write a blank protocol JSON,
configure its definitions and sources, select a new output filename and press
**Compute / Export Reviewed Features**. Results also appear in the Blender Text
Editor as `GNM_Cranial_Features`. The panel reports the last export, not a live
measurement. Every new export reads current geometry and review state; redraw
performs no measurement, fitting or hashing. Existing output files are refused.

The same NumPy core is available offline:

```bash
python -m cranio.features template --output feature_config.json
# Configure and review the protocol before computing.
python -m cranio.features compute --input craniometry.json --config feature_config.json --output skull_features.json
```

The CLI checks input hashes before/after computation and refuses existing outputs
and input/output collisions. It records input/configuration/implementation hashes.
Blender records a canonical input-document hash with an explicit hash method and
protects the current scene/model/source/configuration paths. Results include
software/NumPy versions, observations, definitions, sources, units and status.
A snapshot does not certify that a later-edited scan still matches its contents.

## Configuration contract

The template contains `schema_version: 1`, `features`, `frame_config: null`,
`mandible_pose: null`, `uncertainty: null` and `thresholds: null`. All ten feature
rows start with `definition: null`, `source: null`, `reviewed: false`.
`TODO(verify-source)`: supply the anatomical protocol and review before enabling.
No clinical definition or threshold is guessed from a feature name.

Each definition contains exactly `kind`, ordered `points` (canonical bone codes),
and `space` (`3d` or `sagittal`). Keep every template feature ID, even when inactive.

| Feature ID | Supported kinds | Fixed endpoints, where specified |
|---|---|---|
| `gnathic_ratio` | `ratio`, 3D | `[ba, pr, ba, n]` |
| `facial_angle` | `angle`, `line_angle`, `signed_angle` | Operator protocol |
| `anb_angle` | `angle`, `signed_angle` | `[ss, n, sm]` (A–N–B) |
| `pogonion_projection` | `anterior_offset` | `[pg, n]` |
| `mandibular_plane_angle` | `plane_inclination`, `line_inclination` | Operator protocol |
| `gonial_angle_R`, `gonial_angle_L` | `angle`, `line_angle` | Explicit side-specific construction |
| `ramus_height_R`, `ramus_height_L` | `distance`, `superior_span` | Explicit side-specific construction |
| `bigonial_breadth` | `distance`, 3D | `[go_R, go_L]` |

For example, the requested gnathic ratio's mathematical definition is:

```json
{"kind":"ratio","points":["ba","pr","ba","n"],"space":"3d"}
```

It is **Ba–Pr/Ba–N**, dimensionless, without multiplication by 100. Norms expressed
as percentages cannot be copied unchanged. This definition still needs the
operator's source/review and valid bone placements.

Other named features can have several anatomical constructions. A Condylion–Gonion
chord differs from a vertical ramus span; a three-point mandibular plane differs
from a tangent protocol. No default tangent/endpoint choice is supplied. The
actual mathematical definition is always exported. A source string alone does
not establish scientific applicability.

## Exact geometry

For ordered points P0, P1, P2, P3:

| Kind | Computation | Units |
|---|---|---|
| `distance` | norm(P0−P1) | mm |
| `ratio` | norm(P0−P1) / norm(P2−P3) | ratio |
| `angle` | unsigned angle between P0−P1 and P2−P1, 0–180 | degrees |
| `line_angle` | unsigned angle between P1−P0 and P3−P2, 0–180 | degrees |
| `signed_angle` | sagittal atan2(cross-product right component, dot) from P0−P1 to P2−P1, −180–180 | degrees |
| `anterior_offset` | (P0−P1) dotted with frame anterior; positive anterior | mm |
| `superior_span` | absolute (P0−P1) dotted with frame superior | mm |
| `line_inclination` | acute inclination to Frankfort: atan2(abs(superior), horizontal length) | degrees |
| `plane_inclination` | acute angle between normal of P0/P1/P2 and Frankfort normal, 0–90 | degrees |

Plane inclination requires spatial points (`3d`); sagittal projection is refused
for this operation. Degenerate vectors and nonfinite results are not reported
as plausible measurements. Normalized vectors and atan2 reduce angle instability;
epsilon guards are numerical, not anatomical plausibility thresholds.

Frame-dependent kinds and all sagittal definitions require a complete
[A4.2 configuration](REFERENCE_FRAME.md) in `frame_config`. Its `placement_error`
must be null: configure feature errors only once below. The frame is recomputed
from current reviewed observations rather than trusted from cached metadata.
**Sagittal means the Frankfort frame YZ projection**, not the independent fitted
midline plane. Another projection convention requires a separately implemented
protocol. Unsigned 3D ANB and signed projected ANB are not interchangeable.

## Partial skulls and mandibular assumptions

A missing left Gonion leaves bilateral width and dependent left measurements
unavailable without preventing configured right-side measurements. Missing Porion
affects frame-dependent results but not eligible world-3D measurements. Each
result independently checks observation/review/source provenance; no opposite
side is filled automatically.

Any mandibular reference requires a configured
`mandible_pose: {"reviewed": true, "source": "documented case assembly/pose assumption"}`.
Blender also requires **Mandible articulated with cranium**. The conservative
gate includes intrinsic mandibular measurements because separate fragments may
have uncertain assembly. It records an assumption, not proof of correct occlusion.
Articulation tools and pose sensitivity remain A4.5/A4.6 tasks.

## Conditional placement intervals

`uncertainty: null` means no interval. Otherwise provide `samples` (integer ≥2),
`seed` (nonnegative integer), and a `placement` object mapping bone codes to
`{"sigma_mm": null, "source": null}` rows; fill SDs and sources only when justified.
The existing A2 placement validator is reused. SD is per-coordinate isotropic
Gaussian error, **not** a radial repeat-placement distance. Missing SDs withhold
only the dependent intervals; nothing is imputed. Fully specified features may run.

Independent PCG64 streams derive from `[seed, point_order_index]`; the result
records that registry order. Shared points use identical draws across features
and are perturbed once per draw. Global random state is unchanged. Frame geometry
is recomputed per draw, propagating error from its references as well.

Outputs give sample SD (ddof=1) and 2.5th/97.5th percentiles, labelled
`conditional_uncalibrated`, **not calibrated confidence intervals**. An invalid
draw or signed-angle branch crossing withholds the whole affected interval and
records the failed sample; no favourable-sample filtering occurs. All-zero supplied
SDs are flagged, not interpreted as proof of zero anatomical uncertainty.
Systematic/segmentation error, correlated placement, jaw-pose variation and
population calibration are not modelled. These bone-only features do not sample
GNM coefficients or tissue depths.

## Optional descriptive thresholds

Without thresholds, measured rows report `no_thresholds_configured`. Optional
`thresholds` maps feature IDs to `source`, `definition_sha256`, `units`, ordered
finite `cuts`, and `labels` (one more than the cuts). Obtain the definition hash
from the result or `cranio.features.definition_hash(definition)`. Wrong units or
hashes are refused. No cuts, labels or clinical ranges are bundled.

Bins are left-inclusive/right-exclusive; an exact cut belongs to the upper bin.
The nominal measurement gets a `point_label`. An available perturbation interval
crossing bins gets `interval_label: indeterminate`. Missing/failed uncertainty
never produces an interval label. These labels are operator-supplied descriptions,
not diagnoses; a narrow conditional interval does not validate a threshold.

See [task evidence and deviations](TASK_A4_3.md). CT/anatomical validation remains
manual and is not claimed from synthetic software tests.

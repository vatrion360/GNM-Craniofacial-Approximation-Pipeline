# A4.1 — extended bone references and definition review

Implemented on `feature/extended-bone-reference-catalog`, based on
`aa53c5ff570787c247e8011d06af5d8bad516360` (A2.4). Both Python/packaging and Blender
CI for prerequisite PR #24 were verified successful before this task.

## Changes

- `cranio/landmarks.py`: optional 12-position bone-reference catalogue. Side,
  definition/source or null, existing-marker association, frame-only flag and
  unresolved mapping/tissue values are explicit. Original skin-marker lists stay
  unchanged.
- `cranio/craniometry.py`: separate full reference registry; original 22-point
  registry and 14 measurements retained. New A/B aliases cannot create duplicate
  canonical points. Confirmed new records require case definition/source text.
- `cranio/blender_craniometry.py`: explicit initialization to 34 references,
  definition/source UI, review invalidation and export metadata. New references
  never create extra skin markers. Named links reuse the existing marker only.
- `tests/test_extended_references.py`: 25 regression cases including default
  inventories, unresolved definitions, bilateral fragment status, duplicate aliases,
  metadata round-trip and unchanged offline mesh bytes.
- `tools/blender_extended_reference_checks.py` and `tools/blender_smoke.py`: real
  Blender placement/review/reinitialization/link/export checks using the ZIP.
- README option table, `docs/EXTENDED_BONE_REFERENCES.md`, marker-format notes and
  this report.

## Duplicate audit outcome

Supramentale, Infradentale and Menton already have tissue markers. The new orbital
reference entries use the existing Suborbitale definitions, explicitly distinct
from the inherited Infraorbitale foramen markers. These five positions name their
existing markers and cannot create another skin-control row via the new reference
workflow. Basion, Bregma, Opisthocranion and Frontotemporale are already present in
the 22-point bone registry, so no second catalogue entries are created for them.

The 12 additional bone-list positions are ss, sm, id, me, po_R/L, or_R/L, co_R/L
and zm_R/L. Each side can be independently missing, observed or reconstructed.
There is no auto-completion or transfer of reconstructed status to observed.

## Executed software checks (2026-11-02)

| Check | Before | After |
|---|---|---|
| Python suite with official GNM asset | 578 passed, 1 Windows-only skip | 603 passed, 1 Windows-only skip |
| Actual Blender 4.5.0 Linux ZIP/model/external-Python suite | Pass | Pass, including BLENDER_EXTENDED_REFERENCES_PASS |
| Ruff / diff whitespace check | — | Pass |
| Wheel and source distribution build | — | Pass |
| Installed wheel imported outside source checkout | — | 48 tissue sites, 22/34 reference registries, aliases and measurement validation passed |
| Synthetic offline fit with/without extended bone metadata | — | Statistical/final OBJ and displacement PLY bytes identical |

The Blender test verifies standard initialization remains 22, repeated extended
initialization remains 34, existing values survive, no automatic tissue rows are
created, an unconfigured definition cannot be confirmed, editing its source
invalidates review, bone movement invalidates current review, incorrect orbital
marker linkage is refused, clearing a linked reference retains its borrowed bone
object, and JSON/CSV exports retain source/definition/status in world mm.

An initial headless assertion compared RNA collection-entry memory addresses
before/after appending rows. Blender can reallocate the collection, so that was
an invalid test assumption. The corrected test checks retained codes, case values,
exported records and borrowed-object identity instead; the complete gate then
passed. No pointer identity is required by the feature.

Environment: Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, pytest 9.2.0;
Linux x86_64. Blender archive verified against the official checksum manifest.
GNM model SHA-256 remained
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
Local interactive/Windows/anatomical checks were not performed; subsequent PR
CI reports platform integration, not scientific validation.

## Deliberate deviations and pending evidence

- The original request for new tissue markers is implemented as additional bone
  references where the anatomy is not a reviewed skin target. It does not increase
  the 48 skin/tissue marker count or double-weight existing sites.
- No verified definitions for Subspinale, Porion, Condylion or Zygomaxillare were
  supplied for this extension. Their seven positions start with null catalogue
  definitions/sources and empty case fields, with TODO(verify-source). Operator
  definition/source entry is required before confirmation. Existing counterpart
  definitions reuse repository material and remain subject to expert review.
- New GNM candidate generation is deferred for unconfigured sites; guessing a
  skin vertex from an undefined bone point would violate the no-invention rule.
  Existing counterparts retain their current candidate/manual review workflow.
- CSV v3 already exists. No unnecessary format replacement or lossy migrator is
  added. Current software retains new records in existing craniometry metadata;
  older versions may reject new bone codes and must be upgraded for exchange.
- No Frankfort frame, frame uncertainty, jaw articulation, profile constraints or
  new anatomical measurement formula is claimed. A4.2 and subsequent tasks remain
  separate. No empirical anatomical accuracy or CT validation is inferred.

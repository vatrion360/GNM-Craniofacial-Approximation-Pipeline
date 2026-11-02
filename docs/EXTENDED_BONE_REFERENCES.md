# A4.1 — optional extended bone-reference catalogue

The standard lists remain **48 skin/tissue markers, 22 bone references and 14
Table 3 chords**. In Blender, **Add Extended Bone References (+12)** explicitly
extends the bone list to 34 positions. It adds no skin targets, tissue depths,
GNM vertices, measurement constraints or automatic mirroring. The existing fit,
marker-count lambda and 14 measurement controls are unchanged.

## Catalogue and duplicate prevention

| Bone code | Name | Existing skin-marker route |
|---|---|---|
| `ss` (alias `A`) | Subspinale | None configured |
| `sm` (alias `B`) | Supramentale | `Supramentale` |
| `id` | Infradentale | `Infradentale_BuzaInf` |
| `me` | Menton | `Menton`; not `Gnathion` |
| `po_R`, `po_L` | Porion right/left | None configured; reference-frame only |
| `or_R`, `or_L` | Orbitale, using the existing Suborbitale definition | `Suborbitale_Dr`, `Suborbitale_St`; not the infraorbital-foramen markers |
| `co_R`, `co_L` | Condylion right/left | None configured |
| `zm_R`, `zm_L` | Zygomaxillare right/left | None configured |

Basion (`ba`), Bregma (`b`), Opisthocranion (`op`) and bilateral Frontotemporale
(`ft_R`, `ft_L`) already exist in the standard bone registry and are not added
again. The two naming aliases `A`/`ss` and `B`/`sm` canonicalize to one point each;
a document containing both aliases for the same point is rejected as a duplicate.

The five counterpart positions reuse the **existing** paper-reference site
text and its source recorded in this repository. This is a catalogue association
for operator review, not certification of an anatomical correspondence. In
particular, the orbital-rim reference must not be conflated with the inherited
Infraorbitale foramen marker. No new anatomical definition is inferred from a
model vertex or a name.

`cranio.landmarks.BONE_REFERENCE_EXTENSIONS` records each entry's name, side
(-1 right, +1 left, 0 median), definition text/source or null,
`definition_status=needs_expert_review`, existing counterpart, `skin_correspondent`,
`reference_frame_only`, `fit_target=false`, mapping status and catalogue revision.
`skin_correspondent=true` means only that an existing potential marker is named;
it does not certify its skin vertex, thickness, direction or applicability.
Every new entry's `gnm_vertex`, `tissue_depth_mm` and `sd_mm` remain null. Actual
existing marker values stay in the original registry and case, not duplicated here.

## Placement and definition review

1. Open **Cranial Measurements (Table 3)** and press **Add Extended Bone References
   (+12)**. Repeating either initialization button preserves current placements,
   case definitions, sources, notes, tissue controls and review state. The standard
   button never removes extended references already in a saved scene.
2. Choose a reference and **Place Bone Reference** on a registered surface.
   Placement records that source's identity/hash and preserves observed versus
   reconstructed status. The origin is a valid placement; a missing point remains
   missing. Left and right positions are independent.
3. Review the definition and its source. For Subspinale, Porion, Condylion and
   Zygomaxillare, the supplied materials do not provide a verified definition for
   this extension. `TODO(verify-source)`: enter the specialist's definition and
   cited protocol in **Case landmark definition** and **Definition source /
   protocol**. These start empty; the software does not guess.
4. Use **Confirm Definition / Position** only after review. Empty or placeholder
   definitions/sources are refused. Editing either field invalidates confirmation.
   A displaced reference also fails the existing positional review check.
5. For a named existing counterpart, you may instead select the already placed
   skin marker in the main list and press **Link Selected Marker**. This borrows
   its bone object without adding a marker or changing its inclusion/weight/depth.
   Only the catalogued label is accepted for these new entries; other anatomy
   must be placed as a separate bone reference. Confirm the reference separately.

For example, `or_R` can link `Suborbitale_Dr`, but not `Infraorbitale_Dr`.
The linked skin marker may already participate in fitting under its own existing
settings; the bone-reference row adds no extra fitting observation. Clearing the
reference does not delete a borrowed skin marker's bone object.

New references do not use **Create Skin Marker**. This prevents a second tissue
target for the same named site and avoids guessed correspondences for currently
unmapped sites. Those sites show **! no skin mapping**. They remain bone records
only even if a definition is reviewed. The legacy custom-control workflow for
the original references retains its previous explicit review requirements.

## Exports and compatibility

The existing craniometry schema 1 and marker CSV v3 remain in use. New reference
codes are accepted by the current craniometry validator. After opt-in, JSON and
embedded `craniometry` CSV metadata carry the extended points, case definition,
source, review flag, mapping status, existing counterpart, catalogue revision
and `fit_target=false`. Bone source hashes/status and world-mm coordinates use
the existing fields. No bone-only record is added to the CSV's skin-target rows.

Old CSVs and documents remain readable, and standard initialization produces
the same original point records. Older software versions do not know the new
reference codes and may refuse an extended document: use the updated package
when exchanging these cases. Do not rename a bone-reference row into a skin
CSV target or invent a vertex index to bypass that check.

The offline pipeline validates and retains the records. It continues to measure
only the original 14 chords and uses only explicitly enabled existing skin
controls. A synthetic regression confirms byte-identical statistical/final OBJ
and displacement PLY output with and without the extended bone metadata.

## Limits and next stage

This task does not compute a Frankfort frame, generate new GNM candidate maps,
calculate jaw/prognathism features or validate anatomical placement. Those belong
to subsequent tasks. Null definitions/mappings are deliberate pending scientific
inputs, not anatomical estimates. A reviewed location on reconstructed bone is
still reconstructed evidence, and missing opposite-side anatomy is not filled.
See [execution and deviations](TASK_A4_1.md).

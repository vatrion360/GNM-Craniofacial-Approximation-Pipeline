# PDF-based marker protocol (add-on 15 / 5.0.0rc2)

Source: Gizeh Rangel-de Lazaro, Naomi González, Adrián Martínez-Fernández, Armando Rangel-Rivero and Alfonso Benito-Calvo (2026). *A face from the pre-Columbian Caribbean: methodological pipeline for 3D facial approximation of an individual with intentional cranial modification*. Virtual Archaeology Review 17(34), 26-41. https://doi.org/10.4995/var.2024.24796

The supplied `VAR17(34)_24796.pdf` was checked as text and visually: Table 2 on printed p.30 (PDF page 5), Figure 3 on p.31, the methods on pp.29-31 and limitations on pp.34-36. File SHA-256: `f9e2de637946e90a19297351a2f39c9829f92942e0f0174ef5e906aa66b450fd`. The PDF itself is not redistributed here.

## What is implemented

Table 2 has **21 types**, expanding to **32 positions: 10 median + 11 bilateral pairs**. Their union with the inherited 27 markers is **48 distinct sites**, including **21 newly added positions**. This avoids conflating the inferior orbital rim with the infraorbital foramen, the lateral-orbit tissue site with the canthus, or menton with gnathion.

The GUI and pipeline now share one registry. The GUI offers Extended 48, Paper 32 and Legacy 27 sets. On an existing scene, **Add Missing Markers** only adds absent rows; placed objects, depths and manual vertex choices survive. Choosing a smaller set does not delete existing rows. Deselect **Include in fit** for documentation-only landmarks.

A fresh Paper 32 set receives the table's depths. In Extended 48, the original 27 depth defaults remain unchanged and the additional 21 positions receive their cited table values. **Apply Table 2 Tissue Depths** explicitly replaces values at all available paper sites, updates placed skin targets and records the source. It supports Undo. Recheck direction after changing depth: the same ray is retained, not inferred anew from the paper.

The table applies to landmark depths. Optional dense surface constraints use separate regional offsets; they do not inherit this table. Keep dense fitting disabled unless those offsets and their applicability have been reviewed independently.

## Tissue reference and applicability

The paper used a **normal-female Southwestern Native American reference**, attributed to unpublished Rhine (1983) data via Taylor (2001), because dedicated data for the Caribbean case were unavailable. These are reference distances, not measurements from the reconstructed person or universal values. The article provides no standard deviations in Table 2, so the code invents none. Numerical weights are relative fitting controls, not inverse-variance estimates.

| Table row | Implemented site(s) | Depth (mm) | Placement definition (paraphrased) |
| --- | --- | ---: | --- |
| 1 (sg) | `Supraglabella` | 4.5 | Midline depression immediately superior to glabella. |
| 2 (g) | `Glabella` | 4.5 | Most anterior midline point of frontal bone above the nasal root. |
| 3 (n) | `Nasion` | 7 | Midline junction of the nasofrontal sutures. |
| 4 (rhi) | `Rhinion` | 2.5 | Inferior midline end of the internasal suture at the bone/cartilage boundary. |
| 5 (mp) | `Midphiltrum` | 10 | Projection of the midpoint of the philtral column; see the placement caveat. |
| 6 (pr) | `Prosthion_BuzaSup` | 11 | Most anterior midline point of the maxillary alveolar process, on bone. |
| 7 (id) | `Infradentale_BuzaInf` | 12.25 | Superior midline alveolar point between the mandibular central incisors. |
| 8 (sm) | `Supramentale` | 10 | Deepest midline depression above the mandibular mental prominence. |
| 9 (pg) | `Pogonion` | 13 | Most anterior midline point of the bony chin. |
| 10 (me) | `Menton` | 8 | Lowest midline point of the mandibular symphysis; distinct from gnathion. |
| 11 (fe) | `FrontalEminence_Dr`, `FrontalEminence_St` | 4 | Lateral frontal eminence above the eyebrow midpoint, between metopion and ophryon levels. |
| 12 (mso) | `Supraorbitale_Dr`, `Supraorbitale_St` | 8.5 | Highest point of the superior orbital rim. |
| 13 (or) | `Suborbitale_Dr`, `Suborbitale_St` | 6.25 | Lowest point of the inferior orbital rim; NOT the infraorbital foramen. |
| 14 (im) | `InferiorMalar_Dr`, `InferiorMalar_St` | 12 | Lower maxillary surface aligned vertically with the superior/inferior orbital reference points. |
| 15 (lo) | `LateralOrbit_Dr`, `LateralOrbit_St` | 11.5 | Point 10 mm inferior to the orbit along its lateral margin's vertical line; NOT the lateral canthus. |
| 16 (zy) | `Zygion_Dr`, `Zygion_St` | 7 | Maximum lateral extent of the zygomatic arch, located instrumentally. |
| 17 (sgl) | `Supraglenoid_Dr`, `Supraglenoid_St` | 6.25 | Root of the zygomatic arch anterior to the tragus. |
| 18 (go) | `Gonion_Dr`, `Gonion_St` | 10.5 | Posteroinferior mandibular angle between body and ramus. |
| 19 (ecm2_sup) | `SupraM2_Dr`, `SupraM2_St` | 18 | Lateral buccal alveolar margin at the centre of the maxillary second molar. |
| 20 (mm) | `Midmasseter_Dr`, `Midmasseter_St` | 17.5 | Occlusal-plane point at the centre of the mandibular ramus. |
| 21 (ecm2_inf) | `SubM2_Dr`, `SubM2_St` | 17 | Lateral buccal alveolar margin at the centre of the mandibular second molar. |

Table 2 defines Midphiltrum using a soft-tissue feature. A specialist must review its projection onto bone and measurement direction; do not click an existing skin point and add tissue thickness a second time. Menton needs an inferior target direction. A local mesh normal is only an initial construction and may differ from the original study's measurement direction.

## GNM candidates and the Pogonion correction

**The article contains no GNM vertex map.** New skin-surface candidates were selected on the pinned neutral GNM exterior in model-mm coordinates, then checked for uniqueness, side and exact topological mirror pairing. They are displayed as needing review. This engineering check does not establish bone/skin homology. Inspect each candidate on the live model and use manual vertex selection where needed. New sites start at relative weight 0.5; operators can change weight or exclude them.

The inherited Pogonion index **12284 belongs to GNM's `lower_lip` group**, confirmed by the asset and front/profile inspection. The default Pogonion candidate is now **12261** on the chin. Index 12284 is used for the lower-lip target associated with Infradentale. Existing explicit v3 vertex fields and Blender manual overrides are preserved; they are not silently rewritten by the CSV reader. Legacy encoded CSVs still decode labels and then use the current candidate map. Revalidate old cases after this correction.

| Additional site | GNM vertex candidate |
| --- | ---: |
| `Supraglabella` | 12335 |
| `Midphiltrum` | 12274 |
| `Infradentale_BuzaInf` | 12284 |
| `Supramentale` | 12266 |
| `Menton` | 12346 |
| `FrontalEminence_Dr` | 7073 |
| `FrontalEminence_St` | 945 |
| `Suborbitale_Dr` | 10880 |
| `Suborbitale_St` | 4752 |
| `InferiorMalar_Dr` | 7529 |
| `InferiorMalar_St` | 1401 |
| `LateralOrbit_Dr` | 7600 |
| `LateralOrbit_St` | 1472 |
| `Supraglenoid_Dr` | 11114 |
| `Supraglenoid_St` | 4986 |
| `SupraM2_Dr` | 7491 |
| `SupraM2_St` | 1363 |
| `Midmasseter_Dr` | 11258 |
| `Midmasseter_St` | 5130 |
| `SubM2_Dr` | 10025 |
| `SubM2_St` | 3897 |

## Damaged or intentionally modified crania

The article describes missing dentition and digitally repaired bone. The add-on therefore records **observed**, **digitally repaired**, **inferred**, or **not recorded** provenance per site, plus placement/direction notes. Repaired and inferred points used in fitting are flagged in the offline report. These categories do not change weights automatically: their uncertainty is unknown.

A case-level cranial-modification field triggers a report warning about the general GNM identity model's applicability. Vault or damaged sites can be retained for documentation while excluded from both preview and offline pose/identity fitting. Their coordinates remain in CSV/JSON; exclusion is not a substitute for a model that represents the altered anatomy. Keep the original scan and restoration history.

## What the article does not validate here

This update implements the landmark/tissue-reference and provenance workflow. It does not reproduce the article's manually sculpted Manchester musculature, its alternative nasal methods, artistic features or final rendering. Its eyeball/canthus measurements and nasal rules are not automatically imposed on every case. The existing Gerasimov diagnostic remains a separate experimental method, not the article's selected nasal method.

The paper is a case study, not independent validation of this GNM pipeline. More markers do not by themselves improve accuracy: inaccurate correspondences, inappropriate tissue directions or repeated correlated constraints can worsen the result. Review regional residuals and perform independent validation on paired skull/face data before claiming accuracy. Skin, hair and iris pigmentation are not inferred from skull geometry.

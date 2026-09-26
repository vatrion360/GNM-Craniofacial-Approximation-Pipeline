"""Transcription of Table 2, Rangel-de Lazaro et al. (2026), pp. 29-31.

21 anatomical types expand to 32 positions (10 midline + 11 bilateral).
Depths are the paper's normal-female Southwestern Native American reference,
attributed there to unpublished Rhine (1983) data via Taylor (2001). They are
not universal defaults, a Caribbean dataset, or GNM vertex correspondences.
Definitions below are paraphrased; consult the paper and primary definitions.
"""

DOI = "10.4995/var.2024.24796"
REFERENCE_ID = "var2026_table2"
CITATION = "Rangel-de Lazaro et al. 2026, Table 2 p.30; DOI:" + DOI
TISSUE_SOURCE = CITATION + "; normal female; Southwestern Native American; Rhine 1983 via Taylor 2001"
APPLICABILITY = "Case-study reference: review population, individual variation and measurement direction."

# row, abbreviation, labels, depth_mm, placement definition
TABLE2 = (
    (1, "sg", ("Supraglabella",), 4.5, "Midline depression immediately superior to glabella."),
    (2, "g", ("Glabella",), 4.5, "Most anterior midline point of frontal bone above the nasal root."),
    (3, "n", ("Nasion",), 7.0, "Midline junction of the nasofrontal sutures."),
    (4, "rhi", ("Rhinion",), 2.5, "Inferior midline end of the internasal suture at the bone/cartilage boundary."),
    (5, "mp", ("Midphiltrum",), 10.0, "Projection of the midpoint of the philtral column; see the placement caveat."),
    (6, "pr", ("Prosthion_BuzaSup",), 11.0, "Most anterior midline point of the maxillary alveolar process, on bone."),
    (7, "id", ("Infradentale_BuzaInf",), 12.25, "Superior midline alveolar point between the mandibular central incisors."),
    (8, "sm", ("Supramentale",), 10.0, "Deepest midline depression above the mandibular mental prominence."),
    (9, "pg", ("Pogonion",), 13.0, "Most anterior midline point of the bony chin."),
    (10, "me", ("Menton",), 8.0, "Lowest midline point of the mandibular symphysis; distinct from gnathion."),
    (11, "fe", ("FrontalEminence_Dr", "FrontalEminence_St"), 4.0, "Lateral frontal eminence above the eyebrow midpoint, between metopion and ophryon levels."),
    (12, "mso", ("Supraorbitale_Dr", "Supraorbitale_St"), 8.5, "Highest point of the superior orbital rim."),
    (13, "or", ("Suborbitale_Dr", "Suborbitale_St"), 6.25, "Lowest point of the inferior orbital rim; NOT the infraorbital foramen."),
    (14, "im", ("InferiorMalar_Dr", "InferiorMalar_St"), 12.0, "Lower maxillary surface aligned vertically with the superior/inferior orbital reference points."),
    (15, "lo", ("LateralOrbit_Dr", "LateralOrbit_St"), 11.5, "Point 10 mm inferior to the orbit along its lateral margin's vertical line; NOT the lateral canthus."),
    (16, "zy", ("Zygion_Dr", "Zygion_St"), 7.0, "Maximum lateral extent of the zygomatic arch, located instrumentally."),
    (17, "sgl", ("Supraglenoid_Dr", "Supraglenoid_St"), 6.25, "Root of the zygomatic arch anterior to the tragus."),
    (18, "go", ("Gonion_Dr", "Gonion_St"), 10.5, "Posteroinferior mandibular angle between body and ramus."),
    (19, "ecm2_sup", ("SupraM2_Dr", "SupraM2_St"), 18.0, "Lateral buccal alveolar margin at the centre of the maxillary second molar."),
    (20, "mm", ("Midmasseter_Dr", "Midmasseter_St"), 17.5, "Occlusal-plane point at the centre of the mandibular ramus."),
    (21, "ecm2_inf", ("SubM2_Dr", "SubM2_St"), 17.0, "Lateral buccal alveolar margin at the centre of the mandibular second molar."),
)

PAPER_LABELS = tuple(label for _, _, labels, _, _ in TABLE2 for label in labels)
PAPER_DEPTHS = {label: depth for _, _, labels, depth, _ in TABLE2 for label in labels}
PAPER_DEFINITIONS = {label: definition for _, _, labels, _, definition in TABLE2 for label in labels}
PAPER_ROWS = {label: row for row, _, labels, _, _ in TABLE2 for label in labels}

CAVEATS = {
    "Midphiltrum": "Table 2 defines a soft-tissue site. Its projection onto bone and the target direction require operator review; do not click soft tissue and add depth again.",
    "Menton": "An inferior point/direction, not a forward chin target. Do not substitute the legacy Gnathion marker.",
    "Suborbitale_Dr": "The paper's orbital-rim site differs from the inherited Infraorbitale foramen marker.",
    "Suborbitale_St": "The paper's orbital-rim site differs from the inherited Infraorbitale foramen marker.",
}


def reference_metadata():
    return {"id": REFERENCE_ID, "doi": DOI, "table": 2, "printed_page": 30,
            "pdf_page": 5, "types": 21, "positions": 32,
            "population": "Southwestern Native American reference used in a Cuban case study",
            "sex_category": "female", "body_build_category": "normal",
            "original_data": "Rhine 1983, unpublished; cited via Taylor 2001",
            "applicability": APPLICABILITY, "gnm_correspondences_in_paper": False}

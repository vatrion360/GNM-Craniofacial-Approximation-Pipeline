# -*- coding: utf-8 -*-
"""Registru anatomic UNIC pentru landmarkurile craniofaciale.

Sursa de adevar partajata de addon-ul Blender (addon_v12.py) si de
pipeline-ul de reconstructie (gnm_reconstruct.py). Contine NUMAI date
anatomice independente de modelul statistic: etichete, latura, adancimi
de tesut, ponderi de incredere, perechi pentru verificari de consistenta,
hinturi de plasare, grupuri protejate si offseturi de regiuni dense.

Legatura dintre etichete si indecsii de vertex ai unui model concret
(ex. GNM Head v3.0) NU sta aici - este responsabilitatea backend-ului
(vezi cranio.backend.gnm_backend).

The original numeric defaults are inherited heuristics without row-level traceability.
Additional v15 sites use the cited case-study reference in paper_reference.py.
They are NOT certified transcriptions of the cited tissue-depth literature.
Weights are relative influence controls, not probabilities or inverse variances.
See docs/SCIENCE.md and docs/SPECIALIST_WORKFLOW.md before casework.
"""

# Eticheta -> (adancime_tesut_mm, latura)
# latura: -1 = dreapta subiectului (_Dr), +1 = stanga (_St), 0 = median.
LANDMARK_INFO = {
    "Nasion": (6.0, 0), "Rhinion": (3.0, 0), "Glabella": (5.0, 0),
    "Pogonion": (10.0, 0), "Gnathion": (10.5, 0),
    "Gonion_Dr": (13.0, -1), "Gonion_St": (13.0, 1),
    "Orbita_Dr_Ext": (8.0, -1), "Orbita_St_Ext": (8.0, 1),
    "Orbita_Dr_Int": (6.0, -1), "Orbita_St_Int": (6.0, 1),
    "Supraorbitale_Dr": (7.0, -1), "Supraorbitale_St": (7.0, 1),
    "Infraorbitale_Dr": (7.0, -1), "Infraorbitale_St": (7.0, 1),
    "Zygion_Dr": (8.5, -1), "Zygion_St": (8.5, 1),
    "Alare_Dr": (4.5, -1), "Alare_St": (4.5, 1),
    "Eurion_Dr": (5.0, -1), "Eurion_St": (5.0, 1),
    "Vertex_VarfCap": (5.5, 0),
    "Nasospinale_BazaNas": (11.0, 0), "Prosthion_BuzaSup": (12.0, 0),
    # V13.6: pentru diagnosticul de proiectie nazala (Gerasimov/Ullrich-
    # Stephan). Adancimi orientative (de calibrat la validarea pe cazuri):
    # Acanthion ~ zona subnasale; Piriform ~ tesutul nazolabial de pe
    # marginea inferioara a aperturei.
    "Acanthion": (10.0, 0),
    "Piriform_Dr": (6.5, -1), "Piriform_St": (6.5, 1),
}

# Ordinea canonica (cea din addonul V12) - folosita la initializarea
# listei de markeri in Blender si la documentatie.
LANDMARK_ORDER = [
    "Nasion", "Rhinion", "Glabella", "Pogonion", "Gnathion",
    "Gonion_Dr", "Gonion_St", "Orbita_Dr_Ext", "Orbita_St_Ext",
    "Orbita_Dr_Int", "Orbita_St_Int", "Supraorbitale_Dr",
    "Supraorbitale_St", "Infraorbitale_Dr", "Infraorbitale_St",
    "Zygion_Dr", "Zygion_St", "Alare_Dr", "Alare_St",
    "Eurion_Dr", "Eurion_St", "Vertex_VarfCap",
    "Nasospinale_BazaNas", "Prosthion_BuzaSup",
    "Acanthion", "Piriform_Dr", "Piriform_St",
]

# Ponderi de incredere per landmark (pentru alinierea/fitul ponderat).
# Markerii ososi precisi primesc 1.0; cei cu pozitie mai putin riguroasa
# sau cu tesut moale gros/variabil primesc mai putin.
CONFIDENCE_WEIGHTS = {
    "Nasion": 1.0, "Rhinion": 1.0, "Glabella": 1.0,
    "Pogonion": 1.0, "Gnathion": 1.0,
    "Gonion_Dr": 1.0, "Gonion_St": 1.0,
    "Orbita_Dr_Ext": 1.0, "Orbita_St_Ext": 1.0,
    "Orbita_Dr_Int": 1.0, "Orbita_St_Int": 1.0,
    "Supraorbitale_Dr": 0.5, "Supraorbitale_St": 0.5,
    "Infraorbitale_Dr": 0.7, "Infraorbitale_St": 0.7,
    "Zygion_Dr": 1.0, "Zygion_St": 1.0,
    "Alare_Dr": 0.7, "Alare_St": 0.7,
    "Eurion_Dr": 0.5, "Eurion_St": 0.5,
    "Vertex_VarfCap": 0.5, "Nasospinale_BazaNas": 1.0,
    "Prosthion_BuzaSup": 1.0,
    # V13.6: puncte osoase bine definite pe craniu, dar cu corespondenta
    # aproximativa pe template-ul de piele -> sub ponderea markerilor osoși
    # precisi (1.0).
    "Acanthion": 0.7,
    "Piriform_Dr": 0.6, "Piriform_St": 0.6,
}

DEFAULT_CONFIDENCE = 0.7

# Perechi de referinta pentru verificarea consistentei plasarii markerilor:
# bilaterale (latime) + lantul median facial (inaltime/profundime).
CONSISTENCY_PAIRS = [
    ("Orbita_Dr_Int", "Orbita_St_Int"),
    ("Orbita_Dr_Ext", "Orbita_St_Ext"),
    ("Infraorbitale_Dr", "Infraorbitale_St"),
    ("Supraorbitale_Dr", "Supraorbitale_St"),
    ("Zygion_Dr", "Zygion_St"),
    ("Gonion_Dr", "Gonion_St"),
    ("Eurion_Dr", "Eurion_St"),
    ("Alare_Dr", "Alare_St"),
    ("Nasion", "Rhinion"),
    ("Rhinion", "Nasospinale_BazaNas"),
    ("Nasospinale_BazaNas", "Prosthion_BuzaSup"),
    ("Prosthion_BuzaSup", "Pogonion"),
    ("Pogonion", "Gnathion"),
    ("Nasion", "Pogonion"),
    ("Orbita_Dr_Int", "Infraorbitale_Dr"),
    ("Orbita_St_Int", "Infraorbitale_St"),
    ("Piriform_Dr", "Piriform_St"),
]

# Indicatii de plasare corecta pentru markerii frecvent gresiti (apar in
# avertismente, ca ajutor pentru re-plasarea in Blender). Textele sunt in
# engleza (ajung in rapoarte).
PLACEMENT_HINTS = {
    "Orbita_Dr_Int": "the dacryon bony point (medial rim of the orbit), "
                     "not the center of the orbit/eyeball",
    "Orbita_St_Int": "the dacryon bony point (medial rim of the orbit), "
                     "not the center of the orbit/eyeball",
    "Infraorbitale_Dr": "the infraorbital foramen (below the orbital rim, "
                        "on the vertical of the pupil)",
    "Infraorbitale_St": "the infraorbital foramen (below the orbital rim, "
                        "on the vertical of the pupil)",
    "Rhinion": "midpoint of the nasal bones (~25 mm below Nasion), on bone",
    "Pogonion": "the anterior mental prominence (~35 mm above Gnathion), "
                "not the lower border of the mandible",
    "Prosthion_BuzaSup": "the lower border of the upper lip, on the midline",
    "Acanthion": "tip of the anterior nasal spine (midline, at the base of "
                 "the septum), on bone - NOT on the cartilaginous septum",
    "Piriform_Dr": "the lower border of the piriform aperture (on bone), "
                   "medial to the base of the nasal ala",
    "Piriform_St": "the lower border of the piriform aperture (on bone), "
                   "medial to the base of the nasal ala",
}

# Grupuri de vertecsi fara ancore anatomice (niciun landmark, nici os
# direct): campul TPS interpolat le deformeaza nerealist -> amortizate.
PROTECTED_GROUPS = ("eyes", "eye_interiors", "mouth_sock",
                    "upper_lip", "lower_lip")

# Offseturi per regiune faciala (mm) - preluate din tabelul de adancimi de
# tesut (aceeasi sursa ca LANDMARK_INFO), deci consistente cu baturile
# markerilor. Folosite de constrangerile dense faciale (--skull).
REGION_OFFSETS_MM = {
    "brow_median": 5.0,        # ~ Glabella
    "punte_nazala": 3.0,       # ~ Rhinion
    "zigomatic": 8.5,          # ~ Zygion
    "infraorbital": 7.0,       # ~ Infraorbitale
    "barbie": 10.0,            # ~ Pogonion
}

# Geometria regiunii dense "punte_nazala" (V13.3, corectata).
# Puntea osoasa se afla pe segmentul Nasion -> pronasale (vertex 12296),
# la ~45% din lungime (oasele nazale ocupa jumatatea superioara a nasului
# extern). Centrul patch-ului este interpolat acolo, cu raza de 14 mm, iar
# tot ce e sub 6 mm deasupra varfului este exclus (cartilaj/apertura).
# Istoric: pana in V13.3 patch-ul era centrat direct pe pronasale (sub
# numele eronat "Rhinion" - quirk corectat separat in V13.4 prin remaparea
# Rhinion -> 12310), deci constrangea apertura, nu puntea osoasa.
NOSE_BRIDGE_RADIUS_MM = 14.0    # raza patch-ului pe puntea osoasa
NOSE_BRIDGE_CENTER_FRAC = 0.45  # pozitia centrului pe Nasion -> pronasale
NOSE_BRIDGE_TIP_CUT_MM = 6.0    # exclude vertecsii sub varf+6 mm (cartilaj)


def side_of(label: str) -> int:
    """-1 pentru *_Dr (dreapta), +1 pentru *_St (stanga), 0 altfel."""
    if label.endswith("_Dr"):
        return -1
    if label.endswith("_St"):
        return 1
    return 0


def pair_label(label: str):
    """Eticheta perechii contralaterale (Dr<->St) sau None pentru mediani."""
    if "_Dr" in label:
        return label.replace("_Dr", "_St")
    if "_St" in label:
        return label.replace("_St", "_Dr")
    return None


def bilateral_pairs():
    """Lista de perechi (dr, st) ordonate, derivata din LANDMARK_INFO."""
    pairs = []
    for label in LANDMARK_ORDER:
        if label.endswith("_Dr"):
            st = pair_label(label)
            if st in LANDMARK_INFO:
                pairs.append((label, st))
    return pairs


# v15: union of the inherited 27 and the paper's 32 spatial positions.
# Do not collapse orbital-rim/foramen, lateral-orbit/canthus or menton/gnathion.
from .paper_reference import PAPER_LABELS, PAPER_DEPTHS, PAPER_DEFINITIONS, TISSUE_SOURCE

LEGACY_LANDMARK_ORDER = tuple(LANDMARK_ORDER)
ADDED_LANDMARKS = tuple(label for label in PAPER_LABELS if label not in LANDMARK_INFO)
for _label in ADDED_LANDMARKS:
    LANDMARK_INFO[_label] = (PAPER_DEPTHS[_label], side_of(_label))
    LANDMARK_ORDER.append(_label)
    CONFIDENCE_WEIGHTS[_label] = 0.5  # relative influence, not statistical confidence
PLACEMENT_HINTS.update(PAPER_DEFINITIONS)
for _label in ADDED_LANDMARKS:
    if _label.endswith('_Dr'):
        CONSISTENCY_PAIRS.append((_label, pair_label(_label)))
CONSISTENCY_PAIRS.extend([('Nasion', 'Menton'), ('Pogonion', 'Menton'),
                          ('Prosthion_BuzaSup', 'Infradentale_BuzaInf')])


def marker_labels(marker_set='EXTENDED_48'):
    sets = {'EXTENDED_48': tuple(LANDMARK_ORDER), 'PAPER_32': PAPER_LABELS,
            'LEGACY_27': LEGACY_LANDMARK_ORDER}
    if marker_set not in sets:
        raise ValueError(f'Unknown marker set: {marker_set}')
    return sets[marker_set]


def initial_tissue_source(label):
    # Existing defaults are preserved; only newly introduced rows inherit
    # paper depths automatically. Applying the whole table is a separate UI action.
    return TISSUE_SOURCE if label in ADDED_LANDMARKS else 'legacy-unvalidated'

# -*- coding: utf-8 -*-
"""Backend GNM Head v3.0 (Google).

Incarca ``gnm_head.npz`` direct (fara pachetul gnm complet): cu expresie
si rotatii zero, mesh-ul GNM este exact liniar in coeficientii de
identitate, deci sunt suficiente template-ul si baza din fisier.

Contine si tabelele de legatura eticheta-anatomica <-> vertex GNM
(candidati mosteniti; necesita revizuire anatomica), inclusiv codificarile legacy
ale addon-urilor Blender v11/v12 pentru decodarea CSV-urilor vechi.
"""

import os
from typing import Dict

import numpy as np

from .base import FaceModelBackend, FaceModelData

OFFICIAL_V3_SHA256 = "e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de"
MAPPING_REVISION = "gnm-v3-candidates-15"

# ---------------------------------------------------------------------------
# TABELE DE CORESPONDENTA LANDMARKURI (GNM Head v3.0, skin)
# ---------------------------------------------------------------------------
# Tabelul original din addon_v11.py: (vertex_id_declarat, eticheta, is_exact).
# Codificarea in CSV: -(vid+1) daca is_exact, altfel vid pozitiv.
# Este pastrat DOAR pentru decodarea CSV-urilor exportate cu addon v11
# (index -> eticheta); mai multi indecsi din acest tabel sunt gresiti anatomic
# (vezi tabelul corectat LABEL_TO_VERTEX de mai jos).
LANDMARKS_V11 = [
    (12319, "Nasion", True), (12296, "Rhinion", True),
    (12337, "Glabella", True), (12284, "Pogonion", True),
    (12258, "Gnathion", True), (11165, "Gonion_Dr", True),
    (5037, "Gonion_St", True), (7426, "Orbita_Dr_Ext", True),
    (1298, "Orbita_St_Ext", True), (11027, "Orbita_Dr_Int", True),
    (4899, "Orbita_St_Int", True), (7566, "Supraorbitale_Dr", True),
    (1438, "Supraorbitale_St", True), (9903, "Infraorbitale_Dr", True),
    (3775, "Infraorbitale_St", True), (10603, "Zygion_Dr", True),
    (4475, "Zygion_St", True), (9901, "Alare_Dr", True),
    (3773, "Alare_St", True), (8565, "Eurion_Dr", True),
    (2437, "Eurion_St", True), (12398, "Vertex_VarfCap", True),
    (33, "Nasospinale_BazaNas", False), (51, "Prosthion_BuzaSup", False),
]

# Tabelul din addon_v12.py (indecsi corectati anatomic, toti is_exact=True),
# cu corectia V13.4: Rhinion 12296 -> 12310 (vezi nota de la LABEL_TO_VERTEX).
# CSV-urile vechi cu -(12296+1) raman decodabile prin LANDMARKS_V11.
LANDMARKS_V12 = [
    (12319, "Nasion"), (12310, "Rhinion"), (12337, "Glabella"),
    (12284, "Pogonion"), (12258, "Gnathion"), (8737, "Gonion_Dr"),
    (2609, "Gonion_St"), (7426, "Orbita_Dr_Ext"), (1298, "Orbita_St_Ext"),
    (11027, "Orbita_Dr_Int"), (4899, "Orbita_St_Int"),
    (7566, "Supraorbitale_Dr"), (1438, "Supraorbitale_St"),
    (9903, "Infraorbitale_Dr"), (3775, "Infraorbitale_St"),
    (10002, "Zygion_Dr"), (3874, "Zygion_St"), (10105, "Alare_Dr"),
    (3977, "Alare_St"), (7765, "Eurion_Dr"), (1637, "Eurion_St"),
    (12398, "Vertex_VarfCap"), (12298, "Nasospinale_BazaNas"),
    (12276, "Prosthion_BuzaSup"),
    (12297, "Acanthion"), (10215, "Piriform_Dr"), (4087, "Piriform_St"),
]

# Inherited label-to-skin-vertex candidates for GNM v3.0.
# Historical selection notes below do not establish anatomical validity.
# iBUG skin landmarks cannot by themselves validate bone-to-skin mappings.
# See docs/SCIENCE.md; original template-based rationale follows:
#   * 11165/5037 (v11 Gonion) sunt punctele dlib 0/16 de sus de pe linia
#     mandibulei (langa ureche), NU unghiul gonial -> inlocuiti cu 8737/2609
#     (regiunea dlib 5/13, bigonial ~129 mm pe template).
#   * 10603/4475 si 8565/2437 (v11 Zygion/Eurion) sunt in vertex-group-ul
#     "ears" (pavilionul urechii) -> inlocuiti cu 10002/3874 (regiunea
#     zigomatica, 135.4 mm) si 7765/1637 (eminentele parietale, 155.6 mm).
#   * 9901/3773 (v11 Alare) prea laterali (+-29.9 mm) -> 10105/3977
#     (dlib 31/35, +-16.8 mm).
#   * 33/51 (v11 Nasospinale/Prosthion) sunt pe gat, sub barbie ->
#     12298 (subnasale, median) si 12276 (labrale superius, median).
#   * V13.4: Rhinion 12296 -> 12310. Vertexul 12296 este iBUG 30 =
#     PRONASALE (varful nasului, 43.8 mm sub Nasion), NU rhinion-ul
#     craniometric (mijlocul oaselor nazale); 12310 este iBUG 29 (puntea
#     nazala osoasa, 25.1 mm sub Nasion, median, oglinda exacta).
#     12296 ramane disponibil ca punct anatomic "pronasale" in
#     landmark_vertex_map.json.
#   * V13.6: Acanthion + Piriform_Dr/St pentru diagnosticul de proiectie
#     nazala (Gerasimov, interpretarea Ullrich & Stephan 2011). Pe
#     template-ul de PIELE corespund: 12297 = punctul median imediat sub
#     subnasale (1.5 mm, proiectia spinei nazale anterioare); 10215/4087 =
#     pereche oglinda exacta la +-12.4 mm de planul median, la nivelul
#     subnasale -- proiectia marginii inferioare a aperturei piriforme
#     (semi-latime ~12.5 mm a aperturei osoase adulte). Selectie:
#     historical template inspection (selection script was not committed).
# Toate perechile bilaterale sunt oglinzi topologice exacte (mirror_indices);
# pozitional, template-ul are o micro-asimetrie (< 0.05 mm).
LABEL_TO_VERTEX = {
    "Nasion": 12319, "Rhinion": 12310, "Glabella": 12337,
    "Pogonion": 12284, "Gnathion": 12258,
    "Gonion_Dr": 8737, "Gonion_St": 2609,
    "Orbita_Dr_Ext": 7426, "Orbita_St_Ext": 1298,
    "Orbita_Dr_Int": 11027, "Orbita_St_Int": 4899,
    "Supraorbitale_Dr": 7566, "Supraorbitale_St": 1438,
    "Infraorbitale_Dr": 9903, "Infraorbitale_St": 3775,
    "Zygion_Dr": 10002, "Zygion_St": 3874,
    "Alare_Dr": 10105, "Alare_St": 3977,
    "Eurion_Dr": 7765, "Eurion_St": 1637,
    "Vertex_VarfCap": 12398, "Nasospinale_BazaNas": 12298,
    "Prosthion_BuzaSup": 12276,
    "Acanthion": 12297,
    "Piriform_Dr": 10215, "Piriform_St": 4087,
}

# v15 candidates selected on the neutral exterior, with bilateral pairs from
# mirror_indices. They are not correspondences supplied/validated by Table 2.
# Inspection also found the inherited Pogonion 12284 inside GNM's lower_lip
# group; 12261 is the reviewed chin candidate. Explicit CSV/manual indices
# remain authoritative. See docs/PDF_PROTOCOL.md for evidence and limitations.
LABEL_TO_VERTEX['Pogonion'] = 12261
ADDED_VERTEX_CANDIDATES = {
    'Supraglabella': 12335, 'Midphiltrum': 12274,
    'Infradentale_BuzaInf': 12284, 'Supramentale': 12266, 'Menton': 12346,
    'FrontalEminence_Dr': 7073, 'FrontalEminence_St': 945,
    'Suborbitale_Dr': 10880, 'Suborbitale_St': 4752,
    'InferiorMalar_Dr': 7529, 'InferiorMalar_St': 1401,
    'LateralOrbit_Dr': 7600, 'LateralOrbit_St': 1472,
    'Supraglenoid_Dr': 11114, 'Supraglenoid_St': 4986,
    'SupraM2_Dr': 7491, 'SupraM2_St': 1363,
    'Midmasseter_Dr': 11258, 'Midmasseter_St': 5130,
    'SubM2_Dr': 10025, 'SubM2_St': 3897,
}
LABEL_TO_VERTEX.update(ADDED_VERTEX_CANDIDATES)


def encode_index(v_id: int, is_exact: bool) -> int:
    """Aceeasi codificare ca in addon (v11/v12)."""
    return -(v_id + 1) if is_exact else v_id


def build_index_to_label() -> Dict[int, str]:
    """index CSV codificat -> eticheta landmark (uniune v11 + v12)."""
    table = {}
    for vid, label, is_exact in LANDMARKS_V11:
        enc = encode_index(vid, is_exact)
        assert enc not in table or table[enc] == label, (
            f"Coliziune codificare v11: {enc} ({label} vs {table.get(enc)})")
        table[enc] = label
    for vid, label in LANDMARKS_V12:
        enc = encode_index(vid, True)
        assert enc not in table or table[enc] == label, (
            f"Coliziune codificare v11/v12: {enc} ({label} vs {table.get(enc)})")
        table[enc] = label
    return table


INDEX_TO_LABEL = build_index_to_label()


def default_npz_path() -> str:
    """Calea implicita catre gnm_head.npz (relativa la radacina repo-ului)."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    if os.environ.get("GNM_MODEL_PATH"):
        return os.path.expanduser(os.environ["GNM_MODEL_PATH"])
    for candidate in (os.path.join(repo_root, "models", "gnm_head.npz"),
                      os.path.join(repo_root, "gnm_head.npz")):
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(repo_root, "gnm", "shape", "data", "versions",
                        "v3_0", "gnm_head.npz")


class GNMBackend(FaceModelBackend):
    """Backend pentru GNM Head v3.0 (fisier npz local)."""

    name = "gnm-head-3.0"

    def __init__(self, npz_path: str = None):
        self.npz_path = npz_path or default_npz_path()

    def load(self, dtype=np.float32) -> FaceModelData:
        """Incarca gnm_head.npz si returneaza datele, in milimetri."""
        if not os.path.isfile(self.npz_path):
            raise ValueError(f"GNM model not found: {self.npz_path}. Set --npz or GNM_MODEL_PATH; see docs/INSTALL.md")
        required = {"template_vertex_positions", "vertex_identity_basis", "triangles",
                    "mirror_indices", "vertex_groups", "vertex_group_names"}
        with np.load(self.npz_path, allow_pickle=False) as npz:
            if not required.issubset(npz.files):
                raise ValueError(f"GNM archive missing keys: {sorted(required - set(npz.files))}")
            mu = np.asarray(npz["template_vertex_positions"], dtype=dtype) * 1000.0
            basis = np.asarray(npz["vertex_identity_basis"], dtype=dtype) * 1000.0
            triangles = npz["triangles"]
            mirror_indices = npz["mirror_indices"]
            vertex_groups = np.asarray(npz["vertex_groups"], dtype=dtype)
            names = npz["vertex_group_names"]
            if names.dtype.kind not in "US" or names.ndim != 1:
                raise ValueError("vertex_group_names must be a one-dimensional string array")
            vertex_group_names = [n.decode("utf-8") if isinstance(n, bytes) else str(n) for n in names]
        n = len(mu)
        if mu.shape != (n, 3) or n < 4 or basis.ndim != 3 or basis.shape[1:] != (n, 3) or not len(basis):
            raise ValueError("Invalid model template or identity basis dimensions")
        for name, array in (("template", mu), ("basis", basis), ("vertex_groups", vertex_groups)):
            if not np.isfinite(array).all():
                raise ValueError(f"Non-finite values in model {name}")
        if (triangles.ndim != 2 or triangles.shape[1] != 3 or not len(triangles)
                or triangles.dtype.kind not in "iu" or np.any(triangles < 0) or np.any(triangles >= n)):
            raise ValueError("Invalid triangle topology")
        if (mirror_indices.shape != (n,) or mirror_indices.dtype.kind not in "iu"
                or np.any(mirror_indices < 0) or np.any(mirror_indices >= n)
                or not np.array_equal(mirror_indices[mirror_indices], np.arange(n))):
            raise ValueError("mirror_indices must be a valid involution")
        if vertex_groups.shape != (len(vertex_group_names), n) or len(set(vertex_group_names)) != len(vertex_group_names):
            raise ValueError("Invalid semantic vertex groups")
        return FaceModelData(
            mu=mu, basis=basis, triangles=triangles,
            mirror_indices=mirror_indices, vertex_groups=vertex_groups,
            vertex_group_names=vertex_group_names,
        )

    @property
    def landmark_vertex_map(self) -> Dict[str, int]:
        return LABEL_TO_VERTEX

    @property
    def index_to_label(self) -> Dict[int, str]:
        return INDEX_TO_LABEL

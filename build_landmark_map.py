"""Genereaza landmark_vertex_map.json pentru GNM head.

Combina:
  (a) cele 68 de landmark-uri OFICIALE GNM (gnm_landmarks.GNMLandmarksType.HEAD_SPARSE_68,
      compatibile ca ordine cu schema standard iBUG/dlib-68), convertite din
      baricentric (3 vertecsi + ponderi) in cel mai apropiat vertex simplu; si
  (b) extrase geometrice din vertex_group-urile numite ale mesh-ului (zygomatic,
      chin, brow etc.) pentru punctele craniometrice care NU exista in schema
      de 68 (zygion, gonion etc.)

Rezultatul e un CANDIDAT care trebuie verificat vizual in Blender inainte de
folosire intr-un pipeline forensic -- fiecare intrare are campul "source" si
"confidence" ca sa stii ce sa verifici prioritar.
"""

import json
import numpy as np
from gnm.shape import gnm_numpy
from gnm.shape import gnm_landmarks

gnm = gnm_numpy.GNM.from_local(
    version=gnm_numpy.GNMMajorVersion.V3,
    variant=gnm_numpy.GNMVariant.HEAD,
)
V = np.asarray(gnm.template_vertex_positions)  # (NV, 3)

# ---------------------------------------------------------------------------
# (a) Cele 68 de landmark-uri oficiale GNM (barycentric -> vertex cel mai apropiat)
# ---------------------------------------------------------------------------
cfg = gnm_landmarks.load_landmarks(gnm_landmarks.GNMLandmarksType.HEAD_SPARSE_68)
lm68_positions = np.zeros((68, 3), dtype=np.float64)
lm68_nearest_vertex = np.zeros(68, dtype=np.int64)
for i in range(68):
    idx = cfg.indices[i]
    w = cfg.weights[i]
    pos = (V[idx] * w[:, None]).sum(axis=0)
    lm68_positions[i] = pos
    # vertex cel mai apropiat de punctul baricentric, pt un index "simplu" utilizabil
    lm68_nearest_vertex[i] = idx[np.argmin(np.linalg.norm(V[idx] - pos, axis=1))]

# Subset iBUG-68 -> nume craniometric echivalent de tesut moale (indici 0-based)
IBUG68_TO_FORENSIC = {
    27: "nasion",           # radacina nasului, sub glabella
    29: "rhinion",          # V13.4: puntea nazala osoasa (rhinion craniometric)
    30: "pronasale",        # varful nasului
    33: "subnasale",        # baza septului nazal
    31: "alare_right",      # aripa nazala dreapta (in imagine, poate fi stanga anatomic - verifica orientarea!)
    35: "alare_left",
    36: "exocanthion_right",
    39: "endocanthion_right",
    42: "endocanthion_left",
    45: "exocanthion_left",
    48: "cheilion_right",
    54: "cheilion_left",
    8:  "gnathion",         # menton, cel mai jos punct pe linia barbiei
    0:  "gonion_right_approx",   # aproximare slaba - vezi nota de mai jos
    16: "gonion_left_approx",
}

landmark_map = {}
for ibug_idx, name in IBUG68_TO_FORENSIC.items():
    landmark_map[name] = {
        "vertex_index": int(lm68_nearest_vertex[ibug_idx]),
        "position": V[lm68_nearest_vertex[ibug_idx]].tolist(),
        "barycentric_position": lm68_positions[ibug_idx].tolist(),
        "source": "official_gnm_68_barycentric",
        "ibug68_index": ibug_idx,
        "confidence": "medium-high" if ibug_idx not in (0, 16) else "low",
        "note": (
            "aproximare slaba a gonion-ului real (unghi mandibular); "
            "punctul iBUG e pe conturul fetei in imagine 2D, nu neaparat "
            "pe unghiul mandibular anatomic -- verifica manual"
            if ibug_idx in (0, 16) else ""
        ),
    }

# ---------------------------------------------------------------------------
# (b) Extrase geometrice din vertex_group-uri numite, pt puncte fara corespondent in 68
# ---------------------------------------------------------------------------
def group_vertices(name):
    idx = gnm.vertex_group_indices(name) if callable(getattr(gnm, "vertex_group_indices", None)) else None
    return idx

def get_group_positions(name):
    vg = gnm.vertex_group(name)
    vg = np.asarray(vg)
    if vg.dtype == bool or vg.max() <= 1.0 + 1e-6:
        idx = np.where(vg > 0.5)[0]
    else:
        idx = vg.astype(int)
    return idx, V[idx]

def extremum(name, axis, mode):
    idx, pos = get_group_positions(name)
    col = pos[:, axis]
    local_i = int(np.argmax(col)) if mode == "max" else int(np.argmin(col))
    return int(idx[local_i]), pos[local_i]

geometric_points = {
    # zygion = punctul cel mai lateral (x maxim/minim) in regiunea zigomatica
    "zygion_right": ("right_zygomatic_region", 0, "min"),
    "zygion_left":  ("left_zygomatic_region", 0, "max"),
    # glabella = punctul cel mai anterior (z sau y in fata, aproximam cu y max
    # daca modelul e orientat Y=inainte; AJUSTEAZA axa dupa orientarea reala!)
    "glabella": ("middle_brow_region", 1, "max"),
    # gnathion alternativ, din regiunea barbiei (validare incrucisata cu pct 8 iBUG)
    "gnathion_from_chin_region": ("chin_region", 2, "min"),
}

for name, (group, axis, mode) in geometric_points.items():
    try:
        vidx, pos = extremum(group, axis, mode)
        landmark_map[name] = {
            "vertex_index": vidx,
            "position": pos.tolist(),
            "source": f"geometric_extremum[{group}, axis={axis}, {mode}]",
            "confidence": "low",
            "note": (
                "extrema geometrica pe axa presupusa -- verifica manual in Blender "
                "ca axa/orientarea corespunde anatomiei reale (ex: y=anterior)"
            ),
        }
    except Exception as e:
        landmark_map[name] = {"error": str(e)}

# ---------------------------------------------------------------------------
# Corectii MANUALE (V13.4, verificate anatomic pe template - vezi tabelul V12
# din addon / LABEL_TO_VERTEX din cranio.backend). Acestea suprascriu punctele
# generate automat care au fost validate ca ERONATE:
#   * gonion din iBUG 0/16 = pe conturul fetei 2D, langa ureche (NU unghiul
#     gonial) -> vertexii V12 (bigonial 129.3 mm);
#   * glabella din extremum geometric = prea sus pe frunte (27 mm peste
#     Nasion) -> vertexul V12 (15.8 mm peste Nasion);
#   * zygion: extremum-ul era corect (V12 l-a verificat, 135.4 mm) ->
#     promovat la confidence medium-high;
#   * gnathion_from_chin_region: extremum lateral (x=+26.6 mm!) si nefolosit
#     -> eliminat;
#   * Rhinion NU se genereaza din iBUG 30 (= pronasale/varf); iBUG 29 este
#     rhinion-ul craniometric (adaugat mai sus in IBUG68_TO_FORENSIC).
MANUAL_VERIFIED = {
    "glabella": 12337,
    "gonion_right_approx": 8737,
    "gonion_left_approx": 2609,
}
for name, vid in MANUAL_VERIFIED.items():
    landmark_map[name] = {
        "vertex_index": vid,
        "position": (V[vid]).tolist(),
        "source": "manual_verified_v12",
        "confidence": "medium",
        "note": "vertex verificat anatomic (tabelul V12); inlocuieste "
                "varianta automata eronata (vezi build_landmark_map.py)",
    }
for name in ("zygion_right", "zygion_left"):
    if name in landmark_map and "vertex_index" in landmark_map[name]:
        landmark_map[name]["confidence"] = "medium-high"
        landmark_map[name]["note"] = (
            "verificat anatomic (V12): bizigomatic 135.4 mm pe template")
landmark_map.pop("gnathion_from_chin_region", None)

# ---------------------------------------------------------------------------
# (d) Landmarkuri nazale V13.6 pentru diagnosticul de proiectie nazala
# (Gerasimov, interpretarea Ullrich & Stephan 2011). Nu exista corespondent
# iBUG-68; selectate geometric (tools/suggest_nasal_vertices.py) cu
# constrangeri dure (Acanthion median exact; perechea Piriform oglinda
# topologica exacta) si verificate vizual pe template.
#   * acanthion (12297): punctul de piele median imediat sub subnasale
#     (1.5 mm) -- proiectia spinei nazale anterioare;
#   * piriform_right/left (10215/4087): +-12.4 mm de planul median, la
#     nivelul subnasale -- proiectia marginii inferioare a aperturei
#     piriforme (semi-latime ~12.5 mm a aperturei osoase adulte).
# Sincronizat cu LABEL_TO_VERTEX din cranio.backend.gnm_backend (V12).
NASAL_V13_6 = {
    "acanthion": 12297,
    "piriform_right": 10215,
    "piriform_left": 4087,
}
for name, vid in NASAL_V13_6.items():
    landmark_map[name] = {
        "vertex_index": vid,
        "position": (V[vid]).tolist(),
        "source": "manual_anatomical_v13.6",
        "confidence": "medium",
        "note": "proiectie pe piele a unui punct OSOS (apertura piriforma / "
                "spina nazala), selectata geometric + verificata vizual; "
                "folosit la diagnosticul de proiectie nazala "
                "(Gerasimov/Ullrich-Stephan) si la fit",
    }

# ---------------------------------------------------------------------------
import os
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "landmark_vertex_map.json")
with open(out_path, "w") as f:
    json.dump(landmark_map, f, indent=2, ensure_ascii=False)

print(f"Scris {len(landmark_map)} landmark-uri in landmark_vertex_map.json")
for k, v in landmark_map.items():
    if "vertex_index" in v:
        print(f"  {k:28s} vertex={v['vertex_index']:6d}  source={v['source']:45s} conf={v['confidence']}")
    else:
        print(f"  {k:28s} EROARE: {v.get('error')}")

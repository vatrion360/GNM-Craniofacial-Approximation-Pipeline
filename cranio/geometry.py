# -*- coding: utf-8 -*-
"""Utilitare de geometrie: normale, masti de regiuni, esantionare cranii,
corespondente dense model->craniu.

Nu stie nimic despre optimizare; primeste si returneaza arrays/dict-uri.
"""

import numpy as np

from .landmarks import (NOSE_BRIDGE_CENTER_FRAC, NOSE_BRIDGE_RADIUS_MM,
                        NOSE_BRIDGE_TIP_CUT_MM, PROTECTED_GROUPS,
                        REGION_OFFSETS_MM)


def compute_vertex_normals(vertices, triangles, flip=False):
    """Normale per-vertex (acumulare produse vectoriale ale fetelor)."""
    tri = triangles[:, ::-1] if flip else triangles
    v0 = vertices[tri[:, 0]]
    face_n = np.cross(vertices[tri[:, 1]] - v0, vertices[tri[:, 2]] - v0)
    vn = np.zeros_like(vertices)
    np.add.at(vn, tri[:, 0], face_n)
    np.add.at(vn, tri[:, 1], face_n)
    np.add.at(vn, tri[:, 2], face_n)
    n = np.linalg.norm(vn, axis=1, keepdims=True)
    return vn / np.maximum(n, 1e-12)


def build_scalp_mask(mu, vertex_groups, vertex_group_names):
    """Masca de scalp: vertecsii GNM a caror piele acopera direct osul.

    = skin AND NOT ears AND (NOT hockey_mask OR frunte OR tample)
      AND deasupra unui plan inferior inclinat (anterior: sprancene,
      posterior: baza occiputului), care exclude gatul.
    Validata pe template-ul GNM v3.0 (~2280 vertecsi pe calvarie; include
    Vertex si Eurion, exclude fata/urechile/gatul).
    """
    def grp(name):
        return vertex_groups[vertex_group_names.index(name)] > 0.5

    skin = grp("skin")
    ears = grp("ears")
    hockey = grp("hockey_mask")
    forehead = grp("forehead_region")
    temples = grp("left_temple_region") | grp("right_temple_region")

    v_m = mu / 1000.0  # pragurile sunt derivate in metri, pe template
    lower_plane = 0.31 + 0.238 * (v_m[:, 2] - 0.12)
    mask = skin & ~ears & (~hockey | forehead | temples) & (
        v_m[:, 1] > lower_plane)
    return np.where(mask)[0]


def build_face_dense_regions(mu, vertex_groups, vertex_group_names,
                             pronasale_vid=12296, nasion_vid=12319):
    """Regiuni faciale cu tesut subtire, pentru constrangeri dense.

    Returneaza lista de (nume_regiune, idx_vertecsi, offset_mm). Excluse
    deliberate (tesut gros/mobil sau fara os sub piele): varful nazal si
    alarele, buzele (s-ar atrage de dinti!), obrajii, parotidele, orbitele.

    Puntea nazala (V13.3): patch-ul este centrat pe PUNTEA OSOASA -
    centrul = Nasion + NOSE_BRIDGE_CENTER_FRAC * (pronasale - Nasion),
    cu tot ce e sub pronasale + NOSE_BRIDGE_TIP_CUT_MM exclus. Referinta
    este PRONASALE (vertex 12296, varful nasului); pana in V13.3 patch-ul
    era centrat direct pe acest vertex (sub numele eronat "Rhinion"), deci
    constrangea varful/apertura (fara os; corespondentele cadeau pe
    marginile aperturii sau erau respinse, iar puntea ramanea turtita).
    """
    def grp(name):
        return vertex_groups[vertex_group_names.index(name)] > 0.5

    skin = grp("skin")
    bridge_center = (mu[nasion_vid] + NOSE_BRIDGE_CENTER_FRAC
                     * (mu[pronasale_vid] - mu[nasion_vid]))
    nose_bridge = (grp("nose_region")
                   & (np.linalg.norm(mu - bridge_center, axis=1)
                      < NOSE_BRIDGE_RADIUS_MM)
                   & (mu[:, 1] > mu[pronasale_vid, 1] + NOSE_BRIDGE_TIP_CUT_MM))

    regions = [
        ("punte_nazala", nose_bridge, REGION_OFFSETS_MM["punte_nazala"]),
        ("brow_median", grp("middle_brow_region"),
         REGION_OFFSETS_MM["brow_median"]),
        ("zigomatic", grp("left_zygomatic_region")
         | grp("right_zygomatic_region"), REGION_OFFSETS_MM["zigomatic"]),
        ("infraorbital", grp("left_infraorbital_region")
         | grp("right_infraorbital_region"), REGION_OFFSETS_MM["infraorbital"]),
        ("barbie", grp("chin_region"), REGION_OFFSETS_MM["barbie"]),
    ]
    return [(name, np.where(skin & mask)[0], off)
            for name, mask, off in regions]


def build_vertex_region_map(num_vertices, scalp_idx, face_regions):
    """vertex -> nume regiune densa (sau None) - pentru raportul per regiune."""
    region_of = np.full(num_vertices, "", dtype=object)
    region_of[scalp_idx] = "scalp"
    for name, idx, _off in face_regions:
        region_of[idx] = name
    return region_of


def build_protected_mask(vertex_groups, vertex_group_names):
    """Indicii vertecsilor din grupurile fara ancore anatomice (ochi/buze/
    interior gura) - deplasarea lor TPS se amortizeaza (protect-damping)."""
    mask = np.zeros(vertex_groups.shape[1], dtype=bool)
    for name in PROTECTED_GROUPS:
        if name in vertex_group_names:
            mask |= vertex_groups[vertex_group_names.index(name)] > 0.5
    return np.where(mask)[0]


def load_skull_samples(skull_path, n_samples=200000, seed=42):
    """Incarca craniul si esantioneaza puncte + normale pe suprafata lui.

    Se asteapta coordonate in milimetri, in acelasi spatiu world Blender ca
    CSV-ul markerilor (export STL din scena: fara conversii de axe).
    """
    import trimesh

    mesh = trimesh.load(skull_path, process=False)
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.to_geometry()
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.vertices) == 0:
        raise ValueError(f"Nu am putut citi un mesh valid din {skull_path}")
    if (not len(mesh.faces) or not np.isfinite(mesh.vertices).all()
            or not np.isfinite(mesh.area) or mesh.area <= 0):
        raise ValueError("Skull requires finite vertices and nonzero surface area")
    points, face_idx = trimesh.sample.sample_surface(mesh, n_samples, seed=seed)
    normals = mesh.face_normals[face_idx]
    return mesh, np.asarray(points), np.asarray(normals)


def dense_correspondences(v_world, dense):
    """Corespondente vertecsi-constransi->craniu, cu respingerea celor invalide.

    Pentru fiecare vertex din dense["dense_idx"] (scalp + regiuni faciale):
    cel mai apropiat punct esantionat pe craniu. Se resping corespondentele
    cu distanta > max_dist_mm (craniu partial / zona lipsa, ex. mandibula
    lipsa) sau cu normala craniului aproape opusa celei a modelului (tablita
    interna, muchii taiate). Tintele = punct + offset_regiune * normala.
    Returneaza (idx_pastrati, tinte_world, masca_keep, distanta_medie).
    """
    dense_idx = dense["dense_idx"]
    pts = v_world[dense_idx]
    dists, nn = dense["tree"].query(pts)
    closest = dense["points"][nn]
    n_skull = dense["normals"][nn]
    n_model = compute_vertex_normals(v_world, dense["triangles"],
                                     flip=dense.get("flip", False))[dense_idx]
    dots = np.einsum("ij,ij->i", n_model, n_skull)

    # La primul apel: detecteaza daca orientarea fetelor GNM e inversa fata
    # de conventia craniului si corecteaza global (o singura data).
    if dense.get("flip") is None:
        dense["flip"] = bool(np.median(dots) < 0)
        if dense["flip"]:
            return dense_correspondences(v_world, dense)

    keep = (dists < dense["max_dists"]) & (dots > dense["min_dot"])
    sidx = dense_idx[keep]
    targets_w = closest[keep] + dense["offsets"][keep, None] * n_skull[keep]
    mean_dist = float(dists[keep].mean()) if keep.any() else float("nan")
    return sidx, targets_w, keep, mean_dist


# ---------------------------------------------------------------------------
# V13.6: Proiectia nazala Gerasimov (interpretarea Ullrich & Stephan 2011)
# ---------------------------------------------------------------------------
# Constructia (pe craniu, in profil): pronasale se estimeaza la intersectia a
# doua tangente -
#   * SUPERIOARA: tangenta la capatul distal al oaselor nazale (ultimii
#     ~span_mm de la Rhinion spre Nasion);
#   * INFERIOARA: linia prin Acanthion si punctele marginii inferioare a
#     aperturei piriforme (bilateral), proiectate in planul sagital median -
#     adica tangenta la MARGINEA aperturei, NU directia spinei nazale
#     propriu-zise (clarificarea Ullrich & Stephan 2011; directia spinei
#     este variabila si duce la erori sistematice mari, ~2 cm).
# Toate functiile sunt numpy pur (folosite si in worker thread-ul addonului,
# fara scipy), in milimetri. Coordonate: x = lateral, y = sus, z = anterior.


def _cross2(a, b):
    """Produsul scalar 2D (a x b) pentru vectori (y, z)."""
    return a[0] * b[1] - a[1] * b[0]


def _fit_line_pca(pts_yz):
    """Dreapta LSQ prin puncte (N,2): (punct_mediu, directie_unitar,
    anisotropie). Anisotropia = eigmax/eigmin; ~1 = patch izotrop (blob),
    directia PCA este atunci fara sens."""
    m = pts_yz.mean(axis=0)
    cov = (pts_yz - m).T @ (pts_yz - m)
    vals, vecs = np.linalg.eigh(cov)
    d = vecs[:, int(np.argmax(vals))]
    ratio = float(vals.max() / max(vals.min(), 1e-12))
    return m, d / max(np.linalg.norm(d), 1e-12), ratio


def extract_nasal_profile(points, nasion, rhinion, strip_mm=3.0,
                          perp_max_mm=6.0):
    """Punctele craniului din fasia oaselor nazale, proiectate sagital (y,z).

    points: (N,3) esantioane ale suprafetei craniului (mm, spatiul markerilor).
    Pastreaza punctele dintr-o fasie de +-strip_mm in jurul planului median
    (definit de x-ul lui Nasion/Rhinion), aflate intre Rhinion si Nasion de-a
    lungul liniei lor, la cel mult perp_max_mm distanta perpendiculara de ea
    (elimina punctele posterioare - apertura, proces frontal al maxilarului).
    Returneaza (M,2) coordonate (y, z); posibil M=0 (craniu partial).
    """
    x_med = 0.5 * (nasion[0] + rhinion[0])
    R = np.array([rhinion[1], rhinion[2]])
    N = np.array([nasion[1], nasion[2]])
    u = N - R
    len_nr = np.linalg.norm(u)
    if len_nr < 1e-9:
        return np.zeros((0, 2))
    u = u / len_nr
    p_yz = np.stack([points[:, 1], points[:, 2]], axis=1)
    rel = p_yz - R
    t = rel @ u                                    # de-a lungul liniei R->N
    perp = np.abs(rel[:, 0] * u[1] - rel[:, 1] * u[0])  # dist. perp. la linie
    keep = ((np.abs(points[:, 0] - x_med) <= strip_mm)
            & (t >= -2.0) & (t <= len_nr + 2.0) & (perp <= perp_max_mm))
    return p_yz[keep]


def fit_upper_nasal_tangent(profile_yz, rhinion, nasion, span_mm=2.0,
                            min_anisotropy=2.0):
    """Tangenta superioara la oasele nazale, la capatul distal (Rhinion).

    profile_yz: (M,2) puncte (y,z) din extract_nasal_profile (sau None ->
    fallback pe directia Nasion->Rhinion, cand nu exista esantioane de
    craniu, ex. in live fara craniu incarcat).
    Se fituieaza o dreapta (PCA) pe punctele din ultimii span_mm de arc de
    la Rhinion spre Nasion si se ancoreaza in proiectia lui Rhinion pe ea.

    Garda de anisotropie: pe un arc de doar ~span_mm, esantionarea poate
    forma un patch aproape izotrop (os curb/os subtire), in care directia
    PCA nu are sens (masurat pe ken-13: raport eig 1.4 la span 2 mm vs
    2.75 la span 4 mm). Daca raportul eigmax/eigmin < min_anisotropy,
    cadem pe directia Nasion->Rhinion (ambele puncte sunt PE os).
    Returneaza dict(point=(y,z), dir=(y,z) orientat inainte (spre varf),
    n_points, anisotropy, fallback).
    """
    R = np.array([rhinion[1], rhinion[2]], dtype=np.float64)
    N = np.array([nasion[1], nasion[2]], dtype=np.float64)
    d_fwd = R - N                       # directia Nasion -> Rhinion -> varf
    nrm = np.linalg.norm(d_fwd)
    if nrm < 1e-9:
        raise ValueError("Nasion si Rhinion coincid - tangenta nedefinita")
    d_fwd = d_fwd / nrm

    if profile_yz is not None and len(profile_yz) >= 3:
        u = -d_fwd                      # Rhinion -> Nasion
        rel = profile_yz - R
        t = rel @ u
        # Patch-ul trebuie sa fie la fel de lat ca span-ul; altfel (ex.
        # fasia lata de extractie) PCA ar urma directia perpendiculara pe os.
        perp = np.abs(rel[:, 0] * u[1] - rel[:, 1] * u[0])
        sel = profile_yz[(t >= -1e-9) & (t <= span_mm + 1e-9)
                         & (perp <= span_mm)]
        if len(sel) >= 3:
            m, d, ratio = _fit_line_pca(sel)
            if ratio >= min_anisotropy:
                if d @ d_fwd < 0:
                    d = -d
                # ancoreaza in proiectia lui Rhinion pe dreapta fitata
                anchor = m + ((R - m) @ d) * d
                return {"point": anchor, "dir": d,
                        "n_points": int(len(sel)), "anisotropy": ratio,
                        "fallback": False}
            return {"point": R, "dir": d_fwd, "n_points": int(len(sel)),
                    "anisotropy": ratio, "fallback": True}
    return {"point": R, "dir": d_fwd, "n_points": 0, "anisotropy": 0.0,
            "fallback": True}


def fit_lower_nasal_tangent(acanthion, pir_right, pir_left):
    """Tangenta inferioara: prin Acanthion + marginea aperturei piriforme.

    Interpretarea Ullrich & Stephan (2011): linia prin Acanthion si cele
    doua puncte bilaterale ale marginii inferioare a aperturei, proiectate
    in planul sagital median (cele doua puncte proiecteaza aproape
    coincident, deci LSQ pe cele 3 proiectii ~ linia Acanthion->mijlocul
    perechii). NU directia spinei nazale propriu-zise.
    Returneaza dict(point=(y,z) = Acanthion, dir=(y,z) orientat inainte).
    """
    pts_yz = np.array([[acanthion[1], acanthion[2]],
                       [pir_right[1], pir_right[2]],
                       [pir_left[1], pir_left[2]]], dtype=np.float64)
    _m, d, _ratio = _fit_line_pca(pts_yz)
    if d[1] < 0:                        # orientare: componenta anterior (z) +
        d = -d
    return {"point": pts_yz[0], "dir": d, "n_points": 3, "fallback": False}


def gerasimov_pronasale(nasion, rhinion, acanthion, pir_right, pir_left,
                        profile_pts=None, strip_mm=3.0, span_mm=2.0,
                        min_angle_deg=2.0):
    """Estimeaza pronasale la intersectia tangentelor Gerasimov.

    Toate intrarile sunt (3,) mm in acelasi spatiu (al craniului/markerilor).
    profile_pts: (N,3) esantioane ale craniului pentru tangenta superioara
    (None -> fallback pe directia Nasion->Rhinion).

    Returneaza dict:
      ok (bool), reason (str), pronasale_xyz ((3,) sau None),
      dist_rhinion_mm (float), angle_deg (unghiul dintre tangente),
      upper/lower (sub-dicturi cu point/dir (y,z), n_points, fallback).
    Cazuri ok=False: tangente aproape paralele (< min_angle_deg) sau
    intersectie inapoia ancorei tangentei superioare (nerealist). Mesajele
    `reason` sunt in engleza (ajung in UI-ul addon-ului si in rapoarte).
    """
    nasion = np.asarray(nasion, dtype=np.float64)
    rhinion = np.asarray(rhinion, dtype=np.float64)
    x_med = float(np.median([nasion[0], rhinion[0], acanthion[0]]))

    profile_yz = (extract_nasal_profile(profile_pts, nasion, rhinion,
                                        strip_mm=strip_mm)
                  if profile_pts is not None else None)
    upper = fit_upper_nasal_tangent(profile_yz, rhinion, nasion,
                                    span_mm=span_mm)
    lower = fit_lower_nasal_tangent(acanthion, pir_right, pir_left)

    d_u, d_l = upper["dir"], lower["dir"]
    det = _cross2(d_u, d_l)
    if abs(det) < abs(np.sin(np.radians(min_angle_deg))):
        return {"ok": False, "reason": "near-parallel tangents",
                "pronasale_xyz": None, "dist_rhinion_mm": float("nan"),
                "angle_deg": float("nan"), "upper": upper, "lower": lower}

    # intersectia: R + t*d_u = A + s*d_l  ->  t = (A-R) x d_l / (d_u x d_l)
    # (t si punctul de intersectie sunt invariante la schimbarea semnului
    # directiilor, deci calculul e independent de sistemul de axe)
    t = _cross2(lower["point"] - upper["point"], d_l) / det
    pr_yz = upper["point"] + t * d_u
    # Unghiul dintre RAZELE spre varf: orientam ambele directii spre
    # intersectie, altfel raportarea ar depinde de conventia axelor (ex.
    # Blender Z-up vs GNM Y-up).
    d_l_fwd = d_l if (pr_yz - lower["point"]) @ d_l >= 0 else -d_l
    d_u_fwd = d_u if t >= 0 else -d_u
    cos_a = float(np.clip(d_u_fwd @ d_l_fwd, -1.0, 1.0))
    angle_deg = float(np.degrees(np.arccos(cos_a)))
    pronasale_xyz = np.array([x_med, pr_yz[0], pr_yz[1]])
    dist = float(np.linalg.norm(pronasale_xyz - rhinion))
    ok = bool(t >= 0.0)
    return {"ok": ok,
            "reason": "" if ok else "intersection behind the upper anchor",
            "pronasale_xyz": pronasale_xyz if ok else None,
            "dist_rhinion_mm": dist, "angle_deg": angle_deg,
            "upper": upper, "lower": lower}

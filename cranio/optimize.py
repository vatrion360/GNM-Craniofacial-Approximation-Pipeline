# -*- coding: utf-8 -*-
"""Optimizare: aliniere, fit statistic, corectie TPS, termeni de loss.

Etape (TODO.md, Faza 7):
    1. Aliniere de similaritate (Umeyama 1991, ponderata, robusta).
    2. Fit statistic: estimare alternativa a coeficientilor de identitate
       (ridge LSQ ponderat, IRLS) si a transformarii de similaritate.
       Termeni de loss conectabili (LossConfig):
         * markeri (ponderati, Huber IRLS)          - intotdeauna activi;
         * constrangeri dense scalp/fata -> craniu  - cu --skull;
         * simetrie bilaterala (prior latent)       - symmetry_weight > 0;
         * distante inter-landmark (prior morfologic) - distance_weight > 0;
         * prior latent MOALE peste +-prior_soft_sigma (in locul singurului
           clip dur)                              - prior_soft_sigma > 0.
    3. Corectie locala limitata: camp de deplasare reziduala interpolat cu
       Thin Plate Spline (Bookstein 1989), limitat neted per-vertex.

Regularizarea lambda este aleasa prin cross-validation leave-one-out (LOO)
daca lam == "auto".

Optimizorul nu stie nimic despre Blender sau despre addon.
"""

from dataclasses import dataclass

import numpy as np
from .validation import finite_array, validate_points, rmse


@dataclass
class LossConfig:
    """Ponderile termenilor optionali de loss (0.0 = dezactivat).

    symmetry_weight: ponderea totala a priorului de simetrie bilaterala,
        relativa la regularizarea ridge (lambda); penalizeaza componentele
        de identitate ASIMETRICE (forma c^T G c, G normalizat la medie
        diagonala 1).
    distance_weight: ponderea totala a constrangerilor de distanta intre
        perechile de landmarkuri (CONSISTENCY_PAIRS), relativa la suma
        ponderilor markerilor; tinta = distanta din template (media
        statistica), linearizare Gauss-Newton la fiecare iteratie.
    prior_soft_sigma: pragul (in sigma) peste care se activeaza priorul
        latent MOALE; 0.0 = dezactivat (ramane doar clipul dur).
    prior_soft_weight: intensitatea priorului moale (multiplu de lambda).
    clip_sigma: limita dura a coeficientilor de identitate (+-sigma).
    """
    symmetry_weight: float = 0.0
    distance_weight: float = 0.0
    prior_soft_sigma: float = 0.0
    prior_soft_weight: float = 4.0
    clip_sigma: float = 3.0


# ---------------------------------------------------------------------------
# ETAPA 1: ALINIERE UMEYAMA PONDERATA
# ---------------------------------------------------------------------------
def weighted_umeyama(src, dst, weights):
    """Estimeaza (scala, R, t) cu src -> dst, ponderat, fara reflexie.

    Enforces a proper rotation. Degenerate/invalid input raises ValueError;
    reflected correspondences yield a proper best fit with residual error.
    """
    src = validate_points(src, "source landmarks")
    dst = validate_points(dst, "target landmarks")
    if src.shape != dst.shape:
        raise ValueError("Source and target landmark shapes differ")
    w = finite_array(weights, "weights", (len(src),))
    if np.any(w <= 0):
        raise ValueError("Alignment weights must be positive")
    w = w / w.sum()
    ms = (w[:, None] * src).sum(axis=0)
    md = (w[:, None] * dst).sum(axis=0)
    xc = src - ms
    yc = dst - md
    cov = (yc * w[:, None]).T @ xc
    u, d, vt = np.linalg.svd(cov)
    # Proper rotation, including planar triples whose SVD null vector may
    # change sign. A negative determinant alone is not proof of swapped sides.
    signs = np.ones(3)
    signs[-1] = 1.0 if np.linalg.det(u @ vt) >= 0 else -1.0
    rot = (u * signs) @ vt
    var = (w[:, None] * xc ** 2).sum()
    scale = float((d * signs).sum() / var)
    if not np.isfinite(scale) or scale <= 1e-12:
        raise ValueError("Similarity fit has a degenerate scale")
    trans = md - scale * rot @ ms
    return scale, rot, trans


def huber_downweight(residuals, weights, k_mm=10.0):
    """Ponderi Huber: landmarkurile cu reziduu mare primesc greutate redusa."""
    w = np.asarray(weights, dtype=np.float64).copy()
    big = residuals > k_mm
    w[big] = weights[big] * k_mm / residuals[big]
    return w


def robust_alignment(model_lm, targets_xyz, weights, n_iter=3):
    """Umeyama ponderat cu down-ponderare Huber a outlierilor (2 re-fitari)."""
    w = np.asarray(weights, dtype=np.float64)
    scale, rot, trans = None, None, None
    for _ in range(n_iter):
        scale, rot, trans = weighted_umeyama(model_lm, targets_xyz, w)
        pred = scale * (model_lm @ rot.T) + trans
        res = np.linalg.norm(pred - targets_xyz, axis=1)
        w = huber_downweight(res, weights)
    return scale, rot, trans, res


# ---------------------------------------------------------------------------
# ETAPA 2: FIT STATISTIC (COEFICIENTI DE IDENTITATE)
# ---------------------------------------------------------------------------
def _ridge_solve(basis_lm_flat, offset, weights3, lam, identity_dim):
    """Rezolva min_c ||W(A c - b)||^2 + lam*||c||^2. A: (L*3, I)."""
    sw = np.sqrt(weights3)[:, None]
    a_w = basis_lm_flat * sw
    b_w = offset * sw.ravel()
    a_reg = np.vstack([a_w, np.sqrt(lam) * np.eye(identity_dim)])
    b_reg = np.concatenate([b_w, np.zeros(identity_dim)])
    c, *_ = np.linalg.lstsq(a_reg, b_reg, rcond=None)
    return c


def _irls_weights(residuals, conf_weights, k_mm=10.0):
    """Ponderi efective IRLS: incredere * down-ponderare Huber a outlierilor.

    Un marker plasat gresit (reziduu mare) nu trebuie sa traga fitul global
    dupa el; in schimb este raportat separat ca outlier.
    """
    return huber_downweight(np.asarray(residuals, dtype=np.float64),
                            conf_weights, k_mm=k_mm)


def loo_select_lambda(basis_lm, mu_lm, targets_model, weights, lam_grid,
                      identity_dim):
    """Alege lambda prin cross-validation leave-one-out.

    Transformarea de similaritate se considera fixa (estimata cu lambda
    initial); pentru fiecare landmark exclus, se fit-uiesc coeficientii pe
    restul si se masoara eroarea de predictie pe landmarkul exclus.
    """
    offset_all = (targets_model - mu_lm).reshape(-1)
    n_lm = len(mu_lm)
    results = []
    for lam in lam_grid:
        errors = []
        for j in range(n_lm):
            mask = np.ones(n_lm, dtype=bool)
            mask[j] = False
            b_sub = basis_lm[:, mask, :].reshape(identity_dim, -1).T
            o_sub = (targets_model[mask] - mu_lm[mask]).reshape(-1)
            w_sub = np.repeat(np.asarray(weights)[mask], 3)
            c = _ridge_solve(b_sub, o_sub, w_sub, lam, identity_dim)
            pred_j = mu_lm[j] + np.einsum("i,ik->k", c, basis_lm[:, j, :])
            errors.append(np.linalg.norm(pred_j - targets_model[j]))
        results.append((float(np.mean(errors)), lam))
    results.sort()
    return results[0][1], results


# ---------------------------------------------------------------------------
# TERMENI OPTIONALI DE LOSS
# ---------------------------------------------------------------------------
def _symmetry_rows(basis, mirror_indices, eig_floor=1e-12):
    """Randuri LSQ pentru priorul de simetrie bilaterala.

    Asimetria mesh-ului generat este liniara in coeficienti:
        V - reflect_x(V[mirror]); basis rows use B_i - reflect_x(B_i[mirror]).
    (template-ul mu are doar o micro-asimetrie constanta, < 0.05 mm, deci
    nu intra in penalizare). Penalizarea ||sum_i c_i D_i||^2 este
    forma patratica c^T G c; returnam R cu R^T R = G_normalizat (medie
    diagonala 1), ca sa fie ponderata intuitiv cu lambda.

    Returneaza None daca baza e perfect simetrica (nu e cazul la GNM -
    variatia populationala include si asimetrii).
    """
    mirrored = basis[:, mirror_indices, :].copy()
    mirrored[:, :, 0] *= -1.0  # sagittal reflection is geometric, not just a permutation
    d = basis - mirrored
    flat = d.reshape(d.shape[0], -1)                 # (I, N*3)
    trace = float((flat ** 2).sum())
    if trace <= 0.0:
        return None
    g = (flat @ flat.T) * (d.shape[0] / trace)       # medie diag = 1
    vals, vecs = np.linalg.eigh(g)
    keep = vals > eig_floor * max(vals.max(), 1e-300)
    return np.sqrt(vals[keep])[:, None] * vecs[:, keep].T


def _distance_rows(c, mu, basis, pairs):
    """Randuri LSQ (linearizare Gauss-Newton la c curent) pentru
    constrangerile de distanta intre perechi de landmarkuri.

    Pentru perechea (a, b): reziduul |V_a - V_b| - d_template se
    linearizeaza; randul J c = rhs cu
        J_i = u . (B_i[a] - B_i[b]),   u = (V_a - V_b) / |V_a - V_b|
        rhs = d_template - u . (mu_a - mu_b),  d_template = |mu_a - mu_b|.
    """
    rows = []
    for a, b in pairs:
        pa = mu[a] + np.einsum("i,ik->k", c, basis[:, a, :])
        pb = mu[b] + np.einsum("i,ik->k", c, basis[:, b, :])
        dvec = pa - pb
        dist = float(np.linalg.norm(dvec))
        if dist < 1e-9:
            continue
        u = dvec / dist
        j = (basis[:, a, :] - basis[:, b, :]) @ u
        rhs = (float(np.linalg.norm(mu[a] - mu[b]))
               - float(u @ (mu[a] - mu[b])))
        rows.append((j, rhs))
    return rows


def _per_component_lambda(c, lam, sigma0, weight):
    """Ridge per-componenta pentru priorul latent moale (IRLS).

    Penalizarea weight*lam*(|c_i| - sigma0)^2 pentru |c_i| > sigma0 este
    echivalenta (la c curent) cu un ridge de pondere
        lam_i = weight*lam*(|c_i| - sigma0) / |c_i|
    adaugata peste lambda de baza. Spre deosebire de clipul dur, presiunea
    creste continuu si nu produce un platou de solutii la +-clip.
    """
    lam_vec = np.full(c.shape, lam, dtype=np.float64)
    if sigma0 > 0.0 and weight > 0.0:
        abs_c = np.abs(c)
        over = abs_c - sigma0
        act = over > 0
        lam_vec[act] += weight * lam * (
            over[act] / np.maximum(abs_c[act], 1e-12))
    return lam_vec


def fit_identity(mu, basis, lm_idx, targets_xyz, weights, lam="auto",
                 default_lambda=30.0, max_iter=20, tol=1e-5, dense=None,
                 mirror_indices=None, distance_pairs=None, loss_cfg=None,
                 prior_mean=None, prior_scale=None, prior_weight=1.0,
                 huber_rows=None, pose_rows=None):
    """Fit alternativ: coeficienti identitate <-> transformare similaritate.

    Cu ``dense`` (dict produs de pipeline cand exista --skull), fiecare
    iteratie adauga randuri dense scalp->craniu in rezolvarea ridge (tip
    ICP: corespondentele sunt recalculate pe mesh-ul curent, cu respingere
    de outlieri). Transformarea de similaritate ramane pilotata NUMAI de
    markeri (stabilitate). Ponderile dense sunt normalizate: suma lor =
    dense["weight_ratio"] * suma ponderilor markerilor.

    Termenii optionali din ``loss_cfg`` (simetrie / distante / prior
    moale) sunt implicit dezactivati (0) - comportament identic cu v3.1.

    Prior demografic optional (adaugat in V13.1 pentru preview-ul live din
    addon): daca ``prior_mean`` este dat (vector (I,) in unitati sigma, ex.
    media esantioanelor IdentitySampler pentru un sex x etnie), blocul de
    regularizare isotropic sqrt(lam)*I -> 0 este INLOCUIT cu shrink spre
    media demografica, cu precizie per-componenta:
        min ||W(Ac - b)||^2 + lam*prior_weight*sum_i ((c_i - mu_i)/s_i)^2
    adica estimarea MAP pentru priorul Gaussian N(mu, diag(s^2)).
    ``prior_scale`` (vector (I,)) este clipat defensiv la [0.25, 4.0] si
    ar trebui sa provina din acelasi esantion ca si media. Fara acesti
    parametri (toti None), rezultatul este neschimbat fata de V4.0.

    ``huber_rows`` (optional, V13.3): daca este setat, down-ponderarea
    Huber IRLS se aplica NUMAI primelor ``huber_rows`` randuri (markerii
    anatomici); randurile de dupa (ex. constrangeri dense adaugate ca
    pseudo-markeri de addon-ul live) pastreaza ponderea fixa. Motivatie:
    corespondentele dense sunt deja robustizate prin respingerea pe
    distanta/normale, iar Huber ar down-pondera exact punctele cele mai
    departate - cele care au cea mai mare nevoie de tragere (aceeasi
    semantica ca randurile dense offline, care intra cu pondere fixa).

    ``pose_rows`` (optional, V13.3): daca este setat, transformarea de
    similaritate (scala/rotatie/translatie) este re-estimata la fiecare
    iteratie NUMAI din primele ``pose_rows`` randuri (markerii anatomici);
    randurile dense participa doar la rezolvarea ridge pentru coeficienti.
    Aceeasi separare ca in pipeline-ul offline (acolo transformarea este
    "pilotata NUMAI de markeri (stabilitate)"): fara el, masa mare de
    randuri dense trage scala spre votul lor agregat si distorsioneaza
    poza globala (ex. cap prea mic -> osul zigomatic/nazal iese prin piele).

    Returneaza (c, scale, rot, trans, lam_folosit, fit_info, reziduuri_fit),
    unde fit_info = (loo_table, history, dense_stats).
    """
    if loss_cfg is None:
        loss_cfg = LossConfig()
    targets_xyz = validate_points(targets_xyz, "fit targets")
    if (np.ndim(mu) != 2 or np.shape(mu)[1] != 3 or np.ndim(basis) != 3
            or np.shape(basis)[1:] != np.shape(mu)):
        raise ValueError("Invalid mean/basis shapes")
    lm_idx = np.asarray(lm_idx)
    if (lm_idx.shape != (len(targets_xyz),) or lm_idx.dtype.kind not in "iu"
            or np.any(lm_idx < 0) or np.any(lm_idx >= len(mu))):
        raise ValueError("Landmark indices are invalid or outside the model")
    weights = finite_array(weights, "fit weights", (len(targets_xyz),))
    if np.any(weights <= 0):
        raise ValueError("Fit weights must be positive")
    lam0 = default_lambda if lam == "auto" else float(lam)
    if not np.isfinite(lam0) or lam0 <= 0:
        raise ValueError("Regularization must be finite and positive")
    for name in ("symmetry_weight", "distance_weight", "prior_soft_sigma", "prior_soft_weight", "clip_sigma"):
        value = getattr(loss_cfg, name)
        if not np.isfinite(value) or value < 0:
            raise ValueError(f"Invalid loss setting: {name}")
    if loss_cfg.clip_sigma == 0 or max_iter < 1 or tol <= 0:
        raise ValueError("clip_sigma, max_iter and tol must be positive")
    if pose_rows is not None and not 3 <= pose_rows <= len(targets_xyz):
        raise ValueError("pose_rows must select at least 3 valid landmarks")
    if prior_mean is not None:
        prior_mean = finite_array(prior_mean, "prior mean", (basis.shape[0],))
        prior_scale = finite_array(prior_scale, "prior scale", (basis.shape[0],))
        if np.any(prior_scale <= 0) or not np.isfinite(prior_weight) or prior_weight <= 0:
            raise ValueError("Prior scale and weight must be positive")
    identity_dim = basis.shape[0]
    mu_lm = mu[lm_idx]
    basis_lm = basis[:, lm_idx, :]                      # (I, L, 3)
    basis_lm_flat = basis_lm.reshape(identity_dim, -1).T  # (L*3, I)
    weights = np.asarray(weights, dtype=np.float64)
    use_dense = dense is not None and dense.get("in_fit", True)
    dense_stats = []

    def robust_w(residuals_all):
        """Ponderi IRLS; cu huber_rows, Huber numai pe primele huber_rows."""
        if huber_rows is None:
            return _irls_weights(residuals_all, weights)
        w = np.asarray(weights, dtype=np.float64).copy()
        k = min(int(huber_rows), len(w))
        w[:k] = _irls_weights(residuals_all[:k], weights[:k])
        return w

    # Pregatire termeni optionali (constanti pe parcursul fitului).
    sym_rows = None
    if loss_cfg.symmetry_weight > 0.0 and mirror_indices is not None:
        sym_rows = _symmetry_rows(basis, mirror_indices)
    use_dist = loss_cfg.distance_weight > 0.0 and distance_pairs
    use_soft = loss_cfg.prior_soft_sigma > 0.0

    def solve(c, w_eff, lam_used):
        """O iteratie completa: aliniere + (dense) + rezolvare ridge."""
        model_lm = mu_lm + np.einsum("i,ilk->lk", c, basis_lm)
        if pose_rows is None:
            scale, rot, trans, _ = robust_alignment(
                model_lm, targets_xyz, w_eff)
        else:
            # Poza pilotata NUMAI de primele pose_rows randuri (markeri);
            # randurile dense intra doar in ridge-ul de mai jos.
            kp = min(int(pose_rows), len(w_eff))
            scale, rot, trans, _ = robust_alignment(
                model_lm[:kp], targets_xyz[:kp], w_eff[:kp])
        targets_model = (targets_xyz - trans) @ (scale * rot) / (scale ** 2)

        parts_a = [basis_lm_flat * np.sqrt(np.repeat(w_eff, 3))[:, None]]
        parts_b = [(targets_model - mu_lm).reshape(-1)
                   * np.sqrt(np.repeat(w_eff, 3))]

        if use_dense:
            from .geometry import dense_correspondences
            v_world = scale * ((mu + np.einsum("i,ivk->vk", c, basis)) @ rot.T) + trans
            sidx, dt_w, keep, mean_dist = dense_correspondences(v_world, dense)
            dense_stats.append((int(keep.sum()), mean_dist))
            if keep.sum() >= 10:
                dt_m = (dt_w - trans) @ (scale * rot) / (scale ** 2)
                w_d = dense["weight_ratio"] * weights.sum() / keep.sum()
                a_extra = basis[:, sidx, :].reshape(identity_dim, -1).T
                parts_a.append(a_extra * np.sqrt(w_d))
                parts_b.append(((dt_m - mu[sidx]).reshape(-1)
                                * np.sqrt(w_d)))

        if use_dist:
            drows = _distance_rows(c, mu, basis, distance_pairs)
            if drows:
                w_pair = (loss_cfg.distance_weight * weights.sum()
                          / len(drows))
                for j_row, rhs in drows:
                    parts_a.append((np.sqrt(w_pair) * j_row)[None, :])
                    parts_b.append(np.atleast_1d(np.sqrt(w_pair) * rhs))

        if sym_rows is not None:
            parts_a.append(np.sqrt(loss_cfg.symmetry_weight * lam_used)
                           * sym_rows)
            parts_b.append(np.zeros(sym_rows.shape[0]))

        if prior_mean is not None:
            # Prior demografic (V13.1): shrink spre media demografica, cu
            # precizie per-componenta (inlocuieste shrink-ul isotropic la 0).
            # prior_scale clipat defensiv la [0.25, 4.0]: componentele cu
            # dispersie demografica foarte mica nu trebuie sa inghete fitul.
            ps = np.clip(np.asarray(prior_scale, dtype=np.float64), 0.25, 4.0)
            pm = np.asarray(prior_mean, dtype=np.float64)
            prec = np.sqrt(lam_used * prior_weight) / ps
            parts_a.append(np.diag(prec))
            parts_b.append(prec * pm)
        else:
            if use_soft:
                lam_vec = _per_component_lambda(
                    c, lam_used, loss_cfg.prior_soft_sigma,
                    loss_cfg.prior_soft_weight)
                parts_a.append(np.diag(np.sqrt(lam_vec)))
            else:
                parts_a.append(np.sqrt(lam_used) * np.eye(identity_dim))
            parts_b.append(np.zeros(identity_dim))

        a_all = np.vstack(parts_a)
        b_all = np.concatenate(parts_b)
        c_new, *_ = np.linalg.lstsq(a_all, b_all, rcond=None)
        # Proiectie pe domeniul plauzibil al modelului (+-clip sigma):
        # fara aceasta, constrangerile dense pe un craniu PARTIAL pot
        # produce coeficienti explozivi in zonele neconstranse.
        np.clip(c_new, -loss_cfg.clip_sigma, loss_cfg.clip_sigma, out=c_new)
        return c_new, scale, rot, trans

    # Prima trecere cu lambda initial (default sau cerut), ca sa stabilim
    # transformarea pentru LOO.
    lam0 = default_lambda if lam == "auto" else float(lam)
    c = np.zeros(identity_dim)
    w_eff = weights.copy()
    scale, rot, trans = None, None, None
    for _ in range(4):
        model_lm = mu_lm + np.einsum("i,ilk->lk", c, basis_lm)
        pred = scale * (model_lm @ rot.T) + trans if scale is not None else None
        if pred is not None:
            w_eff = robust_w(np.linalg.norm(pred - targets_xyz, axis=1))
        c, scale, rot, trans = solve(c, w_eff, lam0)

    loo_table = None
    lam_used = lam0
    if lam == "auto":
        model_lm = mu_lm + np.einsum("i,ilk->lk", c, basis_lm)
        kp = len(model_lm) if pose_rows is None else pose_rows
        scale, rot, trans, _ = robust_alignment(model_lm[:kp], targets_xyz[:kp], w_eff[:kp])
        targets_model = (targets_xyz - trans) @ (scale * rot) / (scale ** 2)
        grid = [0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0]
        # Conditional CV is for tuning, not a validation score. Exclude dense
        # pseudo-landmarks from folds when the caller supplies pose_rows.
        lam_used, loo_table = loo_select_lambda(
            basis_lm[:, :kp], mu_lm[:kp], targets_model[:kp], w_eff[:kp], grid, identity_dim)

    # Fit final alternativ cu lambda ales (IRLS: ponderi robuste actualizate).
    c = np.zeros(identity_dim)
    w_eff = weights.copy()
    history = []
    for it in range(max_iter):
        model_lm = mu_lm + np.einsum("i,ilk->lk", c, basis_lm)
        if scale is not None:
            pred = scale * (model_lm @ rot.T) + trans
            w_eff = robust_w(np.linalg.norm(pred - targets_xyz, axis=1))
        c_new, scale, rot, trans = solve(c, w_eff, lam_used)
        delta = np.linalg.norm(c_new - c)
        c = c_new
        model_lm = mu_lm + np.einsum("i,ilk->lk", c, basis_lm)
        pred = scale * (model_lm @ rot.T) + trans
        rms = rmse(np.linalg.norm(pred - targets_xyz, axis=1))
        history.append((it, float(scale), rms, float(np.abs(c).max())))
        if delta < tol:
            break

    model_lm = mu_lm + np.einsum("i,ilk->lk", c, basis_lm)
    kp = len(model_lm) if pose_rows is None else pose_rows
    scale, rot, trans, _ = robust_alignment(model_lm[:kp], targets_xyz[:kp], w_eff[:kp])
    pred = scale * (model_lm @ rot.T) + trans
    residuals_fit = np.linalg.norm(pred - targets_xyz, axis=1)
    return (c, scale, rot, trans, lam_used,
            (loo_table, history, dense_stats), residuals_fit)


# ---------------------------------------------------------------------------
# ETAPA 3: CORECTIE LOCALA LIMITATA (TPS + LIMITARE NETEDA)
# ---------------------------------------------------------------------------
def bounded_tps_correction(vertices_world, centers, residuals_vec, cap_vertex,
                           protected_idx=None, protect_damping=1.0):
    """Interpoleaza campul de deplasare reziduala cu TPS, limitat per-vertex.

    residuals_vec: (C, 3) vectori tinta - pozitie_fit (in spatiul world),
    prescrisi in centre (markeri + puncte dense); cei ai markerilor sunt deja
    scalati cu increderea in pipeline (marker imprecis = constrangere
    partiala, nu exacta).

    Uses a 3-D polyharmonic kernel (-r in SciPy), not the 2-D r^2 log(r).
    Limitarea este neteda si aplicata O SINGURA DATA, campului interpolat:
    |d| -> cap_vertex * tanh(|d| / cap_vertex), cu cap per-vertex (mai mic pe
    fata, mai mare pe scalp). Spline-ul TPS poate depasi local valorile
    prescrise ("ringing" langa gradiente abrupte), deci limitarea pe camp
    (nu pe centre) este cea care garanteaza: NICIUN vertex nu se deplaseaza
    mai mult de cap_vertex in etapa 3.

    Vertecsii din ``protected_idx`` (ochi/interior gura/buze - fara ancore
    anatomice) isi vad deplasarea multiplicata cu ``protect_damping``
    (urmeaza aproape doar fitul global neted).
    """
    from scipy.interpolate import RBFInterpolator
    vertices_world = finite_array(vertices_world, "mesh vertices")
    centers = validate_points(centers, "local correction centres", minimum=4, rank=3)
    residuals_vec = finite_array(residuals_vec, "local displacements", centers.shape)
    cap_vertex = finite_array(cap_vertex, "correction caps", (len(vertices_world),))
    if np.any(cap_vertex <= 0) or not np.isfinite(protect_damping) or not 0 <= protect_damping <= 1:
        raise ValueError("Correction caps must be positive and damping must be in [0, 1]")
    if len(np.unique(centers, axis=0)) != len(centers):
        raise ValueError("Duplicate local correction centres; review marker correspondences")
    # 3-D biharmonic/polyharmonic kernel (-r in SciPy), with affine tail.
    # r^2 log(r) is the classical 2-D TPS kernel, not the 3-D bending kernel.
    origin = centers.mean(axis=0)
    rbf = RBFInterpolator(centers - origin, residuals_vec,
                          kernel="linear", degree=1, smoothing=0.0)
    field = np.vstack([rbf(vertices_world[i:i + 2048] - origin)
                       for i in range(0, len(vertices_world), 2048)])
    finite_array(field, "interpolated correction")

    field_mags = np.linalg.norm(field, axis=1)
    field_safe = np.maximum(field_mags, 1e-12)
    field *= (cap_vertex * np.tanh(field_mags / cap_vertex)
              / field_safe)[:, None]

    if protected_idx is not None and len(protected_idx) and protect_damping != 1.0:
        field[protected_idx] *= protect_damping

    prescribed_mags = np.linalg.norm(residuals_vec, axis=1)
    return vertices_world + field, field, prescribed_mags


# ---------------------------------------------------------------------------
# DIAGNOSTICE DE STABILITATE
# ---------------------------------------------------------------------------
def stability_warnings(lam_used, loo_table, c, clip_sigma=3.0):
    """Semnaleaza fiturile aflate la marginea stabilitatii.

    * LOO-CV alege lambda exact la marginea grilei (grila ar trebui
      extinsa sau datele sunt prea zgomotoase);
    * coeficienti de identitate blocati pe clipul dur (fit la marginea
      modelului - frecvent cand markerii sunt putini sau inconsistenti).
    """
    warns = []
    if loo_table:
        grid_lams = [lam for _, lam in loo_table]
        if lam_used <= min(grid_lams):
            warns.append(
                f"LOO-CV chose lambda={lam_used:g}, the LOWER edge of the "
                f"grid ({min(grid_lams):g}..{max(grid_lams):g}) - the data "
                "selected the weakest shrinkage tested; this is not evidence "
                "of accuracy. Review conditional CV and marker placement.")
        elif lam_used >= max(grid_lams):
            warns.append(
                f"LOO-CV chose lambda={lam_used:g}, the UPPER edge of the "
                f"grid ({min(grid_lams):g}..{max(grid_lams):g}) - "
                "maximum regularization; check marker placement.")
    n_clip = int((np.abs(np.asarray(c)) >= clip_sigma - 1e-9).sum())
    if n_clip:
        warns.append(
            f"{n_clip} identity coefficients hit the "
            f"+/-{clip_sigma:g} sigma limit (clip active) - the fit is at "
            "the edge of the statistical model; check marker consistency "
            "or enable the soft prior (--prior-soft-sigma).")
    return warns

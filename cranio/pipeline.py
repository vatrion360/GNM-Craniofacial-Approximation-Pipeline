# -*- coding: utf-8 -*-
"""Fluxul complet de reconstructie end-to-end (Etapele 0-4).

Asambleaza modulele pachetului cranio intr-un singur apel:
    run_pipeline(PipelineConfig) -> cod de iesire (0 = succes, 2 = fatal).

Folosit atat de CLI (gnm_reconstruct.py), cat - in perspectiva M5 - de
addon-ul Blender. Nu depinde de argparse si nu stie nimic de bpy.
"""

import os
from pathlib import Path

import logging

import numpy as np

logger = logging.getLogger(__name__)

from .backend import GNMBackend
from .checks import (check_landmark_consistency, check_side_swap,
                     flag_outliers)
from .config import PipelineConfig
from .export import export_heatmap_ply, export_obj
from .geometry import (build_face_dense_regions, build_protected_mask,
                       build_scalp_mask, build_vertex_region_map,
                       dense_correspondences, gerasimov_pronasale,
                       load_skull_samples, model_winding_flip)
from .io_csv import read_marker_csv
from .landmarks import (CONSISTENCY_PAIRS, PLACEMENT_HINTS,
                        REGION_OFFSETS_MM)
from .optimize import (LossConfig, bounded_tps_correction, fit_identity,
                       robust_alignment, stability_warnings)
from .report import write_stats
from .report import write_run_json
from .validation import rmse, sha256_file, validate_points
from . import craniometry

# Landmark-urile necesare diagnosticului de proiectie nazala (V13.6).
_GERASIMOV_LABELS = ("Nasion", "Rhinion", "Acanthion",
                     "Piriform_Dr", "Piriform_St")
_PRONASALE_VID = 12296  # iBUG 30 = varful nasului (nu e in LABEL_TO_VERTEX)
# Interval plauzibil pentru distanta estimare->Rhinion (sanity check).
_GERASIMOV_DIST_RANGE_MM = (10.0, 60.0)


def _nasal_diagnostic_report(bone_positions, skull_points, v_final):
    """Blocul de diagnostic Gerasimov/Ullrich-Stephan (V13.6) pentru raport.

    Pur informativ - calculat din POZITIILE markerilor (pe craniu), NU din
    fit; nu influenteaza nimic in fit_identity. Returneaza (linii, rezultat):
    linii = None daca niciunul din cele 5 landmarkuri nu e plasat; rezultat
    = dict-ul gerasimov_pronasale (sau None daca indisponibil).
    """
    pos = {label: np.asarray(point, dtype=np.float64) for label, point in bone_positions.items()}
    if not any(lbl in pos for lbl in _GERASIMOV_LABELS):
        return None, None
    head = ("Gerasimov nasal projection (Ullrich-Stephan interpretation) - "
            "informational diagnostic, does not affect the fit:")
    missing = [lbl for lbl in _GERASIMOV_LABELS if lbl not in pos]
    if missing:
        return [head, f"  unavailable - missing: {', '.join(missing)}"], None
    res = gerasimov_pronasale(pos["Nasion"], pos["Rhinion"], pos["Acanthion"],
                              pos["Piriform_Dr"], pos["Piriform_St"],
                              profile_pts=skull_points)
    if not res["ok"]:
        return [head, f"  unavailable - {res['reason']}"], None
    up = res["upper"]
    if not up["fallback"]:
        src = f"{up['n_points']} profile points"
    elif up["n_points"] > 0:
        src = (f"isotropic profile (anisotropy {up['anisotropy']:.1f} < 2.0)"
               f" - Nasion->Rhinion direction")
    else:
        src = "no skull samples - Nasion->Rhinion direction"
    p = res["pronasale_xyz"]
    lines = [head,
             f"  tangent angle = {res['angle_deg']:.1f} deg, "
             f"upper tangent: {src}",
             f"  estimated pronasale (pose-aligned frame) = ({p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f}) mm,"
             f" distance to Rhinion = {res['dist_rhinion_mm']:.1f} mm"]
    if v_final is not None:
        d = p - v_final[_PRONASALE_VID]
        lines.append(
            f"  deviation vs final fitted pronasale (vertex 12296): "
            f"{np.linalg.norm(d):.1f} mm (dy={d[1]:+.1f}, dz={d[2]:+.1f})")
    return lines, res


def run_pipeline(cfg: PipelineConfig) -> int:
    """Public API: user input failures return 2, including missing dependencies."""
    try:
        return _run_pipeline(cfg)
    except (ValueError, OSError, ImportError, np.linalg.LinAlgError) as exc:
        logger.error(f"[FATAL ERROR] {exc}")
        return 2


def _run_pipeline(cfg: PipelineConfig) -> int:
    """Ruleaza pipeline-ul complet. Returneaza 0 (succes) sau 2 (fatal)."""
    cfg.fill_default_outputs()
    cfg.validate()
    input_hashes = {path: sha256_file(path) for path in (cfg.input, cfg.npz, cfg.skull, cfg.prior, cfg.landmark_map, cfg.protocol, cfg.case_metadata, cfg.craniometry) if path}
    warnings_list = []

    backend = GNMBackend(cfg.npz)
    label_to_vertex = backend.landmark_vertex_map

    loss_cfg = LossConfig(
        symmetry_weight=cfg.symmetry_weight,
        distance_weight=cfg.distance_weight,
        prior_soft_sigma=cfg.prior_soft_sigma,
        prior_soft_weight=cfg.prior_soft_weight, clip_sigma=cfg.clip_sigma,
    )

    prior_options = {}
    if cfg.prior:
        from .prior import load_prior
        prior = load_prior(cfg.prior, backend.load().identity_dim)
        prior_options = dict(prior_mean=prior['mean'], prior_scale=prior['scale'], prior_weight=cfg.prior_weight)
    if cfg.landmark_map:
        from .mapping import read_reviewed_map
        label_to_vertex = dict(label_to_vertex, **read_reviewed_map(cfg.landmark_map, input_hashes[cfg.npz], backend.load().vertex_count))
    # --- Etapa 0: incarcare si verificari ---------------------------------
    logger.info(f"[0] Loading CSV: {cfg.input}")
    targets, skipped, _csv_meta = read_marker_csv(
        cfg.input, backend.index_to_label, label_to_vertex)
    label_to_vertex = dict(label_to_vertex, **{target.label: target.vertex for target in targets})
    if cfg.case_metadata:
        import json
        with open(cfg.case_metadata, encoding='utf-8') as stream:
            case = json.load(stream)
        if not isinstance(case, dict):
            raise ValueError('Case metadata must be a JSON object')
        _csv_meta['case_metadata'] = case
    document = _csv_meta.get('craniometry')
    if document is not None:
        craniometry.validate_document(document)
    if cfg.craniometry:
        external = craniometry.load_document(cfg.craniometry)
        # Derived export tables are recomputed, never treated as authoritative inputs.
        external.pop('measurements', None)
        if document is not None and {k: v for k, v in document.items() if k != 'measurements'} != external:
            raise ValueError('External and embedded craniometry disagree; select one authoritative case document')
        document = external
    if document is not None:
        craniometry.measure(document)
        if document.get('case_id') and _csv_meta.get('case_id') and document['case_id'] != _csv_meta['case_id']:
            raise ValueError('Craniometry case ID does not match marker CSV')
        if _csv_meta.get('bone_sources') is not None:
            # Keep the raw input in the CSV/file hash; evaluate availability against
            # the current export manifest rather than a stale auxiliary manifest.
            document = dict(document, bone_sources=_csv_meta['bone_sources'])
        _csv_meta['craniometry'] = document
    if cfg.measurement_weight > 0 and document is None:
        raise ValueError('--measurement-weight requires craniometry metadata or --craniometry')
    model_hash = input_hashes[cfg.npz]
    recorded_hash = _csv_meta.get("model_sha256")
    if recorded_hash and recorded_hash != model_hash:
        raise ValueError("Marker model SHA-256 does not match the selected model")
    if _csv_meta["version"] < 3:
        warnings_list.append("Legacy CSV assumes world mm and loses bone positions, overrides and tissue provenance; export v3.")
    if not recorded_hash:
        warnings_list.append("Marker CSV has no model SHA-256; manually verify topology/correspondences.")
    if cfg.exclude:
        excl = set(cfg.exclude)
        skipped.extend((t[0], "manually excluded (--exclude)")
                       for t in targets if t[0] in excl)
        targets = [t for t in targets if t[0] not in excl]
        unknown = excl - {t[0] for t in targets} - {l for l, _ in skipped}
        if unknown:
            warnings_list.append(
                "--exclude: labels not found in the CSV: " + ", ".join(sorted(unknown)))
    records = _csv_meta.get("marker_records", {})
    warnings_list.extend(_csv_meta.get('landmark_audit', {}).get('warnings', []))
    unreviewed = [t.label for t in targets if records.get(t.label, {}).get("tissue_source", "unspecified")
                  in ("unspecified", "legacy-unvalidated", "")]
    if unreviewed:
        warnings_list.append("Unreviewed tissue sources: " + ", ".join(unreviewed))
    unreviewed_map = [t.label for t in targets if records.get(t.label, {}).get('mapping_reviewed') is False]
    if unreviewed_map:
        warnings_list.append('Operator has not reviewed skin correspondences: ' + ', '.join(unreviewed_map))
    repaired = [t.label for t in targets if records.get(t.label, {}).get('bone_status') in ('reconstructed', 'inferred')]
    if repaired:
        warnings_list.append('Fitting includes repaired/inferred bone landmarks: ' + ', '.join(repaired))
    if any('10.4995/var.2024.24796' in r.get('tissue_source', '') for r in records.values()):
        warnings_list.append('VAR 2026 Table 2 uses a normal-female Southwestern Native American reference. Review applicability; this is not a universal tissue table or independent validation.')
    if _csv_meta.get('cranial_modification') == 'present':
        warnings_list.append('Intentional cranial modification recorded: general GNM identity variation may not represent the altered vault. Review vault constraints and preserve the original anatomy.')
    if cfg.strict and (_csv_meta["version"] < 3 or not recorded_hash or unreviewed or unreviewed_map):
        raise ValueError("Strict preflight requires v3, matching model hash, recorded tissue sources and no explicitly unreviewed skin correspondences")
    for label, reason in skipped:
        logger.info(f"    - excluded {label}: {reason}")
    if len(targets) < 4:
        logger.error(f"[FATAL ERROR] Too few valid markers ({len(targets)}). "
              f"At least 4 are required (>=10 recommended).")
        return 2
    if len(targets) < 10:
        warnings_list.append(
            f"Only {len(targets)} valid markers (<10) - the reconstruction "
            f"will be weakly constrained and dominated by the statistical "
            f"mean.")

    logger.info(f"[0] Loading GNM model: {cfg.npz}")
    if cfg.protocol:
        from .protocol import validate_protocol
        _csv_meta['protocol_review'] = validate_protocol(cfg, _csv_meta, targets, model_hash)
    model = backend.load()
    mu, basis = model.mu, model.basis
    triangles = model.triangles
    vertex_groups, vertex_group_names = (model.vertex_groups,
                                         model.vertex_group_names)
    labels = [t[0] for t in targets]
    lm_idx = np.array([t[1] for t in targets], dtype=np.int64)
    if np.any(lm_idx < 0) or np.any(lm_idx >= model.vertex_count):
        raise ValueError("Marker vertex outside model topology")
    # Explicit v3 mappings are authoritative for consistency/distance terms too.
    label_to_vertex = {t.label: t.vertex for t in targets}
    targets_xyz = np.array([t[2] for t in targets], dtype=np.float64)
    validate_points(targets_xyz, "marker targets", minimum=4)
    weights = np.array([t[3] for t in targets], dtype=np.float64)

    def measurement_options():
        if document is None or cfg.measurement_weight == 0:
            return dict(measurement_controls=[], measurement_weight=0.), []
        # The current CSV manifest, not just a self-consistent older JSON,
        # determines whether the source geometry is still the same case.
        current = dict(document, bone_sources=_csv_meta.get('bone_sources', []))
        controls, skipped_pairs = craniometry.resolve_controls(current, labels, lm_idx, targets_xyz,
            records, _csv_meta.get('bone_positions_mm', {}), model_hash)
        return dict(measurement_controls=controls, measurement_weight=cfg.measurement_weight), skipped_pairs

    measurement_fit_options, skipped_measurements = measurement_options()

    # Verificare de consistenta a plasarii (distante inter-landmark vs
    # template): markerii suspecti sunt semnalati INAINTE de orice fit.
    cons_rows, cons_suspect = check_landmark_consistency(
        targets, mu, label_to_vertex)
    if cons_rows:
        n_flag = sum(1 for r in cons_rows if r[5])
        logger.info(f"[0] Placement consistency check: {len(cons_rows)} pairs, "
              f"{n_flag} suspect")
        for a, b, dc, dg, dev, flag in cons_rows:
            if flag:
                logger.info(f"    [!] {a} - {b}: {dc:.1f} mm vs {dg:.1f} mm "
                      f"expected ({dev:+.0%})")
        for label in sorted(cons_suspect):
            hint = PLACEMENT_HINTS.get(label)
            msg = f"Marker suspected of misplacement: {label}"
            if hint:
                msg += f". Correct position: {hint}"
            msg += " (check in Blender; you can use --exclude or --exclude-outliers)"
            warnings_list.append(msg)

    # --- Craniu (optional): constrangeri dense de suprafata ---------------
    dense = None
    sk_points = None  # folosit si de diagnosticul nazal V13.6 (profilul oaselor)
    if cfg.skull:
        if not os.path.exists(cfg.skull):
            logger.error(f"[FATAL ERROR] The skull file does not exist: {cfg.skull}")
            return 2
        logger.info(f"[0] Loading skull: {cfg.skull}")
        from scipy.spatial import cKDTree
        skull_mesh, sk_points, sk_normals = load_skull_samples(
            cfg.skull, cfg.dense_samples, seed=cfg.seed, flip_normals=cfg.skull_flip_normals)
        tree = cKDTree(sk_points)
        scalp_idx = build_scalp_mask(mu, vertex_groups, vertex_group_names)
        face_regions = ([] if cfg.no_face_dense else
                        build_face_dense_regions(mu, vertex_groups,
                                                 vertex_group_names))
        # Regiunile faciale PRIMELE (offseturi mai specifice); un vertex
        # prezent in mai multe regiuni (ex. scalp ∩ zigomatic) apare O SINGURA
        # DATA - altfel ar deveni doua centre TPS identice cu tinte diferite
        # (matrice aproape singulara -> camp oscilant).
        region_names = [r[0] for r in face_regions] + ["scalp"]
        region_idx = [r[1] for r in face_regions] + [scalp_idx]
        region_offs = [np.full(len(r[1]), r[2]) for r in face_regions]
        region_offs += [np.full(len(scalp_idx), cfg.scalp_offset_mm)]
        dense_idx_all = np.concatenate(region_idx)
        offsets_all = np.concatenate(region_offs)
        region_of_all = np.repeat(
            np.arange(len(region_names)), [len(x) for x in region_idx])
        dense_idx, first = np.unique(dense_idx_all, return_index=True)
        offsets = offsets_all[first]
        region_of_vertex = region_of_all[first]
        scalp_region_id = region_names.index("scalp")
        logger.info(f"    {len(sk_points)} skull samples; dense constraints: "
              f"{len(scalp_idx)} scalp + "
              f"{len(dense_idx) - len(scalp_idx)} face "
              f"({', '.join(f'{r[0]}:{len(r[1])}' for r in face_regions)})")
        # Sanity: markerii (piele = os + adancime) trebuie sa fie aproape de
        # suprafata craniului; altfel probabil spatii/unitati diferite.
        d_check, _ = tree.query(targets_xyz)
        if float(np.median(d_check)) > 30.0:
            warnings_list.append(
                f"Median marker->skull distance is "
                f"{np.median(d_check):.1f} mm (>30) - the skull is probably "
                f"not in the same space/units as the CSV!")
        dense = {
            "dense_idx": dense_idx, "offsets": offsets, "tree": tree,
            "points": sk_points, "normals": sk_normals,
            "region_names": region_names, "region_of_vertex": region_of_vertex,
            "scalp_region_id": scalp_region_id,
            "weight_ratio": cfg.dense_weight,
            # Respingere per-vertex: o corespondenta valida sta la ~offset mm
            # de os; peste offset+12 mm e sigur o zona lipsa (ex. mandibula
            # absenta -> barbia nu se lipeste de maxilar).
            "max_dists": offsets + 12.0,
            "min_dot": 0.2, "triangles": triangles, "flip": model_winding_flip(mu, triangles),
            "in_fit": not cfg.no_dense_fit,
            "regions": np.asarray(region_names)[region_of_vertex], "max_rows": cfg.dense_max_rows, "nose_weight": cfg.dense_nose_weight,
        }
        # Harta vertex->regiune pentru coloana "Regiune" din tabelul markeri.
        vertex_region = build_vertex_region_map(len(mu), scalp_idx,
                                                face_regions)
    else:
        vertex_region = None

    # --- Etapa 1: aliniere initiala (pentru raportare) --------------------
    logger.info("[1] Weighted Umeyama alignment (robust)...")
    try:
        s1, r1, t1, res_align = robust_alignment(mu[lm_idx], targets_xyz, weights)
    except ValueError as e:
        logger.error(f"[FATAL ERROR] {e}")
        return 2
    logger.info(f"    scale = {s1:.4f}, RMS = {rmse(res_align):.2f} mm "
          f"(max {res_align.max():.2f} mm)")

    swapped = check_side_swap(targets, r1, t1, s1)
    if swapped:
        warnings_list.append(
            "Markers suspected of Left/Right swap: "
            + ", ".join(swapped) + ". Check placement in Blender.")

    # --- Etapa 2: fit statistic -------------------------------------------
    from .regularization import adaptive_lambda
    def selected_lambda(count):
        mode = str(cfg.regularization).lower()
        if mode == 'adaptive':
            return adaptive_lambda(count, cfg.lambda_base, cfg.lambda_min, cfg.lambda_max)
        return 'auto' if mode == 'auto' else float(cfg.regularization)
    lam_arg = selected_lambda(len(targets))
    distance_pairs = ([(label_to_vertex[a], label_to_vertex[b])
                       for a, b in CONSISTENCY_PAIRS if a in label_to_vertex and b in label_to_vertex]
                      if cfg.distance_weight > 0.0 else None)
    active_terms = []
    if dense and dense["in_fit"]:
        active_terms.append("+ dense constraints")
    if loss_cfg.symmetry_weight > 0.0:
        active_terms.append("+ symmetry")
    if distance_pairs:
        active_terms.append("+ distances")
    if loss_cfg.prior_soft_sigma > 0.0:
        active_terms.append("+ soft prior")
    logger.info(f"[2] Statistical fit (regularization: {cfg.regularization}"
          f"{''.join(', ' + t for t in active_terms)})...")
    c, scale, rot, trans, lam_used, fit_info, res_fit = fit_identity(
        mu, basis, lm_idx, targets_xyz, weights, lam=lam_arg, dense=dense,
        mirror_indices=model.mirror_indices, distance_pairs=distance_pairs,
        loss_cfg=loss_cfg, max_iter=cfg.max_iter, tol=cfg.tolerance, **prior_options, **measurement_fit_options)
    logger.info(f"    lambda = {lam_used:g}, |c|max = {np.abs(c).max():.2f} sigma, "
          f"RMS = {rmse(res_fit):.2f} mm (max {res_fit.max():.2f} mm)")
    stab = stability_warnings(lam_used, fit_info[0], c, loss_cfg.clip_sigma)
    for w in stab:
        logger.info(f"    [!] {w}")
    warnings_list.extend(stab)

    # Excludere automata a outlierilor (optional): markerii cu reziduu mare
    # sunt scosi COMPLET (nu doar down-ponderati) si fitul se reia o data;
    # ei nu devin nici centre TPS (ar injecta warp local direct in fata).
    excluded_auto = []
    if cfg.exclude_outliers:
        med = float(np.median(res_fit))
        mad = 1.4826 * float(np.median(np.abs(res_fit - med)))
        thresh_ex = max(15.0, med + 3.0 * mad)
        drop = res_fit > thresh_ex
        if drop.any():
            excluded_auto = [(labels[i], float(res_fit[i]))
                             for i in np.where(drop)[0]]
            keep = ~drop
            targets = [t for t, k in zip(targets, keep) if k]
            labels = [t[0] for t in targets]
            lm_idx = lm_idx[keep]
            targets_xyz = targets_xyz[keep]
            weights = weights[keep]
            res_align = res_align[keep]
            logger.info(f"    [!] Auto-excluded {len(excluded_auto)} markers "
                  f"(residual > {thresh_ex:.1f} mm): "
                  + ", ".join(f"{l} ({r:.1f} mm)" for l, r in excluded_auto))
            warnings_list.append(
                f"Automatically excluded markers (--exclude-outliers), "
                f"residual > {thresh_ex:.1f} mm: "
                + ", ".join(f"{l} ({r:.1f} mm)" for l, r in excluded_auto)
                + ". Check their placement in Blender.")
            if len(targets) < 4:
                logger.error(f"[FATAL ERROR] After outlier exclusion only "
                      f"{len(targets)} markers remain (minimum 4).")
                return 2
            if len(targets) < 10:
                warnings_list.append(
                    f"After outlier exclusion {len(targets)} markers "
                    f"remain (<10) - weakly constrained reconstruction.")
            logger.info("    Re-running the statistical fit without outliers...")
            lam_arg = selected_lambda(len(targets))
            measurement_fit_options, skipped_measurements = measurement_options()
            c, scale, rot, trans, lam_used, fit_info, res_fit = fit_identity(
                mu, basis, lm_idx, targets_xyz, weights, lam=lam_arg,
                dense=dense, mirror_indices=model.mirror_indices,
                distance_pairs=distance_pairs, loss_cfg=loss_cfg, max_iter=cfg.max_iter, tol=cfg.tolerance,
                **prior_options, **measurement_fit_options)
            logger.info(f"    refit: lambda = {lam_used:g}, |c|max = "
                  f"{np.abs(c).max():.2f} sigma, RMS = {rmse(res_fit):.2f} mm "
                  f"(max {res_fit.max():.2f} mm)")
            stab = stability_warnings(lam_used, fit_info[0], c,
                                      loss_cfg.clip_sigma)
            for w in stab:
                logger.info(f"    [!] {w}")
            warnings_list.extend(stab)

    outliers, thresh = flag_outliers(labels, res_fit)
    if outliers:
        warnings_list.append(
            f"Markers with large residual after the fit (threshold "
            f"{thresh:.1f} mm) - check placement and tissue depth: "
            + ", ".join(f"{l} ({r:.1f} mm)" for l, r in outliers))

    # --- Mesh-ul in spatiul world (mm, Blender) ----------------------------
    v_model = model.generate(c)
    v_world = scale * (v_model @ rot.T) + trans
    lm_world = v_world[lm_idx]

    # --- Etapa 3: corectie locala limitata --------------------------------
    dense_report = None
    if dense is not None:
        _, _, dense_stats = fit_info
        dense_report = [
            f"Dense constraints: scalp offset = {cfg.scalp_offset_mm:g} mm"
            + ("" if cfg.no_face_dense else
               ", face: " + ", ".join(
                   f"{k}={v:g}" for k, v in REGION_OFFSETS_MM.items())
               + " mm"),
            f"  total weight = {cfg.dense_weight:g} x markers, "
            f"in fit = {dense['in_fit']}, in TPS = {not cfg.no_dense_tps}",
        ]
        if dense_stats:
            first, last = dense_stats[0], dense_stats[-1]
            dense_report.append(
                f"  Kept correspondences: first iter. {first[0]}"
                f" (mean dist {first[1]:.2f} mm) -> last iter. {last[0]}"
                f" (mean dist {last[1]:.2f} mm)")

    # Cap de corectie per-vertex: scalpul (tesut subtire, forma sigura) poate
    # fi tras pana la --max-correction-mm; fata (ochi/nas/gura, geometrie
    # fina) este limitata la --face-cap-mm. Masca de scalp e disponibila din
    # model, deci cap-urile functioneaza si fara --skull.
    scalp_caps = (scalp_idx if cfg.skull else
                  build_scalp_mask(mu, vertex_groups, vertex_group_names))
    cap_vertex = np.full(len(mu), cfg.face_cap_mm)
    cap_vertex[scalp_caps] = cfg.max_correction_mm
    protected_idx = build_protected_mask(vertex_groups, vertex_group_names)

    if cfg.skip_tps:
        v_final = v_world
        field = np.zeros_like(v_world)
        clamped = np.zeros(len(targets))
        n_scalp_centres = n_face_centres = 0
    else:
        centers = [lm_world]
        # Reziduurile markerilor se scaleaza cu increderea: un marker
        # imprecis (ex. Supraorbitale 0.5) devine constrangere PARTIALA,
        # nu trage mesh-ul pana la tinta lui (posibil gresita).
        res_vecs = [(targets_xyz - lm_world) * weights[:, None]]
        n_scalp_centres = n_face_centres = 0
        if dense is not None and not cfg.no_dense_tps:
            from scipy.spatial import cKDTree
            sidx, dt_w, keep, _ = dense_correspondences(v_world, dense)
            kept_regions = np.asarray(dense['last_diagnostics']['regions'])
            if keep.sum() > 0:
                # Deduplicare: centrele dense aflate aproape de un marker
                # (ex. Vertex/Eurion sunt in masca de scalp) ar face matricea
                # TPS aproape singulara (valori usor conflictuale -> camp
                # oscilant). Markerii au prioritate, centrele se filtreaza.
                d_to_lm, _ = cKDTree(lm_world).query(v_world[sidx])
                far = d_to_lm > 3.0
                sidx, dt_w = sidx[far], dt_w[far]
                kept_regions = kept_regions[far]
            rng = np.random.default_rng(cfg.seed)
            # Centre scalp si faciale, sub-esantionate separat.
            scalp_id = 'scalp'
            for is_scalp, cap_n in ((True, cfg.tps_scalp_centres),
                                    (False, cfg.tps_face_centres)):
                sel_mask = (kept_regions == scalp_id) if is_scalp else (
                    kept_regions != scalp_id)
                cand = np.where(sel_mask)[0]
                if len(cand) == 0:
                    continue
                n_sub = min(cap_n, len(cand))
                # Indici sortati => perechile (vertex, tinta) raman aliniate.
                sel = np.sort(rng.choice(cand, size=n_sub, replace=False))
                centers.append(v_world[sidx[sel]])
                res_vecs.append(dt_w[sel] - v_world[sidx[sel]])
                if is_scalp:
                    n_scalp_centres = len(sel)
                else:
                    n_face_centres = len(sel)
        centers = np.vstack(centers)
        res_vecs = np.vstack(res_vecs)

        logger.info(f"[3] Local TPS correction (face cap {cfg.face_cap_mm:g} mm / "
              f"scalp {cfg.max_correction_mm:g} mm, "
              f"protected-zone damping x{cfg.protect_damping:g}, "
              f"{len(targets)} markers + {n_scalp_centres} scalp + "
              f"{n_face_centres} face)...")
        v_final, field, clamped = bounded_tps_correction(
            v_world, centers, res_vecs, cap_vertex,
            protected_idx=protected_idx,
            protect_damping=cfg.protect_damping)
        mean_corr = float(np.linalg.norm(field, axis=1).mean())
        max_corr = float(np.linalg.norm(field, axis=1).max())
        logger.info(f"    correction: mean {mean_corr:.2f} mm, max {max_corr:.2f} mm")
        if mean_corr > 5.0:
            warnings_list.append(
                f"Mean local correction is large ({mean_corr:.1f} mm) - "
                "possibly inconsistently placed markers; check the report.")

    res_final = np.linalg.norm(v_final[lm_idx] - targets_xyz, axis=1)

    # Metrici finale per regiune: distanta la craniu (tinta = offsetul
    # regiunii) si corectia medie aplicata.
    if dense is not None:
        field_mag = np.linalg.norm(field, axis=1)
        sidx_f, _, keep_f, _ = dense_correspondences(v_final, dense)
        reg_f = np.asarray(dense['last_diagnostics']['regions'])
        dense_report.append("  Per region (final): kept, mean distance to "
                            "skull [target], mean correction:")
        off_all = dense["offsets"]
        for rid, rname in enumerate(dense["region_names"]):
            m = reg_f == rname
            if not m.any():
                dense_report.append(f"    {rname:14s}: 0 correspondences")
                continue
            vids = sidx_f[m]
            d_r, _ = dense["tree"].query(v_final[vids])
            d_r = np.minimum(d_r, 60.0)  # taie cozile (zone fara os)
            target_off = off_all[np.searchsorted(dense['dense_idx'], sidx_f[m])].mean()
            dense_report.append(
                f"    {rname:14s}: {m.sum():5d} | {d_r.mean():6.2f} mm "
                f"[{target_off:4.1f}] | {field_mag[vids].mean():5.2f} mm")
            logger.info(f"    {rname:14s}: dist. to skull {d_r.mean():6.2f} mm "
                  f"(target {target_off:4.1f})")

    from .quality import geometry_quality
    quality = geometry_quality(scale*(mu @ rot.T)+trans, v_world, v_final, triangles, cfg.geometry_qc,
        skin_mask=model.group_mask('skin_exterior') if 'skin_exterior' in model.vertex_group_names else None,
        skull_points=sk_points, skull_normals=sk_normals if cfg.skull else None)
    quality['solver_converged'] = fit_info.diagnostics['converged']
    if not quality['solver_converged']:
        quality['status'] = 'needs_review'
        warnings_list.append('Solver did not meet pose/coefficient/IRLS convergence tolerances')
    if quality['status'] == 'needs_review':
        warnings_list.append('Geometry/solver QC requires review; inspect the JSON diagnostics')
    _csv_meta['geometry_quality'] = quality
    measurement_report = None
    if document is not None:
        controls = measurement_fit_options['measurement_controls']
        measurement_report = dict(protocol=craniometry.PROTOCOL, bone_measurements=craniometry.measure(document),
            weight=cfg.measurement_weight, controls=controls, skipped_controls=skipped_measurements,
            aligned_skin=craniometry.control_residuals(controls, s1*(mu @ r1.T)+t1),
            statistical_skin=craniometry.control_residuals(controls, v_world),
            final_skin=craniometry.control_residuals(controls, v_final),
            interpretation='Bone chords are unchanged input observations. Skin residuals are training diagnostics, not accuracy or calibrated uncertainty.')
        _csv_meta['craniometry_result'] = measurement_report
        if controls:
            warnings_list.append('Reviewed skin-distance controls are experimental; marker-derived pair targets are dependent observations. Conditional LOO still tunes marker rows only.')
    if not cfg.skip_tps:
        _csv_meta['local_correction_centres_world_mm'] = centers.tolist()
        _csv_meta['local_correction_prescribed_vectors_mm'] = res_vecs.tolist()
    # --- Etapa 4: export ---------------------------------------------------
    if any(sha256_file(path) != digest for path, digest in input_hashes.items()):
        raise ValueError("An input changed during fitting; no outputs have been published")
    for path in (cfg.output, cfg.output_error_mesh, cfg.output_stats, cfg.output_json, cfg.output_statistical):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    # Invalidate an older completion record before replacing any of its outputs.
    if cfg.overwrite and Path(cfg.output_json).exists():
        Path(cfg.output_json).unlink()
    logger.info(f"[4] Export statistical OBJ: {cfg.output_statistical}")
    export_obj(cfg.output_statistical, v_world, triangles)
    logger.info(f"[4] Export OBJ: {cfg.output}")
    export_obj(cfg.output, v_final, triangles)
    logger.info(f"    Export heatmap PLY: {cfg.output_error_mesh}")
    export_heatmap_ply(cfg.output_error_mesh, v_final, triangles,
                       np.linalg.norm(field, axis=1))

    # --- Diagnostic proiectie nazala V13.6 (informativ, post-fit) ----------
    # This construction requires BONE markers and sagittal axes. Never feed
    # skin targets or arbitrary world axes to it. Keep lengths in world mm.
    bone_aligned = {label: (np.asarray(xyz) - trans) @ rot
                    for label, xyz in _csv_meta.get("bone_positions_mm", {}).items()
                    if label in labels}
    final_aligned = (v_final - trans) @ rot
    nasal_report, gerasimov_res = _nasal_diagnostic_report(
        bone_aligned, None if sk_points is None else (sk_points - trans) @ rot,
        final_aligned)
    if not bone_aligned:
        nasal_report = ["Nasal diagnostic unavailable: no explicit bone positions in the marker CSV."]
    if gerasimov_res is not None:
        d_ger = gerasimov_res["dist_rhinion_mm"]
        lo, hi = _GERASIMOV_DIST_RANGE_MM
        if not (lo <= d_ger <= hi):
            warnings_list.append(
                f"The Gerasimov pronasale estimate is implausible "
                f"(distance to Rhinion {d_ger:.1f} mm, outside "
                f"[{lo:g}..{hi:g}]) - check the placement of the nasal "
                f"landmarks (Acanthion/Piriform/Nasion/Rhinion).")
        logger.info(f"[3] Gerasimov diagnostic: estimate->Rhinion dist "
              f"{d_ger:.1f} mm, deviation vs final fit "
              f"{np.linalg.norm(gerasimov_res['pronasale_xyz'] - final_aligned[_PRONASALE_VID]):.1f} mm")

    extra = None
    extra_parts = []
    if cfg.skip_tps:
        extra_parts.append("Local correction was disabled (--skip-tps).")
    if loss_cfg.symmetry_weight > 0.0:
        extra_parts.append(
            f"Bilateral symmetry term active "
            f"(symmetry_weight = {loss_cfg.symmetry_weight:g}).")
    if distance_pairs:
        extra_parts.append(
            f"Inter-landmark distance term active "
            f"(distance_weight = {loss_cfg.distance_weight:g}, "
            f"{len(distance_pairs)} pairs).")
    if loss_cfg.prior_soft_sigma > 0.0:
        extra_parts.append(
            f"Soft latent prior active beyond +/-{loss_cfg.prior_soft_sigma:g} "
            f"sigma (prior_soft_weight = {loss_cfg.prior_soft_weight:g}).")
    if extra_parts:
        extra = "\n".join(extra_parts)
    lm_regions = None
    if vertex_region is not None:
        lm_regions = {label: (vertex_region[vid] or "-")
                      for label, vid, _, _ in targets}
    write_stats(cfg.output_stats, cfg, targets, skipped, scale, lam_used,
                fit_info, res_align, res_fit, res_final,
                clamped[:len(targets)], field, c, warnings_list, extra,
                dense_report=dense_report, lm_regions=lm_regions,
                consistency=cons_rows, excluded_auto=excluded_auto,
                nasal_report=nasal_report, craniometry_report=measurement_report)
    logger.info(f"    Statistics: {cfg.output_stats}")
    write_run_json(cfg, _csv_meta, model_hash, targets, skipped, excluded_auto,
                   scale, rot, trans, c, lam_used, fit_info, res_align,
                   res_fit, res_final, field, warnings_list)
    logger.info(f"    Reproducibility report: {cfg.output_json}")
    logger.info("Done.")
    return 3 if (cfg.require_qc or cfg.protocol) and quality['status'] != 'passed_full_checks' else 0

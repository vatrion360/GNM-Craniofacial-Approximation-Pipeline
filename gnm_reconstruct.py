#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GNM Reconstructie Craniofaciala (v4.0)
======================================

Pipeline stiintific de reconstructie faciala (facial approximation) pornind de
la markerii craniofaciali plasati pe un craniu scanat cu addon-ul Blender
``addon_v11.py`` / ``addon_v12.py`` si de la modelul statistic de cap uman
GNM Head v3.0 (Google).

Noutati v4.0 - refactorizare in pachetul ``cranio`` + termeni noi de loss:
    * Toata logica numerica a fost extrasa neschimbata in pachetul pur-Python
      ``cranio`` (fara dependinte de Blender, testabil): registru anatomic
      unic (cranio.landmarks), backend de model abstract
      (cranio.backend.GNMBackend), optimizor cu termeni de loss conectabili
      (cranio.optimize), verificari, geometrie, exporturi, raport.
      Acest script este doar un CLI subtire peste cranio.pipeline.
    * Termeni optionali de loss (implicit dezactivati = rezultate identice
      cu v3.1): --symmetry-weight (prior de simetrie bilaterala in spatiul
      latent), --distance-weight (constrangeri de distanta intre perechile
      de landmarkuri, tinta = template-ul statistic),
      --prior-soft-sigma (prior latent moale peste prag, in locul singurului
      clip dur la 3 sigma).
    * Diagnostice de stabilitate: avertismente explicite cand LOO-CV alege
      lambda la marginea grilei sau cand coeficientii ating clipul dur.
    * Cititor CSV v2 (metadate JSON: unitati, versiune addon, fisier craniu,
      adancimi de tesut) cu compatibilitate legacy v11/v12.

Noutati v3.1 - robustete la markeri plasati gresit + TPS region-aware:
    * Verificare de consistenta a plasarii (Etapa 0): rapoartele distantelor
      inter-landmark CSV vs template GNM (normalizate robust la scara) scot
      in evidenta markerii plasati gresit INAINTE de fit.
    * ``--exclude LABEL...`` si ``--exclude-outliers``: markerii cu reziduu
      mare pot fi exclusi complet din fit si din centrele TPS.
    * Corectia TPS tine cont de CONFIDENCE_WEIGHTS, are cap per-vertex si
      amortizare pe geometria fara ancore anatomice (ochi/buze/gura).

Noutati v3.0 / v2.0 - constrangeri dense de suprafata (optional, --skull):
    atractia de craniu pe scalp + regiuni faciale cu tesut SUBTIRE, fiecare
    cu offsetul ei (brow ~5mm, punte nazala ~3mm, zigomatic ~8.5mm,
    barbie ~10mm, infraorbital ~7mm), cu respingere automata a
    corespondentelor invalide.

Metodologie (in 4 etape):
    0.  Incarcare si verificari (consistenta plasarii markerilor).
    1.  Aliniere de similaritate (Umeyama 1991, ponderata, robusta).
    2.  Fit statistic: estimare alternativa a coeficientilor de identitate
        GNM (ridge LSQ ponderat, IRLS) si a transformarii de similaritate;
        lambda ales prin LOO-CV daca --regularization auto.
    3.  Corectie locala limitata (hibrid): camp TPS (Bookstein 1989) cu o
        singura limitare neta (tanh) si cap per-vertex.
    4.  Export OBJ + PLY heatmap + TXT cu statistici complete.

Dependente: numpy, scipy, trimesh (doar pentru incarcarea craniului).
Rulare din consola (CPython), NU din Blender.
"""

import argparse
import sys

from cranio.backend import default_npz_path
from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline


def parse_args(argv=None) -> PipelineConfig:
    parser = argparse.ArgumentParser(
        description="GNM facial reconstruction from craniofacial markers (Blender addon CSV).")
    parser.add_argument("--input", required=True, help="CSV exported by the addon (v11/v12/v2)")
    parser.add_argument("--output", default=None,
                        help="Output OBJ (default: <input>_reconstructie.obj)")
    parser.add_argument("--output-error-mesh", default=None,
                        help="PLY heatmap of the local correction (default: <output>_heatmap.ply)")
    parser.add_argument("--output-stats", default=None,
                        help="TXT statistics report (default: <output>_statistici.txt)")
    parser.add_argument("--output-json", default=None, help="JSON reproducibility report")
    parser.add_argument("--output-statistical", default=None, help="Unwarped statistical OBJ")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic sampling seed")
    parser.add_argument("--overwrite", action="store_true", help="Explicitly replace previous outputs")
    parser.add_argument("--strict", action="store_true", help="Require v3, model hash, documented tissue sources and no explicitly unreviewed included mappings")
    parser.add_argument("--npz", default=default_npz_path(),
                        help="Path to gnm_head.npz")
    parser.add_argument("--regularization", default="auto",
                        help="'auto' (LOO-CV) or a fixed value, e.g. 30")
    parser.add_argument("--exclude", nargs="+", default=[], metavar="LABEL",
                        help="Marker labels manually excluded from the fit and "
                             "the TPS centres (e.g. --exclude Pogonion Rhinion)")
    parser.add_argument("--exclude-outliers", action="store_true",
                        help="Automatically exclude markers with residual > "
                             "max(15 mm, median+3*MAD) after the first fit and re-fit "
                             "once; by default they are only flagged, not excluded")
    parser.add_argument("--max-correction-mm", type=float, default=15.0,
                        help="Hard cap of the local correction per vertex on the "
                             "SCALP (mm); the face uses --face-cap-mm")
    parser.add_argument("--face-cap-mm", type=float, default=8.0,
                        help="Hard cap of the local correction per vertex on the "
                             "FACE (eyes/nose/mouth), in mm")
    parser.add_argument("--protect-damping", type=float, default=0.25,
                        help="Damping factor of the TPS correction on regions "
                             "without anatomical anchors (eyes/mouth interior/"
                             "lips); 1.0 = no protection")
    parser.add_argument("--skip-tps", action="store_true",
                        help="Stop after statistical fitting (the default)")
    parser.add_argument("--local-correction", action="store_true",
                        help="Enable bounded 3-D polyharmonic local correction (experimental)")
    parser.add_argument("--skull", default=None,
                        help="Skull (STL/OBJ) from the same Blender scene as the "
                             "CSV (world, mm) - enables the dense scalp constraints")
    parser.add_argument("--scalp-offset-mm", type=float, default=5.0,
                        help="Soft-tissue skin-bone offset on the scalp (mm)")
    parser.add_argument("--dense-weight", type=float, default=0.5,
                        help="Total weight of the dense constraints, relative to "
                             "the sum of marker weights")
    parser.add_argument("--dense-samples", type=int, default=200000,
                        help="Number of points sampled on the skull surface")
    parser.add_argument("--tps-scalp-centres", type=int, default=500,
                        help="Maximum number of scalp points used as TPS centres")
    parser.add_argument("--tps-face-centres", type=int, default=200,
                        help="Maximum number of face points used as TPS centres")
    parser.add_argument("--no-face-dense", action="store_true",
                        help="Dense constraints on the scalp only (like v2), not "
                             "on the thin-tissue face regions")
    parser.add_argument("--no-dense-fit", action="store_true",
                        help="No dense constraints in the statistical fit")
    parser.add_argument("--no-dense-tps", action="store_true",
                        help="No dense centres in the TPS correction")
    parser.add_argument("--symmetry-weight", type=float, default=0.0,
                        help="Weight of the bilateral symmetry prior in latent "
                             "space (relative to lambda); 0 = disabled")
    parser.add_argument("--distance-weight", type=float, default=0.0,
                        help="Total weight of the inter-landmark distance "
                             "constraints (target = the template), relative to "
                             "the sum of marker weights; 0 = disabled")
    parser.add_argument("--prior-soft-sigma", type=float, default=0.0,
                        help="Threshold (sigma) beyond which the soft latent "
                             "prior activates; 0 = disabled (hard clip only)")
    parser.add_argument("--prior-soft-weight", type=float, default=4.0,
                        help="Strength of the soft prior (multiple of lambda)")
    args = parser.parse_args(argv)

    return PipelineConfig(
        input=args.input,
        output=args.output,
        output_error_mesh=args.output_error_mesh,
        output_stats=args.output_stats,
        output_json=args.output_json,
        output_statistical=args.output_statistical,
        seed=args.seed,
        overwrite=args.overwrite,
        strict=args.strict,
        npz=args.npz,
        skull=args.skull,
        regularization=args.regularization,
        exclude=args.exclude,
        exclude_outliers=args.exclude_outliers,
        skip_tps=args.skip_tps or not args.local_correction,
        max_correction_mm=args.max_correction_mm,
        face_cap_mm=args.face_cap_mm,
        protect_damping=args.protect_damping,
        scalp_offset_mm=args.scalp_offset_mm,
        dense_weight=args.dense_weight,
        dense_samples=args.dense_samples,
        tps_scalp_centres=args.tps_scalp_centres,
        tps_face_centres=args.tps_face_centres,
        no_face_dense=args.no_face_dense,
        no_dense_fit=args.no_dense_fit,
        no_dense_tps=args.no_dense_tps,
        symmetry_weight=args.symmetry_weight,
        distance_weight=args.distance_weight,
        prior_soft_sigma=args.prior_soft_sigma,
        prior_soft_weight=args.prior_soft_weight,
    )


def main(argv=None) -> int:
    return run_pipeline(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())

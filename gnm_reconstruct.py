#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline craniofacial approximation CLI.

Fits neutral GNM identity to reviewed world-mm targets, with optional dense
bone constraints and bounded local correction. See docs/SCIENTIFIC_HARDENING.md
for the numerical contract, QC limits and frozen CT protocol preparation.
"""

import argparse
import sys

from cranio.backend import default_npz_path
from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline


def parse_args(argv=None) -> PipelineConfig:
    parser = argparse.ArgumentParser(
        description="GNM facial reconstruction from craniofacial markers (Blender addon CSV).")
    parser.add_argument("--input", required=True, help="World-mm marker CSV v3; legacy v1/v2 also readable")
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
                        help="'auto' (conditional LOO-CV), 'adaptive' (base*48/included count), or a fixed value")
    parser.add_argument("--lambda-base", type=float, default=1.0)
    parser.add_argument("--lambda-min", type=float, default=0.3)
    parser.add_argument("--lambda-max", type=float, default=1000.0)
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
    parser.add_argument('--prior', default=None)
    parser.add_argument('--landmark-map', default=None)
    parser.add_argument('--protocol', default=None)
    parser.add_argument('--case-metadata', default=None)
    parser.add_argument('--craniometry', default=None,
                        help='Case craniometry JSON in world mm; otherwise uses embedded CSV metadata')
    parser.add_argument('--measurement-weight', type=float, default=0.,
                        help='Reviewed skin-distance block strength; 0 disables. Bone chords are never skin targets')
    parser.add_argument('--max-iter', type=int, default=30)
    parser.add_argument('--tolerance', type=float, default=1e-5)
    parser.add_argument('--clip-sigma', type=float, default=3.0)
    parser.add_argument('--prior-weight', type=float, default=1.0)
    parser.add_argument('--dense-max-rows', type=int, default=1500)
    parser.add_argument('--dense-nose-weight', type=float, default=0.7)
    parser.add_argument('--skull-normals-reviewed', action="store_true")
    parser.add_argument('--skull-flip-normals', action="store_true")
    parser.add_argument('--geometry-qc', default='basic')
    parser.add_argument('--require-qc', action="store_true")
    args = parser.parse_args(argv)

    return PipelineConfig(
        input=args.input,
        prior=args.prior,
        landmark_map=args.landmark_map,
        protocol=args.protocol,
        case_metadata=args.case_metadata,
        craniometry=args.craniometry,
        measurement_weight=args.measurement_weight,
        max_iter=args.max_iter,
        tolerance=args.tolerance,
        clip_sigma=args.clip_sigma,
        prior_weight=args.prior_weight,
        dense_max_rows=args.dense_max_rows,
        dense_nose_weight=args.dense_nose_weight,
        skull_normals_reviewed=args.skull_normals_reviewed,
        skull_flip_normals=args.skull_flip_normals,
        geometry_qc=args.geometry_qc,
        require_qc=args.require_qc,

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
        lambda_base=args.lambda_base,
        lambda_min=args.lambda_min,
        lambda_max=args.lambda_max,
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
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    return run_pipeline(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())

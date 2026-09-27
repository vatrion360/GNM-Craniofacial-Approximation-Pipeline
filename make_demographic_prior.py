#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genereaza priors/prior_<SEX>_<ETNIE>.npz pentru priorul demografic (V13.1).

Ruleaza intr-un mediu separat cu TensorFlow si GNM IdentitySampler;
NU poate rula in Blender):

    .venv/Scripts/python.exe make_demographic_prior.py
    .venv/Scripts/python.exe make_demographic_prior.py --samples 1024
    .venv/Scripts/python.exe make_demographic_prior.py --only MALE WHITE

Ce face: esantioneaza N identitati din CVAE-ul conditional al GNM
(gnm.shape.semantic_sampler.IdentitySampler; sex x etnie) si salveaza media
si deviatia standard per componenta de identitate (253,) intr-un npz mic.
Addon-ul Blender V13 incarca npz-ul si il foloseste ca prior Gaussian
diagonal in ridge-ul live (shrink spre media demografica, nu spre beta=0;
vezi cranio.optimize.fit_identity: prior_mean/prior_scale/prior_weight).

sigma este clipat la [SIGMA_CLIP_MIN, SIGMA_CLIP_MAX]: componentele cu
dispersie demografica foarte mica (ex. 0.01 sigma) nu trebuie sa inghete
fitul la media demografica. Clip-ul este aplicat numai la generare si
inregistrat in arhiva; solverul foloseste exact scalele salvate.
"""

import argparse
import json
import platform
from importlib.metadata import version
from pathlib import Path
import os
import sys
import time

import numpy as np

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

SIGMA_CLIP_MIN = 0.25
SIGMA_CLIP_MAX = 4.0

# Combinatiile demografice suportate de IdentitySampler (CVAE, GNM v3.0).
GENDERS = ("FEMALE", "MALE")
ETHNICITIES = ("MIDDLE_EASTERN", "ASIAN", "WHITE", "BLACK")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genereaza fisierele npz de prior demografic pentru "
                    "addon-ul Blender V13 (din IdentitySampler/TF).")
    parser.add_argument("--samples", type=int, default=512,
                        help="nr. de identitati esantionate per combo "
                             "(implicit 512)")
    parser.add_argument("--out", default=os.path.join(REPO_ROOT, "priors"),
                        help="directorul de iesire (implicit <repo>/priors)")
    parser.add_argument("--only", nargs=2, metavar=("SEX", "ETNIE"),
                        default=None,
                        help="genereaza un singur combo, ex. --only MALE WHITE")
    parser.add_argument("--seed", type=int, default=42,
                        help="seed RNG (reproductibilitate; implicit 42)")
    parser.add_argument('--decoder', required=True, help='Explicit trusted local GNM identity decoder file (H5/Keras)')
    args = parser.parse_args()
    if args.samples < 2 or args.seed < 0 or not Path(args.decoder).is_file():
        parser.error('Need samples >= 2, seed >= 0 and an existing local decoder')
    if args.only and (args.only[0].upper() not in GENDERS or args.only[1].upper() not in ETHNICITIES):
        parser.error('Unknown sex/ethnicity category')

    os.makedirs(args.out, exist_ok=True)

    # Importul TF dureaza cateva secunde - il facem dupa parsarea argumentelor.
    t0 = time.perf_counter()
    from gnm.shape.semantic_sampler import (
        Ethnicity, Gender, IdentitySampler)
    sampler = IdentitySampler(decoder_model_path=args.decoder, verbose=False)
    from cranio.validation import sha256_file
    from cranio.provenance import implementation_manifest
    manifest = dict(python=platform.python_version(), numpy=np.__version__, tensorflow=version('tensorflow'),
                    decoder_sha256=sha256_file(args.decoder), generator_sha256=sha256_file(__file__),
                    implementation=implementation_manifest(), scientific_status='experimental, not validated on paired CT subjects')
    print(f"IdentitySampler incarcat ({time.perf_counter() - t0:.1f}s).")

    combos = ([(args.only[0].upper(), args.only[1].upper())] if args.only
              else [(g, e) for g in GENDERS for e in ETHNICITIES])
    for g_name, e_name in combos:
        if g_name not in GENDERS or e_name not in ETHNICITIES:
            print(f"COMBO NECUNOSCUT: {g_name}/{e_name} - sarit.")
            continue
        t0 = time.perf_counter()
        rng = np.random.default_rng(args.seed)
        sam = sampler.sample_identity(
            Gender[g_name], Ethnicity[e_name],
            num_samples=args.samples, rng=rng)
        sam = np.asarray(sam, dtype=np.float64)
        if not np.isfinite(sam).all():
            raise ValueError("Sampler produced NaN/Inf")
        if sam.shape != (args.samples, 253):
            print(f"ATENTIE: forma neasteptata {sam.shape} pentru "
                  f"{g_name}/{e_name} - sarit.")
            continue
        mean = sam.mean(axis=0)
        scale = np.clip(sam.std(axis=0), SIGMA_CLIP_MIN, SIGMA_CLIP_MAX)
        path = os.path.join(args.out, f"prior_{g_name}_{e_name}.npz")
        np.savez(
            path, mean=mean, scale=scale, n_samples=args.samples,
            gender=g_name, ethnicity=e_name,
            sigma_clip=np.array([SIGMA_CLIP_MIN, SIGMA_CLIP_MAX]),
            source="gnm.shape.semantic_sampler.IdentitySampler (CVAE, GNM v3.0)",
            seed=args.seed, provenance_json=json.dumps(manifest, sort_keys=True))
        print(f"{g_name:7s}/{e_name:14s} |mu|={np.linalg.norm(mean):5.2f} "
              f"max|mu|={np.abs(mean).max():4.2f} "
              f"sigma[med]={np.median(scale):.2f} -> {path} "
              f"({time.perf_counter() - t0:.1f}s)")
    print("Gata.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

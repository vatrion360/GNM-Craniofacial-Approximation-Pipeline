# -*- coding: utf-8 -*-
"""Configuratia completa a unei rulari de reconstructie (PipelineConfig).

Inlocuieste imprastierea de argumente argparse din v3.1: un singur obiect
de date, cu aceleasi nume de attribute ca vechiul ``args``, care traverseaza
pipeline-ul si ajunge intact in raport (reproductibilitate).
"""

import os
import math
from dataclasses import dataclass, field
from typing import List, Optional

from .backend import default_npz_path


@dataclass
class PipelineConfig:
    """Toate optiunile pipeline-ului, cu implicitele din v3.1."""

    # Intrari/iesiri
    input: str = ""
    output: Optional[str] = None
    output_error_mesh: Optional[str] = None
    output_stats: Optional[str] = None
    output_json: Optional[str] = None
    output_statistical: Optional[str] = None
    npz: str = field(default_factory=default_npz_path)
    skull: Optional[str] = None

    # Fit statistic
    regularization: str = "auto"          # "auto" (LOO-CV) sau valoare fixa
    exclude: List[str] = field(default_factory=list)
    exclude_outliers: bool = False

    # Corectie locala TPS
    skip_tps: bool = True
    max_correction_mm: float = 15.0       # cap neted per-vertex pe scalp
    face_cap_mm: float = 8.0              # cap neted per-vertex pe fata
    protect_damping: float = 0.25         # amortizare zone fara ancore

    # Constrangeri dense (necesita skull)
    scalp_offset_mm: float = 5.0
    dense_weight: float = 0.5
    dense_samples: int = 200000
    tps_scalp_centres: int = 500
    tps_face_centres: int = 200
    no_face_dense: bool = False
    no_dense_fit: bool = False
    no_dense_tps: bool = False

    # Termeni optionali de loss (0.0 = dezactivat, comportament v3.1)
    symmetry_weight: float = 0.0
    distance_weight: float = 0.0
    prior_soft_sigma: float = 0.0
    prior_soft_weight: float = 4.0
    seed: int = 42
    overwrite: bool = False
    strict: bool = False

    def validate(self):
        if not self.input or not os.path.isfile(self.input):
            raise ValueError(f"Marker input not found: {self.input}")
        if not os.path.isfile(self.npz):
            raise ValueError(f"Model not found: {self.npz}; see docs/INSTALL.md")
        if self.skull and not os.path.isfile(self.skull):
            raise ValueError(f"Skull not found: {self.skull}")
        for name in ("max_correction_mm", "face_cap_mm", "scalp_offset_mm"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in ("dense_weight", "symmetry_weight", "distance_weight", "prior_soft_sigma", "prior_soft_weight"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if not math.isfinite(self.protect_damping) or not 0 <= self.protect_damping <= 1:
            raise ValueError("protect_damping must be in [0, 1]")
        for name in ("seed", "tps_scalp_centres", "tps_face_centres", "dense_samples"):
            value = getattr(self, name)
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.dense_samples < 10:
            raise ValueError("dense_samples must be at least 10")
        if str(self.regularization).lower() != "auto":
            value = float(self.regularization)
            if not math.isfinite(value) or value <= 0:
                raise ValueError("regularization must be 'auto' or finite and positive")
        from .validation import validate_outputs
        validate_outputs([self.input, self.npz, self.skull],
                         [self.output, self.output_error_mesh, self.output_stats,
                          self.output_json, self.output_statistical], self.overwrite)

    def fill_default_outputs(self):
        """Completeaza caile de iesire implicite din numele intrarii."""
        for name in ("input", "npz", "skull", "output", "output_stats", "output_error_mesh",
                     "output_json", "output_statistical"):
            value = getattr(self, name)
            if value is not None:
                setattr(self, name, os.fspath(value))
        if self.output is None:
            base, _ = os.path.splitext(self.input)
            self.output = base + "_reconstructie.obj"
        if self.output_error_mesh is None:
            base, _ = os.path.splitext(self.output)
            self.output_error_mesh = base + "_heatmap.ply"
        if self.output_stats is None:
            base, _ = os.path.splitext(self.output)
            self.output_stats = base + "_statistici.txt"
        base, _ = os.path.splitext(self.output)
        if self.output_json is None:
            self.output_json = base + "_report.json"
        if self.output_statistical is None:
            self.output_statistical = base + "_statistical.obj"

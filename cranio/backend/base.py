# -*- coding: utf-8 -*-
"""Interfata abstracta a unui backend de model facial statistic.

Un backend stie sa: incarce modelul, genereze mesh-uri din coeficienti de
identitate, expuna topologia, oglindirile si grupurile de vertecsi, si sa
lege etichetele anatomice de vertecsii modelului.

Nu stie nimic despre cranii, markeri sau Blender.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List

import numpy as np


@dataclass
class FaceModelData:
    """Datele unui model facial statistic liniar, in milimetri.

    Modelul este liniar in coeficientii de identitate (cu expresie si
    rotatii zero):
        V = mu + sum_i c_i * B_i

    Atribute:
        mu: (N, 3) pozitiile template-ului (mm).
        basis: (I, N, 3) baza de identitate (mm / sigma).
        triangles: (F, 3) topologia.
        mirror_indices: (N,) permutare de oglindire (vertex <-> pereche).
        vertex_groups: (G, N) ponderi per grup semantical.
        vertex_group_names: numele celor G grupuri.
        identity_names: optional component names from the archive; required for
            named subspace selection, never inferred from component count.
    """

    mu: np.ndarray
    basis: np.ndarray
    triangles: np.ndarray
    mirror_indices: np.ndarray
    vertex_groups: np.ndarray
    vertex_group_names: List[str]
    identity_names: List[str] | None = None

    @property
    def identity_dim(self) -> int:
        return int(self.basis.shape[0])

    @property
    def vertex_count(self) -> int:
        return int(self.mu.shape[0])

    def generate(self, coefficients: np.ndarray) -> np.ndarray:
        """Genereaza mesh-ul (N, 3) pentru coeficientii de identitate dati."""
        return self.mu + np.einsum("i,ivk->vk", coefficients, self.basis)

    def group_mask(self, name: str, thresh: float = 0.5) -> np.ndarray:
        """Masca booleana (N,) a vertecsilor din grupul semantic dat."""
        if name not in self.vertex_group_names:
            raise KeyError(f"Grup inexistent: {name!r}")
        return self.vertex_groups[self.vertex_group_names.index(name)] > thresh


class FaceModelBackend(ABC):
    """Contractul pe care il respecta orice model statistic de fata."""

    name: str = "abstract"

    @abstractmethod
    def load(self) -> FaceModelData:
        """Incarca modelul si il returneaza in milimetri."""

    @property
    @abstractmethod
    def landmark_vertex_map(self) -> Dict[str, int]:
        """Eticheta anatomica -> index de vertex in model."""

    @property
    @abstractmethod
    def index_to_label(self) -> Dict[int, str]:
        """Index CSV codificat -> eticheta (decodare fisiere markeri)."""

# -*- coding: utf-8 -*-
"""Exporturi: OBJ (mesh reconstruit) si PLY heatmap (corectia locala)."""

import numpy as np


def export_obj(path, vertices, triangles):
    """OBJ simplu (vertecsi in mm, spatiul world Blender)."""
    with atomic_text(path) as f:
        f.write("# GNM Reconstructie Craniofaciala - mesh reconstruit (mm)\n")
        for v in vertices:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for t in triangles:
            f.write(f"f {t[0]+1} {t[1]+1} {t[2]+1}\n")


def _heat_color(value):
    """Gradient albastru->cyan->verde->galben->rosu pentru value in [0,1]."""
    v = float(np.clip(value, 0.0, 1.0)) * 4.0
    seg = int(v)
    palette = [(0, 0, 255), (0, 255, 255), (0, 255, 0), (255, 255, 0),
               (255, 0, 0)]
    seg = min(seg, 3)
    frac = v - seg
    c0, c1 = palette[seg], palette[seg + 1]
    return tuple(int(round(c0[i] + (c1[i] - c0[i]) * frac)) for i in range(3))


def export_heatmap_ply(path, vertices, triangles, magnitudes):
    """PLY ASCII cu culoare per-vertex = magnitudinea corectiei locale."""
    vmax = float(magnitudes.max()) if magnitudes.size else 1.0
    vmax = max(vmax, 1e-9)
    with atomic_text(path) as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write("comment units mm; colors encode local displacement, NOT uncertainty\n")
        f.write(f"comment color_scale_max_mm {vmax:.9g}\n")
        f.write(f"element vertex {len(vertices)}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        f.write("property float displacement_mm\n")
        f.write(f"element face {len(triangles)}\n")
        f.write("property list uchar int vertex_indices\nend_header\n")
        for v, m in zip(vertices, magnitudes):
            r, g, b = _heat_color(m / vmax)
            f.write(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f} {r} {g} {b} {m:.6f}\n")
        for t in triangles:
            f.write(f"3 {t[0]} {t[1]} {t[2]}\n")


from contextlib import contextmanager
import os
from pathlib import Path
import tempfile


@contextmanager
def atomic_text(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            yield stream
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

"""Duplicate checks shared by Blender and offline fitting (NumPy only)."""
from collections import defaultdict
from itertools import combinations

import numpy as np


def duplicate_groups(values):
    groups = defaultdict(list)
    for index, value in enumerate(values):
        groups[value].append(index)
    return [indices for indices in groups.values() if len(indices) > 1]


def audit_landmarks(labels, vertices, targets=None, bones=None, near_mm=0.1):
    labels, vertices = list(labels), list(vertices)
    if len(labels) != len(vertices):
        raise ValueError('Landmark labels and vertices must have equal lengths')
    errors, warnings = [], []
    for what, values in [('label', labels), ('GNM vertex', vertices)]:
        for group in duplicate_groups(values):
            errors.append(f'Duplicate {what}: ' + ', '.join(labels[i] for i in group))
    if targets is not None:
        xyz = np.asarray(targets, dtype=float).reshape(-1, 3)
        if len(xyz) != len(labels) or not np.isfinite(xyz).all():
            raise ValueError('Audit targets must be finite and match the labels')
        for i, j in combinations(range(len(labels)), 2):
            if np.linalg.norm(xyz[i] - xyz[j]) <= 1e-6:
                errors.append(f'Coincident skin targets: {labels[i]}, {labels[j]}; review or exclude one')
    if bones:
        for a, b in combinations(bones, 2):
            distance = float(np.linalg.norm(np.asarray(bones[a]) - np.asarray(bones[b])))
            if distance <= near_mm:
                warnings.append(f'Bone sites within {near_mm:g} mm: {a}, {b} ({distance:.6g} mm); review definitions')
    return {'included_count': len(labels), 'unique_vertex_count': len(set(vertices)),
            'errors': errors, 'warnings': warnings}


def require_unique_landmarks(labels, vertices, targets=None):
    result = audit_landmarks(labels, vertices, targets)
    if result['errors']:
        raise ValueError('; '.join(result['errors']))
    return result

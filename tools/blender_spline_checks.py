"""Installed-ZIP NumPy interpolation against an external SciPy oracle."""
import builtins
from pathlib import Path
import subprocess
import time

import numpy as np


def run_spline_checks(addon, model, directory, executable):
    # The temporary arrays are software fixtures, not reconstructed subjects.
    vertices = model.mu.astype(float)
    rng = np.random.default_rng(3101)
    _, unique = np.unique(vertices, axis=0, return_index=True)
    ids = rng.choice(unique, 700, replace=False)
    centers, values = vertices[ids], rng.normal(size=(700, 3))*3
    caps = np.full(len(vertices), 8.)
    protected = np.flatnonzero(model.group_mask('eyes'))
    source, expected = Path(directory)/'spline-input.npz', Path(directory)/'spline-oracle.npz'
    np.savez(source, vertices=vertices, centers=centers, values=values, caps=caps, protected=protected)
    # Fixed code and argument list; SciPy runs ONLY in the external interpreter.
    bootstrap = """import sys, numpy as np
sys.path.insert(0, sys.argv[1])
from cranio.optimize import bounded_tps_correction
with np.load(sys.argv[2], allow_pickle=False) as data:
    result = bounded_tps_correction(data['vertices'], data['centers'], data['values'], data['caps'], data['protected'], .25)
np.savez(sys.argv[3], final=result[0], field=result[1], magnitudes=result[2])
"""
    options = addon._core_module('external_python').process_options()
    process = subprocess.run([executable, '-c', bootstrap, str(Path(addon.__file__).resolve().parent),
                              str(source), str(expected)], capture_output=True, text=True,
                              encoding='utf-8', errors='replace', stdin=subprocess.DEVNULL, timeout=90, **options)
    assert process.returncode == 0, process.stdout+process.stderr
    before = [x.copy() for x in (vertices, centers, values, caps, protected)]
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split('.')[0] in ('scipy', 'trimesh', 'tensorflow', 'bpy'):
            raise AssertionError('Non-NumPy numerical dependency in Blender spline: '+name)
        return original(name, *args, **kwargs)
    start = time.perf_counter()
    try:
        builtins.__import__ = guarded
        optimize = addon._core_module('optimize')
        actual = optimize.bounded_tps_correction(vertices, centers, values, caps, protected, .25, backend='numpy')
    finally:
        builtins.__import__ = original
    elapsed = time.perf_counter()-start
    with np.load(expected, allow_pickle=False) as oracle:
        for value, key in zip(actual, ('final', 'field', 'magnitudes')):
            np.testing.assert_allclose(value, oracle[key], rtol=0, atol=1e-6)
        maximum = float(np.linalg.norm(actual[0]-oracle['final'], axis=1).max())
        assert maximum <= 1e-6
    for a, b in zip(before, (vertices, centers, values, caps, protected)):
        np.testing.assert_array_equal(a, b)
    assert np.all(np.linalg.norm(actual[1], axis=1) <= caps+1e-12)
    assert np.all(np.linalg.norm(actual[1][protected], axis=1) <= .25*caps[protected]+1e-12)
    print(f'BLENDER_NUMPY_SPLINE_PARITY_PASS: centres=700 vertices={len(vertices)} max_mm={maximum:.12g} seconds={elapsed:.6f}')

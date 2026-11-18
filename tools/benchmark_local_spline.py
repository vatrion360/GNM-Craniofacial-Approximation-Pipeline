"""Seeded software benchmark; synthetic displacements are not CT evidence."""
import argparse
import json
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import scipy
from scipy.interpolate import RBFInterpolator

from cranio.backend import GNMBackend
from cranio.optimize import bounded_tps_correction
from cranio.tps import LinearPolyharmonic3D
from cranio.provenance import numerical_environment
from cranio.validation import sha256_file


def benchmark(model_path, centers=700, seed=3101):
    model = GNMBackend(model_path).load()
    vertices = model.mu.astype(float)
    _, unique = np.unique(vertices, axis=0, return_index=True)
    if type(centers) is not int or not 4 <= centers <= len(unique):
        raise ValueError('Centre count must be between 4 and the number of unique model positions')
    rng = np.random.default_rng(seed)
    ids = rng.choice(unique, centers, replace=False)
    points, values = vertices[ids], rng.normal(size=(centers, 3))*3
    caps = np.full(len(vertices), 8.)  # synthetic uniform cap equal to legacy face default
    protected = np.flatnonzero(model.group_mask('eyes'))
    outputs, seconds = {}, {}
    for backend in ('scipy', 'numpy'):
        start = time.perf_counter()
        outputs[backend] = bounded_tps_correction(vertices, points, values, caps, protected, .25, backend=backend)
        seconds[backend] = time.perf_counter()-start
    origin = points.mean(axis=0)
    reference = RBFInterpolator(points-origin, values, kernel='linear', degree=1, smoothing=0.)(vertices-origin)
    fitted = LinearPolyharmonic3D(points, values)
    raw_error = float(np.linalg.norm(fitted(vertices)-reference, axis=1).max())
    bounded_error = float(np.linalg.norm(outputs['numpy'][0]-outputs['scipy'][0], axis=1).max())
    if max(raw_error, bounded_error) > 1e-6:
        raise ValueError('Backend parity exceeded the 1e-6 mm engineering tolerance')
    return dict(schema_version=1, interpretation='Software benchmark on a model mesh with synthetic displacements; not anatomical validation',
        model_sha256=sha256_file(model_path), seed=seed, centres=centers, vertices=len(vertices),
        synthetic_displacement_sd_mm=3., synthetic_uniform_cap_mm=8., protection_group='eyes', damping=.25,
        bounded_solve_and_evaluate_seconds=seconds, max_raw_field_difference_mm=raw_error,
        max_bounded_vertex_difference_mm=bounded_error, engineering_tolerance_mm=1e-6,
        numpy_solver=fitted.diagnostics,
        runtime=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                     system=platform.system(), release=platform.release(), machine=platform.machine(), processor=platform.processor()),
        numerical_environment=numerical_environment(),
        implementation_sha256={name: sha256_file(Path(__file__).resolve().parents[1]/name)
                               for name in ('cranio/tps.py', 'cranio/optimize.py', 'tools/benchmark_local_spline.py')},
        timing_note='One sequential run per backend; no warm-up or speed guarantee. CPU/BLAS and thread counts affect timing.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--centres', type=int, default=700)
    parser.add_argument('--seed', type=int, default=3101)
    args = parser.parse_args()
    destination = Path(args.output)
    if destination.exists() or destination.is_symlink():
        parser.error('Benchmark output already exists')
    result = benchmark(args.model, args.centres, args.seed)
    from cranio.export import atomic_text
    with atomic_text(destination) as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({key: result[key] for key in ('centres', 'vertices', 'bounded_solve_and_evaluate_seconds',
        'max_raw_field_difference_mm', 'max_bounded_vertex_difference_mm')}))


if __name__ == '__main__':
    main()

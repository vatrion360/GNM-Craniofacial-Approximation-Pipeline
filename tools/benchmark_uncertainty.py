"""Time synthetic model-mean perturbations; no subject or accuracy benchmark.

Set OPENBLAS_NUM_THREADS=1 before Python. Supply an explicit engineering fixture
SD; it must never be interpreted as a measured human placement error.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--npz', required=True)
    parser.add_argument('--sigma-mm', required=True, type=float)
    parser.add_argument('--samples', type=int, default=200)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--max-iter', type=int, default=30)
    args = parser.parse_args()
    from cranio.backend import GNMBackend
    from cranio.io_csv import MarkerTarget
    from cranio.landmarks import LANDMARK_ORDER
    from cranio.uncertainty import monte_carlo_identity
    from cranio.validation import sha256_file
    backend = GNMBackend(args.npz)
    model = backend.load()
    targets = [MarkerTarget(label, backend.landmark_vertex_map[label],
                             model.mu[backend.landmark_vertex_map[label]], 1.) for label in LANDMARK_ORDER]
    config = dict(schema_version=1, placement={t.label: dict(sigma_mm=args.sigma_mm,
                  source='explicit synthetic engineering benchmark') for t in targets})
    start = time.perf_counter()
    result = monte_carlo_identity(model, targets, {'version': 3}, placement=config,
                                 samples=args.samples, seed=args.seed, max_iter=args.max_iter)
    elapsed = time.perf_counter()-start
    scenario = result['variants']['off']
    print(json.dumps(dict(elapsed_seconds=elapsed, samples=args.samples, seed=args.seed,
        sigma_mm=args.sigma_mm, max_iter=args.max_iter, markers=len(targets), components=model.identity_dim,
        model_sha256=sha256_file(args.npz), python=platform.python_version(), platform=platform.platform(),
        logical_cpus=os.cpu_count(), openblas_num_threads=os.environ.get('OPENBLAS_NUM_THREADS'),
        nonconverged=len(scenario['nonconverged_indices']), clipped=len(scenario['clipped_indices']),
        baseline_converged=scenario['baseline']['converged'],
        max_iterations_used=max(s['iterations'] for s in scenario['samples']),
        note='Synthetic model mean, placement only, lambda 30, no prior/TPS/dense; runtime only'), indent=2))


if __name__ == '__main__':
    main()

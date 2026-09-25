"""Optional direct parity check; needs the upstream checkout and its NumPy dependencies."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cranio.backend import GNMBackend
from cranio.validation import sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', required=True)
    parser.add_argument('--npz', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    upstream_root = Path(args.upstream).resolve()
    upstream_asset = upstream_root / 'gnm/shape/data/versions/v3_0/gnm_head.npz'
    if sha256_file(upstream_asset) != sha256_file(args.npz):
        parser.error('Upstream and local model assets differ')
    sys.path.insert(0, str(upstream_root))
    from gnm.shape import gnm_numpy
    reference = gnm_numpy.GNM.from_local(version=gnm_numpy.GNMMajorVersion.V3,
                                         variant=gnm_numpy.GNMVariant.HEAD)
    model = GNMBackend(args.npz).load()
    deviations = []
    for seed in (1, 2, 3):
        coefficients = np.random.default_rng(seed).normal(0, .25, model.identity_dim)
        expected = np.asarray(reference(identity=coefficients)) * 1000
        deviations.append(float(np.abs(expected - model.generate(coefficients)).max()))
    result = {'model_sha256': sha256_file(args.npz), 'seeds': [1, 2, 3],
              'coefficient_sd': .25, 'maximum_coordinate_deviation_mm': deviations,
              'tolerance_mm': .001, 'passed': max(deviations) < .001,
              'scope': 'Neutral expression/pose numerical parity, NOT skull-to-face accuracy'}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())

"""Independent landmark holdout checks, separate from conditional lambda tuning.

The excluded target NEVER enters pose fitting, coefficient fitting or lambda
selection. This tests generalisation to landmark targets; it does not measure
facial identity, population validity or accuracy to an independently known face.
"""
import argparse
import json

import numpy as np
from .backend import GNMBackend
from .export import atomic_text
from .io_csv import read_marker_csv
from .optimize import fit_identity
from .validation import finite_array, residual_metrics, sha256_file, validate_points


def landmark_holdout(model, indices, targets, weights, regularization=30.0):
    targets = validate_points(targets, 'holdout targets', minimum=5)
    indices = np.asarray(indices, dtype=np.int64)
    weights = finite_array(weights, 'holdout weights', (len(targets),))
    if indices.shape != (len(targets),):
        raise ValueError('Holdout indices and targets must have equal length')
    predictions, errors, lambdas = [], [], []
    for held_out in range(len(targets)):
        keep = np.arange(len(targets)) != held_out
        c, s, r, t, lam, _, _ = fit_identity(model.mu, model.basis,
                                           indices[keep], targets[keep], weights[keep],
                                           lam=regularization)
        predicted = s * (model.generate(c)[indices[held_out]] @ r.T) + t
        predictions.append(predicted)
        errors.append(float(np.linalg.norm(predicted - targets[held_out])))
        lambdas.append(float(lam))
    return {'method': 'outer leave-one-landmark-out with pose and identity refitted',
            'units': 'mm', 'metrics': residual_metrics(errors), 'errors_mm': errors,
            'predictions_mm': np.asarray(predictions).tolist(), 'fold_lambdas': lambdas,
            'interpretation': 'Generalisation to provided marker targets; not independent face accuracy'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--npz', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--regularization', default='30', help='Positive fixed lambda, or auto nested within each fold')
    args = parser.parse_args(argv)
    try:
        from .validation import validate_outputs
        validate_outputs([args.input, args.npz], [args.output])
        backend = GNMBackend(args.npz)
        targets, skipped, metadata = read_marker_csv(args.input, backend.index_to_label, backend.landmark_vertex_map)
        digest = sha256_file(args.npz)
        if metadata.get('model_sha256') and metadata['model_sha256'] != digest:
            raise ValueError('Marker/model SHA-256 mismatch')
        result = landmark_holdout(backend.load(), [x.vertex for x in targets],
                                  [x.xyz for x in targets], [x.weight for x in targets],
                                  'auto' if args.regularization == 'auto' else float(args.regularization))
        result.update(labels=[x.label for x in targets], skipped=skipped,
                      input_sha256=sha256_file(args.input), model_sha256=digest)
        with atomic_text(args.output) as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        print(args.output)
        return 0
    except (ValueError, OSError, np.linalg.LinAlgError) as exc:
        print(f'[FATAL ERROR] {exc}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

"""Opt-in empirical error-limit calibration from operator-reviewed measurements.

No CT segmentation, alignment, correspondence or anatomical validity is inferred.
A fitted multiplier defines a radial error limit, NOT a calibrated coordinate SD
or a guaranteed 95% interval. Scientific choices must be explicit in the manifest.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from .export import atomic_text
from .tissue import _json
from .validation import finite_array, has_documented_tissue_source, sha256_file, validate_outputs

PROTOCOL_FIELDS = {'model_sha256', 'fit_settings_sha256', 'region_definition_sha256', 'units',
                   'prediction_kind', 'error_definition', 'target_coverage', 'quantile_method',
                   'pooling', 'alignment_protocol', 'source'}
CASE_FIELDS = {'case_id', 'subject_id', 'split', 'measurements', 'measurements_sha256',
               'ensemble_sha256', 'reference_sha256', 'conditioning'}
CSV_FIELDS = ['vertex_index', 'region', 'error_mm', 'spread_rms_mm']
WARNINGS = [
    'Exploratory empirical error limits; no guaranteed population coverage or calibrated SD.',
    'Vertices are spatially correlated. Vertex count is not the independent subject count.',
    'The pooled-vertices multiplier weights cases by retained vertex count; ROI and density affect it.',
    'Calibration-set coverage is in-sample. Only disjoint validation subjects provide held-out evidence.',
    'Keep validation subjects out of protocol/ROI/parameter selection; repeated tuning on them invalidates held-out interpretation.',
    'Small cohorts cannot establish general validity; counts are reported without a sufficient-N threshold.',
    'Geometry, correspondence, CT segmentation and declared provenance are operator-reviewed, not verified here.',
    'No changes to fitting, meshes, raw SD fields or existing uncertainty exports.'
]


def _keys(value, expected, name):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f'{name}: expected exactly {sorted(expected)}')


def _text(value, name):
    if not has_documented_tissue_source(value):
        raise ValueError(f'{name}: documented non-placeholder text is required')
    return value


def _hash(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError(f'{name}: expected lowercase SHA-256')
    return value


def protocol_hash(protocol):
    """Validate a declared frozen protocol; do not supply missing scientific choices."""
    _keys(protocol, PROTOCOL_FIELDS, 'protocol')
    for key in ('model_sha256', 'fit_settings_sha256', 'region_definition_sha256'):
        _hash(protocol[key], key)
    if protocol['units'] != 'world_mm' or protocol['prediction_kind'] != 'statistical_ensemble_mean':
        raise ValueError('Only world_mm statistical_ensemble_mean predictions are supported')
    if protocol['error_definition'] not in ('euclidean_correspondence', 'unsigned_surface_distance'):
        raise ValueError('Select an explicit supported error_definition')
    q = protocol['target_coverage']
    if type(q) not in (float, int) or not np.isfinite(q) or not 0 < q < 1:
        raise ValueError('target_coverage must be explicitly supplied between 0 and 1')
    if protocol['quantile_method'] != 'higher' or protocol['pooling'] != 'pooled_vertices':
        raise ValueError('Explicit quantile_method=higher and pooling=pooled_vertices are required')
    _text(protocol['alignment_protocol'], 'alignment_protocol')
    _text(protocol['source'], 'source')
    return hashlib.sha256(json.dumps(protocol, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def coverage_metrics(errors_mm, spread_rms_mm, factor):
    """Empirical fraction error <= factor*spread, with inclusive boundary.

    Zero spread yields a zero limit: only exactly zero error is covered. Nothing
    is dropped or replaced by an epsilon. No independence or Gaussian assumption.
    """
    errors = finite_array(errors_mm, 'errors_mm')
    spread = finite_array(spread_rms_mm, 'spread_rms_mm', errors.shape)
    if errors.ndim != 1 or not errors.size or np.any(errors < 0) or np.any(spread < 0):
        raise ValueError('Nonempty nonnegative 1-D errors and spreads are required')
    if type(factor) not in (int, float) or not np.isfinite(factor) or factor < 0:
        raise ValueError('factor must be finite and nonnegative')
    limits = finite_array(factor*spread, 'error limits')
    covered = int(np.count_nonzero(errors <= limits))
    return dict(vertex_count=int(len(errors)), covered_vertices=covered, coverage=covered/len(errors),
                mean_error_mm=float(errors.mean()), mean_limit_mm=float(limits.mean()),
                min_limit_mm=float(limits.min()), max_limit_mm=float(limits.max()),
                zero_spread_vertices=int(np.count_nonzero(spread == 0)),
                zero_spread_positive_error_vertices=int(np.count_nonzero((spread == 0) & (errors > 0))))


def fit_multiplier(errors_mm, spread_rms_mm, target_coverage):
    """Empirical higher quantile of error/spread; zero/positive is not repairable."""
    coverage_metrics(errors_mm, spread_rms_mm, 1.)
    if type(target_coverage) not in (float, int) or not np.isfinite(target_coverage) or not 0 < target_coverage < 1:
        raise ValueError('target_coverage must lie between 0 and 1')
    error, spread = np.asarray(errors_mm, dtype=float), np.asarray(spread_rms_mm, dtype=float)
    if np.any((spread == 0) & (error > 0)):
        raise ValueError('Positive error with zero spread: no finite multiplicative calibration; revise error model')
    if not np.any(spread > 0):
        raise ValueError('No positive spread: cannot estimate a multiplier')
    ratios = np.divide(error, spread, out=np.zeros_like(error), where=spread > 0)
    finite_array(ratios, 'normalized errors')
    return float(np.quantile(ratios, target_coverage, method='higher'))


def _measurements(path):
    with open(path, encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != CSV_FIELDS:
            raise ValueError(f'Measurement CSV header must be {CSV_FIELDS}')
        rows = list(reader)
    if not rows:
        raise ValueError('Measurement CSV is empty')
    ids, regions, errors, spreads = [], [], [], []
    for line, row in enumerate(rows, 2):
        if set(row) != set(CSV_FIELDS) or any(v is None for v in row.values()):
            raise ValueError(f'Malformed measurement row {line}')
        raw = row['vertex_index']
        if not raw.isascii() or not raw.isdecimal():
            raise ValueError(f'Invalid vertex_index at row {line}')
        index = int(raw)
        ids.append(index)
        regions.append(_text(row['region'], f'row {line} region'))
        errors.append(float(row['error_mm']))
        spreads.append(float(row['spread_rms_mm']))
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate vertex_index; each retained vertex must have exactly one region')
    coverage_metrics(errors, spreads, 1.)
    return dict(vertex_indices=ids, regions=np.asarray(regions), errors=np.asarray(errors), spread=np.asarray(spreads))


def load_manifest(path):
    """Read explicit CSV paths only; declared reference/model hashes are not opened."""
    path = Path(path).expanduser().resolve()
    hashes = {str(path): sha256_file(path)}
    manifest = _json(path.read_text(encoding='utf-8-sig'))
    _keys(manifest, {'schema_version', 'protocol', 'cases'}, 'manifest')
    if type(manifest['schema_version']) is not int or manifest['schema_version'] != 1:
        raise ValueError('Expected manifest schema_version 1')
    protocol_hash(manifest['protocol'])
    if not isinstance(manifest['cases'], list) or not manifest['cases']:
        raise ValueError('Supply at least one case')
    seen = {k: set() for k in ('case_id', 'subject_id', 'measurements_sha256', 'ensemble_sha256', 'reference_sha256')}
    cases = []
    for item in manifest['cases']:
        _keys(item, CASE_FIELDS, 'case')
        for key in ('case_id', 'subject_id', 'measurements'):
            _text(item[key], key)
        for key in ('measurements_sha256', 'ensemble_sha256', 'reference_sha256'):
            _hash(item[key], key)
        if item['split'] not in ('calibration', 'validation'):
            raise ValueError('split must be calibration or validation')
        if item['conditioning'] != 'skull_only':
            raise ValueError('CT-conditioned predictions cannot calibrate skull-only approximation error')
        for key, values in seen.items():
            if item[key] in values:
                raise ValueError(f'Reused {key}: repeated subjects/predictions/references cannot count as independent cases')
            values.add(item[key])
        csv_path = Path(item['measurements']).expanduser()
        if not csv_path.is_absolute():
            csv_path = path.parent/csv_path
        csv_path = csv_path.resolve()
        digest = sha256_file(csv_path)
        if digest != item['measurements_sha256']:
            raise ValueError('Measurement CSV SHA-256 mismatch')
        hashes[str(csv_path)] = digest
        cases.append(dict(metadata=dict(item), **_measurements(csv_path)))
    if any(sha256_file(p) != digest for p, digest in hashes.items()):
        raise ValueError('An input changed while loading')
    return manifest, cases, hashes


def summarize_cases(cases, factor):
    """Report each case and region plus pooled and equal-case coverage."""
    if not cases:
        return None
    def metrics(selected, region=None):
        errors, spreads, individual = [], [], []
        for case in selected:
            mask = np.ones(len(case['errors']), dtype=bool) if region is None else case['regions'] == region
            if not mask.any():
                continue
            e, s = case['errors'][mask], case['spread'][mask]
            errors.extend(e)
            spreads.extend(s)
            individual.append(coverage_metrics(e, s, factor)['coverage'])
        result = coverage_metrics(errors, spreads, factor)
        result.update(subject_count=len(individual), equal_case_mean_coverage=float(np.mean(individual)))
        return result
    regions = sorted(set().union(*(set(c['regions']) for c in cases)))
    return dict(subject_count=len(cases), pooled=metrics(cases),
                regions={region: metrics(cases, region) for region in regions},
                cases=[dict(case_id=c['metadata']['case_id'], subject_id=c['metadata']['subject_id'],
                            metrics=metrics([c]), regions={r: metrics([c], r) for r in sorted(set(c['regions']))}) for c in cases])


def _independent_cases(cases):
    if not cases:
        raise ValueError('Supply nonempty case data')
    for key in ('subject_id', 'case_id', 'ensemble_sha256', 'reference_sha256', 'measurements_sha256'):
        values = [c['metadata'][key] for c in cases]
        if len(set(values)) != len(values):
            raise ValueError(f'Reused {key}: cases must be independent')
    for case in cases:
        if case['metadata']['conditioning'] != 'skull_only':
            raise ValueError('Only skull_only predictions are supported')
        if case['metadata']['split'] not in ('calibration', 'validation'):
            raise ValueError('Unknown case split')
        coverage_metrics(case['errors'], case['spread'], 1.)
        if np.asarray(case['regions']).shape != np.asarray(case['errors']).shape:
            raise ValueError('One region per measurement is required')


def fit_calibration(manifest, cases):
    """Fit on >=2 distinct calibration subjects; held-out cases never tune factor."""
    _independent_cases(cases)
    digest = protocol_hash(manifest['protocol'])
    training = [c for c in cases if c['metadata']['split'] == 'calibration']
    testing = [c for c in cases if c['metadata']['split'] == 'validation']
    if len(training) < 2:
        raise ValueError('At least two distinct calibration subjects are required; this is not a sufficient-N claim')
    factor = fit_multiplier(np.concatenate([c['errors'] for c in training]),
                            np.concatenate([c['spread'] for c in training]), manifest['protocol']['target_coverage'])
    result = dict(schema_version=1, method='empirical_radial_limit_multiplier', calibration_status='exploratory',
                  protocol=manifest['protocol'], protocol_sha256=digest, factor=factor,
                  training_cases=[c['metadata'] for c in training],
                  calibration=dict(before=summarize_cases(training, 1.), after=summarize_cases(training, factor)),
                  validation=dict(before=summarize_cases(testing, 1.), after=summarize_cases(testing, factor)),
                  warnings=list(WARNINGS))
    if not testing:
        result['warnings'].append('No held-out validation subjects; scale fitting only, not external validation.')
    if factor == 0:
        result['warnings'].append('Zero fitted multiplier from zero observed calibration errors; not evidence of certainty.')
    if manifest['protocol']['error_definition'] == 'unsigned_surface_distance':
        result['warnings'].append('Nearest-surface distance is not homologous-point error and can understate correspondence error.')
    return result


def evaluate_calibration(calibration, manifest, cases):
    """Apply a frozen factor only to disjoint subjects under the identical protocol."""
    _independent_cases(cases)
    if (not isinstance(calibration, dict) or type(calibration.get('schema_version')) is not int
            or calibration['schema_version'] != 1 or calibration.get('method') != 'empirical_radial_limit_multiplier'
            or calibration.get('calibration_status') != 'exploratory'):
        raise ValueError('Expected an exploratory empirical calibration record')
    digest = protocol_hash(calibration.get('protocol'))
    if calibration.get('protocol_sha256') != digest or protocol_hash(manifest['protocol']) != digest:
        raise ValueError('Frozen calibration protocol mismatch')
    training = calibration.get('training_cases')
    if not isinstance(training, list) or len(training) < 2:
        raise ValueError('Missing calibration subject provenance')
    for row in training:
        _keys(row, CASE_FIELDS, 'training case')
        for key in ('subject_id', 'case_id', 'measurements'):
            _text(row[key], key)
        for key in ('ensemble_sha256', 'reference_sha256', 'measurements_sha256'):
            _hash(row[key], key)
        if row['split'] != 'calibration' or row['conditioning'] != 'skull_only':
            raise ValueError('Invalid training provenance')
    for key in ('subject_id', 'case_id', 'ensemble_sha256', 'reference_sha256', 'measurements_sha256'):
        recorded = [c[key] for c in training]
        if len(set(recorded)) != len(recorded) or any(c['metadata'][key] in recorded for c in cases):
            raise ValueError(f'Calibration/validation leakage or duplicate training {key}')
    if any(c['metadata']['split'] != 'validation' for c in cases):
        raise ValueError('Evaluation accepts validation cases only; it never refits the multiplier')
    factor = calibration.get('factor')
    result = dict(schema_version=1, method='frozen_empirical_limit_evaluation', calibration_status='exploratory',
                  protocol_sha256=digest, factor=factor, calibration_subject_count=len(training),
                  before=summarize_cases(cases, 1.), after=summarize_cases(cases, factor), warnings=list(WARNINGS))
    return result


def empty_manifest():
    """No invented scientific settings; fill the TODO(verify-source) protocol first."""
    protocol = dict.fromkeys(sorted(PROTOCOL_FIELDS))
    protocol.update(units='world_mm', prediction_kind='statistical_ensemble_mean')
    return dict(schema_version=1, protocol=protocol, cases=[])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('template', 'fit', 'evaluate'))
    parser.add_argument('--manifest')
    parser.add_argument('--calibration', help='Frozen fit JSON, required for evaluate')
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == 'template':
            if args.manifest or args.calibration:
                raise ValueError('template takes only --output')
            hashes, result = {}, empty_manifest()
        else:
            if not args.manifest or (args.action == 'evaluate') != bool(args.calibration):
                raise ValueError('Supply --manifest; --calibration is required only for evaluate')
            manifest, cases, hashes = load_manifest(args.manifest)
            if args.action == 'fit':
                result = fit_calibration(manifest, cases)
            else:
                path = str(Path(args.calibration).expanduser().resolve())
                hashes[path] = sha256_file(path)
                calibration = _json(Path(path).read_text(encoding='utf-8-sig'))
                result = evaluate_calibration(calibration, manifest, cases)
            from . import __version__
            result.update(input_hashes=hashes, input_manifest=manifest,
                          implementation=dict(cranio=__version__, numpy=np.__version__, source_sha256=sha256_file(__file__)))
        validate_outputs(hashes, [args.output])
        if any(sha256_file(p) != digest for p, digest in hashes.items()):
            raise ValueError('An analysis input changed; refusing to publish')
        with atomic_text(args.output) as stream:
            json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write('\n')
        print(args.output)
        for warning in result.get('warnings', []):
            print('WARNING: '+warning)
        return 0
    except (ValueError, OSError, TypeError, OverflowError) as exc:
        print(f'Calibration unavailable: {exc}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

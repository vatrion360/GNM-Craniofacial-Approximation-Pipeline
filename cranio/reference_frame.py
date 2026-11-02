"""Explicit bone-based reference frame. NumPy only; never transforms fit inputs.

RAS columns mean anatomical right, anterior, superior, independent of the scan's
world axes. Three-point Frankfort and fitted cranial midline planes are distinct.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from . import craniometry as cm
from .export import atomic_text
from .restoration import fit_reference_plane
from .validation import finite_array, sha256_file, validate_outputs

CRANIAL_MEDIAN = frozenset(('n', 'g', 'ba', 'b', 'l', 'o', 'op', 'ns', 'ss'))
EPS = 64 * np.finfo(float).eps  # numerical degeneracy, not anatomical plausibility


def empty_config():
    """No automatic anatomical convention or placement-error imputation."""
    return dict(schema_version=1, orbitale=None, superior_code=None,
                midline_codes=[], source='', placement_error=None)


def _source(value):
    if not isinstance(value, str) or value.strip().casefold() in (
            '', 'unspecified', 'legacy-unvalidated', 'todo(verify-source)', '[de completat]'):
        raise ValueError('Document the configuration / placement error source')


def validate_config(config):
    """Validate explicit choices, returning the ordered set of required codes."""
    if not isinstance(config, dict) or set(config) != set(empty_config()):
        raise ValueError('Reference-frame configuration fields must match the template')
    if type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ValueError('Unsupported reference-frame schema')
    if config['orbitale'] not in ('or_L', 'or_R'):
        raise ValueError('Explicitly choose orbitale or_L or or_R')
    superior = config['superior_code']
    if not isinstance(superior, str) or superior not in CRANIAL_MEDIAN:
        raise ValueError('Choose a cranial median superior_code, above the Frankfort plane')
    midline = config['midline_codes']
    if (not isinstance(midline, list) or len(midline) < 3
            or any(not isinstance(c, str) or c not in CRANIAL_MEDIAN for c in midline)
            or len(set(midline)) != len(midline)):
        raise ValueError('midline_codes needs >=3 distinct cranial median references; no mandibular points')
    _source(config['source'])
    codes = list(dict.fromkeys(['po_R', 'po_L', config['orbitale'], superior] + midline))
    error = config['placement_error']
    if error is not None:
        if not isinstance(error, dict) or set(error) != {'samples', 'seed', 'points'}:
            raise ValueError('placement_error requires samples, seed and points')
        if type(error['samples']) is not int or error['samples'] < 2:
            raise ValueError('samples must be an integer >=2')
        if type(error['seed']) is not int or error['seed'] < 0:
            raise ValueError('seed must be a nonnegative integer')
        if not isinstance(error['points'], dict) or set(error['points']) != set(codes):
            raise ValueError('Supply placement SD and source for every used point, and only those points')
        for row in error['points'].values():
            if not isinstance(row, dict) or set(row) != {'sigma_mm', 'source'}:
                raise ValueError('Each placement row requires sigma_mm and source')
            sd = row['sigma_mm']
            if isinstance(sd, bool) or not isinstance(sd, (int, float)) or not np.isfinite(sd) or sd < 0:
                raise ValueError('sigma_mm must be finite and nonnegative; no missing-error imputation')
            _source(row['source'])
    return codes


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _inputs(document, config):
    codes = validate_config(config)
    points, _ = cm.validate_document(document)
    cm.measure(document)  # validates unique source IDs and digests too
    sources = {s['id']: s['geometry_sha256'] for s in document.get('bone_sources', [])}
    selected = {}
    for code in codes:
        row = points.get(code, {})
        if row.get('status') != 'observed' or not row.get('definition_reviewed'):
            raise ValueError(f'{code}: reference frame requires observed, reviewed bone')
        digest = row.get('source_geometry_sha256')
        if not digest or sources.get(row.get('source_id')) != digest:
            raise ValueError(f'{code}: missing or stale bone source; re-place and review')
        selected[code] = row
    signature = hashlib.sha256(_json(dict(configuration=config, points=selected)).encode()).hexdigest()
    return {c: finite_array(r['xyz_mm'], c, (3,)) for c, r in selected.items()}, selected, signature


def input_signature(document, config):
    """Validate current provenance and fingerprint used observations only."""
    return _inputs(document, config)[2]


def _unit(value, scale):
    value = finite_array(value, 'frame vector', (3,))
    norm = np.linalg.norm(value)
    if not np.isfinite(norm) or norm <= EPS * scale:
        raise ValueError('Degenerate frame: coincident or collinear Frankfort references')
    return value / norm


def _angle(a, b):
    return float(np.degrees(np.arctan2(np.linalg.norm(np.cross(a, b)), np.dot(a, b))))


def geometry_frame(points, config):
    """Compute a proper RAS transform and an independent least-squares plane."""
    pr, pl, orbital = (points[c] for c in ('po_R', 'po_L', config['orbitale']))
    origin = (pr + pl) / 2
    offset = orbital - origin
    scale = max(np.linalg.norm(pr-pl), np.linalg.norm(offset))
    right = _unit(pr-pl, scale)
    anterior = _unit(offset - right*np.dot(offset, right), scale)
    superior = _unit(np.cross(right, anterior), 1.)
    cue = points[config['superior_code']] - origin
    if not np.isfinite(cue).all() or np.dot(cue, superior) <= EPS*max(scale, np.linalg.norm(cue)):
        raise ValueError('Superior reference is not above Frankfort: review L/R labels, definitions and pose')
    axes = np.column_stack((right, anterior, superior))
    median = np.array([points[c] for c in config['midline_codes']])
    centre, normal, rms = fit_reference_plane(median)
    singular = np.linalg.svd(median-centre, compute_uv=False)
    if singular[1]-singular[2] <= EPS*singular[0] or abs(np.dot(normal, right)) <= EPS:
        raise ValueError('Ambiguous midsagittal plane normal; review reference distribution')
    if np.dot(normal, right) < 0:
        normal = -normal
    frame_to_world = np.eye(4)
    frame_to_world[:3, :3], frame_to_world[:3, 3] = axes, origin
    world_to_frame = np.eye(4)
    world_to_frame[:3, :3], world_to_frame[:3, 3] = axes.T, -axes.T@origin
    finite_array(world_to_frame, 'world_to_frame', (4, 4))
    return dict(origin_mm=origin.tolist(), axes_world=axes.tolist(),
                frame_to_world=frame_to_world.tolist(), world_to_frame=world_to_frame.tolist(),
                midsagittal=dict(origin_mm=centre.tolist(), normal_world=normal.tolist(),
                    residual_rms_mm=rms, singular_values_mm=singular.tolist(),
                    normal_to_right_angle_deg=_angle(normal, right)))


def compute_frame(document, config):
    """Return an auditable snapshot; optional SDs describe a conditional error model.

    Monte Carlo uses independent isotropic per-coordinate Gaussian placement
    errors. No accepted-sample filtering: an invalid draw rejects the analysis.
    Residual RMS is not an uncertainty estimate or anatomical accuracy measure.
    """
    points, rows, signature = _inputs(document, config)
    base = geometry_frame(points, config)
    uncertainty = dict(status='not_assessed', reason='Placement error uncalibrated / not configured')
    warnings = ['Three Frankfort points define a plane exactly; zero residual is not confidence.',
                'Midsagittal residual measures reference agreement, not anatomical accuracy.']
    error = config['placement_error']
    if error is not None:
        rng = np.random.Generator(np.random.PCG64(error['seed']))
        angles, origins, sagittal = [], [], []
        for i in range(error['samples']):
            noisy = {c: p + rng.normal(0., error['points'][c]['sigma_mm'], 3) for c, p in points.items()}
            try:
                draw = geometry_frame(noisy, config)
            except (ValueError, np.linalg.LinAlgError) as exc:
                raise ValueError(f'Placement sample {i+1} invalid; no draws discarded: {exc}') from exc
            origins.append(draw['origin_mm'])
            angles.append([_angle(a, b) for a, b in zip(np.array(base['axes_world']).T,
                                                       np.array(draw['axes_world']).T)])
            sagittal.append(_angle(base['midsagittal']['normal_world'], draw['midsagittal']['normal_world']))
        uncertainty = dict(status='conditional_uncalibrated', model='independent_isotropic_gaussian_per_coordinate',
            samples=error['samples'], seed=error['seed'], generator='PCG64',
            origin_coordinate_sd_mm=np.std(origins, axis=0, ddof=1).tolist(),
            axis_angle_p95_deg=np.percentile(angles, 95, axis=0).tolist(),
            midsagittal_normal_angle_p95_deg=float(np.percentile(sagittal, 95)))
        warnings.append('Placement SD propagation excludes systematic landmark, protocol and segmentation errors.')
        if all(row['sigma_mm'] == 0 for row in error['points'].values()):
            warnings.append('All supplied SDs are zero; this is not evidence of zero anatomical uncertainty.')
    return dict(schema_version=1, status='current', units='world_mm', axes_order=['right', 'anterior', 'superior'],
                method='three_point_frankfort_independent_cranial_midline', configuration=json.loads(_json(config)),
                input_signature=signature, used_points=rows, geometry=base, uncertainty=uncertainty,
                warnings=warnings, numpy_version=np.__version__)


def camera_basis(record, view):
    """Return camera right/up/back columns, preserving anatomical superior roll."""
    if record.get('status') != 'current':
        raise ValueError('Reference frame is stale or missing; recompute after review')
    axes = finite_array(record['geometry']['axes_world'], 'axes', (3, 3))
    finite_array(record['geometry']['origin_mm'], 'origin', (3,))
    if not np.allclose(axes.T@axes, np.eye(3), atol=1e-10, rtol=0) or np.linalg.det(axes) <= 0:
        raise ValueError('Reference axes must be a proper orthonormal frame')
    right, anterior, superior = axes.T
    directions = dict(front=anterior, profile=right, left=-right, **{'3quarter': (anterior+right)/np.sqrt(2)})
    if view not in directions:
        raise ValueError('Unknown reference-frame view')
    back = directions[view]
    return np.column_stack((np.cross(superior, back), superior, back))


def main(argv=None):
    """Offline template/compute entry point; refuses overwrites and input mutation."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    template = sub.add_parser('template')
    template.add_argument('--output', required=True)
    compute = sub.add_parser('compute')
    compute.add_argument('--input', required=True, help='Craniometry JSON in world mm')
    compute.add_argument('--config', required=True)
    compute.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        inputs = [] if args.action == 'template' else [args.input, args.config]
        validate_outputs(inputs, [args.output])
        hashes = {p: sha256_file(p) for p in inputs}
        if args.action == 'template':
            result = empty_config()
        else:
            result = compute_frame(json.loads(Path(args.input).read_text(encoding='utf-8')),
                                   json.loads(Path(args.config).read_text(encoding='utf-8')))
            result['input_sha256'] = hashes[args.input]
            result['config_sha256'] = hashes[args.config]
            result['implementation_sha256'] = sha256_file(__file__)
        if any(sha256_file(p) != digest for p, digest in hashes.items()):
            raise ValueError('Input changed during reference-frame calculation')
        with atomic_text(args.output) as stream:
            stream.write(_json(result)+'\n')
        return 0
    except (ValueError, TypeError, KeyError, OSError, np.linalg.LinAlgError) as exc:
        parser.exit(2, f'Reference frame: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())

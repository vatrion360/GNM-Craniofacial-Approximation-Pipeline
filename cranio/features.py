"""Opt-in, protocol-defined cranial measurements; no inferred classifications.

NumPy only. Bone observations remain independent of skin targets and fitting.
Missing anatomy invalidates only dependent measurements, not the whole case.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np

from . import __version__, craniometry as cm, reference_frame as rf
from .uncertainty import placement_config
from .validation import finite_array, sha256_file, validate_outputs
from .export import atomic_text

FEATURES = {
    'gnathic_ratio': ('ratio',), 'facial_angle': ('angle', 'line_angle', 'signed_angle'),
    'anb_angle': ('angle', 'signed_angle'), 'pogonion_projection': ('anterior_offset',),
    'mandibular_plane_angle': ('plane_inclination', 'line_inclination'),
    'gonial_angle_R': ('angle', 'line_angle'), 'gonial_angle_L': ('angle', 'line_angle'),
    'ramus_height_R': ('distance', 'superior_span'), 'ramus_height_L': ('distance', 'superior_span'),
    'bigonial_breadth': ('distance',),
}
COUNTS = dict(distance=2, ratio=4, angle=3, line_angle=4, signed_angle=3,
              anterior_offset=2, plane_inclination=3, line_inclination=2, superior_span=2)
FRAME_KINDS = frozenset(('anterior_offset', 'plane_inclination', 'line_inclination', 'superior_span', 'signed_angle'))
MANDIBULAR = frozenset(('sm', 'id', 'me', 'pg', 'go_R', 'go_L', 'co_R', 'co_L'))


def empty_config() -> dict:
    """Unconfigured definitions, thresholds and error assumptions; no guesses."""
    return dict(schema_version=1, features={key: dict(definition=None, source=None, reviewed=False)
                for key in FEATURES}, frame_config=None, mandible_pose=None, uncertainty=None, thresholds=None)


def definition_hash(definition):
    return hashlib.sha256(rf._json(definition).encode()).hexdigest()


def needs_frame(spec):
    return spec['space'] == 'sagittal' or spec['kind'] in FRAME_KINDS


def units(spec):
    if spec['kind'] == 'ratio':
        return 'ratio'
    return 'deg' if spec['kind'] in ('angle', 'line_angle', 'signed_angle', 'plane_inclination', 'line_inclination') else 'mm'


def validate_config(config: dict) -> None:
    """Reject ambiguous definitions and malformed uncertainty/threshold contracts."""
    if not isinstance(config, dict) or set(config) != set(empty_config()):
        raise ValueError('Feature configuration fields must match the template')
    if type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ValueError('Unsupported feature schema')
    rows = config['features']
    if not isinstance(rows, dict) or set(rows) != set(FEATURES):
        raise ValueError('features must contain exactly the template feature IDs')
    for name, row in rows.items():
        if not isinstance(row, dict) or set(row) != {'definition', 'source', 'reviewed'} or type(row['reviewed']) is not bool:
            raise ValueError(f'{name}: requires definition, source and boolean reviewed')
        spec = row['definition']
        if spec is None:
            if row['reviewed']:
                raise ValueError(f'{name}: cannot review an absent definition')
            continue
        if not isinstance(spec, dict) or set(spec) != {'kind', 'points', 'space'}:
            raise ValueError(f'{name}: definition needs kind, ordered points and space')
        kind, points, space = spec['kind'], spec['points'], spec['space']
        if kind not in FEATURES[name] or space not in ('3d', 'sagittal'):
            raise ValueError(f'{name}: unsupported operation or projection')
        if (not isinstance(points, list) or len(points) != COUNTS[kind]
                or any(not isinstance(p, str) or p not in cm.ALL_POINTS for p in points)):
            raise ValueError(f'{name}: wrong number of points or unknown canonical bone code')
        fixed = {'gnathic_ratio': ['ba', 'pr', 'ba', 'n'], 'bigonial_breadth': ['go_R', 'go_L'],
                 'anb_angle': ['ss', 'n', 'sm'], 'pogonion_projection': ['pg', 'n']}
        if name in fixed and points != fixed[name]:
            raise ValueError(f'{name}: required ordered bone codes are {fixed[name]}')
        if name in ('gnathic_ratio', 'bigonial_breadth') and space != '3d':
            raise ValueError(f'{name}: requires 3d Euclidean chords')
        if kind == 'plane_inclination' and space != '3d':
            raise ValueError('A plane inclination requires three spatial points, not a sagittal projection')
        if kind == 'signed_angle' and space != 'sagittal':
            raise ValueError('signed_angle requires an explicitly oriented sagittal projection')
        if row['source'] is not None:
            rf._source(row['source'])
        if row['reviewed']:
            rf._source(row['source'])
    frame = config['frame_config']
    if frame is not None:
        rf.validate_config(frame)
        if frame['placement_error'] is not None:
            raise ValueError('Use the feature uncertainty config once; frame placement_error must be null')
    pose = config['mandible_pose']
    if pose is not None:
        if not isinstance(pose, dict) or set(pose) != {'reviewed', 'source'} or type(pose['reviewed']) is not bool:
            raise ValueError('mandible_pose requires reviewed and source')
        if pose['reviewed']:
            rf._source(pose['source'])
    error = config['uncertainty']
    if error is not None:
        if not isinstance(error, dict) or set(error) != {'samples', 'seed', 'placement'}:
            raise ValueError('uncertainty requires samples, seed and placement')
        if type(error['samples']) is not int or error['samples'] < 2 or type(error['seed']) is not int or error['seed'] < 0:
            raise ValueError('Specify samples >=2 and seed >=0 as integers')
        placement_config(dict(schema_version=1, placement=error['placement']), list(cm.ALL_POINTS))
    thresholds = config['thresholds']
    if thresholds is not None:
        if not isinstance(thresholds, dict) or set(thresholds)-set(FEATURES):
            raise ValueError('Unknown threshold feature')
        for name, rule in thresholds.items():
            if not isinstance(rule, dict) or set(rule) != {'source', 'definition_sha256', 'units', 'cuts', 'labels'}:
                raise ValueError(f'{name}: threshold contract fields missing/unknown')
            rf._source(rule['source'])
            spec = rows[name]['definition']
            if spec is None or rule['definition_sha256'] != definition_hash(spec) or rule['units'] != units(spec):
                raise ValueError(f'{name}: thresholds do not match definition hash and units')
            cuts, labels = rule['cuts'], rule['labels']
            if (not isinstance(cuts, list) or not cuts or any(type(v) not in (float, int) for v in cuts)
                    or not np.isfinite(cuts).all() or np.any(np.diff(cuts) <= 0)):
                raise ValueError('Threshold cuts must be finite, strictly increasing numbers')
            if (not isinstance(labels, list) or len(labels) != len(cuts)+1
                    or any(not isinstance(v, str) or not v.strip() for v in labels) or len(set(labels)) != len(labels)):
                raise ValueError('Threshold labels must be distinct nonempty texts; count = cuts + 1')


def _length(vector):
    value = float(np.linalg.norm(vector))
    if not np.isfinite(value) or value <= rf.EPS:
        raise ValueError('Zero/overflowing measurement vector; review points and projection')
    return value


def evaluate_geometry(points: dict, spec: dict, frame: dict | None = None) -> float:
    """Evaluate the fully recorded mathematical construction, without anatomy inference."""
    p = finite_array([points[c] for c in spec['points']], 'feature points')
    kind = spec['kind']
    if needs_frame(spec):
        if frame is None:
            raise ValueError('Frame configuration / observed references required')
        p = (p-np.asarray(frame['origin_mm'])) @ np.asarray(frame['axes_world'])
        if spec['space'] == 'sagittal':
            p[:, 0] = 0  # orthogonal projection onto the frame YZ plane
    if kind == 'distance':
        value = _length(p[0]-p[1])
    elif kind == 'ratio':
        value = _length(p[0]-p[1])/_length(p[2]-p[3])
    elif kind in ('anterior_offset', 'superior_span'):
        value = float((p[0]-p[1])[1 if kind == 'anterior_offset' else 2])
        if kind == 'superior_span':
            value = abs(value)
    elif kind in ('plane_inclination', 'line_inclination'):
        if kind == 'plane_inclination':
            a, b = p[1]-p[0], p[2]-p[0]
            a, b = a/_length(a), b/_length(b)
            normal = np.cross(a, b)
            normal /= _length(normal)
            value = np.degrees(np.arctan2(np.linalg.norm(normal[:2]), abs(normal[2])))
        else:
            direction = p[0]-p[1]
            _length(direction)
            value = np.degrees(np.arctan2(abs(direction[2]), np.linalg.norm(direction[:2])))
    else:
        a, b = (p[0]-p[1], p[2]-p[1]) if kind != 'line_angle' else (p[1]-p[0], p[3]-p[2])
        a, b = a/_length(a), b/_length(b)
        cross, dot = np.cross(a, b), np.dot(a, b)
        value = np.degrees(np.arctan2(cross[0] if kind == 'signed_angle' else np.linalg.norm(cross), dot))
    if not np.isfinite(value):
        raise ValueError('Nonfinite feature result')
    return float(value)


def _observations(document):
    points, _ = cm.validate_document(document)
    cm.measure(document)
    sources = {s['id']: s['geometry_sha256'] for s in document.get('bone_sources', [])}
    return points, sources


def _required(spec, config):
    required = list(spec['points'])
    if needs_frame(spec):
        if config['frame_config'] is None:
            raise ValueError('Reference frame not configured')
        required += rf.validate_config(config['frame_config'])
    return list(dict.fromkeys(required))


def _verified(points, sources, required, config):
    if any(c in MANDIBULAR for c in required) and not (config['mandible_pose'] or {}).get('reviewed'):
        raise ValueError('Mandibular pose / fragment assembly not reviewed')
    xyz = {}
    for code in required:
        row = points.get(code, {})
        if row.get('status') != 'observed' or not row.get('definition_reviewed'):
            raise ValueError(f'{code}: requires observed, reviewed bone; no mirrored/donor substitution')
        if not row.get('source_geometry_sha256') or sources.get(row.get('source_id')) != row['source_geometry_sha256']:
            raise ValueError(f'{code}: bone source missing or stale')
        xyz[code] = finite_array(row['xyz_mm'], code, (3,))
    return xyz


def compute_features(document: dict, config: dict) -> dict:
    """Compute independent rows with optional conditional 95% perturbation intervals.

    Recompute frame geometry for every perturbed draw. Reuse A2's SD contract;
    missing SDs leave the dependent interval unavailable, never zero-filled.
    Threshold labels are operator-supplied descriptions, not diagnostic inference.
    """
    validate_config(config)
    points, sources = _observations(document)
    results = {}
    error = config['uncertainty']
    placement = placement_config(dict(schema_version=1, placement=error['placement']), list(cm.ALL_POINTS)) if error else {}
    for name, row in config['features'].items():
        spec = row['definition']
        out = dict(status='not_configured', value=None, units=units(spec) if spec else None,
                   definition=copy.deepcopy(spec), source=row['source'], uncertainty=dict(status='not_assessed'),
                   classification=dict(status='not_assessed'))
        results[name] = out
        if spec is None or not row['reviewed']:
            out['reason'] = 'TODO(verify-source): configure and review definition/source'
            continue
        try:
            required = _required(spec, config)
            xyz = _verified(points, sources, required, config)
            frame = rf.geometry_frame(xyz, config['frame_config']) if needs_frame(spec) else None
            out['value'] = evaluate_geometry(xyz, spec, frame)
            out.update(status='measured', definition_sha256=definition_hash(spec),
                       observations={c: points[c] for c in required})
        except (ValueError, np.linalg.LinAlgError) as exc:
            out.update(status='unavailable', reason=str(exc))
            continue
        if error:
            missing = [c for c in required if placement[c]['sigma_mm'] is None]
            if missing:
                out['uncertainty'] = dict(status='unavailable', reason='Placement SD uncalibrated / missing', missing=missing)
            else:
                # Shared points have identical draws across features and are sampled once per draw.
                draws = {c: np.random.Generator(np.random.PCG64(np.random.SeedSequence(
                    [error['seed'], list(cm.ALL_POINTS).index(c)]))).normal(0, placement[c]['sigma_mm'], (error['samples'], 3))
                    for c in required}
                values = []
                try:
                    for i in range(error['samples']):
                        noisy = {c: p+draws[c][i] for c, p in xyz.items()}
                        frame = rf.geometry_frame(noisy, config['frame_config']) if needs_frame(spec) else None
                        value = evaluate_geometry(noisy, spec, frame)
                        if spec['kind'] == 'signed_angle' and abs(value-out['value']) > 180:
                            raise ValueError('Signed-angle branch crossed; linear percentile interval refused')
                        values.append(value)
                    out['uncertainty'] = dict(status='conditional_uncalibrated', samples=error['samples'], seed=error['seed'],
                        percentile_interval_95=np.percentile(values, [2.5, 97.5]).tolist(),
                        sd=float(np.std(values, ddof=1)), placement={c: placement[c] for c in required},
                        all_supplied_sd_zero=all(placement[c]['sigma_mm'] == 0 for c in required))
                except (ValueError, np.linalg.LinAlgError) as exc:
                    out['uncertainty'] = dict(status='failed', failed_sample=i+1, reason=str(exc),
                                              interval=None, policy='No filtering; entire interval withheld')
        rule = (config['thresholds'] or {}).get(name)
        if rule is None:
            out['classification'] = dict(status='no_thresholds_configured')
        else:
            label = lambda v: rule['labels'][int(np.searchsorted(rule['cuts'], v, side='right'))]
            interval = out['uncertainty'].get('percentile_interval_95')
            out['classification'] = dict(status='configured_descriptive', point_label=label(out['value']),
                interval_label=('indeterminate' if label(interval[0]) != label(interval[1]) else label(interval[0])) if interval else None,
                interval_status=out['uncertainty']['status'], source=rule['source'])
    return dict(schema_version=1, case_id=document.get('case_id', ''), configuration=copy.deepcopy(config),
                input_signature=hashlib.sha256(rf._json(dict(points=points, sources=sources, config=config)).encode()).hexdigest(),
                features=results, software_version=__version__, numpy_version=np.__version__,
                random_streams=(dict(generator='PCG64', seed_sequence='[seed, point_order_index]',
                                     point_order=list(cm.ALL_POINTS)) if error else None),
                warnings=['Operator-defined geometry, not a diagnostic or facial-fit constraint.',
                          'Intervals are conditional input-error propagation, not calibrated confidence or population ranges.',
                          'Mandibular pose/fragment assembly is a recorded assumption, not an inferred occlusion.',
                          'Sagittal projection uses the Frankfort frame YZ plane, not the independent fitted midline plane.'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('template').add_argument('--output', required=True)
    run = commands.add_parser('compute')
    for flag in ('input', 'config', 'output'):
        run.add_argument('--'+flag, required=True)
    args = parser.parse_args(argv)
    try:
        inputs = [] if args.action == 'template' else [args.input, args.config]
        validate_outputs(inputs, [args.output])
        hashes = {p: sha256_file(p) for p in inputs}
        result = empty_config() if not inputs else compute_features(
            json.loads(Path(args.input).read_text(encoding='utf-8')),
            json.loads(Path(args.config).read_text(encoding='utf-8')))
        if inputs:
            result.update(input_sha256=hashes[args.input], config_sha256=hashes[args.config],
                          implementation_sha256=sha256_file(__file__))
        if any(sha256_file(p) != h for p, h in hashes.items()):
            raise ValueError('Input changed during measurement')
        with atomic_text(args.output) as stream:
            stream.write(rf._json(result)+'\n')
        return 0
    except (ValueError, TypeError, KeyError, OSError, OverflowError, np.linalg.LinAlgError) as exc:
        parser.exit(2, f'Cranial features: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())

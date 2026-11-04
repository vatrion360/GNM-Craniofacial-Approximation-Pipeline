"""Explicit mandibular pose scenarios, not posterior samples or a facial-fit ensemble.

NumPy only. Derived hypothetical coordinates never replace observed input/source hashes.
"""
import argparse
import copy
import itertools
import json
from pathlib import Path
import numpy as np
from . import features as f, reference_frame as rf, __version__
from .validation import finite_array, sha256_file, validate_outputs
from .export import atomic_text


def empty_config() -> dict:
    """No anatomical ranges, pivot, axes, tissue values or norms are guessed."""
    return dict(schema_version=1, case_id=None, reviewed=False, source=None,
        moving_sources=[], pivot_mm=None, axes_world=None, translation_mm=None,
        rotation_deg=None, samples=None, seed=None, feature_config=f.empty_config(), profile=None)


def validate_config(config: dict) -> list:
    if not isinstance(config, dict) or set(config) != set(empty_config()):
        raise ValueError('Sensitivity fields must match the blank template')
    if type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ValueError('Unsupported sensitivity schema')
    if config['reviewed'] is not True or not isinstance(config['case_id'], str) or not config['case_id'].strip():
        raise ValueError('Reviewed case-bound sensitivity configuration required')
    rf._source(config['source'])
    sources = config['moving_sources']
    if not isinstance(sources, list) or not sources:
        raise ValueError('Explicit moving_sources required')
    ids = []
    for row in sources:
        if not isinstance(row, dict) or set(row) != {'id', 'geometry_sha256'}:
            raise ValueError('Moving source requires id and geometry_sha256')
        rf._source(row['id'])
        if not f.cm._sha(row['geometry_sha256']):
            raise ValueError('Moving source hash required')
        ids.append(row['id'])
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate moving source')
    finite_array(config['pivot_mm'], 'pivot_mm', (3,))
    axes = finite_array(config['axes_world'], 'axes_world', (3, 3))
    if not np.allclose(axes.T@axes, np.eye(3), atol=1e-10, rtol=0) or np.linalg.det(axes) <= 0:
        raise ValueError('axes_world must be a right-handed orthonormal column basis')
    for key in ('translation_mm', 'rotation_deg'):
        bounds = finite_array(config[key], key, (3, 2))
        if np.any(bounds[:, 0] > 0) or np.any(bounds[:, 1] < 0):
            raise ValueError(key+' ranges must be ordered and include zero (baseline pose)')
    for key in ('samples', 'seed'):
        if type(config[key]) is not int or config[key] < 0:
            raise ValueError(key+' must be an explicit nonnegative integer')
    f.validate_config(config['feature_config'])
    if config['feature_config']['uncertainty'] is not None:
        raise ValueError('Pose sensitivity does not combine placement-error Monte Carlo; set feature uncertainty null')
    if not (config['feature_config']['mandible_pose'] or {}).get('reviewed'):
        raise ValueError('Review baseline mandibular pose in the feature protocol')
    profile = config['profile']
    if profile is not None:
        if (not isinstance(profile, dict) or set(profile) != {'reviewed','source','segments','gap_notes','points'}
                or profile['reviewed'] is not True):
            raise ValueError('Profile needs reviewed/source/segments/gap_notes/points')
        rf._source(profile['source'])
        segments = profile['segments']
        if not isinstance(segments, list) or not segments or any(not isinstance(s, list) or len(s) < 2 for s in segments):
            raise ValueError('Each profile segment needs at least two explicit bone codes')
        codes = [c for segment in segments for c in segment]
        if any(not isinstance(c, str) or c not in f.cm.ALL_POINTS for c in codes) or len(set(codes)) != len(codes):
            raise ValueError('Unknown/duplicate profile code')
        if not isinstance(profile['gap_notes'], list) or len(profile['gap_notes']) != len(segments)-1:
            raise ValueError('Document each inter-segment gap')
        for note in profile['gap_notes']:
            rf._source(note)
        if not isinstance(profile['points'], dict) or set(profile['points']) != set(codes):
            raise ValueError('One profile definition per explicit bone code required')
        for code, row in profile['points'].items():
            if (not isinstance(row, dict) or set(row) != {'depth_mm','normal_world','tissue_source','reviewed','direction'}
                    or row['reviewed'] is not True or row['direction'] != 'bone_normal'):
                raise ValueError('Profile depths require reviewed bone_normal definitions')
            rf._source(row['tissue_source'])
            depth = row['depth_mm']
            if type(depth) not in (float, int) or not np.isfinite(float(depth)) or depth < 0:
                raise ValueError('Profile depth must be explicitly finite and nonnegative')
            normal = finite_array(row['normal_world'], code+' normal', (3,))
            if not np.isfinite(np.linalg.norm(normal)) or np.linalg.norm(normal) <= rf.EPS:
                raise ValueError('Invalid profile normal')
    return ids


def pose_parameters(config):
    """Baseline + unique range corners + N independent uniform interior draws."""
    bounds = np.vstack((config['translation_mm'], config['rotation_deg'])).astype(float)
    corners = itertools.product(*(sorted(set(row)) for row in bounds))
    draws = np.random.Generator(np.random.PCG64(config['seed'])).uniform(
        bounds[:, 0], bounds[:, 1], size=(config['samples'], 6))
    rows, seen = [], set()
    for kind, values in itertools.chain([('baseline', np.zeros(6))],
            (('corner', v) for v in corners), (('uniform', v) for v in draws)):
        key = tuple(float(x) for x in values)
        if key not in seen:
            seen.add(key)
            rows.append(dict(kind=kind, translation_mm=list(key[:3]), rotation_deg=list(key[3:])))
    return rows


def pose_matrix(parameters, pivot, axes):
    """Column-vector convention: Rz @ Ry @ Rx about fixed local axes, then translate."""
    if not any(parameters['translation_mm']) and not any(parameters['rotation_deg']):
        return np.eye(4)
    x, y, z = np.deg2rad(parameters['rotation_deg'])
    cx, cy, cz, sx, sy, sz = np.cos(x), np.cos(y), np.cos(z), np.sin(x), np.sin(y), np.sin(z)
    rx = np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
    ry = np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])
    rz = np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])
    axes, pivot = np.asarray(axes), np.asarray(pivot)
    r = axes @ (rz@ry@rx) @ axes.T
    matrix = np.eye(4)
    matrix[:3, :3], matrix[:3, 3] = r, pivot-r@pivot+axes@np.asarray(parameters['translation_mm'])
    return finite_array(matrix, 'pose matrix', (4,4))


def _classification(rule, values, failed):
    if rule is None:
        return dict(status='no_thresholds_configured')
    if failed:
        return dict(status='indeterminate', reason='At least one scenario unavailable; no filtering', source=rule['source'])
    indices = np.searchsorted(rule['cuts'], [min(values), max(values)], side='right')
    return dict(status='configured_descriptive', label='indeterminate' if indices[0] != indices[1] else rule['labels'][indices[0]],
        source=rule['source'], rule=copy.deepcopy(rule), interpretation='Sampled scenario classification, not a diagnosis')


def compute(document: dict, config: dict) -> dict:
    """Recompute observed/reviewed landmarks, features and optional profile targets.

    Failed scenarios stay explicit; dependent ranges are withheld. No facial fit,
    collision filtering, source-hash rewriting or scene mutation is performed.
    """
    if not isinstance(document, dict):
        raise ValueError('Sensitivity input must be a craniometry JSON object')
    moving = set(validate_config(config))
    if document.get('case_id') != config['case_id']:
        raise ValueError('Sensitivity case_id mismatch')
    points, hashes = f._observations(document)
    sources = {s['id']: s for s in document['bone_sources']}
    for row in config['moving_sources']:
        if hashes.get(row['id']) != row['geometry_sha256'] or sources[row['id']].get('anatomy') != 'MANDIBLE':
            raise ValueError('Moving source must be a current explicitly classified MANDIBLE source')
    for code, row in points.items():
        if row.get('source_id') in moving and code not in f.MANDIBULAR:
            raise ValueError('Moving source contains a cranial/nonmandibular reference: '+code)
    pose_record = document.get('mandible_pose')
    if pose_record is not None and (not isinstance(pose_record, dict) or pose_record.get('status') != 'reviewed_current'):
        raise ValueError('Baseline articulation record is not current/reviewed')
    features = config['feature_config']
    base = f.compute_features(document, features)
    xyz, unavailable = {}, {}
    for code in points:
        try:
            xyz.update(f._verified(points, hashes, [code], features))
        except ValueError as exc:
            unavailable[code] = str(exc)
    if not any(points[c]['source_id'] in moving for c in xyz):
        raise ValueError('No reviewed observed landmarks on selected moving sources')
    parameters = pose_parameters(config)
    matrices = [pose_matrix(p, config['pivot_mm'], config['axes_world']) for p in parameters]
    trajectories = {c: dict(moving=points[c]['source_id'] in moving, baseline_mm=p.tolist(), samples_mm=[]) for c,p in xyz.items()}
    values, failures = {k: [] for k in f.FEATURES}, {k: [] for k in f.FEATURES}
    profile = config['profile']
    profile_rows = {} if profile is None else {c: dict(samples_mm=[], status='sampled' if c in xyz else 'unavailable',
        reason=None if c in xyz else unavailable.get(c, 'Missing observation')) for c in profile['points']}
    for index, matrix in enumerate(matrices):
        moved = {c: finite_array(matrix[:3,:3]@p+matrix[:3,3], 'derived bone point', (3,))
                 if points[c]['source_id'] in moving else p.copy() for c,p in xyz.items()}
        for code,p in moved.items():
            trajectories[code]['samples_mm'].append(p.tolist())
        for name, baseline in base['features'].items():
            if baseline['status'] != 'measured':
                values[name].append(None)
                continue
            spec = features['features'][name]['definition']
            try:
                frame = rf.geometry_frame(moved, features['frame_config']) if f.needs_frame(spec) else None
                groups = {points[c]['source_id'] in moving for c in spec['points']}
                invariant = groups == {False} or (len(groups) == 1 and spec['space'] == '3d'
                    and spec['kind'] in ('distance', 'ratio', 'angle', 'line_angle'))
                # Preserve exact rigid invariants, avoiding false threshold crossings
                # from roundoff. Frame references are cranial and cannot move here.
                value = baseline['value'] if invariant else f.evaluate_geometry(moved, spec, frame)
                if spec['kind'] == 'signed_angle' and abs(value-baseline['value']) > 180:
                    raise ValueError('Signed-angle branch crossed; linear range withheld')
                values[name].append(value)
            except (ValueError, np.linalg.LinAlgError) as exc:
                values[name].append(None)
                failures[name].append(dict(pose_index=index, reason=str(exc)))
        for code,row in profile_rows.items():
            if code not in moved:
                row['samples_mm'].append(None)
                continue
            definition = profile['points'][code]
            normal = np.asarray(definition['normal_world'], float)
            normal /= np.linalg.norm(normal)
            if points[code]['source_id'] in moving:
                normal = matrix[:3,:3]@normal
            target = finite_array(moved[code]+definition['depth_mm']*normal, 'derived skin profile target', (3,))
            row['samples_mm'].append(target.tolist())
    result_features = {}
    for name, baseline in base['features'].items():
        sampled = values[name]
        valid = baseline['status'] == 'measured' and not failures[name]
        result_features[name] = dict(baseline=baseline, values=sampled, failures=failures[name],
            status='sampled' if valid else 'failed' if failures[name] else baseline['status'],
            sampled_range=[min(sampled),max(sampled)] if valid else None,
            extremum_pose_indices=[int(np.argmin(sampled)),int(np.argmax(sampled))] if valid else None,
            classification=_classification((features['thresholds'] or {}).get(name), sampled, not valid))
    for row in profile_rows.values():
        if row['status'] == 'sampled':
            p = np.asarray(row['samples_mm'])
            row.update(coordinate_ranges_mm=np.stack([p.min(axis=0),p.max(axis=0)],axis=1).tolist(),
                maximum_displacement_mm=float(np.linalg.norm(p-p[0],axis=1).max()))
    return dict(schema_version=1, case_id=config['case_id'], configuration=copy.deepcopy(config),
        input_signature=f.definition_hash(document), software_version=__version__, numpy_version=np.__version__,
        poses=[dict(**p, matrix_world=m.tolist()) for p,m in zip(parameters,matrices)],
        sampling=dict(method='baseline + unique corners + independent uniform draws', generator='PCG64',
                      seed=config['seed'], requested_random_draws=config['samples'], unique_poses=len(parameters)),
        landmarks=trajectories, unavailable_landmarks=unavailable, features=result_features,
        profile=dict(status='not_configured') if profile is None else dict(status='sampled_targets',
            segments=profile['segments'], gap_notes=profile['gap_notes'], points=profile_rows),
        interpretation=['Hypothetical poses; preserved observations and original source hashes were not rewritten.',
            'Sampled extrema, not guaranteed bounds, confidence intervals or calibrated uncertainty.',
            'Profile output contains derived targets, not fitted facial meshes; no GNM refit performed.',
            'No pose rejected for occlusion or anatomical plausibility; inspect declared ranges and all failures.',
            'Selected mandibular sources move as one rigid group; other sources remain fixed.'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action',required=True)
    commands.add_parser('template').add_argument('--output',required=True)
    run = commands.add_parser('compute')
    for flag in ('input','config','output'):
        run.add_argument('--'+flag,required=True)
    args = parser.parse_args(argv)
    try:
        inputs = [] if args.action == 'template' else [args.input,args.config]
        validate_outputs(inputs,[args.output])
        hashes = {p:sha256_file(p) for p in inputs}
        result = empty_config() if not inputs else compute(json.loads(Path(args.input).read_text(encoding='utf-8')),
                                                           json.loads(Path(args.config).read_text(encoding='utf-8')))
        if inputs:
            result.update(input_sha256=hashes[args.input],config_sha256=hashes[args.config],implementation_sha256=sha256_file(__file__))
        if any(sha256_file(p)!=h for p,h in hashes.items()):
            raise ValueError('Input changed during sensitivity computation')
        with atomic_text(args.output) as stream:
            stream.write(rf._json(result)+'\n')
        return 0
    except (ValueError,TypeError,KeyError,OSError,OverflowError,np.linalg.LinAlgError) as exc:
        parser.exit(2,f'Pose sensitivity: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())

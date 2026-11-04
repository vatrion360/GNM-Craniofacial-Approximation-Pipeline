"""Opt-in native-topology measurements and explicit rule residuals (NumPy only).

No anatomical correspondence, prediction, SD or traffic-light threshold is
supplied. The CLI uses trimesh locally; the shared engine does not import it.
"""
import argparse
import copy
import json
from pathlib import Path
import re

import numpy as np

from . import _documented, load_registry, validate_registry
from .contracts import NotConfigured, Prediction, RuleResult, _finite
from .engine import predict
from ..export import atomic_text
from ..tissue import _json
from ..validation import finite_array, sha256_file, validate_outputs

POINTS = ('canthus_medial_L', 'canthus_medial_R', 'canthus_lateral_L',
          'canthus_lateral_R', 'pupil_center_L', 'pupil_center_R', 'pronasale',
          'cheilion_L', 'cheilion_R')
FEATURES = {
    'inner_canthal_width': ('eyes', ('canthus_medial_L', 'canthus_medial_R')),
    'outer_canthal_width': ('eyes', ('canthus_lateral_L', 'canthus_lateral_R')),
    'interpupillary_width': ('eyes', ('pupil_center_L', 'pupil_center_R')),
    'pupil_position_L': ('eyes', ('pupil_center_L',)),
    'pupil_position_R': ('eyes', ('pupil_center_R',)),
    'pronasale_position': ('nose', ('pronasale',)),
    'mouth_width': ('mouth', ('cheilion_L', 'cheilion_R')),
}


def empty_map() -> dict:
    """Unbound review template; no index from a legacy candidate map is trusted."""
    return dict(schema_version=1, model_sha256=None, vertex_count=None,
        points={key: dict(vertex=None, definition=None, source=None, reviewed=False) for key in POINTS},
        features={key: dict(definition=None, source=None, reviewed=False, rule_id=None, thresholds=None)
                  for key in FEATURES})


def _fields(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f'{label}: expected fields {sorted(keys)}')


def validate_thresholds(config: dict | None, point: bool) -> None:
    """Require explicitly reviewed cuts; these labels are not accuracy claims."""
    if config is None:
        return
    _fields(config, ('metric', 'green_max', 'amber_max', 'source', 'reviewed'), 'thresholds')
    metric = 'max_abs_coordinate_z' if point else 'abs_z'
    if (config['metric'] != metric or config['reviewed'] is not True
            or not _documented(config['source'])):
        raise ValueError(f'Thresholds need reviewed source and metric {metric}')
    for key in ('green_max', 'amber_max'):
        _finite(config[key], key)
    if not 0 <= config['green_max'] < config['amber_max']:
        raise ValueError('Thresholds require 0 <= green_max < amber_max')


def validate_map(mapping: dict) -> None:
    """Validate model binding, index uniqueness, definitions and review metadata."""
    _fields(mapping, ('schema_version', 'model_sha256', 'vertex_count', 'points', 'features'), 'map')
    if type(mapping['schema_version']) is not int or mapping['schema_version'] != 1:
        raise ValueError('Unsupported mapping schema_version')
    digest, count = mapping['model_sha256'], mapping['vertex_count']
    if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('Mapping requires model_sha256')
    if type(count) is not int or count <= 0:
        raise ValueError('Mapping requires positive integer vertex_count')
    _fields(mapping['points'], POINTS, 'points')
    _fields(mapping['features'], FEATURES, 'features')
    seen = set()
    for name, row in mapping['points'].items():
        _fields(row, ('vertex', 'definition', 'source', 'reviewed'), name)
        index = row['vertex']
        if index is not None:
            if type(index) is not int or not 0 <= index < count or index in seen:
                raise ValueError(f'{name}: invalid or duplicate vertex index')
            seen.add(index)
        if type(row['reviewed']) is not bool:
            raise ValueError(f'{name}: reviewed must be boolean')
        if row['reviewed'] and (index is None or not _documented(row['definition'])
                                or not _documented(row['source'])):
            raise ValueError(f'{name}: reviewed point needs vertex, definition and source')
    for name, row in mapping['features'].items():
        _fields(row, ('definition', 'source', 'reviewed', 'rule_id', 'thresholds'), name)
        if type(row['reviewed']) is not bool:
            raise ValueError(f'{name}: reviewed must be boolean')
        if row['reviewed'] and (not _documented(row['definition']) or not _documented(row['source'])):
            raise ValueError(f'{name}: reviewed measurement needs definition and source')
        if row['rule_id'] is not None and (not isinstance(row['rule_id'], str)
                or not re.fullmatch('[a-z][a-z0-9_]*', row['rule_id'])):
            raise ValueError(f'{name}: invalid rule_id')
        validate_thresholds(row['thresholds'], len(FEATURES[name][1]) == 1)


def compare_prediction(measured: Prediction, result: RuleResult, thresholds: dict | None = None) -> dict:
    """Signed residual and marginal SD units, never a probability or confidence.

    Point SDs must already use the same world axes as the prediction. They are
    not an isotropic radius or a covariance matrix; no Mahalanobis score is used.
    """
    if not isinstance(measured, Prediction) or not isinstance(result, RuleResult):
        raise TypeError('Prediction and RuleResult required')
    point = type(measured.value) is tuple
    validate_thresholds(thresholds, point)
    output = dict(status='not_assessed', reason=None, residual=None, distance_mm=None,
        standardized_residual=None, score=None, light='not_assessed',
        thresholds=copy.deepcopy(thresholds), rule_result=result.as_dict())
    expected = result.prediction
    if expected is None:
        output['reason'] = 'Rule inapplicable' if result.applicable is False else 'Prediction unavailable'
        return output
    if ((type(expected.value) is tuple) != point or expected.units != measured.units
            or expected.coordinate_space != measured.coordinate_space):
        raise ValueError('Measurement and prediction must share representation, units and frame')
    with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        delta = finite_array(np.asarray(measured.value, dtype=float)
                             - np.asarray(expected.value, dtype=float), 'residual')
        output.update(status='compared', residual=delta.tolist())
        if measured.units == 'mm':
            distance = float(np.linalg.norm(delta))
            _finite(distance, 'distance')
            output['distance_mm'] = distance
        if result.sd is None or np.any(np.asarray(result.sd) <= 0):
            output['reason'] = 'Positive SD unavailable; no standardized score or traffic light'
            return output
        z = finite_array(delta / np.asarray(result.sd), 'standardized residual')
    output['standardized_residual'] = z.tolist()
    if thresholds is None:
        output['reason'] = 'No reviewed thresholds configured'
        return output
    score = float(np.max(np.abs(z)))
    output.update(score=score, light=('green' if score <= thresholds['green_max'] else
                  'amber' if score <= thresholds['amber_max'] else 'red'),
                  reason='Configured descriptive threshold; not validated accuracy or probability')
    return output


def _triangles(value, count):
    triangles = np.asarray(value)
    if (triangles.ndim != 2 or triangles.shape[1] != 3 or not len(triangles)
            or triangles.dtype.kind not in 'iu' or np.any(triangles < 0) or np.any(triangles >= count)):
        raise ValueError('Triangles must be nonempty integer Nx3 indices within vertex_count')
    return triangles


def measure_and_compare(vertices_mm, triangles, model_triangles, model_sha256: str,
                        mapping: dict, *, registry=None) -> dict:
    """Read native GNM world-mm geometry; leave arrays and mapping unchanged.

    Current rules are unavailable stubs. A future numeric predictor also needs
    an explicit case-input adapter and anatomical definition compatibility check;
    this routine refuses numerical execution until those are implemented.
    """
    validate_map(mapping)
    if model_sha256 != mapping['model_sha256']:
        raise ValueError('Mapping model_sha256 does not match model')
    count = mapping['vertex_count']
    vertices = finite_array(vertices_mm, 'face vertices', (count, 3))
    faces = _triangles(triangles, count)
    if not np.array_equal(faces, _triangles(model_triangles, count)):
        raise ValueError('Native model triangle order/topology required')
    selected = load_registry() if registry is None else registry
    rows = {r['id']: r for r in validate_registry(selected.document)[0]['rules']}
    reports = {}
    for name, (family, points) in FEATURES.items():
        config = mapping['features'][name]
        rule_id = config['rule_id']
        if rule_id is not None and (rule_id not in rows or rows[rule_id]['feature'] != family):
            raise ValueError(f'{name}: unknown or conflicting rule_id')
        missing = [p for p in points if not mapping['points'][p]['reviewed']]
        entry = dict(measurement_status='not_assessed', measurement=None, missing_points=missing,
                     comparison=dict(status='not_assessed', light='not_assessed',
                                     reason='Measurement definition or correspondence unreviewed'))
        reports[name] = entry
        if missing or not config['reviewed']:
            continue
        positions = vertices[[mapping['points'][p]['vertex'] for p in points]]
        if len(points) == 1:
            measured = Prediction(tuple(float(v) for v in positions[0]), 'mm', 'world')
        else:
            with np.errstate(over='ignore', invalid='ignore'):
                distance = float(np.linalg.norm(positions[0] - positions[1]))
            if not np.isfinite(distance) or distance <= 0:
                entry['comparison']['reason'] = 'Degenerate or non-finite measured distance'
                continue
            measured = Prediction(distance, 'mm')
        entry.update(measurement_status='measured', measurement=RuleResult(
            measured, None, True, ('Geometric measurement only',)).as_dict()['prediction'])
        if rule_id is None:
            entry['comparison']['reason'] = 'No rule bound to measurement'
            continue
        try:
            result = predict(rule_id, registry=selected)
        except NotConfigured as exc:
            entry['comparison'].update(reason=str(exc), rule_status='not_configured')
            continue
        if result.prediction is not None:
            raise ValueError('Numerical rule case-input adapter not implemented')
        entry['comparison'] = compare_prediction(measured, result, config['thresholds'])
    return dict(schema_version=1, model_sha256=model_sha256, mapping=copy.deepcopy(mapping),
                registry=selected.record(), features=reports, units='mm', coordinate_space='world',
                interpretation='Geometric measurements; no anatomical validation or fit modification')


def _model(path):
    with np.load(path, allow_pickle=False) as archive:
        vertices = finite_array(archive['template_vertex_positions'], 'model vertices')
        if vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices):
            raise ValueError('Model positions must be nonempty Nx3')
        return len(vertices), _triangles(archive['triangles'], len(vertices)).copy()


def main(argv=None) -> None:
    """Write model-bound templates or new reports from native world-mm OBJ files."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('template', 'measure'):
        command = commands.add_parser(name)
        command.add_argument('--npz', required=True)
        command.add_argument('--output', required=True)
        if name == 'measure':
            command.add_argument('--face', required=True, help='Native-topology world-mm OBJ')
            command.add_argument('--mapping', required=True)
    args = parser.parse_args(argv)
    try:
        inputs = {'model': Path(args.npz).expanduser()}
        if args.command == 'measure':
            inputs.update(face=Path(args.face).expanduser(), mapping=Path(args.mapping).expanduser())
        output = Path(args.output).expanduser()
        validate_outputs(inputs.values(), [output])
        hashes = {key: sha256_file(path) for key, path in inputs.items()}
        count, triangles = _model(inputs['model'])
        if args.command == 'template':
            report = empty_map()
            report.update(model_sha256=hashes['model'], vertex_count=count)
            validate_map(report)
        else:
            if inputs['face'].suffix.lower() != '.obj':
                raise ValueError('Use native-topology OBJ in world millimetres')
            import trimesh
            face = trimesh.load(inputs['face'], process=False, maintain_order=True)
            if not isinstance(face, trimesh.Trimesh):
                raise ValueError('Single mesh required; scenes are not merged automatically')
            mapping = _json(inputs['mapping'].read_text(encoding='utf-8-sig'))
            report = measure_and_compare(face.vertices, face.faces, triangles, hashes['model'], mapping)
            report.update(input_sha256=hashes, implementation_sha256=sha256_file(__file__))
        if hashes != {key: sha256_file(path) for key, path in inputs.items()}:
            raise ValueError('Input changed during measurement')
        with atomic_text(output) as stream:
            stream.write(json.dumps(report, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)+'\n')
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as exc:
        parser.exit(2, f'{exc}\n')


if __name__ == '__main__':
    main()

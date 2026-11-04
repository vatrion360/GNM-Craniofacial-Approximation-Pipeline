"""Synthetic geometric checks, not verified anatomical correspondences."""
import copy
import json
import os
from pathlib import Path

import numpy as np
import pytest

from cranio.export import export_obj
from cranio.rules.comparison import (empty_map, validate_map, compare_prediction,
                                     measure_and_compare, main)
from cranio.rules.contracts import Prediction, RuleResult
from cranio.validation import sha256_file


@pytest.fixture
def case():
    vertices = np.arange(27, dtype=float).reshape(9, 3)
    vertices[7:] = [[0, 0, 0], [3, 4, 0]]
    triangles = np.arange(9).reshape(3, 3)
    mapping = empty_map()
    mapping.update(model_sha256='a'*64, vertex_count=9)
    for index, row in enumerate(mapping['points'].values()):
        row.update(vertex=index, reviewed=True, definition='Synthetic point definition', source='Test fixture')
    for row in mapping['features'].values():
        row.update(reviewed=True, definition='Synthetic geometric definition', source='Test fixture')
    return vertices, triangles, mapping


def run(case):
    vertices, triangles, mapping = case
    return measure_and_compare(vertices, triangles, triangles, 'a'*64, mapping)


def cuts(point=False):
    return dict(metric='max_abs_coordinate_z' if point else 'abs_z', green_max=1, amber_max=2,
                source='Synthetic test cutoffs, not anatomical thresholds', reviewed=True)


def test_measurement_and_partial_review_do_not_mutate(case):
    original = copy.deepcopy(case)
    report = run(case)
    assert report['features']['mouth_width']['measurement']['value'] == 5
    assert report['features']['pronasale_position']['measurement']['value'] == case[0][6].tolist()
    assert all(r['comparison']['light'] == 'not_assessed' for r in report['features'].values())
    np.testing.assert_array_equal(case[0], original[0])
    assert case[2] == original[2]
    case[2]['points']['cheilion_L']['reviewed'] = False
    report = run(case)
    assert report['features']['mouth_width']['missing_points'] == ['cheilion_L']
    assert report['features']['mouth_width']['measurement'] is None
    assert report['features']['pronasale_position']['measurement_status'] == 'measured'


def test_missing_rule_preserves_measurement(case):
    case[2]['features']['mouth_width']['rule_id'] = 'mouth_stephan_evaluation'
    row = run(case)['features']['mouth_width']
    assert row['measurement']['value'] == 5
    assert row['comparison']['rule_status'] == 'not_configured'
    assert row['comparison']['light'] == 'not_assessed'


@pytest.mark.parametrize('kind', ['hash', 'count', 'duplicate', 'range', 'bool_index', 'missing_index',
                                 'source', 'reviewed', 'definition', 'unknown_rule', 'family', 'extra'])
def test_bad_mapping_rejected(case, kind):
    mapping = case[2]
    point = mapping['points']['cheilion_L']
    if kind == 'hash': mapping['model_sha256'] = 'b'*64
    elif kind == 'count': mapping['vertex_count'] = True
    elif kind == 'duplicate': point['vertex'] = 0
    elif kind == 'range': point['vertex'] = 9
    elif kind == 'bool_index': point['vertex'] = True
    elif kind == 'missing_index': point['vertex'] = None
    elif kind == 'source': point['source'] = 'TODO(verify-source)'
    elif kind == 'reviewed': point['reviewed'] = 'yes'
    elif kind == 'definition': point['definition'] = ''
    elif kind == 'unknown_rule': mapping['features']['mouth_width']['rule_id'] = 'missing'
    elif kind == 'family': mapping['features']['mouth_width']['rule_id'] = 'eyes_stephan_davidson_2008'
    elif kind == 'extra': mapping['extra'] = True
    with pytest.raises(ValueError): run(case)


def test_geometry_validation_and_degenerate_width(case):
    vertices, triangles, mapping = case
    with pytest.raises(ValueError, match='topology'):
        measure_and_compare(vertices, triangles[::-1], triangles, 'a'*64, mapping)
    with pytest.raises(ValueError, match='integer'):
        measure_and_compare(vertices, triangles.astype(float), triangles, 'a'*64, mapping)
    vertices[0, 0] = np.nan
    with pytest.raises(ValueError, match='NaN'): run(case)
    vertices[0, 0] = 0
    vertices[8] = vertices[7]
    assert run(case)['features']['mouth_width']['measurement'] is None


@pytest.mark.parametrize('value,z,light', [(5, 1, 'green'), (7, 2, 'amber'), (8, 2.5, 'red')])
def test_scalar_residual(value, z, light):
    result = RuleResult(Prediction(3, 'mm'), 2, True, ('Synthetic prediction',))
    report = compare_prediction(Prediction(value, 'mm'), result, cuts())
    assert report['standardized_residual'] == z
    assert report['light'] == light
    negative = compare_prediction(Prediction(1, 'mm'), result)
    assert negative['standardized_residual'] == -1


def test_point_residual_with_marginal_sds():
    result = RuleResult(Prediction((1, 2, 3), 'mm', 'world'), (1, 2, 4), True, ('Synthetic',))
    report = compare_prediction(Prediction((2, 6, 3), 'mm', 'world'), result, cuts(True))
    assert report['standardized_residual'] == [1, 2, 0]
    assert report['distance_mm'] == pytest.approx(np.sqrt(17))
    assert report['score'] == 2 and report['light'] == 'amber'


@pytest.mark.parametrize('sd', [None, 0])
def test_unknown_or_zero_sd_never_green(sd):
    result = RuleResult(Prediction(3, 'mm'), sd, True, ('Synthetic',))
    report = compare_prediction(Prediction(3, 'mm'), result, cuts())
    assert report['residual'] == 0
    assert report['standardized_residual'] is None and report['light'] == 'not_assessed'


def test_unknown_thresholds_applicability_and_units():
    measured = Prediction(5, 'mm')
    result = RuleResult(Prediction(3, 'mm'), 2, True, ('Synthetic',))
    report = compare_prediction(measured, result)
    assert report['standardized_residual'] == 1 and report['light'] == 'not_assessed'
    assert report['score'] is None
    assert compare_prediction(measured, RuleResult(None, None, False, ('Inapplicable',)))['residual'] is None
    with pytest.raises(ValueError, match='units'):
        compare_prediction(Prediction(5, 'degrees'), result)


@pytest.mark.parametrize('key,value', [('green_max', -1), ('amber_max', 1), ('green_max', True),
                                     ('amber_max', float('nan')), ('reviewed', False),
                                     ('source', 'unknown'), ('metric', 'probability')])
def test_unreviewed_or_invalid_cuts_rejected(key, value):
    config = cuts()
    config[key] = value
    with pytest.raises(ValueError):
        compare_prediction(Prediction(5, 'mm'), RuleResult(Prediction(3, 'mm'), 2, True, ('Test',)), config)


def test_rigid_transform_preserves_width_but_transforms_world_point(case):
    initial = run(case)['features']
    rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    case[0][:] = case[0] @ rotation.T + [10, 20, 30]
    final = run(case)['features']
    assert final['mouth_width']['measurement'] == initial['mouth_width']['measurement']
    np.testing.assert_allclose(final['pronasale_position']['measurement']['value'],
        np.array(initial['pronasale_position']['measurement']['value']) @ rotation.T + [10, 20, 30])


def test_cli_bound_template_determinism_and_overwrite_protection(case, tmp_path):
    vertices, triangles, mapping = case
    model = tmp_path/'model.npz'
    np.savez(model, template_vertex_positions=vertices/1000, triangles=triangles)
    face, path = tmp_path/'face.obj', tmp_path/'map.json'
    export_obj(face, vertices, triangles)
    main(['template', '--npz', str(model), '--output', str(path)])
    blank = json.loads(path.read_text(encoding='utf-8'))
    assert blank['model_sha256'] == sha256_file(model) and blank['vertex_count'] == 9
    assert all(p['vertex'] is None and not p['reviewed'] for p in blank['points'].values())
    validate_map(blank)
    mapping['model_sha256'] = blank['model_sha256']
    path.write_text(json.dumps(mapping), encoding='utf-8')
    base = ['measure', '--npz', str(model), '--face', str(face), '--mapping', str(path)]
    outputs = [tmp_path/'a.json', tmp_path/'b.json']
    for output in outputs: main(base+['--output', str(output)])
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    record = json.loads(outputs[0].read_text(encoding='utf-8'))
    assert record['features']['mouth_width']['measurement']['value'] == 5
    assert record['input_sha256']['face'] == sha256_file(face)
    previous = path.read_bytes()
    for output in [outputs[0], path]:
        with pytest.raises(SystemExit) as exc: main(base+['--output', str(output)])
        assert exc.value.code == 2
    assert path.read_bytes() == previous


@pytest.mark.integration
def test_official_model_obj_retains_topology(tmp_path):
    model = os.environ.get('GNM_MODEL_PATH')
    if not model: pytest.skip('Set GNM_MODEL_PATH for official topology check')
    model = Path(model).resolve()
    face, mapping, output = tmp_path/'face.obj', tmp_path/'map.json', tmp_path/'report.json'
    with np.load(model, allow_pickle=False) as archive:
        export_obj(face, archive['template_vertex_positions']*1000, archive['triangles'])
    main(['template', '--npz', str(model), '--output', str(mapping)])
    main(['measure', '--npz', str(model), '--face', str(face), '--mapping', str(mapping),
          '--output', str(output)])
    report = json.loads(output.read_text(encoding='utf-8'))
    assert all(r['measurement_status'] == 'not_assessed' for r in report['features'].values())

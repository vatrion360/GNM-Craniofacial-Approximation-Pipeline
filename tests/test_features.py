"""Synthetic constructions only; not evidence of anatomical accuracy."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

from cranio import craniometry as cm, features as f
from cranio.landmarks import FEATURE_REFERENCE_EXTENSIONS, LANDMARK_ORDER


def spec(kind, points, space='3d'):
    return dict(kind=kind, points=points, space=space)


@pytest.fixture
def case():
    xyz = dict(po_R=[50, 0, 0], po_L=[-50, 0, 0], or_L=[-25, 60, 0],
        n=[0, 60, 30], b=[0, 0, 80], op=[0, -65, 10], ba=[0, 0, 0], pr=[0, 0, 60],
        ss=[0, 70, 30], sm=[0, 60, 40], pg=[0, 75, 0], me=[0, 60, -20],
        go_R=[40, 0, -20], go_L=[-40, 0, -20], co_R=[40, 0, 40], co_L=[-40, 0, 40])
    doc = cm.empty_document('synthetic-features')
    doc['bone_sources'] = [dict(id='bone', geometry_sha256='a'*64)]
    doc['points'] = [dict(code=c, xyz_mm=p, status='observed', definition_reviewed=True,
        source_id='bone', source_geometry_sha256='a'*64, definition_text='Synthetic test point',
        definition_source='Synthetic software fixture') for c, p in xyz.items()]
    config = f.empty_config()
    config['frame_config'] = dict(schema_version=1, orbitale='or_L', superior_code='b', midline_codes=['n', 'b', 'op'],
                                 source='Synthetic frame protocol', placement_error=None)
    config['mandible_pose'] = dict(reviewed=True, source='Synthetic assembly assumption')
    definitions = dict(gnathic_ratio=spec('ratio', ['ba', 'pr', 'ba', 'n']),
        facial_angle=spec('angle', ['n', 'ba', 'pr']), anb_angle=spec('signed_angle', ['ss', 'n', 'sm'], 'sagittal'),
        pogonion_projection=spec('anterior_offset', ['pg', 'n']),
        mandibular_plane_angle=spec('plane_inclination', ['go_R', 'go_L', 'me']),
        gonial_angle_R=spec('angle', ['co_R', 'go_R', 'me']),
        gonial_angle_L=spec('angle', ['co_L', 'go_L', 'me']),
        ramus_height_R=spec('distance', ['co_R', 'go_R']),
        ramus_height_L=spec('superior_span', ['co_L', 'go_L']),
        bigonial_breadth=spec('distance', ['go_R', 'go_L']))
    config['features'] = {k: dict(definition=s, reviewed=True, source='Synthetic construction, not an anatomical prescription')
                          for k, s in definitions.items()}
    return doc, config


def test_known_values_and_no_default_classifications(case):
    original = copy.deepcopy(case)
    rows = f.compute_features(*case)['features']
    assert all(r['status'] == 'measured' and r['classification']['status'] == 'no_thresholds_configured' for r in rows.values())
    expected = dict(gnathic_ratio=60/np.sqrt(60**2+30**2), facial_angle=np.degrees(np.arctan2(60, 30)),
                    anb_angle=90, pogonion_projection=15, mandibular_plane_angle=0,
                    gonial_angle_R=90, gonial_angle_L=90, ramus_height_R=60, ramus_height_L=60, bigonial_breadth=80)
    for name, value in expected.items():
        assert rows[name]['value'] == pytest.approx(value)
    assert rows['gnathic_ratio']['units'] == 'ratio'
    assert case == original


def test_rigid_equivariance_and_scale_units(case):
    doc, config = case
    initial = f.compute_features(*case)['features']
    q, _ = np.linalg.qr(np.random.default_rng(8).normal(size=(3, 3)))
    q[:, 0] *= np.linalg.det(q)
    for row in doc['points']:
        row['xyz_mm'] = (q@np.array(row['xyz_mm'])*2+[100, -25, 13]).tolist()
    transformed = f.compute_features(doc, config)['features']
    for key, row in initial.items():
        assert transformed[key]['value'] == pytest.approx(row['value']*(2 if row['units'] == 'mm' else 1), abs=1e-10)


@pytest.mark.parametrize('kind,points,space,expected', [
    ('distance', ['a', 'b'], '3d', 5), ('ratio', ['a', 'b', 'c', 'a'], '3d', 1),
    ('angle', ['b', 'a', 'c'], '3d', 90), ('line_angle', ['a', 'b', 'a', 'c'], '3d', 90),
    ('signed_angle', ['b', 'a', 'c'], 'sagittal', 90),
    ('anterior_offset', ['b', 'a'], '3d', 5), ('superior_span', ['a', 'c'], '3d', 5),
    ('line_inclination', ['a', 'c'], '3d', 90), ('plane_inclination', ['a', 'b', 'd'], '3d', 0)])
def test_geometry_primitives(kind, points, space, expected):
    xyz = dict(a=[0, 0, 0], b=[0, 5, 0], c=[0, 0, 5], d=[5, 0, 0])
    frame = dict(origin_mm=[0, 0, 0], axes_world=np.eye(3))
    assert f.evaluate_geometry(xyz, spec(kind, points, space), frame) == pytest.approx(expected)


@pytest.mark.parametrize('change', ['missing', 'reconstructed', 'review', 'stale'])
def test_partial_skull_failure_is_regional(case, change):
    doc, config = case
    row = next(p for p in doc['points'] if p['code'] == 'go_L')
    if change == 'missing': row.update(status='missing', xyz_mm=None)
    elif change == 'reconstructed': row['status'] = 'reconstructed'
    elif change == 'review': row['definition_reviewed'] = False
    else: row['source_geometry_sha256'] = 'b'*64
    rows = f.compute_features(doc, config)['features']
    assert rows['bigonial_breadth']['status'] == 'unavailable'
    assert rows['gonial_angle_L']['value'] is None
    assert rows['gonial_angle_R']['value'] == pytest.approx(90)
    assert rows['gnathic_ratio']['status'] == 'measured'


def test_missing_frame_and_unreviewed_jaw_do_not_infer_pose(case):
    doc, config = case
    config['frame_config'] = None
    rows = f.compute_features(doc, config)['features']
    assert rows['anb_angle']['status'] == 'unavailable'
    assert rows['ramus_height_R']['value'] == 60
    config['mandible_pose'] = None
    rows = f.compute_features(doc, config)['features']
    assert rows['ramus_height_R']['status'] == 'unavailable'
    assert rows['gnathic_ratio']['status'] == 'measured'


def configure_error(doc, config, sd):
    config['uncertainty'] = dict(samples=100, seed=29,
        placement={p['code']: dict(sigma_mm=sd, source='Synthetic error model') for p in doc['points']})


def test_mc_reproducibility_no_imputation_and_threshold_crossing(case):
    doc, config = case
    configure_error(doc, config, 1)
    definition = config['features']['bigonial_breadth']['definition']
    config['thresholds'] = dict(bigonial_breadth=dict(source='Synthetic threshold, NOT clinical',
        definition_sha256=f.definition_hash(definition), units='mm', cuts=[80], labels=['below', 'at-or-above']))
    before = copy.deepcopy(case)
    result = f.compute_features(*case)
    assert result == f.compute_features(*case) and before == case
    row = result['features']['bigonial_breadth']
    assert row['classification']['point_label'] == 'at-or-above'
    assert row['classification']['interval_label'] == 'indeterminate'
    lo, hi = row['uncertainty']['percentile_interval_95']
    assert lo < 80 < hi
    config['uncertainty']['placement'].pop('go_L')
    rows = f.compute_features(*case)['features']
    assert rows['bigonial_breadth']['uncertainty']['missing'] == ['go_L']
    assert rows['gonial_angle_R']['uncertainty']['status'] == 'conditional_uncalibrated'


def test_frame_error_propagated_and_invalid_draws_not_filtered(case):
    doc, config = case
    configure_error(doc, config, 0)
    rows = f.compute_features(*case)['features']
    assert rows['pogonion_projection']['uncertainty']['percentile_interval_95'] == [15, 15]
    assert rows['pogonion_projection']['uncertainty']['all_supplied_sd_zero']
    config['uncertainty']['placement']['po_R']['sigma_mm'] = 2
    rows = f.compute_features(*case)['features']
    assert rows['pogonion_projection']['uncertainty']['sd'] > 0
    assert rows['bigonial_breadth']['uncertainty']['sd'] == 0
    config['uncertainty']['placement']['po_R']['sigma_mm'] = 10000
    rows = f.compute_features(*case)['features']
    assert rows['pogonion_projection']['uncertainty']['status'] == 'failed'
    assert rows['pogonion_projection']['uncertainty']['interval'] is None
    assert rows['bigonial_breadth']['uncertainty']['status'] == 'conditional_uncalibrated'


@pytest.mark.parametrize('fault', ['unknown_point', 'wrong_ratio', 'plane_projection', 'bad_seed', 'nan', 'wrong_units', 'wrong_hash'])
def test_malformed_protocols_refused(case, fault):
    doc, config = case
    if fault == 'unknown_point': config['features']['facial_angle']['definition']['points'][0] = 'skin_nasion'
    elif fault == 'wrong_ratio': config['features']['gnathic_ratio']['definition']['points'][0] = 'b'
    elif fault == 'plane_projection': config['features']['mandibular_plane_angle']['definition']['space'] = 'sagittal'
    elif fault in ('bad_seed', 'nan'):
        configure_error(doc, config, 1)
        if fault == 'bad_seed': config['uncertainty']['seed'] = True
        else: config['uncertainty']['placement']['n']['sigma_mm'] = float('nan')
    else:
        s = config['features']['bigonial_breadth']['definition']
        config['thresholds'] = dict(bigonial_breadth=dict(source='Synthetic only', definition_sha256=f.definition_hash(s),
                                    units='mm', cuts=[80], labels=['low', 'high']))
        config['thresholds']['bigonial_breadth']['units' if fault == 'wrong_units' else 'definition_sha256'] = 'wrong'
    with pytest.raises(ValueError): f.compute_features(doc, config)


def test_degenerate_vectors_and_finite_checks(case):
    doc, config = case
    for p in doc['points']:
        if p['code'] == 'pr': p['xyz_mm'] = [0, 0, 0]
    assert f.compute_features(doc, config)['features']['gnathic_ratio']['status'] == 'unavailable'
    doc['points'][0]['xyz_mm'][0] = float('inf')
    with pytest.raises(ValueError): f.compute_features(doc, config)


def test_blank_config_and_catalogue():
    assert len(LANDMARK_ORDER) == 48 and len(cm.POINTS) == 22 and len(cm.ALL_POINTS) == 38
    assert len(cm.MEASUREMENTS) == 14
    for c, row in FEATURE_REFERENCE_EXTENSIONS.items():
        assert row['existing_marker'] in LANDMARK_ORDER and row['gnm_vertex'] is None and not row['fit_target']
    result = f.compute_features(cm.empty_document(), f.empty_config())
    assert all(row['status'] == 'not_configured' for row in result['features'].values())


def test_cli_roundtrip_no_overwrite(case, tmp_path):
    source, cfg = tmp_path/'bones.json', tmp_path/'protocol.json'
    source.write_text(json.dumps(case[0])); cfg.write_text(json.dumps(case[1]))
    outputs = [tmp_path/'a.json', tmp_path/'b.json']
    for output in outputs:
        assert f.main(['compute', '--input', str(source), '--config', str(cfg), '--output', str(output)]) == 0
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    for output in [source, cfg, outputs[0]]:
        before = output.read_bytes()
        with pytest.raises(SystemExit):
            f.main(['compute', '--input', str(source), '--config', str(cfg), '--output', str(output)])
        assert output.read_bytes() == before
    template = tmp_path/'template.json'
    assert f.main(['template', '--output', str(template)]) == 0
    assert json.loads(template.read_text()) == f.empty_config()


def test_feature_reference_metadata_default_fit_parity(marker_file, model_file, tmp_path, case):
    from cranio.config import PipelineConfig
    from cranio.pipeline import run_pipeline
    lines = marker_file.read_text().splitlines(keepends=True)
    metadata = json.loads(lines[1].lstrip('# '))
    metadata['craniometry'] = case[0]
    lines[1] = '# '+json.dumps(metadata)+'\n'
    extra = tmp_path/'features.csv'; extra.write_text(''.join(lines))
    configs = []
    for name, path in [('base', marker_file), ('extra', extra)]:
        config = PipelineConfig(input=str(path), npz=str(model_file), output=str(tmp_path/f'{name}.obj'), regularization='30')
        assert run_pipeline(config) == 0
        configs.append(config)
    for field in ('output', 'output_statistical', 'output_error_mesh'):
        assert Path(getattr(configs[0], field)).read_bytes() == Path(getattr(configs[1], field)).read_bytes()

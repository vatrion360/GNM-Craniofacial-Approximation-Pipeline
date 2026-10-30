"""Synthetic directions only: no empirical tissue measurements or anatomical validation."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import numpy as np
from numpy.testing import assert_allclose, assert_array_equal
import pytest
from cranio.io_csv import MarkerTarget, read_marker_csv, write_marker_csv_v3
from cranio.tissue import empty_table, load_table, write_table
from cranio.tissue_directions import load_directions, unit_vector
from cranio.tissue_application import apply_table
from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline
from gnm_reconstruct import parse_args


def save_manifest(path, table, labels, bones, axes, kinds):
    data = dict(schema_version=1, units='mm', coordinate_space='world', table_sha256s=[table.sha256],
        frame=dict(vertical_world=[0., 1., 0.], sagittal_normal_world=[1., 0., 0.], reviewed=True,
                   definition='Synthetic frame: vertical y, sagittal plane yz'),
        landmarks={label: dict(bone_xyz_mm=list(b), axis_world=list(a), measurement_direction=k,
            reviewed=True, definition='Synthetic engineering direction') for label,b,a,k in zip(labels,bones,axes,kinds)})
    path.write_text(json.dumps(data))
    return data


@pytest.fixture
def scenario(tmp_path):
    kinds = ['bone_normal', 'vertical', 'sagittal']
    labels = ['P0', 'P1', 'P2']
    bones = np.array([[5., 0., 0.], [0., 5., 0.], [0., 0., 5.]])  # sphere radius 5
    axes = np.array([[2., 0., 0.], [0., -2., 0.], [0., 3., 4.]])
    doc = empty_table('synthetic_direction')
    doc['landmarks'] = {l: dict(central_mm=2., measurement_direction=k) for l,k in zip(labels,kinds)}
    table_path = tmp_path/'table.json'
    write_table(table_path, doc)
    table = load_table(table_path)
    path = tmp_path/'directions.json'
    data = save_manifest(path, table, labels, bones, axes, kinds)
    targets = [MarkerTarget(l, i, b+np.array([0., 0., 1.]), .5) for i,(l,b) in enumerate(zip(labels,bones))]
    meta = dict(version=3, marker_records={l: dict(bone_xyz_mm=b.tolist(), tissue_source='synthetic') for l,b in zip(labels,bones)})
    return table, path, data, targets, meta


def test_each_direction_on_synthetic_sphere(scenario):
    table, path, data, targets, meta = scenario
    old = copy.deepcopy(meta)
    result, changed, record = apply_table(targets, meta, table, ['P0','P1','P2'], 'source', load_directions(path))
    assert_allclose([t.xyz for t in result], [[7.,0.,0.], [0.,3.,0.], [0.,1.2,6.6]])
    assert meta == old and record['source_direction_enforced']
    assert record['direction_manifest']['sha256'] == load_directions(path).sha256
    assert all(t.weight == .5 for t in result)
    assert changed['marker_records']['P0']['tissue_source'] == 'unspecified'


def test_rigid_transform_equivariance(scenario):
    table, path, data, targets, meta = scenario
    before = apply_table(targets, meta, table, ['P0','P1','P2'], 'source', load_directions(path))[0]
    q,_ = np.linalg.qr(np.random.default_rng(6).normal(size=(3,3)))
    shift = np.array([30., -22., 11.])
    transform = lambda v: np.asarray(v) @ q.T
    data['frame']['vertical_world'] = transform(data['frame']['vertical_world']).tolist()
    data['frame']['sagittal_normal_world'] = transform(data['frame']['sagittal_normal_world']).tolist()
    new_targets = []
    for t in targets:
        row = data['landmarks'][t.label]
        row['axis_world'] = transform(row['axis_world']).tolist()
        row['bone_xyz_mm'] = (transform(row['bone_xyz_mm'])+shift).tolist()
        meta['marker_records'][t.label]['bone_xyz_mm'] = row['bone_xyz_mm']
        new_targets.append(t._replace(xyz=transform(t.xyz)+shift))
    path.write_text(json.dumps(data))
    after = apply_table(new_targets, meta, table, ['P0','P1','P2'], 'source', load_directions(path))[0]
    assert_allclose([t.xyz for t in after], [transform(t.xyz)+shift for t in before], atol=1e-13)


@pytest.mark.parametrize('kind', ['missing', 'unreviewed', 'definition', 'table_hash', 'anchor', 'source_hash',
    'kind_mismatch', 'frame', 'frame_review', 'placeholder', 'vertical', 'sagittal', 'zero', 'nan', 'unknown_key'])
def test_bad_directions_fail_without_mutating_first_planned_row(scenario, kind):
    table, path, data, targets, meta = scenario
    row = data['landmarks']['P1']
    if kind == 'missing': del data['landmarks']['P1']
    if kind == 'unreviewed': row['reviewed'] = False
    if kind == 'definition': row['definition'] = ' '
    if kind == 'placeholder': row['definition'] = 'TODO(verify-source): unfinished'
    if kind == 'table_hash': data['table_sha256s'] = ['a'*64]
    if kind == 'anchor': row['bone_xyz_mm'][0] += .001
    if kind == 'source_hash': row['bone_source_geometry_sha256'] = 'b'*64
    if kind == 'kind_mismatch': row['measurement_direction'] = 'bone_normal'
    if kind == 'frame': del data['frame']
    if kind == 'frame_review': data['frame']['reviewed'] = False
    if kind == 'vertical': row['axis_world'] = [1., 0., 0.]
    if kind == 'sagittal': data['landmarks']['P2']['axis_world'] = [1., 0., 0.]
    if kind == 'zero': row['axis_world'] = [0., 0., 0.]
    if kind == 'nan': row['axis_world'][0] = float('nan')
    if kind == 'unknown_key': row['axis_wrold'] = [0.,1.,0.]
    path.write_text(json.dumps(data))
    old, points = copy.deepcopy(meta), np.array([t.xyz for t in targets])
    with pytest.raises(ValueError):
        apply_table(targets, meta, table, ['P0','P1','P2'], 'source', load_directions(path))
    assert meta == old
    assert_array_equal([t.xyz for t in targets], points)


@pytest.mark.parametrize('kind', [None, 'other'])
def test_unsupported_source_kind_never_guessed(scenario, kind):
    table,path,data,targets,meta = scenario
    doc = table.document
    doc['landmarks']['P0']['measurement_direction'] = kind
    table_path = path.parent/'unknown.json'
    write_table(table_path, doc)
    table = load_table(table_path)
    data['table_sha256s'] = [table.sha256]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='unsupported or unconfigured'):
        apply_table(targets, meta, table, ['P0'], 'source', load_directions(path))


def test_source_supports_zero_previous_axis_and_selection_only_is_unchanged(scenario):
    table,path,_,targets,meta = scenario
    targets[0] = targets[0]._replace(xyz=np.array(meta['marker_records']['P0']['bone_xyz_mm']))
    result, _, _ = apply_table(targets, meta, table, ['P0'], 'source', load_directions(path))
    assert_allclose(result[0].xyz, [7.,0.,0.])
    with pytest.raises(ValueError, match='axis'):
        apply_table(targets, meta, table, ['P0'], 'existing')
    result, _, _ = apply_table(targets, meta, table)
    assert all(a is b for a,b in zip(result,targets))


@pytest.mark.parametrize('scale', [1e-300, 1e300])
def test_normalization_has_no_overflow_or_arbitrary_length_floor(scale):
    assert_allclose(unit_vector([0.,scale,scale], 'test'), [0.,2**-.5,2**-.5])


@pytest.fixture
def pipeline_case(tmp_path, model_file, marker_file):
    targets, _, metadata = read_marker_csv(marker_file, {}, {})
    rows = [dict(label=t.label, vertex=t.vertex, placed=1, x=t.xyz[0], y=t.xyz[1], z=t.xyz[2],
        bone_x=t.xyz[0], bone_y=t.xyz[1], bone_z=t.xyz[2]-2, tissue_depth_mm=2, weight=t.weight,
        tissue_source='synthetic source') for t in targets]
    write_marker_csv_v3(marker_file, rows, metadata)
    table_path = tmp_path/'table.json'
    doc = empty_table('synthetic_direction')
    doc['landmarks']['P0'] = dict(central_mm=3., measurement_direction='vertical')
    write_table(table_path, doc)
    directions_path = tmp_path/'directions.json'
    bone = targets[0].xyz-np.array([0.,0.,2.])
    save_manifest(directions_path, load_table(table_path), ['P0'], [bone], [[0.,1.,0.]], ['vertical'])
    return PipelineConfig(input=str(marker_file), npz=str(model_file), output=str(tmp_path/'face.obj'),
        tissue_table=str(table_path), tissue_labels=['P0'], tissue_axis='source', tissue_directions=str(directions_path), regularization='30')


def test_cli_pipeline_records_directions_and_preserves_csv(pipeline_case):
    cfg = pipeline_case
    original = Path(cfg.input).read_bytes()
    parsed = parse_args(['--input', cfg.input, '--npz', cfg.npz, '--output', cfg.output,
        '--tissue-table',cfg.tissue_table, '--tissue-labels','P0','--tissue-axis','source',
        '--tissue-directions',cfg.tissue_directions,'--regularization','30'])
    assert run_pipeline(parsed) == 0
    report = json.loads(Path(parsed.output_json).read_text())
    record = report['marker_metadata']['tissue_application']
    assert record['source_direction_enforced']
    assert record['replacements'][0]['axis_world'] == [0.,1.,0.]
    assert report['inputs']['tissue_directions']['sha256'] == load_directions(cfg.tissue_directions).sha256
    assert Path(cfg.input).read_bytes() == original


def test_direction_file_protected_from_output_overwrite(pipeline_case):
    cfg = replace(pipeline_case, output=pipeline_case.tissue_directions, overwrite=True)
    original = Path(cfg.output).read_bytes()
    assert run_pipeline(cfg) == 2 and Path(cfg.output).read_bytes() == original


def test_comparison_preflights_same_manifest_and_reports_applied_direction(pipeline_case, tmp_path):
    cfg = replace(pipeline_case, tissue_table=None, tissue_compare=f'{pipeline_case.tissue_table},{pipeline_case.tissue_table}')
    assert run_pipeline(cfg) == 0
    summary = json.loads((tmp_path/'face_tissue_compare'/'summary.json').read_text())
    assert summary['source_direction_enforced'] and summary['color_scale_max_mm'] == 0
    data=json.loads(Path(cfg.tissue_directions).read_text())
    data['landmarks']['P0']['reviewed']=False
    Path(cfg.tissue_directions).write_text(json.dumps(data))
    assert run_pipeline(replace(cfg, output=str(tmp_path/'bad.obj'))) == 2
    assert not (tmp_path/'bad_tissue_compare').exists()


def test_protocol_freezes_policy_but_directions_are_case_input(pipeline_case):
    from cranio.protocol import frozen_from_report
    cfg = replace(pipeline_case, geometry_qc='full')
    assert run_pipeline(cfg) == 0
    report = json.loads(Path(cfg.output_json).read_text())
    frozen = frozen_from_report(report, 'synthetic/v1', 'a'*64)
    assert frozen['settings']['tissue_axis'] == 'source'
    assert 'tissue_directions' not in frozen['settings']
    assert 'tissue_directions' not in frozen['optional_inputs']
    assert report['inputs']['tissue_directions']['sha256'] == load_directions(cfg.tissue_directions).sha256


def test_direction_change_during_fit_aborts_before_outputs(pipeline_case, monkeypatch):
    import cranio.pipeline as pipeline
    original = pipeline.fit_identity
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        path = Path(pipeline_case.tissue_directions)
        path.write_text(path.read_text()+'\n')
        return result
    monkeypatch.setattr(pipeline, 'fit_identity', changed)
    assert run_pipeline(pipeline_case) == 2
    assert not Path(pipeline_case.output).exists()


def test_template_copies_anchors_but_never_infers_axes(pipeline_case, tmp_path):
    from cranio.tissue_directions import main
    cfg = pipeline_case
    output = tmp_path/'template.json'
    assert main(['--input',cfg.input,'--table',cfg.tissue_table,'--labels','P0','--output',str(output)]) == 0
    template=load_directions(output)
    assert template.document['landmarks']['P0']['axis_world'] is None
    assert template.document['landmarks']['P0']['reviewed'] is False
    assert template.document['frame']['vertical_world'] is None
    assert template.document['landmarks']['P0']['bone_xyz_mm'] == load_directions(cfg.tissue_directions).document['landmarks']['P0']['bone_xyz_mm']
    assert run_pipeline(replace(cfg,tissue_directions=str(output))) == 2
    before=Path(cfg.input).read_bytes()
    assert main(['--input',cfg.input,'--table',cfg.tissue_table,'--labels','P0','--output',cfg.input,'--overwrite']) == 2
    assert Path(cfg.input).read_bytes() == before


@pytest.mark.parametrize('change', ['duplicate_key', 'bad_units', 'bool_version', 'bad_hash', 'unknown_field'])
def test_manifest_rejects_malformed_structure(scenario, change):
    _,path,data,_,_ = scenario
    if change == 'bad_units': data['units']='m'
    if change == 'bool_version': data['schema_version']=True
    if change == 'bad_hash': data['table_sha256s']=['not-a-hash']
    if change == 'unknown_field': data['coordinate_spaec']='world'
    text=json.dumps(data)
    if change == 'duplicate_key': text=text.replace('"units": "mm"','"units": "mm", "units": "m"')
    path.write_text(text)
    with pytest.raises(ValueError):
        load_directions(path)

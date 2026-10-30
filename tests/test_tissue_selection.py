"""Synthetic engineering scenarios; no anatomical estimates or validation claims."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import numpy as np
import pytest
from cranio.tissue import empty_table, load_table, write_table
from cranio.tissue_application import apply_table
from cranio.io_csv import MarkerTarget, read_marker_csv, write_marker_csv_v3
from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline
from cranio.tissue_compare import run_comparison
from gnm_reconstruct import parse_args


@pytest.fixture
def table_file(tmp_path):
    doc = empty_table('synthetic')
    doc['citation'] = 'Synthetic engineering fixture'
    doc['landmarks'] = {'P0': dict(central_mm=4.), 'P1': dict(central_mm=3.)}
    path = tmp_path/'table.json'
    write_table(path, doc)
    return path


def points():
    targets = [MarkerTarget('P0', 0, np.array([1., 2., 5.]), .7), MarkerTarget('P1', 1, np.array([5., 2., 3.]), .4)]
    records = {t.label: dict(bone_xyz_mm=[1., 2., 3.], target_xyz_mm=t.xyz.tolist(),
        tissue_depth_mm=2. if i == 0 else 4., tissue_source='individual measurement') for i, t in enumerate(targets)}
    return targets, dict(version=3, marker_records=records)


def test_explicit_selective_application_preserves_inputs(table_file):
    targets, meta = points()
    original = copy.deepcopy(meta)
    result, new, record = apply_table(targets, meta, load_table(table_file), ['P0'], 'existing')
    assert meta == original
    np.testing.assert_array_equal(targets[0].xyz, [1, 2, 5])
    np.testing.assert_array_equal(result[0].xyz, [1, 2, 7])
    assert result[0].weight == .7 and result[0].vertex == 0 and result[1] is targets[1]
    assert new['marker_records']['P1'] == original['marker_records']['P1']
    assert record['replaced_labels'] == ['P0'] and record['preserved_labels'] == ['P1']
    assert record['replacements'][0]['before'] == original['marker_records']['P0']
    assert not record['source_direction_enforced'] and not record['dense_regions_applied']


def test_selection_without_labels_preserves_all_targets(table_file):
    targets, meta = points()
    result, new, record = apply_table(targets, meta, load_table(table_file))
    assert all(a is b for a, b in zip(result, targets))
    assert new['marker_records'] == meta['marker_records'] and record['status'] == 'selected_only'


@pytest.mark.parametrize('kind', ['axis', 'missing', 'duplicate', 'legacy', 'bone', 'zero', 'nan', 'null'])
def test_invalid_request_never_partially_mutates_inputs(table_file, kind):
    targets, meta = points()
    table, labels, axis = load_table(table_file), ['P0', 'P1'], 'existing'
    if kind == 'axis': axis = 'unconfigured'
    if kind == 'missing': labels.append('absent')
    if kind == 'duplicate': labels.append('P0')
    if kind == 'legacy': meta['version'] = 2
    if kind == 'bone': del meta['marker_records']['P1']['bone_xyz_mm']
    if kind == 'zero': meta['marker_records']['P1']['bone_xyz_mm'] = targets[1].xyz.tolist()
    if kind == 'nan': targets[1] = targets[1]._replace(xyz=np.full(3, np.nan))
    if kind == 'null':
        doc = table.document
        doc['landmarks']['P1']['central_mm'] = None
        write_table(table_file, doc)
        table = load_table(table_file)
    before = copy.deepcopy(meta)
    with pytest.raises(ValueError):
        apply_table(targets, meta, table, labels, axis)
    assert meta == before


@pytest.mark.parametrize('citation,provenance,expected', [(None, 'user_supplied', 'unspecified'),
    ('Source', 'legacy_hardcoded', 'legacy-unvalidated'), ('legacy-unvalidated', 'user_supplied', 'unspecified')])
def test_table_name_does_not_launder_undocumented_provenance(table_file, citation, provenance, expected):
    doc = load_table(table_file).document
    doc['citation'], doc['landmarks']['P0']['provenance'] = citation, provenance
    write_table(table_file, doc)
    _, meta, _ = apply_table(*points(), load_table(table_file), ['P0'], 'existing')
    assert meta['marker_records']['P0']['tissue_source'] == expected


def test_known_source_direction_remains_explicitly_not_enforced(table_file):
    doc = load_table(table_file).document
    doc['landmarks']['P0']['measurement_direction'] = 'vertical'
    write_table(table_file, doc)
    _, _, record = apply_table(*points(), load_table(table_file), ['P0'], 'existing')
    assert record['replacements'][0]['table_row']['measurement_direction'] == 'vertical'
    assert record['source_direction_enforced'] is False


@pytest.fixture
def case(tmp_path, model_file, marker_file, table_file):
    targets, _, metadata = read_marker_csv(marker_file, {}, {})
    rows = [dict(label=t.label, vertex=t.vertex, placed=1, x=t.xyz[0], y=t.xyz[1], z=t.xyz[2],
        bone_x=t.xyz[0], bone_y=t.xyz[1], bone_z=t.xyz[2]-2, tissue_depth_mm=2,
        weight=t.weight, tissue_source='individual manual fixture') for t in targets]
    write_marker_csv_v3(marker_file, rows, metadata)
    return PipelineConfig(input=str(marker_file), npz=str(model_file), output=str(tmp_path/'case.obj'),
                          regularization='30', tissue_table=str(table_file), tissue_labels=['P0'], tissue_axis='existing')


def test_pipeline_selection_is_exact_and_replacement_changes_effective_records(case, tmp_path):
    before = Path(case.input).read_bytes()
    reports, meshes = [], []
    for name, cfg in [('baseline', replace(case, tissue_table=None, tissue_labels=[], tissue_axis='unconfigured')),
                      ('selected', replace(case, tissue_labels=[])), ('changed', case)]:
        cfg.output = str(tmp_path/name/'face.obj')
        assert run_pipeline(cfg) == 0
        reports.append(json.loads(Path(cfg.output_json).read_text()))
        meshes.append(Path(cfg.output).read_bytes())
    assert meshes[0] == meshes[1] and meshes[2] != meshes[0]
    assert reports[0]['identity_coefficients'] == reports[1]['identity_coefficients']
    assert reports[1]['marker_metadata']['tissue_application']['status'] == 'selected_only'
    meta = reports[2]['marker_metadata']
    assert meta['marker_records']['P0']['tissue_depth_mm'] == 4
    assert meta['marker_records']['P1']['tissue_depth_mm'] == 2
    assert reports[2]['inputs']['tissue_table']['sha256'] == load_table(case.tissue_table).sha256
    assert Path(case.input).read_bytes() == before


def test_cli_path_and_axis_guards(case):
    cfg = parse_args(['--input', case.input])
    assert cfg.tissue_table is None and cfg.tissue_compare is None and cfg.tissue_labels == []
    assert run_pipeline(replace(case, tissue_axis='unconfigured')) == 2
    before = Path(case.tissue_table).read_bytes()
    assert run_pipeline(replace(case, output=case.tissue_table, overwrite=True)) == 2
    assert Path(case.tissue_table).read_bytes() == before


def test_frozen_protocol_hashes_custom_table_bytes(case, tmp_path):
    from cranio.protocol import frozen_from_report, validate_protocol
    from cranio.validation import sha256_file
    case.geometry_qc = 'full'
    assert run_pipeline(case) == 0
    report = json.loads(Path(case.output_json).read_text())
    frozen = frozen_from_report(report, 'test/v1', 'a'*64)
    assert frozen['optional_inputs']['tissue_table'] == load_table(case.tissue_table).sha256
    path = tmp_path/'protocol.json'
    path.write_text(json.dumps(frozen))
    case.protocol = str(path)
    doc = load_table(case.tissue_table).document
    doc['landmarks']['P0']['central_mm'] += 1
    write_table(case.tissue_table, doc)
    with pytest.raises(ValueError, match='optional_inputs'):
        validate_protocol(case, {}, [], sha256_file(case.npz))


@pytest.fixture
def comparison(case):
    return replace(case, tissue_table=None, tissue_compare=f'{case.tissue_table},{case.tissue_table}')


def test_self_comparison_zero_lists_each_run_and_never_overwrites(comparison, tmp_path):
    before = Path(comparison.input).read_bytes()
    assert run_pipeline(comparison) == 0
    folder = tmp_path/'case_tissue_compare'
    summary = json.loads((folder/'summary.json').read_text())
    assert len(summary['tables']) == 2 and summary['color_scale_max_mm'] == 0
    for run in summary['tables']:
        assert run['selected_labels'] == ['P0']
        for layer in ('final', 'statistical'):
            result = run['differences_to_first'][layer]
            assert result['all_vertices']['max_mm'] == 0
            text = (folder/result['ply']).read_text()
            assert 'property double vertex_difference_mm' in text and 'NOT uncertainty' in text
        report = json.loads((folder/run['report']).read_text())
        assert report['marker_metadata']['tissue_application']['replacements'][0]['before']['tissue_depth_mm'] == 2
    assert Path(comparison.input).read_bytes() == before
    comparison.overwrite = True
    assert run_pipeline(comparison) == 2
    assert json.loads((folder/'summary.json').read_text()) == summary


def test_distinct_tables_refit_from_same_original_case(comparison, tmp_path):
    doc = empty_table('second')
    doc['landmarks']['P0'] = dict(central_mm=9.)
    path = tmp_path/'second.json'
    write_table(path, doc)
    comparison.tissue_compare = comparison.tissue_compare.split(',')[0]+','+str(path)
    assert run_pipeline(comparison) == 0
    folder = tmp_path/'case_tissue_compare'
    summary = json.loads((folder/'summary.json').read_text())
    assert summary['tables'][1]['differences_to_first']['final']['all_vertices']['max_mm'] > 0
    reports = [json.loads((folder/r['report']).read_text()) for r in summary['tables']]
    assert reports[0]['marker_metadata']['tissue_application']['replacements'][0]['before_target_mm'] == reports[1]['marker_metadata']['tissue_application']['replacements'][0]['before_target_mm']
    assert reports[1]['marker_metadata']['marker_records']['P1']['tissue_depth_mm'] == 2


@pytest.mark.parametrize('kind', ['missing_depth', 'missing_label', 'no_labels', 'no_axis', 'one_table', 'empty_id', 'protocol'])
def test_bad_comparison_fails_before_outputs(comparison, tmp_path, kind):
    if kind == 'missing_depth':
        path = tmp_path/'empty.json'
        write_table(path, empty_table('empty'))
        comparison.tissue_compare += ','+str(path)
    if kind == 'missing_label': comparison.tissue_labels = ['absent']
    if kind == 'no_labels': comparison.tissue_labels = []
    if kind == 'no_axis': comparison.tissue_axis = 'unconfigured'
    if kind == 'one_table': comparison.tissue_compare = comparison.tissue_compare.split(',')[0]
    if kind == 'empty_id': comparison.tissue_compare += ','
    if kind == 'protocol': comparison.protocol = 'some.json'
    assert run_pipeline(comparison) == 2
    assert not (tmp_path/'case_tissue_compare').exists()


def test_failed_second_fit_has_no_success_summary(comparison, tmp_path, monkeypatch):
    import cranio.pipeline
    original, calls = cranio.pipeline.run_pipeline, []
    def failed(cfg):
        calls.append(cfg)
        return 3 if len(calls) == 2 else original(cfg)
    monkeypatch.setattr(cranio.pipeline, 'run_pipeline', failed)
    assert run_comparison(comparison) == 3
    assert not (tmp_path/'case_tissue_compare'/'summary.json').exists()


def test_inputs_pinned_across_all_fits(comparison, tmp_path, monkeypatch):
    import cranio.pipeline
    original = cranio.pipeline.run_pipeline
    def changed(cfg):
        code = original(cfg)
        path = Path(cfg.input)
        path.write_bytes(path.read_bytes()+b'\n')
        return code
    monkeypatch.setattr(cranio.pipeline, 'run_pipeline', changed)
    with pytest.raises(ValueError, match='changed between runs'):
        run_comparison(comparison)
    assert not (tmp_path/'case_tissue_compare'/'summary.json').exists()


def test_tiny_axis_rejected_consistently_with_blender_guard(table_file):
    targets, meta = points()
    targets[0] = targets[0]._replace(xyz=np.array([1., 2., 3.+1e-10]))
    with pytest.raises(ValueError, match='axis'):
        apply_table(targets, meta, load_table(table_file), ['P0'], 'existing')


def test_cli_compare_flags_execute_complete_workflow(comparison, tmp_path):
    from gnm_reconstruct import main
    assert main(['--input', comparison.input, '--npz', comparison.npz,
                 '--output', str(tmp_path/'cli.obj'), '--regularization', '30',
                 '--tissue-compare', comparison.tissue_compare, '--tissue-labels', 'P0',
                 '--tissue-axis', 'existing']) == 0
    assert json.loads((tmp_path/'cli_tissue_compare'/'summary.json').read_text())['status'] == 'completed'

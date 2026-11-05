"""Synthetic audit tests only: no population values, biological or CT validation."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import pytest
from cranio.age_context import KEY, LIMITATION, empty_estimate, validate_estimate, resolve, describe_age, is_declared, load_case_age, main
from cranio.tissue import empty_table, load_table, write_table
from cranio.tissue_context import with_case_metadata, describe_context, context_text
from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline


def estimate(bounds=(30, 35), **kwargs):
    return dict(empty_estimate(), range_years=list(bounds), method='synthetic method',
                source='synthetic fixture', **kwargs)


@pytest.fixture
def table(tmp_path):
    doc=empty_table('synthetic_age')
    doc['age_range_years']=[20, 40]
    path=tmp_path/'table.json'
    write_table(path,doc)
    return load_table(path)


@pytest.mark.parametrize('bounds,status,intersection', [([30,35],'within_reported_range',[30,35]),
    ([20,40],'within_reported_range',[20,40]), ([40,40],'within_reported_range',[40,40]),
    ([0,20],'partial_overlap',[20,20]), ([10,30],'partial_overlap',[20,30]),
    ([30,50],'partial_overlap',[30,40]), ([0,80],'partial_overlap',[20,40]),
    ([41,50],'outside_reported_range',None), ([0,19],'outside_reported_range',None)])
def test_inclusive_intervals(table,bounds,status,intersection):
    metadata={KEY:estimate(bounds,reviewed=True)}
    before=copy.deepcopy(metadata)
    record=describe_age(metadata,table)
    assert record['comparison']==status and record['intersection_years']==intersection
    assert record['table']['sha256']==table.sha256 and metadata==before
    assert LIMITATION in record['warnings']


@pytest.mark.parametrize('value', [None,empty_estimate()])
def test_unknown_not_imputed(table,value):
    assert describe_age({KEY:value},table)['comparison']=='no_estimate'
    assert is_declared({KEY:value})
    assert not is_declared({})


def test_unreviewed_and_unknown_table_are_not_range_matches(table):
    assert describe_age({KEY:estimate()},table)['comparison']=='unreviewed_estimate'
    assert describe_age({KEY:estimate(reviewed=True)})['comparison']=='no_table_selected'
    assert describe_age({KEY:estimate(reviewed=True)},load_table('legacy_hardcoded'))['comparison']=='table_age_unknown'


@pytest.mark.parametrize('updates', [dict(range_years=[-1,2]), dict(range_years=[True,2]),
    dict(range_years=[0,float('nan')]),dict(range_years=[0,float('inf')]),
    dict(range_years=[0,10**400]),dict(range_years=[5,4]),dict(range_years=[5]),
    dict(range_years='30-35'),dict(schema_version=True),dict(schema_version=2),
    dict(reviewed=1),dict(method=42),dict(source=[]),dict(extra='discard me'),
    dict(reviewed=True,source='TODO(verify-source)'),dict(reviewed=True,method='Unknown'),
    dict(reviewed=True,range_years=None)])
def test_malformed_or_falsely_reviewed_rejected(updates):
    with pytest.raises(ValueError):
        validate_estimate(dict(estimate(),**updates))


def test_conflicts_and_mutation_protection(tmp_path):
    value=estimate(reviewed=True)
    metadata={KEY:value,'case_metadata':{KEY:copy.deepcopy(value)}}
    result=resolve(metadata)
    result['estimate']['range_years'][0]=0
    assert metadata[KEY]['range_years']==[30,35]
    path=tmp_path/'external.json'
    path.write_text(json.dumps({KEY:dict(value,source='different assessment')}))
    with pytest.raises(ValueError,match='Conflicting'):
        with_case_metadata(metadata,path)
    with pytest.raises(ValueError,match='Conflicting'):
        resolve({KEY:value,'case_metadata':{KEY:dict(value,reviewed=False)}})
    with pytest.raises(ValueError):
        resolve({'case_metadata':[]})


@pytest.mark.parametrize('external',[{}, {KEY:None}, {'acquisition_posture':'supine'}])
def test_external_metadata_never_erases_embedded_age(tmp_path,external):
    metadata={'case_metadata':{KEY:estimate(reviewed=True)}}
    before=copy.deepcopy(metadata)
    path=tmp_path/'external.json'
    path.write_text(json.dumps(external))
    result=with_case_metadata(metadata,path)
    assert resolve(result)['estimate']==metadata['case_metadata'][KEY]
    assert metadata==before


def test_cli_determinism_hashes_and_no_overwrite(tmp_path,table):
    path=tmp_path/'case.json'
    assert main(['template','--output',str(path)])==0
    assert json.loads(path.read_text())=={KEY:empty_estimate()}
    original=path.read_bytes()
    with pytest.raises(SystemExit):
        main(['template','--output',str(path)])
    assert path.read_bytes()==original
    assert load_case_age(path)['age_estimate_source_file']['sha256']==hashlib.sha256(original).hexdigest()
    outputs=[]
    for name in ('one','two'):
        output=tmp_path/(name+'.json')
        assert main(['compare','--case-metadata',str(path),'--tables',str(tmp_path/'table.json'),
                     'legacy_hardcoded','--output',str(output)])==0
        outputs.append(output.read_bytes())
    assert outputs[0]==outputs[1]
    record=json.loads(outputs[0])
    assert record['comparisons'][0]['table']['sha256']==table.sha256
    assert record['comparisons'][0]['case']['estimate']['range_years'] is None


@pytest.mark.parametrize('text',['[]','{}','{"age_at_death_estimate":null,"age_at_death_estimate":null}',
    '{"age_at_death_estimate":NaN}'])
def test_file_rejects_ambiguous_json(tmp_path,text):
    path=tmp_path/'bad.json'
    path.write_text(text)
    with pytest.raises(ValueError):
        load_case_age(path)
    out=tmp_path/'out.json'
    with pytest.raises(SystemExit):
        main(['compare','--case-metadata',str(path),'--tables','legacy_hardcoded','--output',str(out)])
    assert not out.exists()


def test_context_absence_and_rendering(table):
    assert 'age' not in describe_context(table,{})
    record=describe_context(table,{KEY:estimate(reviewed=True)})
    for compact in (False,True):
        text=context_text(record,compact)
        assert 'Age at death' in text and 'synthetic method' in text and LIMITATION in text


@pytest.mark.parametrize('local',[False,True])
@pytest.mark.parametrize('use_table',[False,True])
def test_age_is_reporting_only(model_file,marker_file,tmp_path,table,local,use_table):
    casefile=tmp_path/'case.json'
    casefile.write_text(json.dumps({KEY:estimate(reviewed=True)}))
    reports,meshes=[],[]
    for name,metadata in [('legacy',None),('age',str(casefile))]:
        cfg=PipelineConfig(input=str(marker_file),npz=str(model_file),output=str(tmp_path/name/'face.obj'),
            case_metadata=metadata,tissue_table=str(tmp_path/'table.json') if use_table else None,
            regularization='30',skip_tps=not local)
        assert run_pipeline(cfg)==0
        reports.append(json.loads(Path(cfg.output_json).read_text()))
        meshes.append(Path(cfg.output).read_bytes())
        if metadata:
            assert 'Age at death' in Path(cfg.output_stats).read_text()
    assert meshes[0]==meshes[1]
    for field in ('identity_coefficients','transform','lambda','solver','metrics'):
        assert reports[0][field]==reports[1][field]
    assert 'age_context' not in reports[0]['marker_metadata']
    age=reports[1]['marker_metadata']['age_context']
    assert age['comparison']==('within_reported_range' if use_table else 'no_table_selected')
    if use_table:
        assert age==reports[1]['marker_metadata']['tissue_application']['context']['age']


def test_invalid_age_fails_before_mesh_export(model_file,marker_file,tmp_path):
    casefile=tmp_path/'case.json'
    casefile.write_text(json.dumps({KEY:dict(estimate(),range_years=[2,1])}))
    cfg=PipelineConfig(input=str(marker_file),npz=str(model_file),output=str(tmp_path/'bad.obj'),case_metadata=str(casefile))
    assert run_pipeline(cfg)==2 and not Path(cfg.output).exists()


def test_tissue_comparison_retains_same_age_audit(model_file,marker_file,tmp_path,table):
    from cranio.io_csv import read_marker_csv, write_marker_csv_v3
    targets,_,metadata=read_marker_csv(marker_file,{}, {})
    rows=[dict(label=t.label,vertex=t.vertex,placed=1,x=t.xyz[0],y=t.xyz[1],z=t.xyz[2],
        bone_x=t.xyz[0],bone_y=t.xyz[1],bone_z=t.xyz[2]-2,tissue_depth_mm=2,
        weight=t.weight,tissue_source='synthetic fixture') for t in targets]
    write_marker_csv_v3(marker_file,rows,metadata)
    doc=table.document
    doc['landmarks']['P0']=dict(central_mm=2.)
    write_table(tmp_path/'table.json',doc)
    casefile=tmp_path/'case.json'
    casefile.write_text(json.dumps({KEY:estimate(reviewed=True)}))
    cfg=PipelineConfig(input=str(marker_file),npz=str(model_file),output=str(tmp_path/'face.obj'),
        case_metadata=str(casefile),tissue_table=str(tmp_path/'table.json'),regularization='30',
        tissue_labels=['P0'],tissue_axis='existing')
    assert run_pipeline(cfg)==0
    expected=json.loads(Path(cfg.output_json).read_text())['marker_metadata']['age_context']
    compare=replace(cfg,output=str(tmp_path/'comparison.obj'),tissue_table=None,
                    output_json=None,output_error_mesh=None,output_stats=None,output_statistical=None,
                    tissue_compare=f'{cfg.tissue_table},{cfg.tissue_table}')
    assert run_pipeline(compare)==0
    record=json.loads((tmp_path/'comparison_tissue_compare'/'summary.json').read_text())
    assert record['color_scale_max_mm']==0
    assert all(t['tissue_context']['age']==expected for t in record['tables'])

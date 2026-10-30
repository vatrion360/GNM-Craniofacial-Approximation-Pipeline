"""Metadata/synthetic regression only, not source validation or CT results."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import numpy as np
import pytest
from cranio.tissue import empty_table, load_table, write_table
from cranio.tissue_context import case_posture, describe_context, context_text
from cranio.tissue_application import apply_table
from cranio.io_csv import MarkerTarget, read_marker_csv, write_marker_csv_v3
from cranio.config import PipelineConfig
from cranio.pipeline import run_pipeline
from gnm_reconstruct import parse_args


@pytest.fixture
def table_file(tmp_path):
    doc=empty_table('synthetic_context')
    doc['posture']='upright'
    doc['measurement_method']='CT'
    doc['landmarks']={'P0':dict(central_mm=4.,estimator='shorth'),
                      'P1':dict(central_mm=7.,estimator='75-shormax'),
                      'P2':dict(central_mm=9.,estimator='mean'),
                      'P3':dict(central_mm=2.,estimator=None)}
    doc['regions']={'scalp':dict(central_mm=3.,estimator='median')}
    path=tmp_path/'table.json'
    write_table(path,doc)
    return path


@pytest.mark.parametrize('case,reference,status', [('supine','upright','different_labels'),
    (' Upright ','UPRIGHT','matching_labels'), ('seated','upright','different_labels'),
    ('supine CT','supine','different_labels'), (None,'supine','unknown'),
    ('unknown','supine','unknown'), ('supine',None,'unknown'), ('supine','not reported','unknown')])
def test_posture_labels_only_no_synonym_or_ct_inference(table_file,case,reference,status):
    table=load_table(table_file).document
    table['posture']=reference
    write_table(table_file,table)
    meta=dict(acquisition_posture=case, modality='CT')
    before=copy.deepcopy(meta)
    record=describe_context(load_table(table_file),meta)
    assert record['posture_comparison']==status and meta==before
    assert record['table_posture']==reference
    assert bool(record['warnings'])==(status!='matching_labels')


def test_modalities_never_impute_case_posture(table_file):
    record=describe_context(load_table(table_file),dict(modality='CT',case_metadata=dict(modality='CT')))
    assert record['case_posture']['value'] is None
    assert record['posture_comparison']=='unknown'


@pytest.mark.parametrize('metadata,explicit', [({'acquisition_posture':'supine'},'upright'),
    ({'acquisition_posture':'supine','case_metadata':{'acquisition_posture':'upright'}},None),
    ({'acquisition_posture':12},None), ({'case_metadata':[]},None)])
def test_conflicting_or_malformed_case_posture_rejected(metadata,explicit):
    with pytest.raises(ValueError):
        case_posture(metadata,explicit)


def test_consistent_raw_declarations_retained():
    rec=case_posture({'acquisition_posture':'SUPINE','case_metadata':{'acquisition_posture':' supine '}},'Supine')
    assert rec['normalized']=='supine' and rec['declarations']['case_metadata']==' supine '


@pytest.mark.parametrize('label,depth', [('P0',4.),('P1',7.)])
def test_precomputed_estimators_applied_verbatim_without_deriving_from_mean(table_file,label,depth):
    table=load_table(table_file)
    targets=[MarkerTarget(label,0,np.array([0.,0.,1.]),1.)]
    meta=dict(version=3,acquisition_posture='supine',marker_records={label:dict(bone_xyz_mm=[0.,0.,0.])})
    result,_,record=apply_table(targets,meta,table,[label],'existing')
    np.testing.assert_array_equal(result[0].xyz,[0.,0.,depth])
    context=record['context']
    assert context['estimators']['landmarks'][label]['depth_applied']
    assert not context['estimators']['landmarks']['P2']['depth_applied']
    assert not context['estimators']['regions']['scalp']['depth_applied']
    text=context_text(context)
    assert 'shorth' in text and '75-shormax' in text and 'unknown' in text
    assert 'no estimator is calculated from means' in text


@pytest.fixture
def case(tmp_path,model_file,marker_file,table_file):
    targets,_,metadata=read_marker_csv(marker_file,{}, {})
    rows=[dict(label=t.label,vertex=t.vertex,placed=1,x=t.xyz[0],y=t.xyz[1],z=t.xyz[2],
        bone_x=t.xyz[0],bone_y=t.xyz[1],bone_z=t.xyz[2]-2,tissue_depth_mm=2,
        weight=t.weight,tissue_source='synthetic fixture') for t in targets]
    write_marker_csv_v3(marker_file,rows,metadata)
    return PipelineConfig(input=str(marker_file),npz=str(model_file),output=str(tmp_path/'fit.obj'),
        tissue_table=str(table_file),tissue_labels=['P0'],tissue_axis='existing',regularization='30')


@pytest.mark.parametrize('local',[False,True])
def test_posture_only_changes_reporting_not_fit_or_tps(case,tmp_path,local):
    meshes,reports=[],[]
    original=Path(case.input).read_bytes()
    for name,posture in [('unknown',None),('matched','upright'),('mismatch','supine')]:
        cfg=replace(case,output=str(tmp_path/name/'face.obj'),case_posture=posture,skip_tps=not local)
        assert run_pipeline(cfg)==0
        meshes.append(Path(cfg.output).read_bytes())
        reports.append(json.loads(Path(cfg.output_json).read_text()))
        if posture=='supine':
            assert 'Tissue posture mismatch' in Path(cfg.output_stats).read_text()
            assert 'Tissue estimator landmarks.P0: shorth' in Path(cfg.output_stats).read_text()
            assert any('posture mismatch' in w for w in reports[-1]['warnings'])
    assert meshes[0]==meshes[1]==meshes[2] and Path(case.input).read_bytes()==original
    for field in ('identity_coefficients','transform','lambda','solver','metrics'):
        assert reports[0][field]==reports[1][field]==reports[2][field]


def test_external_case_metadata_matches_single_and_comparison(case,tmp_path):
    doc=tmp_path/'case.json'
    doc.write_text(json.dumps({'acquisition_posture':'supine'}))
    cfg=replace(case,case_metadata=str(doc))
    assert run_pipeline(cfg)==0
    single=json.loads(Path(cfg.output_json).read_text())['marker_metadata']['tissue_application']['context']
    compare=replace(case,output=str(tmp_path/'compare.obj'),case_metadata=str(doc),tissue_table=None,
                    tissue_compare=f'{case.tissue_table},{case.tissue_table}')
    assert run_pipeline(compare)==0
    summary=json.loads((tmp_path/'compare_tissue_compare'/'summary.json').read_text())
    assert summary['color_scale_max_mm']==0
    assert all(t['tissue_context']==single for t in summary['tables'])
    conflict=replace(compare,output=str(tmp_path/'conflict.obj'),case_posture='upright')
    assert run_pipeline(conflict)==2 and not (tmp_path/'conflict_tissue_compare').exists()


def test_cli_and_protocol_treat_posture_as_case_metadata(case,tmp_path):
    from cranio.protocol import scientific_settings
    cfg=parse_args(['--input',case.input,'--npz',case.npz,'--tissue-table',case.tissue_table,
                    '--case-posture','supine','--output',str(tmp_path/'cli.obj'),'--regularization','30'])
    assert run_pipeline(cfg)==0
    report=json.loads(Path(cfg.output_json).read_text())
    context=report['marker_metadata']['tissue_application']['context']
    assert context['case_posture']['value']=='supine'
    assert not any(r['depth_applied'] for r in context['estimators']['landmarks'].values())
    assert 'case_posture' not in scientific_settings(cfg)


def test_compact_ui_does_not_dump_unapplied_catalogue(table_file):
    rec=describe_context(load_table(table_file),{'acquisition_posture':'supine'},['P0'])
    text=context_text(rec,compact=True)
    assert 'shorth: 1' in text and 'P2' not in text and '75-shormax' not in text


def test_null_case_document_leaves_posture_unknown():
    assert case_posture({"case_metadata": None})["value"] is None

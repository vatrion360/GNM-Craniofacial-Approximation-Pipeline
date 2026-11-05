"""Bundle integrity and shared intent checks; no biological inference."""
import json
import shutil
import numpy as np
import pytest
from cranio.blender_prior_audit import load_comparison, _surface
from cranio.prior import validate_justification
from cranio.pipeline import run_pipeline
from cranio.config import PipelineConfig
from cranio.validation import sha256_file


@pytest.fixture
def bundle(tmp_path, model_file, marker_file):
    prior=tmp_path/'prior.npz'
    np.savez(prior,mean=np.zeros(3),scale=np.ones(3))
    config=PipelineConfig(input=str(marker_file),npz=str(model_file),output=str(tmp_path/'case.obj'),
        prior=str(prior),prior_compare=True,prior_justification='Synthetic scenario only',regularization='30')
    assert run_pipeline(config)==0
    return tmp_path/'case_prior_compare'


@pytest.mark.parametrize('separator',['/','\\'])
def test_bundle_roundtrip_and_relocation(bundle,tmp_path,separator):
    path=bundle/'summary.json'
    record=json.loads(path.read_text())
    for row in record['scenarios']:
        row['report']=row['id']+separator+'face_report.json'
    path.write_text(json.dumps(record))
    summary,rows=load_comparison(bundle)
    assert [r['id'] for r in rows]==['neutral','prior']
    assert summary['comparison_status']=='completed_converged'
    np.testing.assert_array_equal(rows[0]['vertices'],rows[1]['vertices'])
    relocated=tmp_path/'relocated'
    shutil.copytree(bundle,relocated)
    assert load_comparison(relocated)[0]==summary


@pytest.mark.parametrize('artifact',['neutral/face.obj','prior/face_statistical.obj',
    'prior/face_report.json','neutral/face_heatmap.ply','prior/face_statistici.txt',
    'difference_final.ply','difference_statistical.ply','comparison.txt'])
def test_modified_artifact_rejected(bundle,artifact):
    path=bundle/artifact
    path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='checksum'):
        load_comparison(bundle)


@pytest.mark.parametrize('kind',['status','units','reference','duplicate_scenario','path','null_hash','boolean_version','solver_status'])
def test_summary_malformed_or_ambiguous_rejected(bundle,kind):
    path=bundle/'summary.json'
    record=json.loads(path.read_text())
    if kind=='status': record['status']='running'
    if kind=='units': record['units']='m'
    if kind=='reference': record['reference']='prior'
    if kind=='duplicate_scenario': record['scenarios'][1]=record['scenarios'][0]
    if kind=='path': record['scenarios'][0]['report']='../face_report.json'
    if kind=='null_hash': record['scenarios'][0]['report_sha256']=None
    if kind=='boolean_version': record['schema_version']=True
    if kind=='solver_status': record['comparison_status']='diagnostic_only_nonconverged'
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError): load_comparison(bundle)


def test_missing_completion_marker_rejected(bundle):
    (bundle/'summary.json').unlink()
    with pytest.raises(OSError): load_comparison(bundle)


def test_nonconvergence_remains_explicit(bundle):
    path=bundle/'summary.json'
    record=json.loads(path.read_text())
    child=bundle/'prior/face_report.json'
    report=json.loads(child.read_text())
    report['solver']['converged']=False
    child.write_text(json.dumps(report))
    record['scenarios'][1]['report_sha256']=sha256_file(child)
    record['scenarios'][1]['solver']=report['solver']
    record['comparison_status']='diagnostic_only_nonconverged'
    path.write_text(json.dumps(record))
    assert load_comparison(bundle)[0]['comparison_status']=='diagnostic_only_nonconverged'


def test_different_topology_rejected_even_with_matching_hashes(bundle):
    path=bundle/'prior/face.obj'
    text=path.read_text().replace('f 1 2 3','f 1 3 2')
    path.write_text(text)
    report_path=bundle/'prior/face_report.json'
    report=json.loads(report_path.read_text())
    report['outputs']['output']['sha256']=sha256_file(path)
    report_path.write_text(json.dumps(report))
    summary_path=bundle/'summary.json'
    summary=json.loads(summary_path.read_text())
    summary['scenarios'][1]['report_sha256']=sha256_file(report_path)
    summary_path.write_text(json.dumps(summary))
    with pytest.raises(ValueError,match='topology'): load_comparison(bundle)


@pytest.mark.parametrize('data',[b'',b'v nan 0 0\nf 1 1 1',b'v 0 0 0\nf 0 1 2',
    b'v 0 0 0\nf 1 2 3',b'v 0 0 0\nf 1 1 1',b'v 0 0 0\nv 1 1 1\nv 2 2 2\nf 1/1 2/2 3/3',
    b'v 0 0 0 1',b'not_an_obj'])
def test_invalid_obj_rejected(data):
    with pytest.raises(ValueError): _surface(data)


@pytest.mark.parametrize('reason',[None,'',' ',12,'unknown','TODO(verify-source): justification'])
def test_required_rationale_rejected(reason):
    with pytest.raises(ValueError): validate_justification(reason,required=True)


def test_optional_legacy_and_documented_unicode_rationale():
    validate_justification(None)
    validate_justification('Scenariu sintetic — verificare software, fără validare anatomică',required=True)

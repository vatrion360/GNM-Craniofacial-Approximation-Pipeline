"""No humans, DICOM, real CT data or clinical thresholds: synthetic manual ledgers only."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from cranio import validation_cases as v
from cranio.backend import GNMBackend
from cranio.config import PipelineConfig
from cranio.io_csv import write_marker_csv_v3
from cranio.pipeline import run_pipeline


def edit(path, fn):
    d=json.loads(path.read_bytes())
    fn(d)
    path.write_text(json.dumps(d),encoding='utf-8')


def plane(x,z):
    return f'v {x} 0 {z}\nv {x+1} 0 {z}\nv {x} 1 {z}\nf 1 2 3\n'.encode()


def study(root,arm='blind_ct'):
    subjects=['S01','S02','S03']
    runs=['live_A','live_B']
    v.initialize(root,arm,subjects,runs,[] if arm=='historical' else ['face'])
    (root/'protocol.txt').write_text('Synthetic plane protocol. Case-frame mm, one ROI; no surface alignment.')
    def plan(d):
        d['protocol_file']='protocol.txt'
        for label in runs:
            d['runs'][label].update(stage='blender_live',observer=label,session='one')
        if arm!='historical':
            d['outcomes']['face'].update(quantity='surface_signed',direction='approx_to_reference',
                                         definition='Plane normal +Z; synthetic signed offsets in mm')
    edit(root/'study.json',plan)
    for i,k in enumerate(subjects):
        p=root/k
        (p/'skull.obj').write_bytes(plane(i,-5))
        (p/'fit.obj').write_bytes(plane(i,i+1))
        def case(d):
            d.update(skull='skull.obj',strata={'preservation':{'value':'partial' if i==2 else 'complete','source':'Synthetic cases'}})
            for label in runs:
                d['runs'][label].update(mesh='fit.obj',reference_access=v.ACCESS[arm])
            if i==2:
                d['runs']['live_B'].update(mesh=None,reason='No saved fit',reference_access=None)
        edit(p/'case.json',case)


def reviewed(root,lock):
    for i,k in enumerate(('S01','S02','S03')):
        p=root/k
        (p/'reference.obj').write_bytes(plane(i,0))
        (p/'roi.txt').write_text('Synthetic untransformed plane')
        def review(d):
            d.update(reference_face='reference.obj',roi_alignment_record='roi.txt',evaluator='separate reader')
            for run in ('live_A','live_B'):
                if run=='live_B' and i==2: continue
                (p/(run+'.csv')).write_text('//X;Signed mm\n'+f'0;{-i-1}\n'*(90 if i==0 else 1))
                d['runs'][run]['face']=dict(file=run+'.csv',column='Signed mm',separator='semicolon',reason=None)
        edit(lock/(k+'.review.json'),review)


def test_three_subjects_manual_roundtrip_equal_subject_weight_and_session_separation(tmp_path):
    root,lock,out=(tmp_path/x for x in ('cases','lock','out'))
    study(root)
    digest=v.freeze(root,lock)
    assert digest==hashlib.sha256((lock/'lock.json').read_bytes()).hexdigest()
    reviewed(root,lock)
    assert v.main(['summarize','--root',str(root),'--lock-dir',str(lock),'--expected-sha256',digest,
                   '--output-dir',str(out)])==0
    with (out/'cases.csv').open() as f: rows=list(csv.DictReader(f))
    assert [r['n'] for r in rows if r['run']=='live_A']==['90','1','1']
    assert rows[0]['signed_bias_mm']=='-1.0' and rows[-1]['status']=='missing_fit'
    with (out/'cohort.csv').open() as f: groups=list(csv.DictReader(f))
    overall=[r for r in groups if r['stratum']=='overall']
    assert [(r['run'],r['enrolled'],r['measured'],r['mean_subject_mae_mm']) for r in overall]==[
        ('live_A','3','3','2.0'),('live_B','3','2','1.5')]
    missing=next(r for r in groups if r['run']=='live_B' and r['value']=='partial')
    assert missing['measured']=='0' and missing['mean_subject_mae_mm']==''
    assert 'Exploratory' in (out/'summary.md').read_text()
    a=json.loads((out/'manifest.json').read_bytes())
    assert a['reviews']['S01']['fields'][0]['sha256']==v.sha256_file(root/'S01'/'live_A.csv')
    v.summarize(root,lock,digest,tmp_path/'again')
    assert (out/'manifest.json').read_bytes()==(tmp_path/'again'/'manifest.json').read_bytes()
    with pytest.raises(ValueError,match='new output'):
        v.summarize(root,lock,digest,out)


@pytest.mark.parametrize('arm',['historical','ct_conditioned','paired_ct_unblinded'])
def test_separate_nonblind_arm_and_missing_not_zero(tmp_path,arm):
    root,lock,out=(tmp_path/x for x in ('cases','lock','out'))
    study(root,arm)
    digest=v.freeze(root,lock)
    assert bool(list(lock.glob('*.review.json')))==(arm!='historical')
    v.summarize(root,lock,digest,out)
    assert json.loads((out/'manifest.json').read_bytes())['arm']==arm
    with (out/'cases.csv').open() as f: rows=list(csv.DictReader(f))
    assert all(r['mae_mm']=='' for r in rows)
    assert rows[0]['status']==('no_reference' if arm=='historical' else 'not_evaluated')


@pytest.mark.parametrize('problem',['wrong_digest','moved_fit','wrong_case','wrong_lock','no_roi','observer',
                                   'duplicate_field','reference_as_fit','cross_case_path','used_reference','duplicate_subject'])
def test_reject_mixed_or_unverifiable_evidence(tmp_path,problem):
    root,lock,out=(tmp_path/x for x in ('cases','lock','out'))
    study(root)
    if problem=='used_reference':
        edit(root/'S01/case.json',lambda d:d['runs']['live_A'].update(reference_access='used'))
    if problem=='duplicate_subject':
        (root/'S02/skull.obj').write_bytes((root/'S01/skull.obj').read_bytes())
    if problem in ('used_reference','duplicate_subject'):
        with pytest.raises(ValueError): v.freeze(root,lock)
        return
    digest=v.freeze(root,lock)
    reviewed(root,lock)
    r=lock/'S01.review.json'
    if problem=='wrong_digest': digest='0'*64
    elif problem=='moved_fit': (root/'S01/fit.obj').write_bytes(plane(0,5))
    elif problem=='wrong_case': edit(r,lambda d:d.update(case_id='S02'))
    elif problem=='wrong_lock': edit(r,lambda d:d.update(lock_sha256='e'*64))
    elif problem=='no_roi': edit(r,lambda d:d.update(roi_alignment_record=None))
    elif problem=='observer': edit(r,lambda d:d.update(evaluator='LIVE_A'))
    elif problem=='duplicate_field': edit(r,lambda d:d['runs']['live_B']['face'].update(file='live_A.csv'))
    elif problem=='reference_as_fit': edit(r,lambda d:d.update(reference_face='fit.obj'))
    elif problem=='cross_case_path': edit(r,lambda d:d.update(reference_face='../S02/reference.obj'))
    with pytest.raises(ValueError): v.summarize(root,lock,digest,out)
    assert not out.exists()


def test_arithmetic_and_invalid_cloud_fields(tmp_path):
    p=tmp_path/'export.csv'
    p.write_text('//X,Distance\n-1,-3\n2,4\n')
    r=v.distances(p,'Distance','comma',True)
    assert r['rmse_mm']==pytest.approx((25/2)**.5) and r['signed_bias_mm']==.5
    assert r['mae_mm']==r['median_abs_mm']==3.5 and r['p95_abs_mm']==pytest.approx(3.95)
    with pytest.raises(ValueError): v.distances(p,'Distance','comma',False)
    for s in ('Distance,Distance\n1,2','Distance\nNaN','Distance\n','Distance\n1,2','Distance\ninf'):
        p.write_text(s)
        with pytest.raises(ValueError): v.distances(p,'Distance','comma',True)


def test_stage_and_case_bound_to_real_pipeline_report(tmp_path,model_file):
    root=tmp_path/'study';study(root)
    p=root/'S01'; csvfile=p/'markers.csv'
    model=GNMBackend(str(model_file)).load()
    rows=[dict(label=f'P{i}',vertex=i,placed=1,weight=1,x=x,y=y,z=z) for i,(x,y,z) in enumerate(model.mu[:7])]
    write_marker_csv_v3(csvfile,rows,dict(case_id='S01'))
    cfg=PipelineConfig(input=str(csvfile),npz=str(model_file),output=str(p/'offline.obj'),regularization='20')
    assert run_pipeline(cfg)==0
    edit(root/'study.json',lambda d:d['runs']['live_A'].update(stage='offline_final'))
    edit(p/'case.json',lambda d:d['runs']['live_A'].update(mesh='offline.obj',fit_report=Path(cfg.output_json).name))
    row=v.inventory(root)['cases']['S01']['runs']['live_A']
    assert row['fit_report']['sha256']==v.sha256_file(cfg.output_json)
    assert 'new_degenerate_faces' in row['recorded_qc']['recorded_face_counts']
    edit(p/'case.json',lambda d:d['runs']['live_A'].update(mesh='fit.obj'))
    with pytest.raises(ValueError,match='exact exported stage'): v.inventory(root)


def test_reviewed_profile_points_computed_not_fitted(tmp_path):
    root,lock,out=(tmp_path/x for x in ('cases','lock','out'))
    study(root)
    edit(root/'study.json',lambda d:d['outcomes']['face'].update(quantity='profile_point_distance',
        direction='paired_points',sites=['Gl','N'],definition='Synthetic homologous sagittal points in the case frame'))
    digest=v.freeze(root,lock)
    p=root/'S01'; (p/'ref.obj').write_bytes(plane(0,0)); (p/'roi.txt').write_text('Synthetic section plane')
    pts=p/'points.csv'
    pts.write_text('site,approx_x_mm,approx_y_mm,approx_z_mm,ref_x_mm,ref_y_mm,ref_z_mm\nN,0,0,0,0,0,0\nGl,0,3,4,0,0,0\n')
    def read(d):
        d.update(reference_face='ref.obj',roi_alignment_record='roi.txt',evaluator='separate reader')
        d['runs']['live_A']['face'].update(file='points.csv',column=None,separator='comma',reason=None)
    edit(lock/'S01.review.json',read)
    v.summarize(root,lock,digest,out)
    with (out/'paired_sites.csv').open() as f:
        assert [(r['site'],float(r['distance_mm'])) for r in csv.DictReader(f)]==[('Gl',5),('N',0)]
    for text in ('Gl,3,4,0,0,0,0','N,nan,0,0,0,0,0','unplanned,1,0,0,0,0,0'):
        with pts.open('a') as f: f.write(text+'\n')
        with pytest.raises(ValueError): v.summarize(root,lock,digest,tmp_path/'bad')
        pts.write_text('\n'.join(pts.read_text().splitlines()[:-1])+'\n')


def test_changing_roi_during_import_does_not_publish(tmp_path,monkeypatch):
    root,lock,out=(tmp_path/x for x in ('cases','lock','out'))
    study(root);digest=v.freeze(root,lock);reviewed(root,lock)
    original=v.distances
    def change(*args):
        (root/'S01/roi.txt').write_text('Different alignment decision')
        return original(*args)
    monkeypatch.setattr(v,'distances',change)
    with pytest.raises(ValueError,match='changed during'):
        v.summarize(root,lock,digest,out)
    assert not out.exists()

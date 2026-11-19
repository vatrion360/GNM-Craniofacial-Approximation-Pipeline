import copy
import json

import numpy as np
import pytest

from cranio import surface_origin as origin
from cranio.backend import GNMBackend
from cranio.config import PipelineConfig
from cranio.io_csv import read_marker_csv,write_marker_csv_v3
from cranio.pipeline import run_pipeline
from cranio.record import compile_record
from cranio.uncertainty import main


def policy():
    return dict(schema='gnm.origin-factors.v1',case_id='fixture',status='calibrate',source='Synthetic factors only',
                mirrored=dict(weight_factor=.5,placement_sd_factor=2.),
                donor=dict(weight_factor=.25,placement_sd_factor=3.))


@pytest.mark.parametrize('key,value',[('weight_factor',0),('weight_factor',2),('placement_sd_factor',.5),
    ('placement_sd_factor',float('inf')),('placement_sd_factor',True)])
def test_reject_invalid_factors(key,value):
    p=policy()
    p['donor'][key]=value
    with pytest.raises(ValueError):
        origin.policy(p)


def test_named_origins_survive_csv_fit_record_and_mc(tmp_path,model_file):
    model=GNMBackend(str(model_file)).load()
    p=policy()
    rows=[]
    meta=dict(case_id='fixture',face_origins={},face_origin_policy=p,face_origin_base_weights={})
    plac={}
    expected=[]
    for i,(xyz,kind) in enumerate(zip(model.mu,['original','mirrored','donor','original','mirrored','donor'])):
        k='P'+str(i)
        bone=(xyz-[0,0,1]).tolist()
        rec=dict(origin=kind,polygon=i,point_mm=bone,source_id=kind,geometry_sha256='c'*64,lineage_sha256='e'*64)
        meta['face_origins'][k]=rec
        meta['face_origin_base_weights'][k]=.8
        factor=1 if kind=='original' else p[kind]['weight_factor']
        expected.append(.8*factor)
        rows.append(dict(label=k,vertex=i,placed=1,weight=expected[-1],x=xyz[0],y=xyz[1],z=xyz[2],
            bone_x=bone[0],bone_y=bone[1],bone_z=bone[2],tissue_depth_mm=1,
            bone_source_id=kind,bone_source_geometry_sha256='c'*64,bone_status='observed' if kind=='original' else 'reconstructed'))
        plac[k]=dict(sigma_mm=.2,source='Synthetic baseline')
    csv=tmp_path/'markers.csv'
    write_marker_csv_v3(csv,rows,meta)
    t,_,m=read_marker_csv(csv,{},{})
    assert [v.weight for v in t]==expected
    conf=PipelineConfig(input=str(csv),npz=str(model_file),output=str(tmp_path/'fit.obj'),regularization='30')
    assert run_pipeline(conf)==0
    from pathlib import Path
    record=compile_record(json.loads(Path(conf.output_json).read_text()))
    assert [r['provenance']['face_origin']['origin'] for r in record['markers']]==[r['bone_source_id'] for r in rows]
    sp=tmp_path/'sd.json'
    sp.write_text(json.dumps(dict(schema_version=1,placement=plac)))
    ensemble=tmp_path/'mc.json'
    assert main(['--placement',str(sp),'--input',str(csv),'--npz',str(model_file),'--output',str(ensemble),
                 '--samples','2','--seed','17'])==0
    a=json.loads(ensemble.read_text())
    sd=np.array([.2,.4,.6,.2,.4,.6])
    np.testing.assert_allclose([a['placement'][r['label']]['sigma_mm'] for r in rows],sd)
    np.testing.assert_allclose(a['placement_draws_mm'],np.random.Generator(np.random.PCG64(17)).normal(size=(2,6,3))*sd[None,:,None])
    assert a['weights']==expected
    empty=copy.deepcopy(plac)
    empty['P1']['sigma_mm']=None
    m['face_origin_policy']['donor']['placement_sd_factor']=None
    out=origin.apply_sd(empty,m)
    assert out['P1']['sigma_mm'] is None and out['P2']['sigma_mm'] is None
    bad=copy.deepcopy(meta)
    bad['face_origin_base_weights']['P1']=1
    with pytest.raises(ValueError,match='CSV weight'):
        write_marker_csv_v3(tmp_path/'bad.csv',rows,bad)
    bad=copy.deepcopy(meta)
    bad['face_origins']['P1']['origin']='original'
    with pytest.raises(ValueError,match='disagrees'):
        write_marker_csv_v3(tmp_path/'bad.csv',rows,bad)

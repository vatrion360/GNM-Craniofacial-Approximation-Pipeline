"""Engineering checks with known offsets. No subject data or anatomical cutoffs."""
import json
import os
from pathlib import Path

import numpy as np
import pytest

from cranio import dental_consistency as d
from cranio.backend import GNMBackend
from cranio.config import PipelineConfig
from cranio.io_csv import write_marker_csv_v3
from cranio.pipeline import run_pipeline
from cranio.validation import sha256_file

KEY = 'upper_right_central_incisor'
LOW = 'lower_left_canine'
SHA = 'b'*64


@pytest.fixture
def case(tmp_path, model_file):
    with np.load(model_file, allow_pickle=False) as z:
        arrays = dict(z)
    names, masks = arrays['vertex_group_names'].tolist(), list(arrays['vertex_groups'])
    for k, ids in dict(teeth=[0,1,3], upper_teeth_and_gums=[0,3], lower_teeth_and_gums=[1],
                       right=[0,2,3], left=[1,4], upper_lip=[2], lower_lip=[4], skin_exterior=[2,4]).items():
        m=np.zeros(12); m[ids]=1
        masks.append(m); names.append(k)
    arrays.update(vertex_groups=np.array(masks),vertex_group_names=np.array(names))
    np.savez(model_file, **arrays)
    model = GNMBackend(str(model_file)).load()
    marker=tmp_path/'case.csv'
    rows=[dict(label='P'+str(i), vertex=i, placed=1, weight=1, x=x, y=y, z=z) for i,(x,y,z) in enumerate(model.mu[:7])]
    write_marker_csv_v3(marker, rows, dict(case_id='synthetic', bone_sources=[dict(id='frag',geometry_sha256=SHA,
                                                                                 anatomy='MIXED')]))
    cfg=PipelineConfig(input=str(marker),npz=str(model_file),output=str(tmp_path/'fit.obj'),regularization='20')
    assert run_pipeline(cfg)==0
    report=Path(cfg.output_json); sites=tmp_path/'sites.json'; out=tmp_path/'result.json'
    assert d.main(['template','--report',str(report),'--output',str(sites)])==0
    args=['compare','--report',str(report),'--sites',str(sites),'--npz',str(model_file),'--output',str(out)]
    manifest=json.loads(sites.read_text())
    points=d._obj(Path(cfg.output).read_bytes(),12,model.triangles)
    def row(vertex,lip,other):
        return dict(state='observed', observation=dict(case_id='synthetic',source_id='frag',geometry_sha256=SHA,
                    xyz_mm=other.tolist()),correspondence=dict(reviewer='Fixture operator',definition='Synthetic vertex',
                    tooth_vertex=vertex, lip_vertex=lip))
    manifest['sites'][KEY]=row(0,2,points[0]+[3,4,0])
    manifest['sites'][LOW]=row(1,None,points[1])
    sites.write_text(json.dumps(manifest))
    return cfg,sites,out,args,manifest,points


def test_full_saved_fit_report_and_no_edits(case):
    cfg,sites,out,args,manifest,p=case
    paths=[cfg.npz,cfg.input,cfg.output,cfg.output_statistical,cfg.output_json,sites]
    old=[sha256_file(k) for k in paths]
    assert d.main(args)==0
    result=json.loads(out.read_text())
    for stage in ('final','statistical'):
        row=result['sites'][KEY]['stages'][stage]
        assert row['model_minus_observed_mm']==pytest.approx([-3,-4,0])
        assert row['tooth_distance_mm']==pytest.approx(5)
        proxy=np.linalg.norm(p[2]-(p[0]+[3,4,0]))-np.linalg.norm(p[2]-p[0])
        assert row['lip_chord']['observed_minus_model_mm']==pytest.approx(proxy)
        assert result['summary'][stage]==dict(measured=1,total=12,mean_tooth_distance_mm=pytest.approx(5),
                                               max_tooth_distance_mm=pytest.approx(5))
    assert 'articulation' in result['sites'][LOW]['reason']
    page=d.result_text(result)
    assert 'statistical: 5.000 / ' in page and 'Measured 1/12 sites.' in page
    assert [sha256_file(k) for k in paths]==old
    assert d.main(args)==2  # never overwrite
    report=json.loads(Path(cfg.output_json).read_text())
    report['marker_metadata']['mandible_articulation_reviewed']=True
    masks,_=d._asset(cfg.npz)
    result=d.compare(report,manifest['report_sha256'],manifest,masks,{'statistical':p,'final':p+[3,4,0]})
    assert result['sites'][KEY]['stages']['final']['tooth_distance_mm']==pytest.approx(0)
    assert result['sites'][LOW]['stages']['statistical']['lip_chord'] is None
    assert result['summary']['statistical']['measured']==2


def test_no_measurable_dentition_is_not_zero(case):
    cfg,sites,out,args,m,_=case
    m['sites'][KEY]['observation']['geometry_sha256']='c'*64
    m['sites'][LOW].update(state='reconstructed',observation=None)
    m['sites']['upper_left_canine']['state']='absent'
    sites.write_text(json.dumps(m))
    assert d.main(args)==0
    r=json.loads(out.read_text())
    assert 'changed' in r['sites'][KEY]['reason']
    assert r['sites'][LOW]['reason']=='reconstructed'
    assert r['summary']['final']['mean_tooth_distance_mm'] is None


@pytest.mark.parametrize('change',['case','fit','model','units','side','arch','gum','lip','duplicate','nonfinite','stale_obj','topology'])
def test_invalid_bindings_refused_before_publishing(case,change):
    cfg,sites,out,args,m,_=case
    row=m['sites'][KEY]
    if change=='case': row['observation']['case_id']='other'
    elif change=='fit': m['report_sha256']='e'*64
    elif change=='model': m['model_sha256']='e'*64
    elif change=='units': m['units']='m'
    elif change in ('side','arch','gum'):
        if change=='side':
            m['sites']['upper_left_central_incisor'],m['sites'][KEY]=row,m['sites']['upper_left_central_incisor']
        elif change=='arch':
            m['sites']['lower_right_central_incisor'],m['sites'][KEY]=row,m['sites']['lower_right_central_incisor']
        else: row['correspondence']['tooth_vertex']=5
    elif change=='lip': row['correspondence']['lip_vertex']=0
    elif change=='duplicate': m['sites']['upper_right_canine']=row
    elif change=='nonfinite': row['observation']['xyz_mm'][0]=float('nan')
    else:
        mesh=Path(cfg.output)
        if change=='stale_obj':
            mesh.write_bytes(mesh.read_bytes()+b'# edited\n')
        else:
            ls=mesh.read_text().splitlines()
            i=next(i for i,l in enumerate(ls) if l.startswith('f '))
            a,b,c=ls[i].split()[1:]; ls[i]=f'f {a} {c} {b}'
            mesh.write_text('\n'.join(ls)+'\n')
            report=Path(cfg.output_json); data=json.loads(report.read_text())
            data['outputs']['output']['sha256']=sha256_file(mesh); report.write_text(json.dumps(data))
            m['report_sha256']=sha256_file(report)
    sites.write_text(json.dumps(m))
    assert d.main(args)==2 and not out.exists()


@pytest.mark.integration
def test_official_asset_has_dental_anatomical_masks():
    path=os.environ.get('GNM_MODEL_PATH')
    if not path: pytest.skip('Official asset not configured')
    masks, tris=d._asset(path)
    assert len(tris)>0
    for arch in ('upper','lower'):
        for side in ('right','left'):
            assert (masks['teeth'] & masks[arch+'_teeth_and_gums'] & masks[side]).any()
            assert (masks[arch+'_lip'] & masks['skin_exterior'] & masks[side]).any()

import copy
import json

import numpy as np
import pytest

from cranio.repeatability import paired_report, for_uncertainty
from cranio.uncertainty import main, placement_config

DIGEST = 'a'*64


def pair(labels=('p','q','r')):
    a = dict(id='first',case_id='case',observer_id='op',labels=list(labels),
             sources=dict(bone=DIGEST),points={k:dict(source_id='bone',xyz_mm=[0,1,2]) for k in labels})
    b = copy.deepcopy(a)
    b['id'] = 'second'
    b['points'][labels[0]]['xyz_mm'] = [1,3,4]
    del b['points'][labels[-1]]
    return a,b


def metadata(labels):
    return dict(version=3,case_id='case',observer_id='op', bone_sources=[dict(id='bone',geometry_sha256=DIGEST)],
        marker_records={k:dict(bone_status='observed',bone_source_id='bone',
                               bone_source_geometry_sha256=DIGEST) for k in labels})


def test_paired_distance_is_not_sigma_or_a_population_statistic():
    a,b = pair()
    r = paired_report(a,b)
    assert r['compared'] == 2 and r['requested'] == 3
    assert r['landmarks']['p'] == dict(status='paired',delta_B_minus_A_mm=[1,2,2],distance_mm=3.)
    assert r['landmarks']['r']['distance_mm'] is None and r['median_across_paired_sites_mm'] == 1.5
    m = metadata(a['labels'])
    c = placement_config(for_uncertainty(r,a['labels'],m,'synthetic scenario'),a['labels'])
    assert c['p']['sigma_mm'] == pytest.approx(3/np.sqrt(6))
    assert c['q']['sigma_mm'] is None and c['r']['sigma_mm'] is None
    with pytest.raises(ValueError,match='Document'):
        for_uncertainty(r,a['labels'],m,' ')
    m['proposal_reviews_at_placement']={'p':{}}
    assert for_uncertainty(r,['p'],m,'test')['placement']['p']['sigma_mm'] is None
    m['bone_sources'][0]['geometry_sha256']='b'*64
    with pytest.raises(ValueError,match='manifest'):
        for_uncertainty(r,['p'],m,'test')


@pytest.mark.parametrize('key,value',[('case_id','other'),('observer_id','other'),('id','first'),
                                      ('sources',{'bone':'b'*64}),('labels',['q','p','r'])])
def test_no_comparison_across_incompatible_sessions(key,value):
    a,b = pair()
    b[key] = value
    with pytest.raises(ValueError):
        paired_report(a,b)


def test_mixed_fragments_tampering_and_coordinates():
    a,b=pair()
    for s in (a,b):
        s['sources']['jaw']='b'*64
    b['points']['p']['source_id']='jaw'
    assert paired_report(a,b)['landmarks']['p']['status']=='different_source'
    r=paired_report(a,b)
    r['landmarks']['q']['distance_mm']=17
    with pytest.raises(ValueError,match='disagrees'):
        for_uncertainty(r,['q'],metadata(['q']),'synthetic')
    b['points']['q']['xyz_mm'][1]=float('nan')
    with pytest.raises(ValueError):
        paired_report(a,b)


def test_a2_consumes_report_only_with_documented_model(model_file,tmp_path):
    from cranio.io_csv import write_marker_csv_v3
    from cranio.backend import GNMBackend
    model=GNMBackend(str(model_file)).load()
    labels=[f'P{i}' for i in range(5)]
    a,b=pair(labels)
    meta=metadata(labels)
    rows=[dict(label=k,vertex=i,placed=1,weight=1.,bone_x=x,bone_y=y,bone_z=z,
               x=x,y=y,z=z+1.,tissue_depth_mm=1,**meta['marker_records'][k]) for i,(k,(x,y,z))
          in enumerate(zip(labels,model.mu))]
    csv=tmp_path/'m.csv'
    write_marker_csv_v3(csv,rows,{k:v for k,v in meta.items() if k!='marker_records'})
    f=tmp_path/'placement_error.json'
    f.write_text(json.dumps(paired_report(a,b)))
    out=tmp_path/'ensemble.json'
    args=['--repeatability',str(f),'--input',str(csv),'--npz',str(model_file),'--output',str(out),
          '--regularization','30','--samples','2','--allow-partial']
    assert main(args)==2 and not out.exists()
    assert main(args+['--paired-iid-isotropic-reason','synthetic independence assumption'])==0
    result=json.loads(out.read_text())
    assert result['placement']['P0']['sigma_mm']==pytest.approx(3/np.sqrt(6))
    assert 'synthetic independence assumption' in result['placement']['P0']['source']
    assert result['input_hashes'][str(f)]==result['repeatability_model']['input_sha256']
    assert result['analysis_status']=='partial_conditional_sensitivity'

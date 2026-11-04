"""Synthetic input ranges and depths below are not anatomical recommendations."""
import copy
import json
import numpy as np
import pytest
from cranio import sensitivity as s, features as f, craniometry as cm


def case_data():
    doc=cm.empty_document('synthetic-sensitivity')
    doc['bone_sources']=[dict(id='jaw',geometry_sha256='a'*64,anatomy='MANDIBLE'),
                         dict(id='skull',geometry_sha256='b'*64,anatomy='CRANIUM')]
    xyz=dict(po_R=[50,0,0],po_L=[-50,0,0],or_L=[-25,60,0],n=[0,60,30],b=[0,0,80],op=[0,-65,10],
             pg=[0,75,0],go_R=[40,0,-20],go_L=[-40,0,-20],co_R=[40,0,40],me=[0,60,-20])
    doc['points']=[dict(code=c,xyz_mm=p,status='observed',definition_reviewed=True,
        source_id='jaw' if c in f.MANDIBULAR else 'skull',source_geometry_sha256=('a' if c in f.MANDIBULAR else 'b')*64,
        definition_text='Synthetic test point',definition_source='Synthetic fixture') for c,p in xyz.items()]
    config=s.empty_config()
    config.update(case_id=doc['case_id'],reviewed=True,source='Synthetic pose scenario protocol',
        moving_sources=[dict(id='jaw',geometry_sha256='a'*64)],pivot_mm=[0,0,0],axes_world=np.eye(3).tolist(),
        translation_mm=[[0,0],[-2,4],[0,0]],rotation_deg=[[0,0],[0,0],[0,0]],samples=4,seed=46)
    fc=config['feature_config']
    fc['mandible_pose']=dict(reviewed=True,source='Synthetic baseline articulation')
    fc['frame_config']=dict(schema_version=1,orbitale='or_L',superior_code='b',midline_codes=['n','b','op'],
                            source='Synthetic frame',placement_error=None)
    for name,kind,points in [('pogonion_projection','anterior_offset',['pg','n']),
            ('bigonial_breadth','distance',['go_R','go_L']),('ramus_height_R','distance',['co_R','go_R'])]:
        fc['features'][name]=dict(reviewed=True,source='Synthetic definition',definition=dict(kind=kind,points=points,space='3d'))
    return doc,config


def test_known_translation_range_and_input_preservation():
    doc,config=case_data();before=copy.deepcopy((doc,config))
    result=s.compute(doc,config)
    assert (doc,config)==before and result==s.compute(doc,config)
    assert result['features']['pogonion_projection']['sampled_range']==[13.,19.]
    assert result['features']['bigonial_breadth']['sampled_range']==[80.,80.]
    assert result['features']['ramus_height_R']['sampled_range']==[60.,60.]
    assert len(result['poses'])==7
    assert all(p==[0,60,30] for p in result['landmarks']['n']['samples_mm'])
    assert result['features']['pogonion_projection']['classification']['status']=='no_thresholds_configured'


def test_threshold_crossing_is_indeterminate():
    doc,config=case_data();fc=config['feature_config']
    definition=fc['features']['pogonion_projection']['definition']
    fc['thresholds']=dict(pogonion_projection=dict(source='Synthetic cut, not clinical',
        definition_sha256=f.definition_hash(definition),units='mm',cuts=[15.],labels=['below','at-or-above']))
    assert s.compute(doc,config)['features']['pogonion_projection']['classification']['label']=='indeterminate'
    fc['thresholds']['pogonion_projection']['cuts']=[20.]
    assert s.compute(doc,config)['features']['pogonion_projection']['classification']['label']=='below'


def add_profile(config):
    config['profile']=dict(reviewed=True,source='Synthetic skin-target profile',segments=[['pg','me']],gap_notes=[],
        points={c:dict(depth_mm=2.,normal_world=[0,1,0],tissue_source='Synthetic offset',reviewed=True,direction='bone_normal')
                for c in ('pg','me')})


def test_profile_normal_rotates_with_bone_and_pivot():
    doc,config=case_data();add_profile(config)
    config.update(translation_mm=[[0,0]]*3,rotation_deg=[[0,0],[0,0],[0,90]],pivot_mm=[0,75,0],samples=0)
    result=s.compute(doc,config)
    assert result['profile']['points']['pg']['samples_mm'][0]==[0.,77.,0.]
    np.testing.assert_allclose(result['profile']['points']['pg']['samples_mm'][1],[-2,75,0],atol=1e-12)
    assert len(result['poses'])==2
    assert result['profile']['points']['pg']['maximum_displacement_mm']==pytest.approx(np.sqrt(8))


def test_axes_and_rotation_order():
    axes=np.array([[0,-1,0],[1,0,0],[0,0,1.]])
    m=s.pose_matrix(dict(translation_mm=[1,0,0],rotation_deg=[90,90,0]),[0,0,0],axes)
    np.testing.assert_allclose(m[:3,3],[0,1,0],atol=1e-14)
    np.testing.assert_allclose(m[:3,:3].T@m[:3,:3],np.eye(3),atol=1e-14)
    np.testing.assert_allclose(m[:3,:3]@axes[:,1],axes[:,0],atol=1e-14)


def test_zero_ranges_one_exact_baseline():
    doc,config=case_data();config['translation_mm']=[[0,0]]*3
    result=s.compute(doc,config)
    assert len(result['poses'])==1
    assert result['features']['pogonion_projection']['sampled_range']==[15.,15.]
    assert result['landmarks']['pg']['samples_mm']==[[0.,75.,0.]]


@pytest.mark.parametrize('change',['missing','review','stale','reconstructed'])
def test_incomplete_anatomy_is_regional(change):
    doc,config=case_data();add_profile(config)
    p=next(p for p in doc['points'] if p['code']=='go_L')
    if change=='missing':p.update(status='missing',xyz_mm=None)
    elif change=='review':p['definition_reviewed']=False
    elif change=='stale':p['source_geometry_sha256']='c'*64
    else:p['status']='reconstructed'
    result=s.compute(doc,config)
    assert result['features']['bigonial_breadth']['sampled_range'] is None
    assert result['features']['pogonion_projection']['sampled_range']==[13.,19.]
    assert 'go_L' in result['unavailable_landmarks']


def test_failed_scenario_is_not_filtered():
    doc,config=case_data();config['translation_mm']=[[0,0],[-15,0],[0,0]];config['samples']=0
    next(p for p in doc['points'] if p['code']=='n')['xyz_mm']=[0,60,0]
    config['feature_config']['features']['facial_angle']=dict(reviewed=True,source='Synthetic degeneracy',
        definition=dict(kind='angle',points=['pg','n','me'],space='3d'))
    row=s.compute(doc,config)['features']['facial_angle']
    assert row['status']=='failed' and row['sampled_range'] is None
    assert len(row['failures'])==1 and None in row['values']


@pytest.mark.parametrize('key,value',[('reviewed',False),('case_id',None),('samples',None),('samples',True),
    ('seed',-1),('translation_mm',[[1,2],[0,0],[0,0]]),('rotation_deg',[[0,float('nan')],[0,0],[0,0]]),
    ('axes_world',[[-1,0,0],[0,1,0],[0,0,1]]),('pivot_mm',[0,float('inf'),0]),('source','TODO(verify-source)')])
def test_invalid_configuration(key,value):
    doc,config=case_data();config[key]=value
    with pytest.raises((ValueError,TypeError)):s.compute(doc,config)


@pytest.mark.parametrize('change',['case','hash','anatomy','cranial_code','record','placement'])
def test_evidence_and_scope_gates(change):
    doc,config=case_data()
    if change=='case':doc['case_id']='other'
    elif change=='hash':config['moving_sources'][0]['geometry_sha256']='c'*64
    elif change=='anatomy':doc['bone_sources'][0]['anatomy']='MIXED'
    elif change=='cranial_code':next(p for p in doc['points'] if p['code']=='n')['source_id']='jaw'
    elif change=='record':doc['mandible_pose']=dict(status='stale')
    else:config['feature_config']['uncertainty']=dict(samples=2,seed=0,placement={})
    with pytest.raises(ValueError):s.compute(doc,config)


def test_profile_missing_bone_or_depth_is_not_imputed():
    doc,config=case_data();add_profile(config)
    config['profile']['points']['pg']['depth_mm']=None
    with pytest.raises(ValueError):s.compute(doc,config)
    config['profile']['points']['pg']['depth_mm']=2.
    next(p for p in doc['points'] if p['code']=='me').update(xyz_mm=None,status='missing')
    row=s.compute(doc,config)['profile']['points']['me']
    assert row['status']=='unavailable' and all(v is None for v in row['samples_mm'])


def test_cli_reproducibility_and_output_safety(tmp_path):
    doc,config=case_data();inp,cfg=tmp_path/'bones.json',tmp_path/'config.json'
    inp.write_text(json.dumps(doc));cfg.write_text(json.dumps(config))
    blank=tmp_path/'blank.json'
    assert s.main(['template','--output',str(blank)])==0
    assert json.loads(blank.read_text())==s.empty_config()
    for name in ('a','b'):
        assert s.main(['compute','--input',str(inp),'--config',str(cfg),'--output',str(tmp_path/(name+'.json'))])==0
    assert (tmp_path/'a.json').read_bytes()==(tmp_path/'b.json').read_bytes()
    for output in (inp,tmp_path/'a.json'):
        before=output.read_bytes()
        with pytest.raises(SystemExit):s.main(['compute','--input',str(inp),'--config',str(cfg),'--output',str(output)])
        assert output.read_bytes()==before


def test_signed_angle_branch_crossing_withholds_range():
    doc,config=case_data()
    config.update(translation_mm=[[0,0]]*3,rotation_deg=[[-2,2],[0,0],[0,0]],pivot_mm=[0,60,30],samples=0)
    for code,xyz,sid,digest in [('ss',[0,61,30],'skull','b'*64),
        ('sm',[0,60+np.cos(np.deg2rad(179)),30+np.sin(np.deg2rad(179))],'jaw','a'*64)]:
        doc['points'].append(dict(code=code,xyz_mm=xyz,status='observed',definition_reviewed=True,
            source_id=sid,source_geometry_sha256=digest,definition_text='Synthetic reference',definition_source='Synthetic test'))
    fc=config['feature_config']
    spec=dict(kind='signed_angle',points=['ss','n','sm'],space='sagittal')
    fc['features']['anb_angle']=dict(definition=spec,source='Synthetic branch test',reviewed=True)
    fc['thresholds']=dict(anb_angle=dict(source='Synthetic threshold',definition_sha256=f.definition_hash(spec),
        units='deg',cuts=[0],labels=['negative','nonnegative']))
    result=s.compute(doc,config)['features']['anb_angle']
    assert result['status']=='failed' and result['sampled_range'] is None
    assert any('branch crossed' in r['reason'] for r in result['failures'])
    assert result['classification']['status']=='indeterminate'


@pytest.mark.parametrize('document',[[],None,42])
def test_nonobject_document_is_actionable(document):
    _,config=case_data()
    with pytest.raises(ValueError,match='JSON object'):s.compute(document,config)


def test_rigid_coordinate_equivariance():
    doc,config=case_data();add_profile(config)
    config['rotation_deg']=[[-5,5],[0,0],[0,0]]
    first=s.compute(doc,config)
    q=np.array([[0,-1,0],[1,0,0],[0,0,1.]])
    t=np.array([100.,20,30])
    for row in doc['points']:row['xyz_mm']=(q@row['xyz_mm']+t).tolist()
    config['axes_world']=q.tolist();config['pivot_mm']=(q@config['pivot_mm']+t).tolist()
    for row in config['profile']['points'].values():row['normal_world']=(q@row['normal_world']).tolist()
    second=s.compute(doc,config)
    for name in ('pogonion_projection','bigonial_breadth','ramus_height_R'):
        np.testing.assert_allclose(first['features'][name]['values'],second['features'][name]['values'],atol=1e-12)
    expected=np.asarray(first['profile']['points']['pg']['samples_mm'])@q.T+t
    np.testing.assert_allclose(second['profile']['points']['pg']['samples_mm'],expected,atol=1e-12)


def test_rigid_invariant_at_threshold_does_not_cross_due_to_roundoff():
    doc,config=case_data();config['rotation_deg']=[[-40,40]]*3
    fc=config['feature_config'];definition=fc['features']['bigonial_breadth']['definition']
    fc['thresholds']=dict(bigonial_breadth=dict(source='Synthetic exact cut, not clinical',
        definition_sha256=f.definition_hash(definition),units='mm',cuts=[80],labels=['below','at-or-above']))
    row=s.compute(doc,config)['features']['bigonial_breadth']
    assert row['sampled_range']==[80.,80.]
    assert row['classification']['label']=='at-or-above'

import copy

import pytest

from cranio import scenarios as guide


def rules(**kw):
    return dict(dict(case_id='case',scenario='partial',source='Synthetic regression fixture',
                exclude=['Nasion'],weights={'Gonion_St':.4},required_policy_ids=['case-count']),**kw)


def report(spec):
    return dict(marker_metadata=dict(guided_scenario=spec,case_id='case',
            bone_sources=[dict(id='jaw',geometry_sha256='a'*64,anatomy='MANDIBLE')],
            marker_records={'Gonion_St':dict(use_for_fit=True,bone_status='observed',bone_source_id='jaw',
                                              bone_source_geometry_sha256='a'*64,csv_base_weight=.4)}),
            landmarks=[dict(label='Gonion_St',weight=.4)])


def test_partial_does_not_infer_side_and_manual_exclusion_wins():
    spec=guide.configure('partial','case','Right vault, nasal bone, left mandibular fragment',rules())
    assert guide.decision(spec,'Gonion_St','observed',True,.7)[:2]==(True,.4)
    assert not guide.decision(spec,'Gonion_Dr','reconstructed',True,.7)[0]
    assert not guide.decision(spec,'Gonion_St','observed',False,.7)[0]
    assert not guide.decision(spec,'Nasion','observed',True,1.)[0]
    assert guide.validate(copy.deepcopy(spec))==spec
    before=copy.deepcopy(spec)
    checks=[dict(id=k,status='pass') for k in spec['required_checks']]
    assert all(row['status']=='pass' for row in guide.assessment(report(spec),checks))
    for state,want in [('warn','block'),('block','block'),('not_assessed','not_assessed')]:
        checks[-1]['status']=state
        assert guide.assessment(report(spec),checks)[-1]['status']==want
    assert before==spec


@pytest.mark.parametrize('override',[dict(weights={'Unknown':.2}),dict(case_id='other'),dict(weights={'Nasion':.5}),
                                    dict(weights={'Gonion_St':True}),dict(source='TODO'),dict(required_policy_ids=['a','a'])])
def test_reject_invalid_customizations(override):
    with pytest.raises(ValueError):
        guide.configure('partial','case','',rules(**override))


def test_missing_or_contradictory_metadata_never_green():
    spec=guide.configure('no_mandible','case')
    r=report(spec)
    def rows():
        return {x['id']:x['status'] for x in guide.assessment(r,[])}
    assert rows()['scenario:review']=='block' and rows()['scenario:marker_evidence']=='block'
    assert rows()['scenario:absent_mandible']=='block'
    r['marker_metadata']['bone_sources'][0]['anatomy']='MIXED'
    assert rows()['scenario:absent_mandible']=='not_assessed'
    r['marker_metadata']['guided_scenario']['excluded_catalogue_labels']=[]
    with pytest.raises(ValueError):
        rows()


def test_geometry_or_weight_changed_holds_saved_assessment():
    spec=guide.configure('partial','case','Synthetic',rules())
    r=report(spec)
    row=r['marker_metadata']['marker_records']['Gonion_St']
    for key,value in [('bone_source_geometry_sha256','b'*64),('csv_base_weight',1.),('bone_status','inferred')]:
        before=row[key]
        row[key]=value
        assert next(x for x in guide.assessment(r,[]) if x['id']=='scenario:marker_evidence')['status']=='block'
        row[key]=before

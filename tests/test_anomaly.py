"""Synthetic distances and decision policies; no anatomical reference values."""
import json
from pathlib import Path

import numpy as np
import pytest

from cranio import anomaly, craniometry as cm
from cranio.backend import GNMBackend
from cranio.config import PipelineConfig
from cranio.io_csv import write_marker_csv_v3
from cranio.pipeline import run_pipeline
from cranio.record import compile_record
from cranio.validation import sha256_file

CASE = 'geometry-fixture'
DIGEST = 'f' * 64


def inputs():
    doc = cm.empty_document(CASE)
    sources = [dict(id='scan', geometry_sha256=DIGEST)]
    xyz = dict(eu_R=[2,0,0], eu_L=[-2,0,0], g=[0,3,0], op=[0,-3,0], b=[0,0,3],
               id=[0,3,-2], me=[0,3,-4])
    doc.update(points=[dict(code=k, xyz_mm=v, status='observed', definition_reviewed=True,
                            definition_text='Synthetic site', definition_source='Fixture',
                            source_id='scan', source_geometry_sha256=DIGEST) for k,v in xyz.items()], bone_sources=sources)
    meta = dict(case_id=CASE, version=3, bone_sources=sources, mandible_articulation_reviewed=True)
    return doc, meta


def rule(key, low=None, high=None, action='flag', labels=(), factor=None):
    return dict(units=anomaly.SCORES[key][1], low=low, high=high, source='Synthetic test fixture only',
                action=action, labels=list(labels), factor=factor)


def test_analytic_distortions_pose_rotation_partial_and_stale():
    doc, meta = inputs()
    p = anomaly.template(CASE)
    def scores():
        return anomaly.screen(p, meta, doc, [], [])[2]['scores']
    before = scores()
    assert before['vault_breadth_length']['score'] == pytest.approx(2/3)
    assert before['vault_side_difference']['score'] == 0
    assert before['axis_obliquity']['flag'] is None
    p['rules'] = {k: rule(k, high=v) for k,v in [('axis_obliquity', .1), ('jaw_transverse_offset', .5),
                                                     ('vault_side_difference', .1)]}
    p['rules']['vault_breadth_length'] = rule('vault_breadth_length', low=.5)
    assert all(scores()[k]['flag'] is False for k in p['rules'])
    # Shear x by y, compress original x, displace jaw. Rotate and translate everything.
    for row in doc['points']:
        x,y,z = row['xyz_mm']
        new_x = x/2 + y/2 + (1 if row['code'] in ('me','id','b') else 0)
        row['xyz_mm'] = [5-y, 12+new_x, 2+z]
    after = scores()
    for k in p['rules']:
        assert after[k]['flag'] is True
    assert after['axis_obliquity']['score'] == pytest.approx(1/np.sqrt(5))
    assert after['jaw_transverse_offset']['score'] == pytest.approx(2.5)
    assert after['anterior_mandible_chord']['score'] == pytest.approx(2)
    meta['mandible_articulation_reviewed'] = False
    assert scores()['jaw_transverse_offset']['status'] == 'not_assessed'
    doc['points'][0]['status'] = 'reconstructed'
    assert scores()['vault_breadth_length']['score'] is None
    assert scores()['anterior_mandible_chord']['score'] == 2
    meta['bone_sources'] = [dict(id='scan',geometry_sha256='a'*64)]
    assert all(r['flag'] is None and r['score'] is None for r in scores().values())


def test_partial_dentition_uses_inspected_sites_and_current_source():
    doc,meta = inputs()
    obs = dict(source_id='scan', source_geometry_sha256=DIGEST, observation_source='Synthetic inventory',
               sites={'A':'absent','B':'present','C':'unknown'})
    meta['case_metadata'] = dict(case_id=CASE,dentition_observation=obs)
    p = anomaly.template(CASE)
    p['rules']['absent_reviewed_sites'] = rule('absent_reviewed_sites',high=.5)
    def result():
        return anomaly.screen(p,meta,doc,[],[])[2]['scores']['absent_reviewed_sites']
    assert result()['score'] == .5 and result()['flag'] is False
    obs['sites']['B'] = 'unknown'
    assert result()['flag'] is True
    obs['sites']['A'] = 'unknown'
    assert result()['score'] is None
    obs['sites']['A'] = 'absent'
    obs['source_geometry_sha256'] = 'b'*64
    assert result()['score'] is None
    meta['case_metadata']['case_id'] = 'another-case'
    with pytest.raises(ValueError, match='same marker case'):
        result()


def test_degenerate_and_unconfigured_are_not_negative_results():
    doc, meta = inputs()
    doc['points'][0]['xyz_mm'] = doc['points'][1]['xyz_mm']
    p=anomaly.template(CASE)
    audit=anomaly.screen(p,meta,doc,[],[])[2]
    assert audit['scores']['axis_obliquity']['status']=='not_assessed'
    assert audit['scores']['anterior_mandible_chord']['status']=='no_thresholds_configured'
    assert 'No thresholds configured' in anomaly.report_text(audit)
    assert all(v['score'] is None for v in anomaly.screen(p,meta,None,[],[])[2]['scores'].values())


@pytest.mark.parametrize('edit', [dict(high=float('nan')),dict(high=True),dict(source='TODO(verify-source)'),
                                  dict(units='mm'),dict(action='reduce',labels=['X'],factor=2),
                                  dict(action='exclude',labels=['unknown']),dict(low=2,high=1)])
def test_reject_invalid_rules(edit):
    doc, meta = inputs()
    p=anomaly.template(CASE)
    r=rule('axis_obliquity', high=.2)
    r.update(edit)
    p['rules']['axis_obliquity']=r
    with pytest.raises(ValueError):
        anomaly.screen(p, meta, doc, [], ['X'])


def test_fit_actions_reports_and_default_mesh_parity(tmp_path, model_file):
    doc, meta = inputs()
    model=GNMBackend(str(model_file)).load()
    csv=tmp_path/'markers.csv'
    meta.update(craniometry=doc)
    rows=[dict(label=f'P{i}',vertex=i,placed=1,weight=.8, x=x,y=y,z=z) for i,(x,y,z) in enumerate(model.mu[:7])]
    write_marker_csv_v3(csv,rows,meta)
    cfg=PipelineConfig(input=str(csv),npz=str(model_file),output=str(tmp_path/'base.obj'),regularization='20')
    assert run_pipeline(cfg)==0
    ref=Path(cfg.output).read_bytes()
    path=tmp_path/'policy.json'
    p=anomaly.template(CASE)
    path.write_text(json.dumps(p))
    def run(name):
        c=PipelineConfig(input=str(csv),npz=str(model_file),output=str(tmp_path/(name+'.obj')),
                         regularization='20',anomaly_policy=str(path))
        assert run_pipeline(c)==0
        return c,json.loads(Path(c.output_json).read_text())
    same, report=run('empty')
    assert Path(same.output).read_bytes()==ref
    assert 'No thresholds configured' in Path(same.output_stats).read_text()
    p['rules']['vault_breadth_length']=rule('vault_breadth_length',high=.5,action='reduce',labels=['P0','P1'],factor=.5)
    p['rules']['axis_obliquity']=rule('axis_obliquity',low=.25,action='exclude',labels=['P1'])
    p['rules']['anterior_mandible_chord']=rule('anterior_mandible_chord',low=3,action='reduce',labels=['P0'],factor=.75)
    path.write_text(json.dumps(p))
    before=csv.read_bytes()
    c,report=run('action')
    assert report['inputs']['anomaly_policy']['sha256']==sha256_file(path)
    assert 'P1' not in [r['label'] for r in report['landmarks']]
    assert report['landmarks'][0]['weight']==.4
    assert len(report['landmarks'])==6
    assert report['marker_metadata']['anomaly_screen']['changes']['P1']['after'] is None
    assert 'P1: weight 0.8 -> excluded' in Path(c.output_stats).read_text()
    assert compile_record(report)['run']['marker_metadata']['anomaly_screen'] == report['marker_metadata']['anomaly_screen']
    assert csv.read_bytes()==before

def test_reject_case_mismatch_and_undocumented_source():
    doc, meta = inputs()
    p = anomaly.template('wrong')
    with pytest.raises(ValueError, match='bound'):
        anomaly.screen(p, meta, doc, [], [])
    p['case_id'] = CASE
    p['rules']['axis_obliquity'] = dict(rule('axis_obliquity', high=.5), source=' legacy-unvalidated ')
    with pytest.raises(ValueError, match='sourced'):
        anomaly.screen(p, meta, doc, [], [])

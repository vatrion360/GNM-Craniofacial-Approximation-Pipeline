"""Opt-in marker workflow configuration; no inferred anatomical weights or cutoffs."""
from functools import lru_cache
import hashlib
from pathlib import Path
import re

from .landmarks import LANDMARK_INFO, MANDIBULAR_LANDMARKS
from .tissue import _json

PROFILE_IDS = ('complete','partial','no_mandible','deformed')
CUSTOM = {'case_id','scenario','exclude','weights','required_policy_ids','source'}


@lru_cache(maxsize=1)
def catalog():
    raw = Path(__file__).with_name('data').joinpath('scenarios.json').read_bytes()
    doc = _json(raw.decode())
    if set(doc['profiles']) != set(PROFILE_IDS):
        raise ValueError('Invalid bundled scenario catalogue')
    return doc, hashlib.sha256(raw).hexdigest()


def _text(s):
    return isinstance(s,str) and bool(s.strip()) and s.strip().lower() not in {
        'unknown','unspecified','todo','todo(verify-source)','none','null','[de completat]'}


def _labels(seq):
    return isinstance(seq,list) and all(_text(k) and k.strip()==k for k in seq) and len(seq)==len(set(seq))


def configure(profile,case_id,note='',custom=None):
    doc,digest = catalog()
    if not isinstance(profile,str) or profile not in PROFILE_IDS or not _text(case_id) or not isinstance(note,str):
        raise ValueError('Select a recognized scenario and a nonempty case ID')
    policy = doc['profiles'][profile]
    if custom is not None:
        if not isinstance(custom,dict) or set(custom)!=CUSTOM:
            raise ValueError('Invalid scenario customization fields')
        if custom['case_id']!=case_id or custom['scenario']!=profile or not _text(custom['source']):
            raise ValueError('Customization requires matching case, scenario and documented source')
        if not _labels(custom['exclude']) or not _labels(custom['required_policy_ids']):
            raise ValueError('Exclusions and required policy IDs must be lists of distinct names')
        if any(k.startswith(('builtin:','scenario:')) or k=='absent_mandible' for k in custom['required_policy_ids']):
            raise ValueError('Use custom A5 rule IDs without reserved prefixes')
        w = custom['weights']
        if not isinstance(w,dict) or any(type(v) not in (float,int) or not 0 < v <= 1 for v in w.values()):
            raise ValueError('Each configured absolute marker weight must be in (0,1]')
        exclusions=set(custom['exclude']) | (MANDIBULAR_LANDMARKS if policy['exclude_mandible'] else set())
        if (set(w)|set(custom['exclude']))-LANDMARK_INFO.keys() or set(w)&exclusions:
            raise ValueError('Unknown marker or weight configured for excluded marker')
    return dict(schema='gnm.guided-case.v1',scenario=profile,case_id=case_id,note=note.strip(),
                catalog_revision=doc['revision'],catalog_sha256=digest,custom=custom,weight_status=policy['weight_status'],
                required_checks=policy['required_checks']+(custom or {}).get('required_policy_ids',[]),
                excluded_catalogue_labels=sorted(MANDIBULAR_LANDMARKS) if policy['exclude_mandible'] else [])


def validate(spec):
    if not isinstance(spec,dict) or configure(spec.get('scenario'),spec.get('case_id'),
            spec.get('note'),spec.get('custom')) != spec:
        raise ValueError('Scenario snapshot differs from the supported catalogue or schema')
    return spec


def decision(spec,label,bone_status,included,weight):
    """Effective marker only. Never re-enable a manually excluded site."""
    profile=catalog()[0]['profiles'][spec['scenario']]
    custom=spec['custom'] or {}
    if not included:
        return False,weight,'manually excluded'
    if profile['exclude_mandible'] and label in MANDIBULAR_LANDMARKS:
        return False,weight,'mandibular site'
    if label in custom.get('exclude',[]):
        return False,weight,'case exclusion'
    if bone_status!='observed':
        return False,weight,'not recorded as observed bone'
    return True,custom.get('weights',{}).get(label,profile['weights'].get(label,weight)),'included'


def assessment(report,checks):
    """Compare actual fitted markers with the frozen scenario and source manifest."""
    meta=report['marker_metadata']
    spec=validate(meta['guided_scenario'])
    profile=catalog()[0]['profiles'][spec['scenario']]
    def row(key,status,reason,observed=None):
        return dict(id='scenario:'+key,status=status,reason=reason,observed=observed,
                    provenance='guided_case_workflow')
    out=[row('review','pass' if _text(spec['note']) and spec['case_id']==meta.get('case_id') else 'block',
             'Operator case note and matching case ID required; not independent verification',
             dict(scenario=spec['scenario'],note=spec['note']))]
    sources=meta.get('bone_sources')
    valid=isinstance(sources,list) and bool(sources) and all(isinstance(s,dict) and _text(s.get('id'))
                and isinstance(s.get('geometry_sha256'),str) and re.fullmatch('[0-9a-f]{64}',s['geometry_sha256'])
                for s in sources)
    registry={s['id']:s for s in sources} if valid else {}
    valid=bool(valid and len(registry)==len(sources))
    issues=[]
    for fit in report['landmarks']:
        label=fit['label']
        record=meta.get('marker_records',{}).get(label,{})
        uid=record.get('bone_source_id')
        source=registry.get(uid) if _text(uid) else None
        permitted=decision(spec,label,record.get('bone_status'),record.get('use_for_fit') is True,fit['weight'])[0]
        expected=(spec['custom'] or {}).get('weights',{}).get(label)
        if (not valid or not source or not permitted or record.get('bone_source_geometry_sha256')!=source['geometry_sha256']
                or (expected is not None and expected!=record.get('csv_base_weight'))):
            issues.append(label)
    out.append(row('marker_evidence','block' if issues else 'pass',
                   'Actual fitted sites must be permitted and bound to observed geometry in this report',issues))
    states={r['id']:r['status'] for r in checks}
    if any(key.startswith('scenario:') for key in states):
        raise ValueError('Use A5 rule IDs without the scenario: prefix for guided cases')
    for name in profile['required_checks']+(spec['custom'] or {}).get('required_policy_ids',[]):
        if name=='absent_mandible' and name in profile['required_checks']:
            types=[s.get('anatomy') for s in registry.values()]
            status=('block' if 'MANDIBLE' in types else 'pass' if valid and all(t in ('CRANIUM','NASAL') for t in types)
                    else 'not_assessed')
            out.append(row(name,status,'Enabled source classifications must support the no-mandible declaration',types))
        else:
            status=states.get(name,'not_assessed')
            out.append(row('requires:'+name,'pass' if status=='pass' else 'not_assessed' if status=='not_assessed' else 'block',
                'This scenario requires a pass; a warning, failure or missing finding cannot satisfy it',status))
    return out

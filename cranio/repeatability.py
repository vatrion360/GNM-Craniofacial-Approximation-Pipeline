"""Paired, within-observer manual bone placements in one unchanged world-mm frame."""
import hashlib
import json
import re

import numpy as np

from .validation import finite_array

SCHEMA = 'gnm.paired-bone-placement.v1'
FIELDS = {'id','case_id','observer_id','sources','labels','points'}
NOTE = ('One paired observation per compared site. Distances are not per-coordinate SDs, '
        'anatomical accuracy, population repeatability or CT validation.')


def _text(s):
    return isinstance(s, str) and bool(s.strip())


def _session(s):
    if not isinstance(s, dict) or set(s) != FIELDS or not all(_text(s[k]) for k in ('id','case_id','observer_id')):
        raise ValueError('A session requires an ID, case, observer, sources, labels and points')
    labels, sources, points = s['labels'], s['sources'], s['points']
    if (not isinstance(labels,list) or not labels or not all(_text(k) for k in labels)
            or len(set(labels)) != len(labels)):
        raise ValueError('The label list must be nonempty and unique')
    if (not isinstance(sources,dict) or not sources or any(not _text(k) or not isinstance(v,str)
            or not re.fullmatch('[0-9a-f]{64}',v) for k,v in sources.items())):
        raise ValueError('Missing source ID or geometry SHA-256')
    if not isinstance(points,dict) or not points or not set(points) <= set(labels):
        raise ValueError('Session has no measurements or includes unknown labels')
    for k,p in points.items():
        if (not isinstance(p,dict) or set(p) != {'source_id','xyz_mm'} or not _text(p['source_id'])
                or p['source_id'] not in sources):
            raise ValueError('Invalid observed source for '+k)
        xyz = p['xyz_mm']
        if not isinstance(xyz,list) or len(xyz)!=3 or any(type(x) not in (int,float) for x in xyz):
            raise ValueError('Expected three numeric world coordinates for '+k)
        finite_array(xyz,k,(3,))


def paired_report(a,b):
    """B−A and Euclidean norm for same-source pairs. Never register or impute."""
    for s in (a,b):
        _session(s)
    if a['id'] == b['id']:
        raise ValueError('Two distinct capture sessions are required')
    for k in ('case_id','observer_id','sources','labels'):
        if a[k] != b[k]:
            raise ValueError('Session mismatch: '+k)
    rows, distances = {}, []
    for k in a['labels']:
        p,q = a['points'].get(k), b['points'].get(k)
        reason = ('missing_both' if not p and not q else 'missing_A' if not p else
                  'missing_B' if not q else 'different_source' if p['source_id'] != q['source_id'] else None)
        row = dict(status=reason or 'paired', delta_B_minus_A_mm=None, distance_mm=None)
        if reason is None:
            delta = np.subtract(q['xyz_mm'],p['xyz_mm'],dtype=float)
            distance = float(finite_array(np.linalg.norm(delta),k+' distance'))
            row.update(delta_B_minus_A_mm=delta.tolist(),distance_mm=distance)
            distances.append(distance)
        rows[k] = row
    return dict(schema=SCHEMA, units='world_mm', sessions=dict(A=a,B=b), landmarks=rows,
                compared=len(distances), requested=len(rows),
                median_across_paired_sites_mm=float(np.median(distances)) if distances else None,
                interpretation=NOTE)


def for_uncertainty(document, labels, metadata, rationale):
    """Explicit same-case sensitivity model; never treat radial distance as sigma."""
    if not _text(rationale):
        raise ValueError('Document why independent isotropic equal-variance placement is a suitable sensitivity scenario')
    if not isinstance(document,dict) or document.get('schema') != SCHEMA:
        raise ValueError('Expected a B2.4 paired placement report')
    sessions = document.get('sessions')
    if not isinstance(sessions,dict) or set(sessions) != {'A','B'}:
        raise ValueError('Report must contain sessions A and B')
    result = paired_report(sessions['A'],sessions['B'])
    if result != document:
        raise ValueError('Repeatability report disagrees with its measurements')
    a = sessions['A']
    if (metadata.get('version') != 3 or metadata.get('case_id') != a['case_id']
            or metadata.get('observer_id') != a['observer_id']):
        raise ValueError('Repeatability requires matching v3 case and observer IDs')
    manifest = metadata.get('bone_sources')
    if not isinstance(manifest,list) or not all(isinstance(r,dict) and _text(r.get('id')) for r in manifest):
        raise ValueError('Repeatability requires the exported observed bone source manifest')
    registered = {r['id']:r.get('geometry_sha256') for r in manifest}
    if len(registered) != len(manifest) or any(registered.get(uid) != digest for uid,digest in a['sources'].items()):
        raise ValueError('CSV source manifest differs from repeat-session bone geometry')
    key = hashlib.sha256(json.dumps(document,sort_keys=True,allow_nan=False).encode()).hexdigest()
    placement = {}
    for label in labels:
        row = result['landmarks'].get(label)
        reason = row['status'] if row else 'not measured'
        sd = None
        if reason == 'paired':
            record = metadata.get('marker_records',{}).get(label,{})
            uid = a['points'][label]['source_id']
            if (record.get('bone_source_id') != uid or record.get('bone_source_geometry_sha256') != a['sources'][uid]):
                raise ValueError(label+': marker and repeat-session bone source or geometry differ')
            if (record.get('bone_status') != 'observed' or label in metadata.get('proposal_reviews_at_placement',{})):
                reason = 'not an unassisted observed placement'
            elif row['distance_mm'] == 0.:
                reason = 'coincident repeats do not establish zero uncertainty'
            else:
                sd = float(row['distance_mm']/np.sqrt(6.))
                reason = 'one pair; sigma=distance/sqrt(6) under stipulated independent isotropic errors'
        placement[label] = dict(sigma_mm=sd,source=f'B2.4 {key}; {reason}. Scenario: {rationale.strip()}')
    return dict(schema_version=1,placement=placement)

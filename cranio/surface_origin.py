"""Face-origin receipts and explicit sensitivity factors; no anatomical defaults."""
import hashlib
import math
import re

CODES = {'original':1,'mirrored':2,'donor':3}
ATTRIBUTE = 'gnm_bone_origin'
RECEIPT = 'gnm_face_origin_at_placement'


def _str(v):
    return isinstance(v,str) and bool(v.strip()) and v.strip().lower() not in {
        'unknown','unspecified','todo','none','null','todo(verify-source)'}


def digest(text):
    return hashlib.sha256(text.encode('utf8')).hexdigest()


def policy(p):
    if (not isinstance(p,dict) or set(p)!={'schema','case_id','source','status','mirrored','donor'}
            or p['schema']!='gnm.origin-factors.v1' or p['status']!='calibrate'
            or not all(_str(p[k]) for k in ('case_id','source'))):
        raise ValueError('Provide a case-bound gnm.origin-factors.v1 policy, source and status=calibrate')
    for kind in ('mirrored','donor'):
        row=p[kind]
        if not isinstance(row,dict) or set(row)!={'weight_factor','placement_sd_factor'}:
            raise ValueError(kind+': provide both factors or null')
        for k,v in row.items():
            if v is None:
                continue
            if type(v) not in (float,int) or not math.isfinite(v) or not (0<v<=1 if k=='weight_factor' else v>=1):
                raise ValueError(kind+': require a weight factor in (0,1] or a placement SD factor >=1')
    return p


def validate_receipt(r,record):
    if (not isinstance(r,dict) or set(r)!={'origin','source_id','geometry_sha256','lineage_sha256',
            'polygon','point_mm'} or not isinstance(r['origin'],str) or r['origin'] not in CODES
            or not _str(r['source_id']) or type(r['polygon']) is not int or r['polygon']<0
            or any(not isinstance(r[k],str) or not re.fullmatch('[0-9a-f]{64}',r[k])
                   for k in ('geometry_sha256','lineage_sha256'))):
        raise ValueError('Invalid face provenance receipt')
    xyz=r['point_mm']
    if not isinstance(xyz,list) or len(xyz)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) for x in xyz):
        raise ValueError('Invalid face receipt point')
    if (record.get('bone_source_id')!=r['source_id'] or record.get('bone_source_geometry_sha256')!=r['geometry_sha256']
            or record.get('bone_xyz_mm')!=xyz or record.get('bone_status')!=('observed' if r['origin']=='original' else 'reconstructed')):
        raise ValueError('Face provenance disagrees with the marker/source; re-place the marker')
    return r


def apply_sd(config,metadata):
    """Input config is detached by placement_config. Only a frozen case policy opts in."""
    if 'face_origin_policy' not in metadata:
        return config
    p=policy(metadata['face_origin_policy'])
    if p['case_id']!=metadata.get('case_id'):
        raise ValueError('Face-origin policy case ID mismatch')
    for label,row in config.items():
        record=metadata.get('marker_records',{}).get(label,{})
        r=validate_receipt(record.get('face_origin'),record)
        kind=r['origin']
        if kind=='original':
            continue
        f=p[kind]['placement_sd_factor']
        sd=row['sigma_mm']
        if sd is not None and f is not None:
            sd=float(sd*f)
            if not math.isfinite(sd):
                raise ValueError('Nonfinite adjusted placement SD')
        else:
            sd=None
        row.update(sigma_mm=sd,source=f"{row['source'] or 'No baseline placement SD'}; {kind} placement SD factor: {f}; "
                   f"operator sensitivity policy: {p['source']} (uncalibrated).")
    return config

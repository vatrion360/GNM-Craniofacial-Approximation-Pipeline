"""Freeze case meshes and summarize manually evaluated world-mm distances. No CT processing."""
import argparse
import csv
import hashlib
import io
import math
from pathlib import Path, PureWindowsPath
import re
import shutil
import tempfile

import numpy as np

from .anomaly import documented
from .record import canonical_bytes, validate_report
from .tissue import _json
from .validation import sha256_file

ARMS = ('blind_ct', 'paired_ct_unblinded', 'ct_conditioned', 'historical')
STAGES = ('blender_live', 'blender_finalize', 'offline_statistical', 'offline_final', 'baseline')
ACCESS = dict(blind_ct='withheld', paired_ct_unblinded='seen', ct_conditioned='used', historical='no_reference')
SCOPE = ('Exploratory descriptive results. N counts subjects, not vertices or sessions. '
         'No independent validation, acceptance threshold or calibration is inferred.')


def _keys(d, keys, label):
    if not isinstance(d, dict) or set(d) != set(keys.split()):
        raise ValueError(label+': unexpected or missing fields')


def _ids(items, label, empty=False):
    if (not isinstance(items,list) or (not empty and not items)
            or any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',v)
                   or PureWindowsPath(v).is_reserved() for v in items)
            or len(set(v.lower() for v in items)) != len(items)):
        raise ValueError(label+': expected unique portable IDs')


def _file(root, rel):
    if (not isinstance(rel,str) or not rel or PureWindowsPath(rel).anchor
            or '\\' in rel or ':' in rel or '..' in Path(rel).parts):
        raise ValueError('Expected a relative file within the case/study: '+str(rel))
    root = Path(root).resolve()
    p = (root / rel).resolve()
    if not p.is_relative_to(root) or not p.is_file():
        raise ValueError('Missing file or path escapes case/study: '+rel)
    return p


def _pin(root, rel):
    p=_file(root,rel)
    if not p.stat().st_size:
        raise ValueError('Empty evidence file: '+rel)
    return dict(file=rel,sha256=sha256_file(p))


def _mesh(root, rel):
    if not isinstance(rel,str) or Path(rel).suffix.lower() not in ('.stl','.obj','.ply'):
        raise ValueError('Use a saved STL, OBJ or PLY mesh, not DICOM or a measurement file')
    return _pin(root,rel)


def _jsonfile(path):
    return _json(path.read_text(encoding='utf-8-sig'))


def _publish(folder, files):
    """Never use an existing output directory. Publish only complete, new files."""
    folder=Path(folder)
    if folder.exists() or folder.is_symlink():
        raise ValueError('Choose a new output directory: '+str(folder))
    folder.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder.parent) as tmp:
        staging=Path(tmp)/'package'
        staging.mkdir()
        for name,data in files.items():
            p=staging/name
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(data)
        # mkdir reserves the destination even when two users choose the same path.
        folder.mkdir()
        try:
            for p in staging.iterdir():
                p.rename(folder/p.name)
        except BaseException:
            shutil.rmtree(folder)
            raise


def initialize(root, arm, subjects, runs, outcomes):
    for items,label in [(subjects,'subjects'),(runs,'runs'),(outcomes,'outcomes')]:
        _ids(items,label,empty=(label=='outcomes' and arm=='historical'))
    if arm not in ARMS or (arm=='historical' and outcomes):
        raise ValueError('Historical studies have no CT outcomes')
    study=dict(schema='gnm.manual-study.v1',units='mm',arm=arm,subjects=subjects,protocol_file=None,
               runs={r:dict(stage=None,observer=None,session=None) for r in runs},
               outcomes={o:dict(quantity=None,direction=None,definition=None,sites=None) for o in outcomes})
    files={'study.json':canonical_bytes(study)}
    for case in subjects:
        doc=dict(case_id=case,skull='skull.stl',strata={},runs={
            r:dict(mesh=None,fit_report=None,reason=None,reference_access=None) for r in runs})
        files[case+'/case.json']=canonical_bytes(doc)
    _publish(root,files)


def _folder(root, subject):
    path=Path(root)/subject
    if path.is_symlink() or not path.is_dir():
        raise ValueError('Expected a distinct subject directory: '+subject)
    return path


def inventory(root):
    root=Path(root)
    study=_jsonfile(_file(root,'study.json'))
    _keys(study,'schema units arm subjects protocol_file runs outcomes','study')
    arm=study['arm']
    if study['schema']!='gnm.manual-study.v1' or study['units']!='mm' or arm not in ARMS:
        raise ValueError('Unknown manual study schema or arm')
    _ids(study['subjects'],'subjects')
    for key in ('runs','outcomes'):
        if not isinstance(study[key],dict):
            raise ValueError('Invalid '+key)
        _ids(list(study[key]),key,empty=key=='outcomes' and arm=='historical')
    if arm=='historical' and study['outcomes']:
        raise ValueError('Historical approximations have no paired face reference')
    for r in study['runs'].values():
        _keys(r,'stage observer session','run')
        if r['stage'] not in STAGES or not all(documented(r[k]) for k in ('observer','session')):
            raise ValueError('Document run stage, observer and session')
    for o in study['outcomes'].values():
        _keys(o,'quantity direction definition sites','outcome')
        q=o['quantity']
        if q in ('surface_unsigned','surface_signed'):
            valid=o['direction'] in ('approx_to_reference','reference_to_approx') and o['sites'] is None
        else:
            _ids(o['sites'],'predeclared paired sites')
            valid=q in ('landmark_distance','profile_point_distance') and o['direction']=='paired_points'
        if not valid or not documented(o['definition']):
            raise ValueError('Document outcome quantity, direction and the measurement protocol')
    cases,skulls={},set()
    for subject in study['subjects']:
        folder=_folder(root,subject)
        case=_jsonfile(_file(folder,'case.json'))
        _keys(case,'case_id skull strata runs','case')
        if case['case_id']!=subject or not isinstance(case['runs'],dict) or case['runs'].keys()!=study['runs'].keys():
            raise ValueError(subject+': case/run IDs differ from enrolment')
        if not isinstance(case['strata'],dict):
            raise ValueError('Invalid case strata')
        _ids(list(case['strata']),'strata',empty=True)
        if 'overall' in case['strata']:
            raise ValueError('Reserved stratum name: overall')
        for v in case['strata'].values():
            _keys(v,'value source','stratum')
            if not all(documented(x) for x in v.values()):
                raise ValueError('Stratum needs a documented value and source')
        skull=_mesh(folder,case['skull'])
        if skull['sha256'] in skulls:
            raise ValueError('Identical skull under more than one subject ID')
        skulls.add(skull['sha256'])
        runs={}
        for label,row in case['runs'].items():
            _keys(row,'mesh fit_report reason reference_access','case run')
            if row['mesh'] is None:
                if not documented(row['reason']) or row['reference_access'] is not None or row['fit_report'] is not None:
                    raise ValueError('Document the missing run; do not attest an absent mesh')
                runs[label]=dict(row)
            else:
                if row['reference_access']!=ACCESS[arm] or row['reason'] is not None:
                    raise ValueError('Reference access declaration conflicts with study arm')
                mesh=_mesh(folder,row['mesh'])
                if mesh['sha256']==skull['sha256']:
                    raise ValueError('Approximation cannot be the frozen skull')
                report_pin=None
                qc=None
                if row['fit_report'] is not None:
                    stage=study['runs'][label]['stage']
                    if stage not in ('offline_statistical','offline_final'):
                        raise ValueError('Only offline outputs can be attributed to an offline fit report')
                    raw=_file(folder,row['fit_report']).read_bytes()
                    report=_json(raw.decode('utf-8-sig'))
                    validate_report(report)
                    role='output_statistical' if stage=='offline_statistical' else 'output'
                    if report['marker_metadata'].get('case_id')!=subject or report['outputs'][role]['sha256']!=mesh['sha256']:
                        raise ValueError('Offline report does not match subject or exact exported stage mesh')
                    report_pin=dict(file=row['fit_report'],sha256=hashlib.sha256(raw).hexdigest())
                    quality=report.get('geometry_quality') or {}
                    recorded=quality.get('statistical' if stage=='offline_statistical' else 'final') or {}
                    qc=dict(fit_converged=report['solver']['converged'],run_status=quality.get('status'),
                            recorded_face_counts={k:len(recorded[k]) for k in ('reference_degenerate_faces',
                            'new_degenerate_faces','normal_reversed_faces') if isinstance(recorded.get(k),list)})
                runs[label]=dict(row,mesh=mesh,fit_report=report_pin,recorded_qc=qc)
        cases[subject]=dict(skull=skull,runs=runs,strata=case['strata'])
    return dict(schema='gnm.manual-lock.v1',study=study,protocol=_pin(root,study['protocol_file']),cases=cases)


def _review(case,digest,study):
    return dict(schema='gnm.manual-review.v1',case_id=case,lock_sha256=digest,
                reference_face=None,roi_alignment_record=None,evaluator=None,
                runs={k:{o:dict(file=None,column=None,separator=None,reason='Not evaluated')
                         for o in study['outcomes']} for k in study['runs']})


def freeze(root, output):
    lock=inventory(root)
    data=canonical_bytes(lock)
    digest=hashlib.sha256(data).hexdigest()
    files={'lock.json':data}
    if lock['study']['arm']!='historical':
        files.update({case+'.review.json':canonical_bytes(_review(case,digest,lock['study'])) for case in lock['cases']})
    _publish(output,files)
    return digest


def distances(path, column, separator, signed):
    """Read exactly the named scalar field. No NaN deletion, clipping, binning or ICP."""
    sep={'comma':',','tab':'\t','semicolon':';'}.get(separator)
    if not sep or not isinstance(column,str) or not column.strip():
        raise ValueError('Specify a named numeric column and comma, tab or semicolon')
    values=[]
    with path.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.reader(f,delimiter=sep,strict=True)
        header=next(reader,[])
        if header:
            header[0]=header[0].removeprefix('//')
        header=[s.strip() for s in header]
        if len(set(header))!=len(header) or column not in header:
            raise ValueError('Missing or ambiguous scalar field: '+column)
        index=header.index(column)
        for row in reader:
            if len(row)!=len(header):
                raise ValueError('Malformed scalar-field row')
            v=float(row[index])
            if not math.isfinite(v) or (not signed and v<0):
                raise ValueError('Nonfinite value or negative unsigned distance')
            values.append(v)
    if not values:
        raise ValueError('Empty distance field')
    return _metrics(values,signed)


def _metrics(values,signed):
    a=np.array(values)
    scale=float(np.max(np.abs(a)))
    norm=a/scale if scale else a
    magn=np.abs(norm)
    return dict(n=len(a),mae_mm=float(np.mean(magn)*scale),median_abs_mm=float(np.median(magn)*scale),
                rmse_mm=float(np.sqrt(np.mean(norm**2))*scale),p95_abs_mm=float(np.percentile(magn,95)*scale),
                signed_bias_mm=float(np.mean(norm)*scale) if signed else None)


def paired_points(path, separator, sites):
    """Same-frame Euclidean errors on preregistered homologous points, with no alignment."""
    sep={'comma':',','tab':'\t','semicolon':';'}.get(separator)
    if not sep:
        raise ValueError('Unknown paired-point delimiter')
    keys=['site']+[a+'_'+axis+'_mm' for a in ('approx','ref') for axis in 'xyz']
    measured={}
    with path.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f,delimiter=sep,strict=True)
        if reader.fieldnames is None or sorted(reader.fieldnames)!=sorted(keys):
            raise ValueError('Paired points need site, approx_{x,y,z}_mm and ref_{x,y,z}_mm columns')
        for row in reader:
            site=row['site']
            if None in row or site not in sites or site in measured:
                raise ValueError('Unknown or duplicate paired site or extra fields')
            value=math.dist([float(row[k]) for k in keys[1:4]], [float(row[k]) for k in keys[4:]])
            if not math.isfinite(value):
                raise ValueError('Nonfinite paired point distance')
            measured[site]=value
    if set(measured)!=set(sites):
        raise ValueError('Missing planned paired site; document the unavailable outcome')
    return _metrics(list(measured.values()),False), measured


def _csv(rows,keys):
    f=io.StringIO(newline='')
    writer=csv.writer(f,lineterminator='\n')
    writer.writerow(keys)
    for row in rows:
        # CSV is also opened in spreadsheets; preserve literal notes as text.
        writer.writerow([("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v)
                         for v in (row.get(k) for k in keys)])
    return f.getvalue().encode('utf-8')


def summarize(root, frozen, expected, output):
    root,frozen=Path(root),Path(frozen)
    raw=_file(frozen,'lock.json').read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=expected or canonical_bytes(inventory(root))!=raw:
        raise ValueError('Lock hash or frozen study inputs differ; preserve the original study')
    lock=_json(raw.decode())
    study,cases=lock['study'],lock['cases']
    rows, reviews={},{}
    pins={}
    references=set()
    pairs=[]
    for subject,case in cases.items():
        folder=_folder(root,subject)
        if study['arm']=='historical':
            rows[subject]=[{ 'case_id':subject,'run':run,'stage':study['runs'][run]['stage'],
                             'observer':study['runs'][run]['observer'],'session':study['runs'][run]['session'],
                             'status':'no_reference' if item['mesh'] else 'missing_fit',
                             'reason':item['reason'] or 'Historical case without a reference face'} for run,item in case['runs'].items()]
            continue
        review_path=_file(frozen,subject+'.review.json')
        data=review_path.read_bytes()
        pins[review_path]=hashlib.sha256(data).hexdigest()
        review=_json(data.decode('utf-8-sig'))
        blank=_review(subject,digest,study)
        _keys(review,' '.join(blank),'review')
        if (any(review[k]!=blank[k] for k in ('schema','case_id','lock_sha256'))
                or not isinstance(review['runs'],dict) or review['runs'].keys()!=study['runs'].keys()):
            raise ValueError(subject+': wrong case/lock/run set')
        evidence=dict(review_sha256=hashlib.sha256(data).hexdigest(),evaluator=review['evaluator'],fields=[])
        for k in ('reference_face','roi_alignment_record'):
            evidence[k]=(_mesh if k=='reference_face' else _pin)(folder,review[k]) if review[k] is not None else None
            if evidence[k]:
                pins[_file(folder,review[k])]=evidence[k]['sha256']
        if evidence['reference_face'] and evidence['reference_face']['sha256'] in {
                case['skull']['sha256'],*(r['mesh']['sha256'] for r in case['runs'].values() if r['mesh'])}:
            raise ValueError('Reference reuses skull or approximation geometry file')
        if evidence['reference_face']:
            ref=evidence['reference_face']['sha256']
            if ref in references or (evidence['roi_alignment_record'] and evidence['roi_alignment_record']['sha256']==ref):
                raise ValueError('Reference face reused across subjects or as its own ROI/alignment record')
            references.add(ref)
        rows[subject]=[]
        used=set()
        for run,fields in review['runs'].items():
            if not isinstance(fields,dict) or fields.keys()!=study['outcomes'].keys():
                raise ValueError('Missing or unknown planned outcome')
            fit=case['runs'][run]
            for o,entry in fields.items():
                _keys(entry,'file column separator reason','measurement')
                spec=study['outcomes'][o]
                row=dict(case_id=subject,run=run,**study['runs'][run],outcome=o,
                         quantity=spec['quantity'],direction=spec['direction'])
                if entry['file'] is None:
                    if not documented(entry['reason']) or any(entry[k] is not None for k in ('column','separator')):
                        raise ValueError('Missing measurements require a reason and no numeric field')
                    row.update(status='not_evaluated' if fit['mesh'] else 'missing_fit',reason=fit['reason'] or entry['reason'])
                else:
                    if (not fit['mesh'] or entry['reason'] is not None or not documented(review['evaluator'])
                            or not evidence['reference_face'] or not evidence['roi_alignment_record']):
                        raise ValueError('A measurement needs a frozen fit, evaluator, reference and ROI/alignment record')
                    if study['arm']=='blind_ct' and review['evaluator'].strip().casefold() in {
                            r['observer'].strip().casefold() for r in study['runs'].values()}:
                        raise ValueError('Blind reference evaluator must be independent of the fit observers')
                    pin=_pin(folder,entry['file'])
                    path=_file(folder,entry['file'])
                    item=(path,entry['column'])
                    if (entry['column'] is not None and not isinstance(entry['column'],str)) or item in used:
                        raise ValueError('Repeated or invalid field; review the measurement assignment')
                    used.add(item)
                    if spec['direction']=='paired_points':
                        if entry['column'] is not None:
                            raise ValueError('Paired coordinates require a null scalar column')
                        stats,values=paired_points(path,entry['separator'],spec['sites'])
                        pairs.extend(dict(case_id=subject,run=run,outcome=o,site=site,distance_mm=values[site])
                                     for site in spec['sites'])
                    else:
                        stats=distances(path,entry['column'],entry['separator'],spec['quantity']=='surface_signed')
                    row.update(status='measured',reason=None,**stats)
                    if path in pins and pins[path]!=pin['sha256']:
                        raise ValueError('Measurement file changed between outcome imports')
                    pins[path]=pin['sha256']
                    evidence['fields'].append(dict(run=run,outcome=o,column=entry['column'],separator=entry['separator'],**pin))
                rows[subject].append(row)
        reviews[subject]=evidence
    flat=[r for subject in study['subjects'] for r in rows[subject]]
    group=[]
    for run in study['runs']:
        for o in study['outcomes']:
            eligible=[r for r in flat if r['run']==run and r['outcome']==o]
            groups={('overall','all'):eligible}
            for field in sorted(set().union(*(c['strata'] for c in cases.values()))):
                for r in eligible:
                    v=cases[r['case_id']]['strata'].get(field,{}).get('value')
                    groups.setdefault((field,v),[]).append(r)
            for (field,v),subset in groups.items():
                scores=[r['mae_mm'] for r in subset if r['status']=='measured']
                group.append(dict(run=run,outcome=o,stratum=field,value=v,enrolled=len(subset),measured=len(scores),
                                  mean_subject_mae_mm=math.fsum(x/len(scores) for x in scores) if scores else None))
    lines=['# Manual validation summary','',f"Study arm: **{study['arm']}**. Enrolled subjects: {len(cases)}.",
           '',SCOPE,'','Reference access and observer identity are operator declarations, not independently verified.',
           '', 'Locked protocol and assets: see manifest.json. Case-level results and reasons: see cases.csv.']
    if group:
        lines+=['','| Run | Outcome | Measured / enrolled subjects | Mean subject MAE (mm) |','|---|---|---:|---:|']
        for g in group:
            if g['stratum']=='overall':
                value=g['mean_subject_mae_mm']
                lines.append(f"| {g['run']} | {g['outcome']} | {g['measured']} / {g['enrolled']} | "
                             +('not assessed' if value is None else f'{value:.4g}')+' |')
    else:
        lines+=['','No paired face reference. No numerical accuracy statistics.']
    stats='n mae_mm median_abs_mm rmse_mm p95_abs_mm signed_bias_mm'
    files={'cases.csv':_csv(flat,('case_id run stage observer session outcome quantity direction status reason '+stats).split()),
           'paired_sites.csv':_csv(pairs,'case_id run outcome site distance_mm'.split()),
           'cohort.csv':_csv(group,'run outcome stratum value enrolled measured mean_subject_mae_mm'.split()),
           'summary.md':('\n'.join(lines)+'\n').encode()}
    manifest=dict(schema='gnm.manual-summary.v1',arm=study['arm'],lock_sha256=digest,lock=lock,reviews=reviews,scope=SCOPE,
                  outputs={k:hashlib.sha256(v).hexdigest() for k,v in files.items()})
    files['manifest.json']=canonical_bytes(manifest)
    if (sha256_file(_file(frozen,'lock.json'))!=digest or canonical_bytes(inventory(root))!=raw
            or any(sha256_file(path)!=h for path,h in pins.items())):
        raise ValueError('Evidence changed during summarization; no results published')
    _publish(output,files)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    cmds=parser.add_subparsers(dest='command',required=True)
    for name in ('init','freeze','summarize'):
        p=cmds.add_parser(name)
        p.add_argument('--root',required=True)
        if name=='init':
            p.add_argument('--arm',choices=ARMS,required=True)
            for arg in ('subjects','runs','outcomes'):
                p.add_argument('--'+arg,nargs='+',required=arg!='outcomes',default=[])
        else:
            p.add_argument('--lock-dir',required=True)
        if name=='summarize':
            p.add_argument('--expected-sha256',required=True)
            p.add_argument('--output-dir',required=True)
    a=parser.parse_args(argv)
    try:
        if a.command=='init': initialize(a.root,a.arm,a.subjects,a.runs,a.outcomes)
        elif a.command=='freeze': print('Lock SHA-256: '+freeze(a.root,a.lock_dir))
        else: summarize(a.root,a.lock_dir,a.expected_sha256,a.output_dir)
        return 0
    except (ValueError, OSError, TypeError, csv.Error, OverflowError) as exc:
        print('Cannot complete manual validation step: '+str(exc))
        return 2


if __name__=='__main__':
    raise SystemExit(main())

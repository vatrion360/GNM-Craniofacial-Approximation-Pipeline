"""Report-only comparison of reviewed incisor/canine sites on a saved neutral fit."""
import argparse
import math
from pathlib import Path, PureWindowsPath
import zipfile

import numpy as np

from .anomaly import documented
from .record import _digest, _hash, canonical_bytes, validate_report
from .review_export import geometry_lines
from .tissue import _json
from .validation import sha256_file, validate_outputs

SITES = tuple(f'{arch}_{side}_{tooth}' for arch in ('upper', 'lower') for side in ('left', 'right')
              for tooth in ('central_incisor', 'lateral_incisor', 'canine'))
GROUPS = ('teeth', 'upper_teeth_and_gums', 'lower_teeth_and_gums', 'right', 'left',
          'upper_lip', 'lower_lip', 'skin_exterior')
INTERPRETATION = ('Point correspondence in the saved world-mm frame. A tooth-to-fitted-lip chord difference '
                  'is a support proxy, not observed lip thickness, an inferred lip displacement or a diagnosis.')


def template(report, digest):
    validate_report(report)
    case = report['marker_metadata'].get('case_id')
    if not documented(case):
        raise ValueError('Saved fit requires an explicit marker case ID')
    return dict(schema='gnm.dental-sites.v1', units='mm', coordinate_space='world', case_id=case,
                report_sha256=digest, model_sha256=report['inputs']['model']['sha256'],
                sites={k: dict(state='unknown', observation=None, correspondence=None) for k in SITES})


def _asset(path):
    """Read only the topology and semantic masks, never the identity/expression bases."""
    with np.load(path, allow_pickle=False) as z:
        names, groups, tris = z['vertex_group_names'], z['vertex_groups'], z['triangles']
        if names.ndim != 1 or names.dtype.kind not in 'US':
            raise ValueError('Invalid GNM group names')
        names = names.astype(str).tolist()
        if (len(names) != len(set(names)) or not set(GROUPS) <= set(names) or groups.ndim != 2
                or groups.shape[0] != len(names) or groups.dtype.kind not in 'fiu' or not np.isfinite(groups).all()
                or tris.ndim != 2 or tris.shape[1:] != (3,) or not len(tris) or tris.dtype.kind not in 'iu'
                or np.any(tris < 0) or np.any(tris >= groups.shape[1])):
            raise ValueError('Model lacks valid dental masks or triangle topology')
        # Same mask membership convention as FaceModelData.group_mask; not an anatomical cutoff.
        return {name: groups[names.index(name)] > .5 for name in GROUPS}, tris


def _obj(raw, count, triangles):
    lines, counts = geometry_lines(raw)
    if counts != dict(vertices=count, triangles=len(triangles)):
        raise ValueError('Saved OBJ vertex/face count differs from GNM model')
    tris = np.array([[int(x)-1 for x in l.split()[1:]] for l in lines if l.startswith('f ')])
    if not np.array_equal(tris, triangles):
        raise ValueError('Saved OBJ face order or topology differs from GNM model')
    return np.array([[float(x) for x in l.split()[1:]] for l in lines if l.startswith('v ')])


def _metric(vertices, tooth, lip, observed):
    model = vertices[tooth]
    delta = model - observed
    distance = math.hypot(*delta)
    if not np.isfinite(distance):
        raise ValueError('Dental offset exceeds finite range')
    result = dict(model_tooth_mm=model.tolist(), model_minus_observed_mm=delta.tolist(),
                  tooth_distance_mm=distance, lip_chord=None)
    if lip is not None:
        a, b = math.dist(vertices[lip], model), math.dist(vertices[lip], observed)
        if not all(map(math.isfinite, (a,b))):
            raise ValueError('Lip chord exceeds finite range')
        result['lip_chord'] = dict(fitted_lip_mm=vertices[lip].tolist(), model_to_fitted_lip_mm=a,
                                   observed_to_fitted_lip_mm=b, observed_minus_model_mm=b-a)
    return result


def compare(report, digest, manifest, masks, meshes):
    """Measure paired reviewed points; refuse inconsistent bindings, never invent absent teeth."""
    expected = template(report, digest)
    if (not isinstance(manifest, dict) or set(manifest) != set(expected)
            or any(manifest[k] != v for k,v in expected.items() if k != 'sites')
            or not isinstance(manifest['sites'], dict) or set(manifest['sites']) != set(SITES)):
        raise ValueError('Dental manifest schema, case, units, report, model or site IDs do not match')
    meta = report['marker_metadata']
    sources = {}
    raw_sources = meta.get('bone_sources', [])
    if not isinstance(raw_sources, list):
        raise ValueError('Invalid saved bone-source manifest')
    for r in raw_sources:
        if not isinstance(r, dict) or not documented(r.get('id')) or r['id'] in sources:
            raise ValueError('Invalid or duplicate saved bone source')
        _hash(r.get('geometry_sha256'))
        sources[r['id']] = r
    rows, used_vertices, used_obs = {}, set(), set()
    for key in SITES:
        arch, side, _ = key.split('_', 2)
        row = manifest['sites'][key]
        if not isinstance(row, dict) or set(row) != {'state','observation','correspondence'}:
            raise ValueError(key+': invalid site row')
        state, obs, mapping = row['state'], row['observation'], row['correspondence']
        if state not in ('unknown','absent','reconstructed','observed'):
            raise ValueError(key+': unknown observation state')
        if state != 'observed' and obs is not None:
            raise ValueError(key+': only observed sites can supply a bone pick')
        tooth = lip = None
        if mapping is not None:
            if (not isinstance(mapping, dict) or set(mapping) != {'reviewer','definition','tooth_vertex','lip_vertex'}
                    or not all(documented(mapping[k]) for k in ('reviewer','definition'))):
                raise ValueError(key+': document the exact corresponding point and reviewer')
            tooth, lip = mapping['tooth_vertex'], mapping['lip_vertex']
            def matches(i, names):
                return type(i) is int and 0 <= i < len(masks['teeth']) and all(masks[n][i] for n in names)
            if not matches(tooth, ('teeth', arch+'_teeth_and_gums', side)) or tooth in used_vertices:
                raise ValueError(key+': duplicate or incorrect tooth vertex, arch or side')
            used_vertices.add(tooth)
            if lip is not None and not matches(lip, (arch+'_lip','skin_exterior',side)):
                raise ValueError(key+': wrong exterior lip vertex, side or arch')
        reason = state if state != 'observed' else None
        if state == 'observed':
            if obs is None:
                reason = 'No observed point supplied'
            else:
                if (not isinstance(obs, dict) or set(obs) != {'case_id','source_id','geometry_sha256','xyz_mm'}
                        or obs['case_id'] != manifest['case_id'] or not documented(obs['source_id'])):
                    raise ValueError(key+': invalid or wrong-case observation')
                _hash(obs['geometry_sha256'])
                xyz = obs['xyz_mm']
                if (not isinstance(xyz, list) or len(xyz) != 3 or
                        any(type(x) not in (float,int) or not math.isfinite(x) for x in xyz)):
                    raise ValueError(key+': expected a finite world-mm point')
                # Opposing teeth can meet. Only reuse on the same recorded arch/source is contradictory.
                observed_key = (arch, obs['source_id'], tuple(xyz))
                if observed_key in used_obs:
                    raise ValueError(key+': repeated observed point on one arch and source')
                used_obs.add(observed_key)
                src = sources.get(obs['source_id'])
                if not src or src['geometry_sha256'] != obs['geometry_sha256']:
                    reason = 'Observed source missing or changed since the fit'
                elif src.get('anatomy') not in ('MIXED', 'CRANIUM' if arch=='upper' else 'MANDIBLE'):
                    reason = 'Recorded bone source does not match the dental arch'
                elif arch == 'lower' and meta.get('mandible_articulation_reviewed') is not True:
                    reason = 'Mandibular articulation not reviewed for the saved fit'
                elif mapping is None:
                    reason = 'No reviewed model correspondence'
        rows[key] = dict(state=state, observation=obs, correspondence=mapping, reason=reason,
                         status='not_assessed' if reason else 'measured',
                         stages={} if reason else {stage:_metric(v,tooth,lip,np.asarray(xyz, dtype=float))
                                                  for stage,v in meshes.items()})
    summary = {}
    for stage in meshes:
        distances = [r['stages'][stage]['tooth_distance_mm'] for r in rows.values() if r['status']=='measured']
        summary[stage] = dict(measured=len(distances), total=len(SITES),
                              mean_tooth_distance_mm=math.fsum(v/len(distances) for v in distances) if distances else None,
                              max_tooth_distance_mm=max(distances, default=None))
    return dict(schema='gnm.dental-consistency.v1', units='mm', case_id=manifest['case_id'],
                report_sha256=digest, model_sha256=manifest['model_sha256'], interpretation=INTERPRETATION,
                saved_fit_converged=report['solver']['converged'], saved_fit_warnings=report['warnings'],
                sites=rows, summary=summary)


def result_text(result):
    """Readable companion to the JSON; missing sites never display a numeric zero."""
    lines = ['Dental comparison: '+result['case_id'], INTERPRETATION,
             'Distances in mm. Columns: tooth discrepancy / observed-minus-model tooth-to-fitted-lip chord.']
    for key, row in result['sites'].items():
        if row['status'] != 'measured':
            lines.append(f"{key}: not assessed ({row['reason']})")
            continue
        parts = [key+':']
        for stage in ('statistical','final'):
            item = row['stages'][stage]
            proxy = item['lip_chord']
            chord = 'not assessed' if proxy is None else f"{proxy['observed_minus_model_mm']:+.3f}"
            parts.append(f"{stage}: {item['tooth_distance_mm']:.3f} / {chord}")
        lines.append('  '.join(parts))
    lines.append(f"Measured {result['summary']['final']['measured']}/{len(SITES)} sites.")
    return '\n'.join(lines)+'\n'


def _save(path, data):
    # Exclusive create: no request can replace an original artifact/scene or another report.
    raw = canonical_bytes(data)
    with Path(path).open('xb') as f:
        f.write(raw)


def run(report_path, output, *, model=None, sites=None, artifacts=None):
    """Write a bound empty template or a new standalone report; source files are read only."""
    report_path = Path(report_path)
    raw = report_path.read_bytes()
    digest = _digest(raw)
    report = _json(raw.decode('utf-8-sig'))
    blank = template(report, digest)
    if Path(output).exists() or Path(output).is_symlink():
        raise ValueError('Dental output exists; choose a new file')
    validate_outputs([report_path, model, sites], [output])
    if model is None and sites is None:
        _save(output, blank)
        return blank
    if model is None or sites is None:
        raise ValueError('Both the GNM model and reviewed sites file are required')
    pins = {report_path:digest, Path(model):blank['model_sha256']}
    if sha256_file(model) != blank['model_sha256']:
        raise ValueError('GNM model checksum differs from saved fit')
    masks, triangles = _asset(model)
    raw_sites = Path(sites).read_bytes()
    pins[Path(sites)] = _digest(raw_sites)
    folder = Path(artifacts or report_path.parent).resolve()
    meshes, outputs = {}, {}
    for stage, role in [('statistical','output_statistical'), ('final','output')]:
        entry = report['outputs'][role]
        path = (folder / PureWindowsPath(entry['path']).name).resolve()
        if path.parent != folder:
            raise ValueError('Mesh path escapes the artifact directory')
        raw = path.read_bytes()
        pins[path] = _digest(raw)
        if pins[path] != entry['sha256']:
            raise ValueError(stage+': saved mesh checksum mismatch')
        meshes[stage] = _obj(raw, len(masks['teeth']), triangles)
        outputs[stage] = pins[path]
    result = compare(report, digest, _json(raw_sites.decode('utf-8-sig')), masks, meshes)
    result.update(sites_sha256=pins[Path(sites)], mesh_sha256=outputs)
    if any(sha256_file(p) != h for p,h in pins.items()):
        raise ValueError('Input changed during comparison')
    _save(output, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('template','compare'):
        p = sub.add_parser(name)
        p.add_argument('--report', required=True)
        p.add_argument('--output', required=True)
        if name == 'compare':
            p.add_argument('--npz', required=True)
            p.add_argument('--sites', required=True)
            p.add_argument('--artifacts', help='Moved saved OBJ directory')
    args = parser.parse_args(argv)
    try:
        res = run(args.report, args.output, model=getattr(args,'npz',None), sites=getattr(args,'sites',None),
                  artifacts=getattr(args,'artifacts',None))
        if 'summary' in res:
            print(result_text(res), end='')
        return 0
    except (ValueError, OSError, KeyError, OverflowError, zipfile.BadZipFile) as exc:
        print('Cannot evaluate dental sites: '+str(exc))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

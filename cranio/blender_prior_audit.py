"""Read an intact paired audit and import its two surfaces on Blender's main thread.

Only NumPy/stdlib until explicit import_comparison; no fitting, network or bpy
access during validation. Paths in external JSON never choose files to load.
"""
import hashlib
from pathlib import Path
import numpy as np
from .tissue import _json


OUTPUT_NAMES = dict(output='face.obj', output_statistical='face_statistical.obj',
                    output_error_mesh='face_heatmap.ply', output_stats='face_statistici.txt')
_UNHASHED = object()


def _read(root, relative, expected_hash=_UNHASHED):
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Comparison artifact escapes its bundle')
    data = path.read_bytes()
    if expected_hash is not _UNHASHED:
        if (not isinstance(expected_hash, str) or len(expected_hash) != 64
                or any(c not in '0123456789abcdef' for c in expected_hash)
                or hashlib.sha256(data).hexdigest() != expected_hash):
            raise ValueError('Comparison artifact checksum mismatch: '+relative)
    return data


def _surface(data):
    """Parse only the pipeline's triangle OBJ dialect, in world millimetres."""
    vertices, faces = [], []
    for line in data.decode('utf-8').splitlines():
        fields = line.split()
        if not fields or fields[0].startswith('#'):
            continue
        if fields[0] == 'v' and len(fields) == 4:
            vertices.append([float(x) for x in fields[1:]])
        elif fields[0] == 'f' and len(fields) == 4:
            faces.append([int(x)-1 for x in fields[1:]])
        else:
            raise ValueError('Unsupported comparison OBJ record')
    v, f = np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64)
    if (v.ndim != 2 or v.shape[1] != 3 or not len(v) or not np.isfinite(v).all()
            or f.ndim != 2 or f.shape[1] != 3 or not len(f) or np.any(f < 0) or np.any(f >= len(v))
            or np.any(f[:,0] == f[:,1]) or np.any(f[:,1] == f[:,2]) or np.any(f[:,0] == f[:,2])):
        raise ValueError('Invalid comparison OBJ vertices/triangles')
    return v, f


def load_comparison(folder):
    """Validate the complete bundle before any Blender objects can be created.

    Integrity checks do not authenticate the author or establish scientific validity.
    The fixed layout also supports moving a complete bundle to another directory.
    """
    root = Path(folder)
    summary = _json(_read(root, 'summary.json').decode('utf-8'))
    try:
        if (type(summary['schema_version']) is not int or summary['schema_version'] != 1 or summary['status'] != 'completed'
                or summary['units'] != 'mm' or summary['coordinate_space'] != 'world'
                or summary['comparison_status'] not in {'completed_converged','diagnostic_only_nonconverged'}
                or summary['reference'] != 'neutral'):
            raise ValueError('Incomplete or unsupported prior comparison')
        rows = summary['scenarios']
        if len(rows) != 2 or [row['id'] for row in rows] != ['neutral','prior']:
            raise ValueError('Expected exactly neutral and prior scenarios')
        scenarios = []
        for row in rows:
            name = row['id']
            relative = name+'/face_report.json'
            # The existing writer serializes native Path separators. Accept only
            # the two exact spellings of this fixed path, including moved bundles.
            if row['report'] not in (relative, relative.replace('/', '\\')) or row['prior_enabled'] is not (name == 'prior'):
                raise ValueError('Comparison scenario identity/path mismatch')
            report = _json(_read(root, relative, row['report_sha256']).decode('utf-8'))
            if report['status'] != 'completed' or report['units'] != 'mm':
                raise ValueError('Incomplete child run report')
            if bool(report['config']['prior']) != (name == 'prior'):
                raise ValueError('Child prior state disagrees with scenario')
            if type(report['solver']['converged']) is not bool or row['solver'] != report['solver']:
                raise ValueError('Child solver diagnostics disagree with comparison')
            for key, filename in OUTPUT_NAMES.items():
                data = _read(root, name+'/'+filename, report['outputs'][key]['sha256'])
                if key == 'output':
                    vertices, faces = _surface(data)
            scenarios.append(dict(id=name, report=report, report_path=str(root/relative),
                                  vertices=vertices, faces=faces))
        if (scenarios[0]['vertices'].shape != scenarios[1]['vertices'].shape
                or not np.array_equal(scenarios[0]['faces'], scenarios[1]['faces'])):
            raise ValueError('Comparison surfaces have different topology')
        status = ('completed_converged' if all(r['report']['solver']['converged'] for r in scenarios)
                  else 'diagnostic_only_nonconverged')
        if summary['comparison_status'] != status:
            raise ValueError('Comparison convergence status disagrees with child reports')
        for kind in ('final','statistical'):
            row = summary['differences_to_neutral'][kind]
            expected = 'difference_'+kind+'.ply'
            if row['ply'] != expected:
                raise ValueError('Unexpected difference artifact path')
            _read(root, expected, row['sha256'])
        if summary['text_report']['path'] != 'comparison.txt':
            raise ValueError('Unexpected comparison text path')
        _read(root, 'comparison.txt', summary['text_report']['sha256'])
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError('Malformed prior comparison record') from exc
    return summary, scenarios


def import_comparison(scene, folder):
    """Import both surfaces transactionally, preserving all existing scene objects."""
    import bpy
    summary, scenarios = load_comparison(folder)
    created, meshes = [], []
    try:
        for row in scenarios:
            mesh = bpy.data.meshes.new('GNM Prior Audit '+row['id'])
            meshes.append(mesh)
            mesh.from_pydata(row['vertices'].tolist(), [], row['faces'].tolist())
            mesh.update()
            obj = bpy.data.objects.new('GNM_Audit_'+Path(folder).parent.name+'_'+row['id'], mesh)
            created.append(obj)
            obj['gnm_report'] = row['report_path']
            obj['gnm_prior_comparison'] = str(Path(folder)/'summary.json')
            obj['gnm_prior_scenario'] = row['id']
            obj['gnm_comparison_status'] = summary['comparison_status']
            scene.collection.objects.link(obj)
            # Avoid overlapping surfaces on initial import; both remain in Outliner.
            obj.hide_viewport = row['id'] == 'neutral'
            obj.hide_render = row['id'] == 'neutral'
        scene.gnm_settings.offline_status = ('Comparison completed; '+summary['comparison_status']+
            '; selected-prior surface shown, neutral hidden. Sensitivity, NOT accuracy. '+str(folder))
    except Exception:
        for obj in reversed(created):
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in reversed(meshes):
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        raise
    return created

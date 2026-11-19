"""Engineering fixtures in mm; deliberate nested shells and partial meshes."""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest
import trimesh

from cranio.coherence import main, measure
from cranio.export import export_obj
from cranio.record import canonical_bytes


def obj(path, vertices, faces):
    export_obj(path, vertices, faces)
    return path


def reviewed(skull, face, ids):
    path = face.with_suffix('.json')
    path.write_bytes(canonical_bytes(dict(schema='gnm.coherence-review.v1',
        skull_sha256=hashlib.sha256(skull.read_bytes()).hexdigest(),
        face_sha256=hashlib.sha256(face.read_bytes()).hexdigest(),
        review_source='Synthetic geometry and explicit evaluation mask',
        bone_solid_reviewed=True, eligible_face_vertices=ids)))
    return path


def shell_files(folder, radii):
    mesh = trimesh.creation.icosphere(subdivisions=1, radius=10)
    skull = obj(folder/'bone.obj', mesh.vertices, mesh.faces)
    vertices = mesh.vertices*np.asarray(radii).reshape(-1, 1)
    face = obj(folder/'skin.obj', vertices, mesh.faces)
    return skull, face, len(vertices)


@pytest.mark.parametrize('scale,category,percent', [(0.8,'inside',100), (1.2,'outside',0), (1,'boundary',0)])
def test_concentric_shells_and_repeatable_json(tmp_path, scale, category, percent):
    pytest.importorskip('rtree')
    skull, face, n = shell_files(tmp_path, [scale])
    review = reviewed(skull, face, list(range(n)))
    result = measure(skull, face, review)
    metric = result['skin_in_bone']
    assert metric['status'] == 'measured' and metric['percent'] == percent
    assert metric['counts'][category] == n and sum(metric['counts'].values()) == n
    assert canonical_bytes(result) == canonical_bytes(measure(skull, face, review))


def test_selection_and_shared_frame_survive_stl_facet_duplication(tmp_path):
    pytest.importorskip('rtree')
    mesh = trimesh.creation.box(extents=[4,4,4])
    shift = np.array([100, -70, 5])
    mesh.apply_translation(shift)
    skull = tmp_path/'box.stl'
    mesh.export(skull)
    face = obj(tmp_path/'face.obj', np.array([[0,0,0],[1,0,0],[2,1,0],[3,0,0]])+shift, [[0,1,2],[1,3,2]])
    s = measure(skull, face, reviewed(skull, face, [3,0,2]))['skin_in_bone']
    assert s['inside_vertex_indices'] == [0] and s['percent'] == pytest.approx(100/3)
    assert s['counts'] == dict(inside=1, outside=1, boundary=1, ambiguous=0)


def test_review_hashes_missing_selection_and_partial_bone(tmp_path, capsys):
    skull, face, n = shell_files(tmp_path, [1.2])
    args = ['--skull',str(skull),'--face',str(face)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)['skin_in_bone']['percent'] is None
    skull.write_text('\n'.join(skull.read_text().splitlines()[:-1])+'\n')
    review = reviewed(skull, face, [0,2])
    s = measure(skull, face, review)['skin_in_bone']
    assert s['status'] == 'not_assessed' and s['percent'] is None and 'open' in s['reason']
    for invalid in ([n], [True], [], [0,0]):
        with pytest.raises(ValueError, match='indices'):
            measure(skull, face, reviewed(skull, face, invalid))
    review = reviewed(skull, face, [1])
    skull.write_bytes(skull.read_bytes()+b'\n')
    assert main([*args,'--review',str(review)]) == 2
    captured = capsys.readouterr()
    assert not captured.out and 'exact skull and face' in captured.err


@pytest.mark.integration
def test_offline_baseline_faces_with_synthetic_bone(tmp_path):
    pytest.importorskip('rtree')
    model = os.environ.get('GNM_MODEL_PATH')
    if not model:
        pytest.skip('Set GNM_MODEL_PATH for both T0.2 fixtures')
    from cranio.consistency import saved_obj_mesh
    from cranio.pipeline import run_pipeline
    from gnm_reconstruct import parse_args
    suite = Path(__file__).resolve().parents[1]/'examples/regression/suite.json'
    for name, args in json.loads(suite.read_bytes()).items():
        cfg = parse_args(args)
        cfg.input = str(suite.parent/cfg.input)
        cfg.npz, cfg.output = model, str(tmp_path/f'{name}.obj')
        assert run_pipeline(cfg) == 0
        face = Path(cfg.output)
        vertices, _ = saved_obj_mesh(face.read_bytes())
        marks = {row['label']:row['vertex'] for row in json.loads(Path(cfg.output_json).read_bytes())['landmarks']}
        ids = [marks[k] for k in ('Nasion','Rhinion','Pogonion')]
        sphere = trimesh.creation.icosphere(subdivisions=1, radius=2)
        skull = obj(tmp_path/f'{name}-bone.obj', sphere.vertices+vertices[ids[0]], sphere.faces)
        metric = measure(skull, face, reviewed(skull, face, ids))['skin_in_bone']
        assert metric['inside_vertex_indices'] == ids[:1]
        assert metric['percent'] == pytest.approx(100/3)


def test_nested_closed_shells_exclude_enclosed_cavity(tmp_path):
    pytest.importorskip('rtree')
    outer = trimesh.creation.icosphere(subdivisions=1, radius=5)
    inner = trimesh.creation.icosphere(subdivisions=1, radius=2)
    inner.invert()
    joined = trimesh.util.concatenate([outer, inner])
    skull = obj(tmp_path/'bone.obj', joined.vertices, joined.faces)
    face = obj(tmp_path/'skin.obj', np.array([[0.,0,0],[3.,0,0],[0,8.,0]]), [[0,1,2]])
    metric = measure(skull, face, reviewed(skull, face, [0,1,2]))['skin_in_bone']
    assert metric['counts'] == dict(inside=1, outside=2, boundary=0, ambiguous=0)
    assert metric['inside_vertex_indices'] == [1]


def test_unreviewed_closed_surface_and_disagreement_are_not_zero(tmp_path, monkeypatch):
    skull, face, _ = shell_files(tmp_path, [0.8])
    review = reviewed(skull, face, [0,1])
    declaration = json.loads(review.read_bytes())
    declaration['bone_solid_reviewed'] = False
    review.write_bytes(canonical_bytes(declaration))
    metric = measure(skull, face, review)['skin_in_bone']
    assert metric['status'] == 'not_assessed' and metric['percent'] is None
    monkeypatch.setattr('cranio.coherence._classify', lambda *args: (np.array(['inside','ambiguous']), 1e-8))
    metric = measure(skull, face, reviewed(skull, face, [0,1]))['skin_in_bone']
    assert metric['percent'] is None and metric['ambiguous_vertex_indices'] == [1]


@pytest.mark.parametrize('problem', ['duplicated', 'reversed'])
def test_invalid_ply_solid_declines_volume_score(tmp_path, problem):
    mesh = trimesh.creation.icosphere(subdivisions=1, radius=10)
    triangles = mesh.faces.copy()
    if problem == 'duplicated':
        triangles = np.vstack((triangles, triangles[0]))
    else:
        triangles[0] = triangles[0][::-1]
    skull = tmp_path/'reviewed.ply'
    trimesh.Trimesh(mesh.vertices, triangles, process=False).export(skull)
    face = obj(tmp_path/'face.obj', mesh.vertices * 0.8, mesh.faces)
    result = measure(skull, face, reviewed(skull, face, [0, 1]))
    assert result['skin_in_bone']['status'] == 'not_assessed'
    assert result['skin_in_bone']['percent'] is None

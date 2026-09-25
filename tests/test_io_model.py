import json
import numpy as np
import pytest
from cranio.io_csv import read_marker_csv, write_marker_csv_v3, write_marker_csv_v2
from cranio.backend import GNMBackend


def row(**changes):
    data = dict(label='Nasion', vertex=12, placed=1, x=0, y=0, z=0, weight=.5)
    data.update(changes)
    return data


def test_v3_preserves_origin_and_manual_vertex(tmp_path):
    path = tmp_path / 'markers.csv'
    write_marker_csv_v3(path, [row()])
    targets, skipped, meta = read_marker_csv(path, {}, {'Nasion': 999})
    assert targets[0].vertex == 12
    assert np.all(targets[0].xyz == 0)
    assert targets[0].weight == .5
    assert not skipped
    assert meta['version'] == 3


@pytest.mark.parametrize('changes', [dict(x='nan'), dict(z='inf'), dict(vertex=-1), dict(weight=0),
                                     dict(weight=-.2), dict(weight=2), dict(placed='yes'), dict(label='')])
def test_bad_v3_rows_rejected(tmp_path, changes):
    path = tmp_path / 'markers.csv'
    write_marker_csv_v3(path, [row(**changes)])
    with pytest.raises(ValueError, match='row 1'):
        read_marker_csv(path, {}, {})


@pytest.mark.parametrize('second', [row(), row(label='Glabella')])
def test_duplicate_labels_and_vertices_rejected(tmp_path, second):
    path = tmp_path / 'markers.csv'
    write_marker_csv_v3(path, [row(), second])
    with pytest.raises(ValueError, match='duplicate'):
        read_marker_csv(path, {}, {})


def test_bone_and_skin_separate(tmp_path):
    path = tmp_path / 'markers.csv'
    write_marker_csv_v3(path, [row(z=5, bone_x=0, bone_y=0, bone_z=0, tissue_depth_mm=5,
                                      tissue_source='study DOI and landmark definition')])
    targets, _, meta = read_marker_csv(path, {}, {})
    assert targets[0].xyz[2] == 5
    assert meta['bone_positions_mm']['Nasion'] == [0, 0, 0]


def test_inconsistent_depth_rejected(tmp_path):
    path = tmp_path / 'markers.csv'
    write_marker_csv_v3(path, [row(z=10, bone_x=0, bone_y=0, bone_z=0, tissue_depth_mm=5)])
    with pytest.raises(ValueError, match='differs'):
        read_marker_csv(path, {}, {})


def test_legacy_compatibility(tmp_path):
    path = tmp_path / 'markers.csv'
    write_marker_csv_v2(path, [(-1, 0, 0, 0), (-2, 1, 2, 3)])
    targets, skipped, meta = read_marker_csv(path, {-1: 'a', -2: 'b'}, {'a': 10, 'b': 20})
    assert targets[0].vertex == 20
    assert skipped[0][0] == 'a'
    assert 'legacy_assumptions' in meta


@pytest.mark.parametrize('metadata', ['{broken', '[]', '{"units":"m"}'])
def test_bad_metadata_rejected(tmp_path, metadata):
    path = tmp_path / 'bad.csv'
    path.write_text('# gnm-marker-csv v2\n# ' + metadata + '\ngnm_landmark_index,x,y,z\n')
    with pytest.raises(ValueError):
        read_marker_csv(path, {}, {})


def test_model_load_is_safe_and_units_explicit(model_file):
    model = GNMBackend(str(model_file)).load()
    assert model.mu.dtype == np.float32
    assert model.basis.shape == (3, 12, 3)
    assert model.mu[:, 1].mean() > 100


@pytest.mark.parametrize('key,value', [('triangles', np.array([[0, 1, 99]])),
                                      ('mirror_indices', np.full(12, -1)),
                                      ('template_vertex_positions', np.full((12, 3), np.nan)),
                                      ('vertex_group_names', np.array([{'payload': 'object'}], dtype=object))])
def test_invalid_models_fail(model_file, key, value):
    with np.load(model_file, allow_pickle=False) as archive:
        data = dict(archive)
    data[key] = value
    np.savez(model_file, **data)
    with pytest.raises(ValueError):
        GNMBackend(str(model_file)).load()

"""Paired world-mm profile measurements on independently indexed synthetic surfaces."""
import hashlib
import json

import numpy as np
import pytest
import trimesh

from cranio.coherence import main, measure
from cranio.export import export_obj
from cranio.validation_cases import paired_points


def anchor(triangle, weights):
    return dict(triangle=triangle, barycentric=weights)


def fixture(folder, *, rotation=None, shift=None, suffix='.obj'):
    skull, face, target, review = (folder/n for n in ('skull.obj','fit.obj','target'+suffix,'review.json'))
    vertices = np.array([[0.,0.,0.],[0.,8.,0.],[0.,0.,8.]])
    rotation = np.eye(3) if rotation is None else rotation
    shift = np.zeros(3) if shift is None else shift
    points = vertices @ rotation.T + shift
    export_obj(skull, points+[10,0,0], [[0,1,2]])
    export_obj(face, points, [[0,1,2]])
    # One common site and one site moved by (1,3,4); different corner order.
    vertices[1] += [1,3,4]
    refs = (vertices @ rotation.T + shift)[[1,2,0]]
    if suffix == '.obj':
        export_obj(target, refs, [[0,1,2]])
    else:
        trimesh.Trimesh(refs,[[0,1,2]],process=False).export(target)
    hashes = measure(skull,face,profile_reference_path=target)['input_sha256']
    data = dict(schema='gnm.profile-error-review.v1',
                **{k+'_sha256':v for k,v in hashes.items()},
                reference_source='Synthetic withheld reference skin surface',
                registration_source='Common synthetic skull frame, no realignment', reference_access='withheld',
                plane=dict(origin_mm=shift.tolist(), normal_world=(3*rotation[:,0]).tolist(),
                           source='Synthetic midsagittal section fixed before evaluation', tolerance_mm=1.01),
                sites={'Gl':dict(approx=anchor(0,[1,0,0]), reference=anchor(0,[0,0,1])),
                       'N':dict(approx=anchor(0,[0,1,0]), reference=anchor(0,[1,0,0]))})
    review.write_text(json.dumps(data))
    return skull, face, target, review


def metric(paths):
    skull, face, target, review = paths
    return measure(skull,face,profile_reference_path=target,profile_review_path=review)['profile_error']


def edit(path, change):
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


@pytest.mark.parametrize('suffix',['.obj','.stl','.ply'])
def test_same_frame_planar_error_preserves_lateral_component_and_matches_c3(tmp_path,suffix):
    rot = np.array([[0.,0.,1.],[-1.,0.,0.],[0.,-1.,0.]])
    paths = fixture(tmp_path,rotation=rot,shift=np.array([350.,27.,-5.]),suffix=suffix)
    result = metric(paths)
    assert result == metric(paths)
    assert result['status'] == 'measured' and result['site_count'] == result['measured_count'] == 2
    assert result['sites']['Gl']['distance_3d_mm'] == 0
    n = result['sites']['N']
    assert n['distance_in_plane_mm'] == 5
    assert n['reference_plane_offset_mm'] == 1
    assert n['distance_3d_mm'] == pytest.approx(np.sqrt(26))
    assert result['summary_in_plane']['rmse_mm'] == pytest.approx(np.sqrt(12.5))
    csv = tmp_path/'paired.csv'
    rows = [','.join([name,*map(str,s['approx_xyz_mm']),*map(str,s['reference_xyz_mm'])])
            for name,s in result['sites'].items()]
    csv.write_text('site,approx_x_mm,approx_y_mm,approx_z_mm,ref_x_mm,ref_y_mm,ref_z_mm\n'+'\n'.join(rows)+'\n')
    c3, values = paired_points(csv,'comma',['Gl','N'])
    assert c3 == result['summary_3d'] and values['N'] == n['distance_3d_mm']


def test_partial_off_plane_missing_and_fractional_site(tmp_path):
    paths = fixture(tmp_path)
    def revise(d):
        d['plane']['tolerance_mm'] = .5
        d['sites']['P'] = {'reason':'Reference patch cropped'}
        d['sites']['M'] = dict(approx=anchor(0,[.5,.5,0]), reference=anchor(0,[.5,0,.5]))
    edit(paths[-1],revise)
    result = metric(paths)
    assert result['status'] == 'partial' and (result['site_count'],result['measured_count']) == (4,2)
    assert result['summary_in_plane']['mae_mm'] == 1.25
    assert result['sites']['M']['distance_in_plane_mm'] == 2.5
    assert result['sites']['N']['distance_in_plane_mm'] is None
    assert result['sites']['N']['reference_plane_offset_mm'] == 1
    assert result['sites']['P']['reason'] == 'Reference patch cropped'


def test_no_measurable_sites(tmp_path):
    paths = fixture(tmp_path)
    edit(paths[-1], lambda d:d.update(sites={'N':{'reason':'Unavailable homologous site'}}))
    result = metric(paths)
    assert result['status']=='not_assessed' and result['summary_3d'] is None and result['summary_in_plane'] is None


@pytest.mark.parametrize('access',['seen','used'])
def test_documented_reference_access(tmp_path, access):
    paths = fixture(tmp_path)
    edit(paths[-1], lambda d:d.update(reference_access=access))
    result = metric(paths)
    assert result['reference_access'] == access and result['measured_count'] == 0
    assert result['summary_3d'] is None and all(v['distance_3d_mm'] is None for v in result['sites'].values())


def test_copied_fit_never_scores_zero_error(tmp_path):
    skull, face, target, review = fixture(tmp_path)
    target.write_bytes(face.read_bytes())
    edit(review,lambda d:d.update(reference_sha256=d['face_sha256']))
    result = metric((skull,face,target,review))
    assert 'identical' in result['reason'] and result['summary_in_plane'] is None


@pytest.mark.parametrize('which',[0,1,2])
def test_hash_mismatch_no_partial_cli_output(tmp_path,which,capsys):
    paths = fixture(tmp_path)
    paths[which].write_bytes(paths[which].read_bytes()+b'\n')
    skull, face, target, review = map(str,paths)
    assert main(['--skull',skull,'--face',face,'--profile-reference',target,'--profile-review',review]) == 2
    capture = capsys.readouterr()
    assert not capture.out and 'exact skull, face and reference' in capture.err


def test_inventory_and_unchanged_legacy_reviews(tmp_path, capsys):
    skull, face, target, review = fixture(tmp_path)
    args = ['--skull',str(skull),'--face',str(face)]
    assert main([*args,'--profile-review',str(review)]) == 2
    assert '--profile-reference' in capsys.readouterr().err
    base = measure(skull,face)
    assert set(base['input_sha256']) == {'face','skull'} and 'profile_error' not in base
    vertex_review = tmp_path/'vertices.json'
    vertex_review.write_text(json.dumps(dict(schema='gnm.coherence-review.v1',
        **{k+'_sha256':v for k,v in base['input_sha256'].items()},review_source='Synthetic selected vertices',
        bone_solid_reviewed=False,eligible_face_vertices=[0,1])))
    args += ['--review',str(vertex_review),'--profile-reference',str(target)]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['profile_error']['summary_3d'] is None
    assert result['input_sha256']['reference'] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert main([*args,'--profile-review',str(review)]) == 0
    assert json.loads(capsys.readouterr().out)['skin_in_bone'] == result['skin_in_bone']


@pytest.mark.parametrize('change',[
    lambda d:d['plane'].update(normal_world=[0,0,0]),lambda d:d['plane'].update(tolerance_mm=True),
    lambda d:d['sites']['N']['reference'].update(barycentric=[.6,.5,0]),
    lambda d:d['sites']['Gl']['approx'].update(triangle=True),
    lambda d:d['sites']['Gl']['approx'].update(triangle=1),
    lambda d:d['sites'].update(N={'reason':'unknown'}),
    lambda d:d.update(reference_access='unknown'),lambda d:d.update(registration_source=''),
    lambda d:d.update(sites={})])
def test_invalid_review(tmp_path,change):
    paths = fixture(tmp_path)
    edit(paths[-1],change)
    with pytest.raises(ValueError):
        metric(paths)


def test_degenerate_reference_anchor(tmp_path):
    skull,face,target,review = fixture(tmp_path)
    export_obj(target,[[0,0,0],[0,1,0],[0,2,0]],[[0,1,2]])
    edit(review,lambda d:d.update(reference_sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    result = metric((skull,face,target,review))
    assert result['sites']['Gl']['reason'] == 'Degenerate anchor triangle' and result['summary_3d'] is None


def test_oblique_sagittal_plane_with_nonunit_normal(tmp_path):
    rotation = np.array([[.6,-.8,0.],[.8,.6,0.],[0.,0.,1.]])
    result = metric(fixture(tmp_path,rotation=rotation,shift=np.array([-2.,8.,3.])))
    row = result['sites']['N']
    assert row['distance_3d_mm'] == pytest.approx(np.sqrt(26))
    assert row['distance_in_plane_mm'] == pytest.approx(5)
    assert row['reference_plane_offset_mm'] == pytest.approx(1)

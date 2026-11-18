import numpy as np
import pytest

from cranio import landmark_atlas as atlas
from cranio.landmarks import marker_labels
from cranio.paper_reference import DOI


def test_reference_catalogue_keeps_each_marker_and_its_own_source():
    cards = [atlas.card(label) for label in marker_labels()]
    assert len(cards) == len({row['label'] for row in cards}) == 48
    assert sum(c['definition_source'] is not None for c in cards) == 32
    assert all(c['status'] == 'needs_expert_review' for c in cards)
    assert DOI in atlas.card('Suborbitale_Dr')['definition_source']
    assert 'foramen' in atlas.card('Suborbitale_Dr')['caution']
    assert atlas.card('Infraorbitale_Dr')['definition'] is None
    assert 'foramen' in atlas.card('Infraorbitale_Dr')['placement_hint']
    assert atlas.card('Infraorbitale_Dr')['definition_source'] is None
    assert atlas.card('Menton')['definition'] != atlas.card('Gnathion')['definition']
    assert atlas.card('Orbita_Dr_Int')['side'] == 'right'
    assert atlas.card('Orbita_St_Int')['side'] == 'left'
    assert atlas.card('Midphiltrum')['caution']
    with pytest.raises(ValueError): atlas.card('external_unmapped_label')


@pytest.mark.parametrize('axis', atlas.VIEWS)
def test_view_orientation_and_projection_round_trip(axis):
    vertices = np.array([[-2,0,1],[1.,3,4],[3,1,-5]])
    view = atlas.make_view(vertices, axis, 176)
    desired = np.zeros(3)
    desired['XYZ'.index(axis[1])] = 1 if axis[0]=='+' else -1
    np.testing.assert_array_equal(view.toward, desired)
    np.testing.assert_array_equal(np.cross(view.right,view.up), desired)
    for point in vertices:
        px,py = view.project(point)
        assert -.5 < px < 176 and -.5 < py < 176
        delta = view.ray_origin(px,py)-point
        assert delta @ view.toward > 0
        np.testing.assert_allclose(delta, (delta @ view.toward)*view.toward, atol=1e-12)


@pytest.mark.parametrize('points,axis', [([[1,1,1]]*3,'+Z'), ([[np.nan,0,0]]*3,'-Y'),
                                        ([0,1,2],'+X'), (np.eye(3),'anterior')])
def test_degenerate_or_undeclared_frame_fails(points, axis):
    with pytest.raises(ValueError): atlas.make_view(points, axis, 160)

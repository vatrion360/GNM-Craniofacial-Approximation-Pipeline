import json

import numpy as np
import pytest

from cranio.config import PipelineConfig
from cranio.io_csv import write_marker_csv_v3
from cranio.marker_audit import audit_landmarks, require_unique_landmarks
from cranio.pipeline import run_pipeline
from cranio.regularization import adaptive_lambda, tuning_key
from cranio.restoration import donor_half, fit_reference_plane, reflect_points


@pytest.mark.parametrize('n,expected', [(0, 1000), (4, 12), (6, 8), (12, 4), (24, 2), (32, 1.5), (48, 1)])
def test_count_based_regularization(n, expected):
    assert adaptive_lambda(n) == expected


def test_lambda_bounds_and_invalid_settings():
    assert adaptive_lambda(1000) == .3
    assert adaptive_lambda(1, 100) == 1000
    for args in [(-1,), (2.5,), (4, float('nan')), (4, 1, 20, 10)]:
        with pytest.raises(ValueError):
            adaptive_lambda(*args)


def test_loo_cache_depends_on_constraint_identity_not_just_count():
    vertices, xyz, weights = [1, 2, 3], np.eye(3), np.ones(3)
    key = tuning_key(vertices, xyz, weights, 'model1')
    assert key == tuning_key(vertices, xyz.copy(), weights.copy(), 'model1')
    assert key != tuning_key([1, 2, 4], xyz, weights, 'model1')
    assert key != tuning_key(vertices, xyz + .1, weights, 'model1')
    assert key != tuning_key(vertices, xyz, [1, 1, .5], 'model1')
    assert key != tuning_key(vertices, xyz, weights, 'model2')


@pytest.mark.parametrize('labels,vertices,xyz,match', [
    (['A', 'A'], [1, 2], [[0, 0, 0], [1, 0, 0]], 'Duplicate label'),
    (['A', 'B'], [1, 1], [[0, 0, 0], [1, 0, 0]], 'Duplicate GNM vertex'),
    (['A', 'B'], [1, 2], [[0, 0, 0], [0, 0, 0]], 'Coincident skin targets'),
])
def test_runtime_duplicate_constraints_are_rejected(labels, vertices, xyz, match):
    with pytest.raises(ValueError, match=match):
        require_unique_landmarks(labels, vertices, xyz)


def test_near_bone_sites_warn_without_merging_distinct_sites():
    result = audit_landmarks(['A', 'B'], [1, 2], [[0, 0, 0], [1, 0, 0]],
                             {'A': [1, 1, 1], 'B': [1.01, 1, 1]})
    assert result['included_count'] == 2 and not result['errors']
    assert len(result['warnings']) == 1


def test_adaptive_offline_count_uses_only_remaining_constraints(tmp_path, model_file, marker_file):
    import csv
    lines = marker_file.read_text().splitlines()
    rows = list(csv.DictReader(lines[2:]))
    rows[0]['use_for_fit'] = 0
    write_marker_csv_v3(marker_file, rows, json.loads(lines[1][1:]))
    cfg = PipelineConfig(input=marker_file, npz=model_file, output=tmp_path/'face.obj',
                         regularization='adaptive', exclude=['P1', 'P2'])
    assert run_pipeline(cfg) == 0
    report = json.loads(open(cfg.output_json).read())
    assert len(report['landmarks']) == 9
    assert report['lambda'] == pytest.approx(48 / 9)


def test_plane_and_reflection_work_in_rotated_translated_frame():
    angle = .37
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    points = np.array([[0, 0, 0], [0, 3, 0], [0, 0, 4], [0, 2, 3]]) @ rotation.T + [7, 8, 9]
    centre, normal, rms = fit_reference_plane(points)
    assert rms < 1e-10
    assert abs(normal @ rotation[:, 0]) > .999999
    donor = np.array([[2, 1, 1], [2, 3, 1], [3, 2, 3]]) @ rotation.T + [7, 8, 9]
    mirrored = reflect_points(donor, centre, normal)
    assert np.allclose(reflect_points(mirrored, centre, normal), donor)
    assert donor_half(donor, centre, normal) == -donor_half(mirrored, centre, normal)


def test_degenerate_plane_and_mixed_side_donor_are_rejected():
    with pytest.raises(ValueError):
        fit_reference_plane([[0, 0, 0], [0, 1, 0], [0, 2, 0]])
    with pytest.raises(ValueError, match='nearly collinear'):
        fit_reference_plane([[0, 0, 0], [0, 100, .001], [0, 200, 0]])
    with pytest.raises(ValueError, match='both sides'):
        donor_half([[2, 0, 0], [-2, 0, 0]], [0, 0, 0], [1, 0, 0])
    with pytest.raises(ValueError, match='midline'):
        donor_half([[0, 1, 0], [0, 2, 0]], [0, 0, 0], [1, 0, 0])

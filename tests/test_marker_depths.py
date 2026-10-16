"""Arithmetic contract for the Blender-only manual percentage editor."""
import math
import pytest
from cranio.blender_marker_depths import adjusted_depth


@pytest.mark.parametrize('depth,percent,mode,expected', [
    (10, 20, 'INCREASE', 12), (10, 20, 'DECREASE', 8),
    (12, 20, 'DECREASE', 9.6), (8, 0, 'INCREASE', 8),
    (8, 100, 'DECREASE', 0), (0, 50, 'INCREASE', 0),
    (2, 150, 'INCREASE', 5),
])
def test_manual_percentage(depth, percent, mode, expected):
    assert adjusted_depth(depth, percent, mode) == pytest.approx(expected)


@pytest.mark.parametrize('depth,percent,mode', [
    (10, 100.1, 'DECREASE'), (10, -1, 'INCREASE'), (-1, 10, 'INCREASE'),
    (math.nan, 10, 'INCREASE'), (math.inf, 10, 'INCREASE'),
    (10, math.nan, 'INCREASE'), (10, math.inf, 'DECREASE'),
    (10, 10, 'unknown'), (3e38, 100, 'INCREASE'),
])
def test_invalid_depth_change_is_rejected(depth, percent, mode):
    with pytest.raises(ValueError):
        adjusted_depth(depth, percent, mode)

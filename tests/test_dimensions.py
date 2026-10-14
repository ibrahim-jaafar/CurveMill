import pytest

from curvemill.dimensions import (
    Dimension,
    Feature,
    OverConstrainedError,
    is_overconstrained,
    measure,
    nearest_feature,
    solve_axis,
)

BOARD = (0.0, 0.0, 600.0, 400.0)


def _pat(feat_kind, h, v):
    return Feature(feat_kind, h, v)


def test_measure_reports_signed_axis_distance():
    pat = (10.0, 20.0, 60.0, 80.0)
    dim = Dimension(_pat("pattern", "left", "center"), _pat("pattern", "right", "center"), axis="x")
    assert measure(dim, pat, BOARD) == pytest.approx(50.0)


def test_size_dim_scales_about_centre():
    pat = (10.0, 10.0, 110.0, 60.0)  # 100 wide
    dim = Dimension(_pat("pattern", "left", "center"), _pat("pattern", "right", "center"), axis="x", value=200.0)
    scale, translate = solve_axis([dim], pat, BOARD, "x")
    assert scale == pytest.approx(2.0)
    assert translate == pytest.approx(0.0)


def test_single_position_dim_translates_without_scaling():
    pat = (10.0, 0.0, 110.0, 50.0)
    # board-left to pattern-left = current 10 (left margin); drive it to 50.
    dim = Dimension(_pat("pattern", "left", "center"), _pat("board", "left", "center"), axis="x", value=5.0)
    scale, translate = solve_axis([dim], pat, BOARD, "x")
    assert scale == pytest.approx(1.0)
    center = (pat[0] + pat[2]) / 2.0
    new_left = center + (pat[0] - center) * scale + translate
    # value = coord(feat2=board-left=0) - coord(feat1=pattern-left) == 5 => pattern-left = -5
    assert new_left == pytest.approx(-5.0)


def test_two_position_dims_solve_scale_and_translate():
    pat = (10.0, 0.0, 110.0, 50.0)  # 100 wide
    left_margin = Dimension(_pat("board", "left", "center"), _pat("pattern", "left", "center"), axis="x", value=50.0)
    right_margin = Dimension(_pat("pattern", "right", "center"), _pat("board", "right", "center"), axis="x", value=50.0)
    scale, translate = solve_axis([left_margin, right_margin], pat, BOARD, "x")
    center = (pat[0] + pat[2]) / 2.0
    new_left = center + (pat[0] - center) * scale + translate
    new_right = center + (pat[2] - center) * scale + translate
    assert new_left == pytest.approx(50.0)
    assert new_right == pytest.approx(550.0)  # board 600 - 50 margin


def test_size_override_forces_scale():
    pat = (0.0, 0.0, 100.0, 50.0)
    scale, translate = solve_axis([], pat, BOARD, "x", size_override=250.0)
    assert scale == pytest.approx(2.5)
    assert translate == pytest.approx(0.0)


def test_three_driving_dims_raise():
    pat = (0.0, 0.0, 100.0, 50.0)
    dims = [
        Dimension(_pat("pattern", "left", "center"), _pat("board", "left", "center"), axis="x", value=0.0)
        for _ in range(3)
    ]
    assert is_overconstrained(dims)
    with pytest.raises(OverConstrainedError):
        solve_axis(dims, pat, BOARD, "x")


def test_two_size_dims_raise():
    pat = (0.0, 0.0, 100.0, 50.0)
    dims = [
        Dimension(_pat("pattern", "left", "center"), _pat("pattern", "right", "center"), axis="x", value=100.0)
        for _ in range(2)
    ]
    assert is_overconstrained(dims)
    with pytest.raises(OverConstrainedError):
        solve_axis(dims, pat, BOARD, "x")


def test_conflicting_position_dims_raise():
    pat = (10.0, 0.0, 110.0, 50.0)
    # Both pin the same pattern feature to the board but demand different gaps.
    a = Dimension(_pat("board", "left", "center"), _pat("pattern", "left", "center"), axis="x", value=50.0)
    b = Dimension(_pat("board", "left", "center"), _pat("pattern", "left", "center"), axis="x", value=80.0)
    with pytest.raises(OverConstrainedError):
        solve_axis([a, b], pat, BOARD, "x")


def test_nearest_feature_snaps_to_closest_corner():
    pat = (5.0, 5.0, 100.0, 50.0)
    feat = nearest_feature(6.0, 6.0, pat, BOARD, 10.0)
    assert feat == Feature("pattern", "left", "bottom")


def test_nearest_feature_returns_none_outside_tolerance():
    pat = (5.0, 5.0, 100.0, 50.0)
    assert nearest_feature(300.0, 300.0, pat, BOARD, 5.0) is None


def test_edges_are_clickable_along_their_whole_length():
    pat = (5.0, 5.0, 100.0, 50.0)
    # Near the pattern's left edge, far from its midpoint or corners.
    feat = nearest_feature(6.0, 15.0, pat, BOARD, 5.0)
    assert feat == Feature("pattern", "left", "center")
    # Near the board's bottom edge.
    feat = nearest_feature(400.0, 2.0, pat, BOARD, 5.0)
    assert feat == Feature("board", "center", "bottom")


def test_corner_wins_over_edge_when_both_in_reach():
    pat = (5.0, 5.0, 100.0, 50.0)
    feat = nearest_feature(7.0, 8.0, pat, BOARD, 10.0)
    assert feat == Feature("pattern", "left", "bottom")

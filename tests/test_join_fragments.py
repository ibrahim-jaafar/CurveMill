"""Tests for joining Inkscape's fragmented bezier SPLINEs back into whole shapes."""

from curvemill.geometry import join_spline_fragments
from curvemill.models import SplineEntity


def _bezier(p0, p1, p2, p3, layer="0"):
    return SplineEntity(control_points=[p0, p1, p2, p3], degree=3, layer=layer)


def test_joins_fragments_into_one_spline_per_shape():
    # Two beziers of one path, stored out of order and with the second reversed
    # (Inkscape's exporter guarantees neither order nor direction).
    fragments = [
        _bezier((10, 10), (10, 5), (5, 0), (0, 0)),  # reversed: ends where the other starts
        _bezier((10, 10), (12, 14), (16, 18), (20, 20)),
    ]
    joined = join_spline_fragments(fragments)

    assert len(joined) == 1
    # Two chained cubics -> 3n+1 control points, running end to end.
    assert len(joined[0].control_points) == 7
    assert joined[0].degree == 3
    ends = {joined[0].control_points[0], joined[0].control_points[-1]}
    assert ends == {(0.0, 0.0), (20.0, 20.0)}
    assert not joined[0].closed


def test_hard_corners_split_into_one_spline_per_side():
    # Four straight bezier sides meeting at 90-degree corners. Joining them into
    # one closed spline would survive a fit-point resample only by rounding the
    # corners and bowing the sides (the "wavy straight lines" export bug), so the
    # chain must be cut at every corner: one spline per side, none closed.
    square = [
        _bezier((0, 0), (3, 0), (7, 0), (10, 0)),
        _bezier((10, 0), (10, 3), (10, 7), (10, 10)),
        _bezier((10, 10), (7, 10), (3, 10), (0, 10)),
        _bezier((0, 10), (0, 7), (0, 3), (0, 0)),
    ]
    far_away = [_bezier((99, 99), (99, 96), (99, 93), (99, 90))]

    joined = join_spline_fragments(square + far_away)

    assert len(joined) == 5  # 4 sides + the disconnected fragment, never chained together
    assert not any(s.closed for s in joined)  # a cornered side is not a closed loop
    assert all(len(s.control_points) == 4 for s in joined)  # each side stays one bezier


def test_smooth_closed_loop_stays_one_closed_spline():
    # A tangent-continuous loop (4-bezier circle) has no corners, so it must NOT
    # be split -- it stays a single closed spline (one SolidWorks element).
    k = 5.522847498  # kappa * r for a radius-10 circle
    circle = [
        _bezier((10, 0), (10, k), (k, 10), (0, 10)),
        _bezier((0, 10), (-k, 10), (-10, k), (-10, 0)),
        _bezier((-10, 0), (-10, -k), (-k, -10), (0, -10)),
        _bezier((0, -10), (k, -10), (10, -k), (10, 0)),
    ]

    joined = join_spline_fragments(circle)

    assert len(joined) == 1
    assert joined[0].closed
    assert len(joined[0].control_points) == 13


def test_non_bezier_splines_pass_through_untouched():
    # Only pure cubic beziers can be chained; a 5-point spline must survive as-is.
    other = SplineEntity(control_points=[(0, 0), (1, 1), (2, 0), (3, 1), (4, 0)], degree=3)
    joined = join_spline_fragments([other])

    assert len(joined) == 1
    assert joined[0].control_points == other.control_points


def test_join_is_lossless():
    """The whole point: joining must not move the curve."""
    from ezdxf.math import Bezier4P, Vec2

    segments = [
        ((0, 0), (2, 6), (8, 8), (10, 10)),
        ((10, 10), (13, 12), (17, 9), (20, 4)),
    ]
    joined = join_spline_fragments([_bezier(*s) for s in segments])[0]

    from ezdxf.math import BSpline
    curve = BSpline(joined.control_points, order=joined.degree + 1, knots=joined.knots)
    for index, seg in enumerate(segments):
        source = Bezier4P([Vec2(p) for p in seg])
        for t in (0.0, 0.5, 1.0):
            assert source.point(t).distance(curve.point(index + t)) < 1e-9

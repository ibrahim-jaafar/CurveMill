"""Smooth Corners: fillet sharp corners on raw polylines AND optimized splines.

A corner is a tangent break, which after Optimize lives at the shared endpoint
of two separate entities -- so the feature must weld coincident pieces into one
chain and round the junction, not just interior polyline vertices.
"""

import math

from curvemill.editor import EditorModel, _round_chain
from curvemill.geometry import CORNER_DEGREES
from curvemill.models import SplineEntity, VectorEntity

SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def _max_deflection(points, closed):
    pts = points[:-1] if closed and points[0] == points[-1] else points
    n = len(pts)
    worst = 0.0
    rng = range(n) if closed else range(1, n - 1)
    for i in rng:
        a, b, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        d1 = math.hypot(b[0] - a[0], b[1] - a[1])
        d2 = math.hypot(c[0] - b[0], c[1] - b[1])
        if d1 == 0 or d2 == 0:
            continue
        dot = ((b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1])) / (d1 * d2)
        worst = max(worst, math.degrees(math.acos(max(-1.0, min(1.0, dot)))))
    return worst


def test_square_corners_become_smooth():
    assert _max_deflection(SQUARE, True) > CORNER_DEGREES  # starts sharp
    rounded, changed = _round_chain(SQUARE, True, 2.0, "all", CORNER_DEGREES)
    assert changed
    assert len(rounded) > len(SQUARE)
    assert (0.0, 0.0) not in rounded  # every hard corner replaced by an arc
    assert _max_deflection(rounded, True) <= CORNER_DEGREES  # no corner survives


def test_mode_respects_convex_vs_reflex():
    # A CCW square is all-convex ("outside" tips), so "inside" has nothing to do.
    _, out = _round_chain(SQUARE, True, 2.0, "outside", CORNER_DEGREES)
    _, inside = _round_chain(SQUARE, True, 2.0, "inside", CORNER_DEGREES)
    assert out is True
    assert inside is False


def test_radius_clamped_to_fit_short_legs():
    # Radius 100 can't fit a 10mm square; it shrinks to fit instead of blowing up.
    rounded, changed = _round_chain(SQUARE, True, 100.0, "all", CORNER_DEGREES)
    assert changed
    xs = [p[0] for p in rounded]
    ys = [p[1] for p in rounded]
    assert min(xs) >= -1e-6 and max(xs) <= 10.0 + 1e-6
    assert min(ys) >= -1e-6 and max(ys) <= 10.0 + 1e-6


def test_cross_entity_corner_is_welded_and_rounded():
    # Two SEPARATE open polylines meeting at (10,0): the corner is between them,
    # not inside either -- the post-Optimize case. They must weld and round.
    v1 = VectorEntity(points=[(0.0, 0.0), (10.0, 0.0)], layer="0")
    v2 = VectorEntity(points=[(10.0, 0.0), (10.0, 10.0)], layer="0")
    editor = EditorModel(vectors=[v1, v2])
    editor.selected_ids = {v1.id, v2.id}
    assert editor.round_corners(2.0, "all")
    assert not editor.splines  # pure polylines stay polylines
    pts = [p for v in editor.vectors for p in v.points]
    assert (10.0, 0.0) not in pts  # the shared corner got filleted away


def test_spline_corner_rounds_and_stays_a_spline():
    # The real post-Optimize case: a single fit-point spline CAN'T hold a corner,
    # so an L is TWO splines meeting at (10,0). Rounding that junction must weld
    # them, round it, and re-emit splines (preserving the SolidWorks element count
    # -- not flatten to lines).
    horizontal = SplineEntity(
        control_points=[], fit_points=[(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)], layer="0"
    )
    vertical = SplineEntity(
        control_points=[], fit_points=[(10.0, 0.0), (10.0, 5.0), (10.0, 10.0)], layer="0"
    )
    editor = EditorModel(splines=[horizontal, vertical])
    editor.selected_spline_ids = {horizontal.id, vertical.id}
    assert editor.round_corners(2.0, "all")
    assert editor.splines  # re-fit output, not flattened to lines
    assert not editor.vectors
    flat = [p for s in editor.splines for p in s.flatten(0.2).points]
    assert _max_deflection(flat, False) < 80.0  # the 90-degree corner is gone

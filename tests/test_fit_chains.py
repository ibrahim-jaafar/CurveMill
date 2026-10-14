"""Tests for rebuilding loose LINE soup into native splines."""

import math

from curvemill.geometry import (
    _fit_self_crosses,
    _straight_cubic,
    fit_vector_chains,
    to_fit_splines,
)
from curvemill.models import SplineEntity, VectorEntity


def _segments(points, layer="0"):
    """One VectorEntity per segment -- how pattern DXFs actually arrive."""
    return [
        VectorEntity(points=[points[i], points[i + 1]], layer=layer)
        for i in range(len(points) - 1)
    ]


def _straight(a, b):
    """A straight spline piece between two points, like the fallback emits."""
    return SplineEntity(control_points=_straight_cubic(a, b), degree=3,
                        knots=None, closed=False, layer="0")


def test_fit_self_crosses_flags_only_fit_introduced_crossings():
    # This guards the SolidWorks "no solution found" fix: the corner-split fit
    # bulges ~0.1mm off the polyline, and on a thin shape the two sides cross,
    # yielding a self-intersecting profile SolidWorks refuses to cut. The guard
    # must fire ONLY when the fit introduced the crossing -- a clean fit, or a
    # source that was already crossing (Repair's job), must be left alone.
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    crossing = [_straight((0, 0), (10, 10)), _straight((10, 0), (0, 10))]  # an X
    clean = [_straight((0, 0), (10, 0)), _straight((10, 0), (10, 10)),
             _straight((10, 10), (0, 10)), _straight((0, 10), (0, 0))]

    assert _fit_self_crosses(square, crossing, 1e-4) is True   # fit introduced it
    assert _fit_self_crosses(square, clean, 1e-4) is False     # fit is clean

    bowtie = [(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)]      # source crosses
    assert _fit_self_crosses(bowtie, crossing, 1e-4) is False  # not our regression

    open_run = [(0, 0), (10, 0), (10, 10)]                     # not a closed loop
    assert _fit_self_crosses(open_run, crossing, 1e-4) is False


def test_corner_shape_seam_welds_bit_exact_for_solidworks():
    # A closed shape WITH corners splits into separate spline pieces; the closing
    # segment lands within join tolerance of the start but not bit-exact. Unwelded,
    # that sub-micron gap reads as an OPEN profile in SolidWorks (the 5-opens bug).
    # The loop must close bit-exact: first piece's start == last piece's end.
    eps = 1e-6  # < the 1e-4 join tolerance, > SolidWorks' ~1e-8 m merge tolerance
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (eps, eps)]
    fitted = to_fit_splines(fit_vector_chains(_segments(square)))

    assert len(fitted) > 1  # corners split it into pieces, so the seam is real
    assert fitted[0].fit_points[0] == fitted[-1].fit_points[-1]  # bit-exact, not ~=


def test_sampled_curve_becomes_one_spline():
    # A circle sampled into 60 separate LINEs must come back as a single curve.
    pts = [(10 * math.cos(t * math.tau / 60), 10 * math.sin(t * math.tau / 60))
           for t in range(61)]
    fitted = fit_vector_chains(_segments(pts))

    assert len(fitted) == 1
    assert fitted[0].degree == 3
    assert fitted[0].closed
    # Far fewer entities than the 60 we started with, and still a real curve.
    assert len(fitted[0].control_points) < 200


def test_fit_passes_through_every_source_point():
    """The whole point: reducing entity count must not move the geometry."""
    from ezdxf.math import BSpline

    pts = [(x, math.sin(x / 5) * 8) for x in range(0, 60, 2)]
    fitted = fit_vector_chains(_segments(pts))
    assert len(fitted) == 1

    # Rebuilt from the stored control points and knots, so this also proves the
    # SplineEntity round-trip is intact -- that is what gets written to the DXF.
    curve = BSpline(fitted[0].control_points, order=4, knots=fitted[0].knots)
    # Evaluated at the knots, not by sampling: sampling a curve and measuring to
    # the resulting polyline has a chord-gap floor that hides real error. The fit
    # densifies long runs before interpolating (kills the high-curvature overshoot),
    # so there are now more knots than source points -- but every ORIGINAL point
    # must still land exactly on the curve, since densify only inserts colinear
    # points between them and never moves them.
    knot_points = [(curve.point(t).x, curve.point(t).y) for t in sorted(set(fitted[0].knots))]
    assert len(knot_points) >= len(pts)
    for point in pts:
        assert min(math.dist(kp, point) for kp in knot_points) < 1e-9


def test_sparse_run_into_a_tight_radius_does_not_overshoot():
    """A long straight (Douglas-Peucker thins it to 2 points) leading into a tight
    radius made the single interpolating cubic bulge ~1.3mm off the milled wall --
    the "wave" a user saw entering sharp curvature after Replace-with-Simulated.
    fit_vector_chains densifies the long runs first, so the fit stays pinned to the
    outline as ONE spline (not the corner-angle workaround that shatters it).
    """
    from shapely.geometry import LineString, Point

    r, cx, cy = 3.0, 40.0, 3.0
    pts = [(0.0, 0.0), (40.0, 0.0)]  # long straight, DP-thinned to two points
    pts += [(cx + r * math.sin(math.radians(a)), cy - r * math.cos(math.radians(a)))
            for a in (0, 25, 50, 75, 90)]
    pts += [(cx + r, cy + 30.0)]  # exit straight

    fitted = fit_vector_chains(_segments(pts))
    # One smooth spline -- not the straight-segment fallback (would be ~7 here).
    assert len(fitted) == 1
    flat = [p for spline in fitted for p in spline.flatten(0.01).points]
    overshoot = max(LineString(pts).distance(Point(p)) for p in flat)
    # Undensified this run overshoots ~1.3mm; densified it hugs the wall.
    assert overshoot < 0.25


def test_smooth_circle_stays_one_spline_at_any_sampling():
    """A smooth closed curve must not shatter into the straight-segment fallback.

    Densify used to place its last insert a hair before a segment's end whenever the
    length was not a clean multiple of the step; that near-duplicate point kinked the
    interpolating cubic into a microscopic self-loop, tripping _fit_self_crosses. A
    plain circle sampled at ~2mm chords (R8 -> 25-gon, R20 -> 62-gon) came back as 25
    or 62 straight segments instead of one spline -- an element-count blow-up in
    SolidWorks. Even-spaced inserts never sit near a vertex, so it stays one spline.
    """
    for radius, sides in [(8.0, 25), (20.0, 62), (4.0, 13)]:  # all turn < corner angle
        pts = [(radius * math.cos(a * math.tau / sides),
                radius * math.sin(a * math.tau / sides)) for a in range(sides + 1)]
        fitted = fit_vector_chains(_segments(pts))
        assert len(fitted) == 1, f"R={radius} {sides}-gon fell to the fallback"
        assert fitted[0].closed


def test_flatten_draws_the_whole_joined_curve():
    """A joined spline's knots run 0..segment-count, not 0..1.

    Feeding flatten's 0..1 parameter straight to the NURBS evaluator drew only the
    first segment, so the canvas showed slivers and milling found no real profiles.
    """
    pts = [(10 * math.cos(t * math.tau / 60), 10 * math.sin(t * math.tau / 60))
           for t in range(61)]
    flat = fit_vector_chains(_segments(pts))[0].flatten(0.5).points

    width = max(x for x, _ in flat) - min(x for x, _ in flat)
    assert width > 19.0  # the full circle is 20 wide; a single segment is a sliver


def test_hard_corner_splits_so_it_stays_sharp():
    # An L: a single spline through the corner would round it off.
    pts = [(0, 0), (10, 0), (20, 0), (20, 10), (20, 20)]
    fitted = fit_vector_chains(_segments(pts))

    assert len(fitted) == 2
    ends = {f.control_points[0] for f in fitted} | {f.control_points[-1] for f in fitted}
    assert (20.0, 0.0) in ends  # the corner survives as a real endpoint


def test_disconnected_shapes_stay_separate():
    near = _segments([(0, 0), (5, 1), (10, 0)])
    far = _segments([(99, 99), (95, 98), (90, 99)])

    assert len(fit_vector_chains(near + far)) == 2


def test_straight_run_stays_straight():
    fitted = fit_vector_chains(_segments([(0, 0), (5, 0), (10, 0)]))

    assert len(fitted) == 1
    assert all(abs(y) < 1e-9 for _x, y in fitted[0].control_points)


def test_to_fit_splines_samples_lie_on_the_curve():
    """SolidWorks counts a fit-point spline as ONE element; the samples we hand
    it must be exact points of the source curve, seam bit-identical if closed."""
    pts = [(10 * math.cos(t * math.tau / 60), 10 * math.sin(t * math.tau / 60))
           for t in range(61)]
    source = fit_vector_chains(_segments(pts))[0]
    converted = to_fit_splines([source])

    assert len(converted) == 1
    fit = converted[0]
    assert not fit.control_points  # export writes the fit-point branch
    assert fit.closed and fit.fit_points[0] == fit.fit_points[-1]
    # Every fit point is an exact evaluation of the source curve at its own
    # uniform parameter (not a control point or an approximation). The closed
    # seam (last point) is forced to equal the first, so check the interior.
    count = len(fit.fit_points) - 1
    for i, sample in enumerate(fit.fit_points[:-1]):
        assert math.dist(sample, source._evaluate(i / count)) < 1e-9


def test_to_fit_splines_samples_by_arc_length_not_per_segment():
    """A long, straight-ish run must get intermediate samples so SolidWorks'
    interpolating refit can't overshoot it into a 'dog bone'. A flat count per
    segment under-sampled long segments; sampling must be arc-length-bounded:
    no two consecutive fit points farther apart than roughly max_step."""
    from curvemill.models import SplineEntity

    # One straight cubic spanning 40mm: a single segment, so the old code emitted
    # just `per_segment` points across the whole span (~13mm apart).
    line = SplineEntity(
        control_points=[(0.0, 0.0), (13.3, 0.0), (26.6, 0.0), (40.0, 0.0)],
        knots=[0, 0, 0, 0, 1, 1, 1, 1], degree=3, closed=False,
    )
    fit = to_fit_splines([line], max_step=0.5)[0]
    gaps = [math.dist(a, b) for a, b in zip(fit.fit_points, fit.fit_points[1:])]
    # Sampling is uniform in parameter, not arc length, so spacing can drift a
    # few % past max_step -- the guarantee is "roughly every max_step", enough to
    # bound overshoot. The old per-segment code left one ~13mm gap here (26x over).
    assert max(gaps) <= 0.5 * 1.2
    assert len(fit.fit_points) >= 40 / 0.5  # long span densified, not 5 points


def test_fit_only_spline_still_flattens():
    """Re-imported optimized files have no control net; canvas and milling
    both go through flatten, which must fall back to the fit points."""
    from curvemill.models import SplineEntity

    spline = SplineEntity(control_points=[], fit_points=[(0, 0), (5, 3), (10, 0)],
                          closed=False)
    flat = spline.flatten(0.5)
    assert flat.points == [(0, 0), (5, 3), (10, 0)]

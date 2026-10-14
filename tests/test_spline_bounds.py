"""SplineEntity.bounds() must hug the curve, not the control net.

Control points bulge outside a NURBS curve (convex-hull property). A
control-point bbox over-reports the extent, which showed up as the dashed
selection gap and made size dimensions under-scale the SolidWorks export.
"""

from curvemill.models import SplineEntity


def test_bounds_hug_curve_not_control_points():
    # A cubic with a wildly out-of-line middle control point: the control net
    # spans y up to 100, but the curve only bulges to a fraction of that.
    spline = SplineEntity(
        control_points=[(0.0, 0.0), (33.0, 100.0), (66.0, 100.0), (100.0, 0.0)],
        degree=3,
    )
    x1, y1, x2, y2 = spline.bounds()
    curve_top = spline.flatten(0.5).bounds()[3]

    assert y2 == max(p[1] for p in spline.flatten(0.5).points)  # measures the curve
    assert y2 < 100.0 - 1.0            # NOT the control-point extent (=100)
    assert y2 == curve_top
    assert x1 == 0.0 and x2 == 100.0   # endpoints are on the curve, so x is exact


def test_fit_point_only_spline_bounds_are_exact():
    # Re-imported optimized splines have fit points on the curve, no control net.
    spline = SplineEntity(
        control_points=[],
        fit_points=[(0.0, 0.0), (5.0, 2.0), (10.0, 0.0)],
    )
    assert spline.bounds() == (0.0, 0.0, 10.0, 2.0)

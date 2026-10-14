"""Tests for the Potrace SVG output parser (no potrace binary required)."""

from curvemill.autotrace import _parse_svg_paths

# Shaped like real potrace 1.16 output: one path element holding an outer
# contour and a hole, a y-flipping group transform, and implicit relative
# linetos after the explicit "l".
_SVG = """<svg width="100.000000pt" height="80.000000pt" viewBox="0 0 100 80">
<g transform="translate(0.000000,80.000000) scale(0.100000,-0.100000)"
fill="#000000" stroke="none">
<path d="M100 700 l0 -600 800 0 0 600 -800 0z m700 -100 l0 -400 -600 0
0 400 600 0z"/>
</g>
</svg>"""


def test_parse_svg_paths_applies_transform_and_splits_subpaths():
    splines = _parse_svg_paths(_SVG, px_to_mm=1.0)

    assert len(splines) == 2
    assert all(spline.closed for spline in splines)

    outer_x = [p[0] for p in splines[0].control_points]
    outer_y = [p[1] for p in splines[0].control_points]
    assert (min(outer_x), max(outer_x)) == (10.0, 90.0)
    assert (min(outer_y), max(outer_y)) == (10.0, 70.0)

    # The hole uses "m" + implicit relative linetos; getting these wrong
    # produced huge negative coordinates before the fix.
    inner_x = [p[0] for p in splines[1].control_points]
    inner_y = [p[1] for p in splines[1].control_points]
    assert (min(inner_x), max(inner_x)) == (20.0, 80.0)
    assert (min(inner_y), max(inner_y)) == (20.0, 60.0)


def test_traced_contour_is_one_spline_not_sampled_points():
    """The SolidWorks-crash regression: a curve must stay a curve.

    Sampling potrace's beziers into line segments made each contour explode
    into hundreds of sketch elements. Four beziers must yield one degree-3
    spline of 13 control points (3n+1), not a sampled polyline.
    """
    curved = (
        '<svg width="100.000000pt" height="100.000000pt">\n'
        '<g transform="translate(0.000000,100.000000) scale(0.100000,-0.100000)">\n'
        '<path d="M500 100 c220 0 400 180 400 400 c0 220 -180 400 -400 400 '
        'c-220 0 -400 -180 -400 -400 c0 -220 180 -400 400 -400z"/>\n'
        '</g></svg>'
    )
    splines = _parse_svg_paths(curved, px_to_mm=1.0)

    assert len(splines) == 1
    assert splines[0].degree == 3
    assert len(splines[0].control_points) == 13
    assert splines[0].closed

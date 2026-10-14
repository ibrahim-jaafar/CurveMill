"""Regression: tool-corrected geometry must be simplified before it reaches the
editor, or fitting the over-sampled walls self-crosses and fit_vector_chains'
anti-self-cross fallback emits one segment per point (measured: 88k pts -> 88k
SolidWorks entities on a real file)."""
import math

from shapely.geometry import Polygon

from curvemill.geometry import result_export_vectors, fit_vector_chains, join_spline_fragments
from curvemill.solidworks_bridge import curves_from_entities
from curvemill.models import ProcessResult


def _dense_circle_wkt(n: int = 2000, r: float = 20.0) -> str:
    ring = [(r * math.cos(t * 2 * math.pi / n), r * math.sin(t * 2 * math.pi / n)) for t in range(n)]
    return Polygon(ring).wkt


def _result(wkt: str) -> ProcessResult:
    return ProcessResult(
        repaired_vectors=[], toolpaths=[], removed_wkt="", remaining_wkt="",
        hidden_islands_wkt="", corrected_wkt=wkt,
    )


def test_corrected_geometry_is_simplified_not_dense():
    vectors = result_export_vectors(_result(_dense_circle_wkt(2000)))
    points = sum(len(v.points) for v in vectors)
    # 2000 raw points collapse to a small fraction; a smooth circle needs nowhere
    # near that many to stay within 0.02mm.
    assert points < 200, f"expected the dense circle to simplify, got {points} points"


def test_fitting_corrected_geometry_does_not_explode():
    vectors = result_export_vectors(_result(_dense_circle_wkt(2000)))
    curves = fit_vector_chains(vectors)
    # Without the simplify, the self-cross fallback would emit ~one curve per point.
    assert len(curves) < 50, f"fit exploded to {len(curves)} curves -- simplify regressed"


def test_optimize_reported_count_matches_solidworks_entity_count():
    # The Optimize message must report the SAME number the entity column and Send
    # show. fit_vector_chains emits control-point fragments; curves_from_entities
    # re-joins them, so the message's "after" is len(join_spline_fragments(curves)),
    # not len(curves). Guards the "88 -> 2500 vs actual 252" regression.
    vectors = result_export_vectors(_result(_dense_circle_wkt(2000)))
    curves = fit_vector_chains(vectors)
    reported_after = len(join_spline_fragments(curves))
    # curves_from_entities is what the layer column and Send both run on the result.
    column = len(curves_from_entities([], curves, 100.0, 100.0, 0.001))
    assert reported_after == column, f"message would say {reported_after}, column shows {column}"


def test_tolerance_controls_thinning():
    result = _result(_dense_circle_wkt(2000))
    coarse = sum(len(v.points) for v in result_export_vectors(result, tolerance=0.5))
    fine = sum(len(v.points) for v in result_export_vectors(result, tolerance=0.005))
    disabled = sum(len(v.points) for v in result_export_vectors(result, tolerance=0.0))
    assert coarse < fine < disabled  # looser tol -> fewer points; 0 keeps them all
    assert disabled == 2000

import pytest
from shapely import wkt

from curvemill.geometry import (
    assemble_closed_profiles,
    build_toolpaths,
    count_open_profiles,
    count_profile_issues,
    count_self_intersections,
    heal_self_intersections,
    process_vectors,
    repair_vectors,
    result_export_vectors,
    split_islands,
)
from curvemill.models import ProcessOptions, TraceMode, VectorEntity


def test_repair_snaps_and_closes_small_gap():
    vector = VectorEntity(points=[(0, 0), (10, 0), (10, 10), (0.1, 0.05)], closed=False)

    repaired = repair_vectors([vector], 0.25)[0]

    assert repaired.closed is True
    assert repaired.points == [(0.05, 0.025), (10, 0), (10, 10)]


def test_self_intersection_counted_and_healed():
    # A bowtie: the two diagonals cross, so SolidWorks rejects the profile even
    # though it is closed with no gaps, no duplicates and no over-used vertices.
    bowtie = VectorEntity(points=[(0, 0), (10, 10), (10, 0), (0, 10)], closed=True)
    clean = VectorEntity(points=[(20, 0), (30, 0), (30, 10), (20, 10)], closed=True)

    issues = count_profile_issues([bowtie, clean])
    assert issues.self_intersections == 1
    assert issues.open_profiles == 0 and issues.duplicates == 0 and issues.multi_vertex == 0

    healed, count = heal_self_intersections([bowtie, clean])
    assert count == 1
    # Splitting at the crossing yields the bowtie's two triangular lobes; the clean
    # square is passed through untouched.
    assert count_self_intersections(healed) == 0
    assert all(v.closed for v in healed)
    assert clean in healed  # untouched entity keeps its identity


def test_heal_splits_at_crossing_preserving_every_vertex():
    # The old buffer(0) heal rebuilt the ring's area and drifted its vertices, which
    # unstuck endpoints it shared with neighbours and opened them. Splitting at the
    # crossing must preserve every original vertex exactly and only ADD the crossing
    # node -- and be idempotent (a second heal finds nothing).
    bowtie = VectorEntity(points=[(0, 0), (10, 10), (10, 0), (0, 10)], closed=True)
    healed, count = heal_self_intersections([bowtie])
    assert count == 1

    out_points = {p for v in healed for p in v.points}
    for original in bowtie.points:
        assert original in out_points  # exact, not drifted
    assert (5.0, 5.0) in out_points  # the crossing node, added

    again, count_again = heal_self_intersections(healed)
    assert count_again == 0
    assert count_self_intersections(again) == 0


def test_heal_deletes_zero_area_self_crossing_specks():
    # Snap welds sub-tolerance fragments into closed loops with no enclosed face
    # (real file: 0.02mm specks the pattern generator left behind). They count as
    # self-intersections but polygonize finds nothing to split, so the old heal
    # kept them and the count stuck forever. Nothing SolidWorks could cut ->
    # deletion is the heal; a genuine crossing must still split, not vanish.
    spike = VectorEntity(points=[(0, 0), (10, 0), (5, 0)], closed=True)  # retraced line
    bowtie = VectorEntity(points=[(0, 0), (10, 10), (10, 0), (0, 10)], closed=True)
    clean = VectorEntity(points=[(20, 0), (30, 0), (30, 10), (20, 10)], closed=True)

    assert count_self_intersections([spike, bowtie, clean]) == 2
    healed, count = heal_self_intersections([spike, bowtie, clean])
    assert count == 2
    assert count_self_intersections(healed) == 0
    assert clean in healed
    assert not any(v.points == spike.points for v in healed)  # speck deleted
    assert len(healed) == 3  # bowtie's two lobes + clean


def test_fit_keeps_closed_vectors_closed():
    # A closed VectorEntity's final edge is implicit -- points[0] is not
    # repeated. fit_vector_chains used to push closed entities through
    # _build_chains, which only sees the point list, so the closing edge was
    # dropped and the optimized shape came out OPEN with a gap the size of the
    # lost edge (real file: Repair's healed sub-loops became 10 open profiles).
    from curvemill.geometry import fit_vector_chains

    square = VectorEntity(points=[(0, 0), (10, 0), (10, 10), (0, 10)], closed=True)
    fitted = fit_vector_chains([square])

    flattened = [s.flatten(0.5) for s in fitted]
    assert count_open_profiles(flattened) == 0
    assert all(len(f.points) >= 2 for f in flattened)


def test_repair_leaves_closed_profiles_unchanged():
    closed = VectorEntity(points=[(0, 0), (10, 0), (10, 10), (0, 10)], closed=True)
    open_path = VectorEntity(points=[(0.1, 0), (20, 0)])
    matching_open_path = VectorEntity(points=[(0, 0.1), (0, 20)])

    repaired_closed, repaired_open, _ = repair_vectors([closed, open_path, matching_open_path], 0.25)

    assert repaired_closed.closed is True
    assert repaired_closed.points == closed.points
    assert repaired_open.points[0] != open_path.points[0]


def test_center_cut_removes_material_from_board():
    vector = VectorEntity(points=[(10, 10), (90, 10)])
    options = ProcessOptions(board_width=100, board_height=40, endmill_diameter=10)

    result = process_vectors([vector], options)
    removed = wkt.loads(result.removed_wkt)
    remaining = wkt.loads(result.remaining_wkt)

    assert removed.area > 700
    assert remaining.area < 4000


def test_inside_open_path_falls_back_to_center_with_warning():
    vector = VectorEntity(points=[(0, 0), (10, 0)])
    options = ProcessOptions(trace_mode=TraceMode.INSIDE, endmill_diameter=2)

    result = process_vectors([vector], options)

    assert result.toolpaths[0].points == vector.points
    assert "isn't fully closed" in result.warnings[0]
    assert len(result.warning_details) == 1
    detail = result.warning_details[0]
    assert detail.kind == "open_path_fallback"
    assert detail.message == result.warnings[0]
    assert detail.vector_id == vector.id
    assert detail.path.id == vector.id
    assert detail.path.points == vector.points
    assert detail.path is not vector


def test_invalid_and_offset_removed_paths_include_structured_warnings():
    invalid = VectorEntity(points=[(20, 20), (30, 30), (20, 30), (30, 20)], closed=True)
    tiny = VectorEntity(points=[(50, 50), (52, 50), (52, 52), (50, 52)], closed=True)
    options = ProcessOptions(
        board_width=100,
        board_height=100,
        endmill_diameter=10,
        trace_mode=TraceMode.INSIDE,
    )

    result = process_vectors([invalid, tiny], options)

    assert [detail.kind for detail in result.warning_details] == [
        "invalid_closed_path",
        "offset_removed_path",
    ]
    assert [detail.message for detail in result.warning_details] == result.warnings
    assert [detail.vector_id for detail in result.warning_details] == [invalid.id, tiny.id]
    assert [detail.path.points for detail in result.warning_details] == [invalid.points, tiny.points]


def test_connected_open_segments_assemble_into_closed_profile_for_inside_outside():
    segments = [
        VectorEntity(points=[(20, 20), (60, 20)]),
        VectorEntity(points=[(60, 20), (60, 60)]),
        VectorEntity(points=[(60, 60), (20, 60)]),
        VectorEntity(points=[(20, 60), (20, 20)]),
    ]

    assembled = assemble_closed_profiles(repair_vectors(segments, 0.01), 0.01)
    assert len(assembled) == 1
    assert assembled[0].closed is True

    inside = process_vectors(
        segments,
        ProcessOptions(board_width=100, board_height=100, endmill_diameter=10, trace_mode=TraceMode.INSIDE),
    )
    outside = process_vectors(
        segments,
        ProcessOptions(board_width=100, board_height=100, endmill_diameter=10, trace_mode=TraceMode.OUTSIDE),
    )

    assert inside.warnings == []
    assert outside.warnings == []
    assert wkt.loads(inside.removed_wkt).symmetric_difference(wkt.loads(outside.removed_wkt)).area > 1000


def test_processing_does_not_auto_repair_gapped_profiles():
    segments = [
        VectorEntity(points=[(20, 20), (60, 20)]),
        VectorEntity(points=[(60.2, 20), (60, 60)]),
        VectorEntity(points=[(60, 60), (20, 60)]),
        VectorEntity(points=[(20, 60), (20, 20)]),
    ]

    assert count_open_profiles(segments) == 1
    result = process_vectors(
        segments,
        ProcessOptions(repair_tolerance=0.5, trace_mode=TraceMode.INSIDE),
    )

    assert any("isn't fully closed" in warning for warning in result.warnings)

    repaired = repair_vectors(segments, 0.5)
    assert count_open_profiles(repaired) == 0


def test_outside_closed_profile_creates_exportable_contours():
    square = VectorEntity(points=[(20, 20), (60, 20), (60, 60), (20, 60)], closed=True)
    options = ProcessOptions(board_width=100, board_height=100, endmill_diameter=10, trace_mode=TraceMode.OUTSIDE)

    result = process_vectors([square], options)
    vectors = result_export_vectors(result)

    assert vectors
    assert all(len(v.points) >= 2 for v in vectors)


def test_corrected_export_is_cut_side_wall_without_stock_rectangle():
    # 'Replace with Corrected' must emit one curve per shape -- the tool-compensated
    # cut-side wall -- not the whole board with both groove edges. A single square on
    # a big board should give exactly one contour, and never the stock outline.
    square = VectorEntity(points=[(20, 20), (60, 20), (60, 60), (20, 60)], closed=True)
    board = dict(board_width=600, board_height=400, endmill_diameter=6)

    for mode in (TraceMode.CENTER, TraceMode.OUTSIDE, TraceMode.INSIDE):
        result = process_vectors([square], ProcessOptions(trace_mode=mode, **board))
        vectors = result_export_vectors(result)
        assert len(vectors) == 1, mode  # one wall per shape, no stock rectangle
        v = vectors[0]
        assert all(x >= 1 and y >= 1 for x, y in v.points), mode  # stays off the stock edge
        assert min(x for x, _ in v.points) >= 19  # near the nominal 20mm line, not offset far

    # An inside cut can't reach a sharp internal corner, so it rounds to the tool
    # radius: the corrected curve gains points a straight-sided center cut lacks.
    center = result_export_vectors(process_vectors([square], ProcessOptions(trace_mode=TraceMode.CENTER, **board)))
    inside = result_export_vectors(process_vectors([square], ProcessOptions(trace_mode=TraceMode.INSIDE, **board)))
    assert len(inside[0].points) > len(center[0].points)


def test_hide_islands_removes_disconnected_remaining_components():
    board = wkt.loads("POLYGON ((0 0, 100 0, 100 100, 0 100, 0 0))")
    remaining = wkt.loads(
        "MULTIPOLYGON (((0 0, 100 0, 100 100, 0 100, 0 0), (40 40, 60 40, 60 60, 40 60, 40 40)), "
        "((45 45, 55 45, 55 55, 45 55, 45 45)))"
    )

    visible, hidden = split_islands(remaining, board)

    assert visible.area > hidden.area
    assert hidden.area == 100


def test_hide_islands_marks_disconnected_wood_as_removed_material():
    square = VectorEntity(points=[(30, 30), (70, 30), (70, 70), (30, 70)], closed=True)

    result = process_vectors(
        [square],
        ProcessOptions(
            board_width=100,
            board_height=100,
            endmill_diameter=10,
            hide_islands=True,
        ),
    )

    remaining = wkt.loads(result.remaining_wkt)
    removed = wkt.loads(result.removed_wkt)
    hidden = wkt.loads(result.hidden_islands_wkt)

    assert hidden.area > 0
    assert not remaining.contains(wkt.loads("POINT (50 50)"))
    assert removed.contains(wkt.loads("POINT (50 50)"))


def test_repair_and_processing_report_monotonic_progress():
    vector = VectorEntity(points=[(10, 10), (90, 10)])
    repair_events: list[tuple[int, str]] = []
    process_events: list[tuple[int, str]] = []

    repair_vectors([vector], 0.25, lambda value, message: repair_events.append((value, message)))
    process_vectors(
        [vector],
        ProcessOptions(board_width=100, board_height=40, endmill_diameter=10),
        lambda value, message: process_events.append((value, message)),
    )

    assert repair_events[0][0] == 0
    assert repair_events[-1] == (100, "Repair complete")
    assert process_events[0][0] > 0
    assert process_events[-1] == (100, "Processing complete")
    assert [value for value, _ in repair_events] == sorted(value for value, _ in repair_events)
    assert [value for value, _ in process_events] == sorted(value for value, _ in process_events)


def _circle(cx, cy, r, n=64):
    from math import cos, pi, sin

    return VectorEntity(
        points=[(cx + r * cos(2 * pi * i / n), cy + r * sin(2 * pi * i / n)) for i in range(n)],
        closed=True,
    )


def test_nested_circle_is_a_ring_not_two_discs():
    """A circle inside a circle is material in between: inside shrinks the outer
    edge and grows the inner one, outside does the reverse."""
    outer, inner = _circle(50, 50, 20), _circle(50, 50, 10)
    options = ProcessOptions(board_width=100, board_height=100, endmill_diameter=2)

    options.trace_mode = TraceMode.INSIDE
    radii = sorted(_path_radius(p) for p in build_toolpaths([outer, inner], options))
    assert radii == pytest.approx([11.0, 19.0], abs=0.05)

    options.trace_mode = TraceMode.OUTSIDE
    radii = sorted(_path_radius(p) for p in build_toolpaths([outer, inner], options))
    assert radii == pytest.approx([9.0, 21.0], abs=0.05)


def _path_radius(vector):
    from math import hypot

    return sum(hypot(x - 50, y - 50) for x, y in vector.points) / len(vector.points)

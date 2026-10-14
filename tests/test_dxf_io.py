import ezdxf

from curvemill.dxf_io import _is_degenerate_spline, export_process_result, export_vectors, import_dxf
from curvemill.geometry import process_vectors
from curvemill.models import ProcessOptions, SplineEntity, VectorEntity


def test_full_circle_arc_with_equal_angles_imports_as_full_circle(tmp_path):
    # Some tools store a 360 deg circle as an ARC whose start and end angles match.
    # The importer must read that as the whole circle, not a zero-width sliver.
    path = tmp_path / "circle_arc.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    doc.modelspace().add_arc((0, 0), radius=5, start_angle=0, end_angle=0)
    doc.saveas(path)

    result = import_dxf(path)

    assert result.vectors
    x1, y1, x2, y2 = result.vectors[0].bounds()
    assert x2 - x1 > 8 and y2 - y1 > 8  # ~diameter 10, not a collapsed speck


def test_degenerate_spline_is_flagged_and_a_real_one_is_not():
    dot = SplineEntity(control_points=[(3, 3), (3, 3), (3, 3)])
    assert _is_degenerate_spline(dot)
    real = SplineEntity(control_points=[(0, 0), (5, 5), (10, 0)])
    assert not _is_degenerate_spline(real)


def test_import_supported_entities_and_warning_for_ignored_text(tmp_path):
    path = tmp_path / "input.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_circle((5, 5), 2)
    msp.add_text("ignore me")
    doc.saveas(path)

    result = import_dxf(path)

    assert result.units == "mm"
    assert len(result.vectors) == 2
    assert any("unsupported TEXT shape" in warning for warning in result.warnings)


def test_zero_length_lines_are_skipped_not_counted_as_open_profiles(tmp_path):
    # Inkscape's R14 export drops a zero-length LINE (start == end) at each
    # spline node; kept, each would masquerade as an open profile and spawn an
    # empty warning balloon. They must be filtered on import.
    path = tmp_path / "inkscape.dxf"
    doc = ezdxf.new("R2000")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    msp.add_line((10, 20), (10, 20))  # exact zero length
    msp.add_line((30, 40), (30.00001, 40))  # sub-micron float noise
    msp.add_line((0, 0), (50, 0))  # a real line, must survive
    doc.saveas(path)

    result = import_dxf(path)

    assert len(result.vectors) == 1
    assert result.vectors[0].points == [(0.0, 0.0), (50.0, 0.0)]
    assert any("Skipped 2" in warning and "no real size" in warning for warning in result.warnings)


def test_spline_knot_vector_is_preserved_on_import(tmp_path):
    # Regression: import previously read a non-existent ``knot_values`` attribute,
    # so knots were silently dropped. They come from ``entity.knots`` in ezdxf.
    path = tmp_path / "knots.dxf"
    doc = ezdxf.new("R2000")
    control_points = [(0, 0), (5, 10), (10, -5), (15, 0)]
    doc.modelspace().add_open_spline(control_points, degree=3)
    doc.saveas(path)

    result = import_dxf(path)

    assert len(result.splines) == 1
    assert result.splines[0].knots is not None
    assert len(result.splines[0].knots) > 0


def test_unit_override_scales_inches_to_mm(tmp_path):
    path = tmp_path / "inch.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 1
    doc.modelspace().add_line((0, 0), (1, 0))
    doc.saveas(path)

    result = import_dxf(path, units_override="mm")

    assert result.vectors[0].points[1] == (25.4, 0.0)


def test_export_vectors_reopens(tmp_path):
    path = tmp_path / "out.dxf"
    export_vectors(path, [VectorEntity(points=[(0, 0), (10, 0), (10, 10)], closed=False)])

    doc = ezdxf.readfile(path)

    assert len(list(doc.modelspace())) == 1


def test_fit_point_spline_survives_import_and_export_as_spline(tmp_path):
    source = tmp_path / "fit_spline.dxf"
    doc = ezdxf.new("R2010")
    doc.modelspace().add_spline(fit_points=[(0, 0), (5, 8), (10, 0), (15, 8)])
    doc.saveas(source)

    result = import_dxf(source)

    # The curve is preserved as a real spline, not dropped or flattened.
    assert len(result.splines) == 1
    assert len(result.vectors) == 0
    assert result.splines[0].control_points

    output = tmp_path / "fit_spline_out.dxf"
    export_vectors(output, result.vectors, result.splines)
    reopened = ezdxf.readfile(output)
    assert [entity.dxftype() for entity in reopened.modelspace()] == ["SPLINE"]


def test_export_process_result_reopens(tmp_path):
    path = tmp_path / "corrected.dxf"
    result = process_vectors(
        [VectorEntity(points=[(10, 10), (40, 10)], closed=False)],
        ProcessOptions(board_width=50, board_height=30, endmill_diameter=5),
    )

    export_process_result(path, result)

    doc = ezdxf.readfile(path)
    assert len(list(doc.modelspace())) >= 1


def test_import_and_export_report_progress(tmp_path):
    source = tmp_path / "progress_input.dxf"
    output = tmp_path / "progress_output.dxf"
    doc = ezdxf.new("R2010")
    doc.modelspace().add_line((0, 0), (10, 0))
    doc.saveas(source)
    import_events: list[tuple[int, str]] = []
    export_events: list[tuple[int, str]] = []

    result = import_dxf(source, progress=lambda value, message: import_events.append((value, message)))
    export_vectors(output, result.vectors, progress=lambda value, message: export_events.append((value, message)))

    assert import_events[-1] == (100, "DXF loaded")
    assert export_events[-1] == (100, "Export complete")
    assert [value for value, _ in import_events] == sorted(value for value, _ in import_events)
    assert [value for value, _ in export_events] == sorted(value for value, _ in export_events)

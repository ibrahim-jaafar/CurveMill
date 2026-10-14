"""V-Carve: width<->depth inversion, iso-depth bands, hazards, and UI gating."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from curvemill import project
from curvemill.geometry import process_layers, vcarve_layer
from curvemill.models import (
    Layer,
    LayerJob,
    ProcessOptions,
    Tool,
    ToolKind,
    VectorEntity,
)


def _app():
    return QApplication.instance() or QApplication([])


def _square(size: float = 60.0) -> VectorEntity:
    return VectorEntity(points=[(0, 0), (size, 0), (size, size), (0, size)], closed=True)


def test_depth_for_width_inverts_effective_diameter():
    tapered = Tool("t", ToolKind.TAPERED, diameter=20.0, taper_angle_deg=30.0, tip_diameter=1.0)
    assert tapered.depth_for_width(tapered.effective_diameter(5.0)) == pytest.approx(5.0)
    ball = Tool("b", ToolKind.BALL, diameter=6.0)
    assert ball.depth_for_width(ball.effective_diameter(1.0)) == pytest.approx(1.0)


def test_flat_and_laser_cannot_vcarve():
    assert not Tool("f", ToolKind.FLAT).can_vcarve
    assert not Tool("l", ToolKind.LASER).can_vcarve
    assert Tool("v", ToolKind.V_BIT, taper_angle_deg=30.0).can_vcarve
    with pytest.raises(ValueError):
        Tool("f", ToolKind.FLAT).depth_for_width(3.0)


def test_vcarve_bands_get_deeper_toward_the_middle_and_flag_a_flat_bottom():
    tool = Tool("t", ToolKind.TAPERED, diameter=20.0, taper_angle_deg=30.0, tip_diameter=0.5)
    carve = vcarve_layer([_square(60.0)], tool, max_depth=5.0, options=ProcessOptions())
    depths = [depth for depth, _ in carve.bands]
    assert len(depths) >= 2
    assert depths == sorted(depths)  # shallow at the edge, deep toward the centre
    assert max(depths) == pytest.approx(5.0)  # capped at the max depth
    # A 60 mm square is far wider than the bit at 5 mm, so the floor goes flat.
    assert any(kind == "flat_bottom" for kind, _ in carve.hazards)


def test_vcarve_bands_are_simplified_so_the_preview_stays_light():
    # A 720-point circle stands in for a spline-heavy pattern. Unsimplified,
    # every ring would carry the full input density (~12x720 coords) and the
    # canvas freezes parsing/painting it; simplified bands must total far less.
    import math

    from shapely import wkt as shapely_wkt

    n = 720
    circle = VectorEntity(
        points=[
            (50 + 40 * math.cos(2 * math.pi * k / n), 50 + 40 * math.sin(2 * math.pi * k / n))
            for k in range(n)
        ],
        closed=True,
    )
    tool = Tool("t", ToolKind.TAPERED, diameter=20.0, taper_angle_deg=30.0, tip_diameter=0.5)
    carve = vcarve_layer([circle], tool, max_depth=5.0, options=ProcessOptions())
    assert len(carve.bands) >= 2

    def coords(geom):
        polygons = getattr(geom, "geoms", [geom])
        return sum(
            len(p.exterior.coords) + sum(len(r.coords) for r in p.interiors)
            for p in polygons
            if not p.is_empty
        )

    total = sum(coords(shapely_wkt.loads(band)) for _, band in carve.bands)
    assert total < 4 * n  # ~12 unsimplified rings would be well past 12 * n


def test_a_neck_narrower_than_the_tip_is_flagged_unreachable():
    thin = VectorEntity(points=[(0, 0), (40, 0), (40, 1.0), (0, 1.0)], closed=True)
    tool = Tool("t", ToolKind.TAPERED, diameter=20.0, taper_angle_deg=30.0, tip_diameter=2.0)
    carve = vcarve_layer([thin], tool, max_depth=5.0, options=ProcessOptions())
    assert any(kind == "unreachable" for kind, _ in carve.hazards)


def test_process_layers_routes_a_vcarve_job_into_bands_and_hazards():
    tool = Tool("t", ToolKind.TAPERED, diameter=20.0, taper_angle_deg=30.0, tip_diameter=0.5)
    options = ProcessOptions(board_width=100, board_height=100)
    job = LayerJob("Carve", 5.0, "vcarve", [_square(60.0)], options, tool)
    result = process_layers([job])
    assert len(result.depth_cuts) >= 2  # one entry per iso-depth band
    assert result.vcarve_hazards
    assert "POLYGON" in result.removed_wkt or "MULTIPOLYGON" in result.removed_wkt


def test_vcarve_mode_drops_the_flat_mill_from_the_tool_list():
    from curvemill.app import MainWindow

    _app()
    window = MainWindow()
    window.cut_mode.setCurrentIndex(window.cut_mode.findData("vcarve"))
    kinds = {window.tool_combo.itemData(i) for i in range(window.tool_combo.count())}
    assert ToolKind.FLAT.value not in kinds  # a flat mill can't V-carve
    assert ToolKind.V_BIT.value in kinds
    window.close()


def test_vcarve_mode_hides_the_trace_selector():
    # V-carve rides the centerline between the walls â€” inside/outside/center is a
    # dead control there, so the row must disappear (and come back in profile mode).
    from curvemill.app import MainWindow

    _app()
    window = MainWindow()
    window.cut_mode.setCurrentIndex(window.cut_mode.findData("vcarve"))
    assert not window._sim_form.isRowVisible(window.trace)
    window.cut_mode.setCurrentIndex(window.cut_mode.findData("profile"))
    assert window._sim_form.isRowVisible(window.trace)
    window.close()


def test_laser_mode_shows_only_the_laser_tool():
    from curvemill.app import MainWindow

    _app()
    window = MainWindow()
    window.cut_mode.setCurrentIndex(window.cut_mode.findData("laser"))
    kinds = [window.tool_combo.itemData(i) for i in range(window.tool_combo.count())]
    assert kinds == [ToolKind.LASER.value]
    window.close()


def test_selecting_a_vcarve_layer_drops_the_flat_mill_and_stores_a_v_tool():
    from curvemill.app import MainWindow

    _app()
    window = MainWindow()
    window.editor.load(
        [
            VectorEntity(points=[(0, 0), (9, 0), (9, 9), (0, 9)], closed=True, layer="Vine"),
            VectorEntity(points=[(0, 0), (9, 9)], layer="Groove"),
        ],
        [],
    )
    window.editor.layers = [Layer("Vine"), Layer("Groove")]
    window._refresh_sim_layers()
    # Select the first layer and switch it to V-Carve from the toolbar.
    window.sim_layers.setCurrentItem(window.sim_layers.topLevelItem(0))
    window.cut_mode.setCurrentIndex(window.cut_mode.findData("vcarve"))
    kinds = {window.tool_combo.itemData(i) for i in range(window.tool_combo.count())}
    assert ToolKind.FLAT.value not in kinds  # a flat mill can't V-carve

    layer = window._selected_sim_layer()
    assert layer.mode == "vcarve"
    assert layer.tool.can_vcarve  # its stored tool is now V-capable
    window.close()


def test_mixed_laser_and_vcarve_layers_build_the_right_jobs():
    from curvemill.app import MainWindow
    from curvemill.models import TraceMode

    _app()
    window = MainWindow()
    window.editor.load(
        [
            VectorEntity(points=[(0, 0), (30, 0), (30, 30), (0, 30)], closed=True, layer="Carve"),
            VectorEntity(points=[(0, 0), (20, 20)], layer="Engrave"),
        ],
        [],
    )
    window.editor.layers = [
        Layer("Carve", depth=5.0, mode="vcarve", tool=Tool("v", ToolKind.V_BIT, diameter=12.0, taper_angle_deg=30.0)),
        Layer("Engrave", depth=1.0, mode="laser", tool=Tool("l", ToolKind.LASER, diameter=0.2)),
    ]
    jobs = {job.name: job for job in window._layer_jobs()}
    assert jobs["Carve"].mode == "vcarve"  # V-bit layer carves
    # The laser layer runs as a centered kerf sweep, not a V-carve.
    assert jobs["Engrave"].mode == "profile"
    assert jobs["Engrave"].options.trace_mode is TraceMode.CENTER
    assert jobs["Engrave"].options.endmill_diameter == 0.2  # constant kerf
    window.close()


def test_layers_carry_independent_recipes_and_survive_a_round_trip(tmp_path):
    from curvemill.app import MainWindow

    _app()
    window = MainWindow()
    window.editor.load(
        [
            VectorEntity(points=[(0, 0), (9, 9)], layer="Carve"),
            VectorEntity(points=[(0, 0), (5, 5)], layer="Engrave"),
        ],
        [],
    )
    vbit = Tool("v", ToolKind.V_BIT, diameter=12.0, taper_angle_deg=30.0)
    window.editor.layers = [
        Layer("Carve", depth=4.0, mode="vcarve", tool=vbit),
        Layer("Engrave", depth=1.0, mode="laser", tool=Tool("l", ToolKind.LASER, diameter=0.2)),
    ]
    path = tmp_path / "modes.curvemill"
    project.save(
        path,
        window.editor.vectors,
        window.editor.splines,
        window.editor.layers,
        window.editor.active_layer,
        window._project_settings(),
    )
    window.close()

    reopened = MainWindow()
    reopened.open_project(path)
    recipes = [(l.name, l.mode, l.tool.kind) for l in reopened.editor.layers]
    assert recipes == [
        ("Carve", "vcarve", ToolKind.V_BIT),
        ("Engrave", "laser", ToolKind.LASER),
    ]
    reopened.close()

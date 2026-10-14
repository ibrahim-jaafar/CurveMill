"""Depth belongs to the layer: one part, several depths, one preview."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from curvemill import project
from curvemill.app import MainWindow, _depth_shade
from curvemill.geometry import process_layers
from curvemill.models import Layer, Tool, ToolKind, VectorEntity
from curvemill.solidworks_bridge import SWTarget


def _app():
    return QApplication.instance() or QApplication([])


def _two_layer_window():
    window = MainWindow()
    window.editor.load(
        [
            VectorEntity(points=[(20, 20), (80, 20)], layer="Carve"),
            VectorEntity(points=[(20, 60), (80, 60)], layer="Groove"),
        ],
        [],
    )
    # A tapered bit cuts wider the deeper it goes, so depth has to reach the sweep.
    # Each layer owns its own tool now, so give both the same tapered bit.
    def tapered():
        return Tool("t", ToolKind.TAPERED, diameter=6.0, taper_angle_deg=30.0, tip_diameter=1.0)

    window.editor.layers = [
        Layer("Carve", depth=3.0, tool=tapered()),
        Layer("Groove", depth=9.0, tool=tapered()),
    ]
    window._refresh()
    return window


def test_each_layer_cuts_at_its_own_depth_and_width():
    _app()
    window = _two_layer_window()

    jobs = window._layer_jobs()
    widths = {job.name: job.options.endmill_diameter for job in jobs}
    depths = {job.name: job.depth for job in jobs}
    assert depths == {"Carve": 3.0, "Groove": 9.0}
    # 1 mm tip + 2 * depth * tan(30Â°): deeper layer, wider cut.
    assert widths["Groove"] > widths["Carve"] > 1.0

    result = process_layers(jobs)
    assert [name for name, _, _ in result.depth_cuts] == ["Carve", "Groove"]  # shallowest first
    window.close()


def test_a_skipped_layer_is_not_cut():
    _app()
    window = _two_layer_window()
    window.editor.layers[1].cut = False

    assert [job.name for job in window._layer_jobs()] == ["Carve"]
    window.close()


def test_deeper_layers_shade_darker():
    _app()
    shallow = _depth_shade(3.0, 9.0)
    deep = _depth_shade(9.0, 9.0)
    assert deep.lightness() < shallow.lightness()


def test_layer_depths_survive_a_project_round_trip(tmp_path):
    _app()
    window = _two_layer_window()
    window.editor.layers[0].cut = False
    path = tmp_path / "depths.curvemill"
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
    assert [(l.name, l.depth, l.cut) for l in reopened.editor.layers] == [
        ("Carve", 3.0, False),
        ("Groove", 9.0, True),
    ]
    reopened.close()


def test_a_depth_past_the_solidworks_board_thickness_is_flagged():
    _app()
    window = _two_layer_window()
    window._sw_target = SWTarget("face", b"", "Face of Boss-Extrude1", 200.0, 100.0, 6.0, None)
    window._refresh_sim_layers()

    assert not window.sim_layers.topLevelItem(0).toolTip(3)  # 3 mm into a 6 mm board is fine
    assert "6 mm board" in window.sim_layers.topLevelItem(1).toolTip(3)  # 9 mm is not
    window.close()


def test_a_vcarve_depth_past_the_board_warns_to_use_a_sacrificial_board():
    _app()
    window = _two_layer_window()  # Carve @ 3 mm, Groove @ 9 mm, both tapered (V-capable)
    window.editor.layers[1].mode = "vcarve"  # Groove now carves; 9 mm is its max depth
    window._sw_target = SWTarget("face", b"", "Face of Boss-Extrude1", 200.0, 100.0, 6.0, None)
    window._refresh_sim_layers()

    tip = window.sim_layers.topLevelItem(1).toolTip(3)
    assert "sacrificial board" in tip  # max depth 9 mm breaks through a 6 mm board
    window.close()


def test_a_laser_layer_still_shows_its_depth_in_the_panel():
    _app()
    window = _two_layer_window()
    window.sim_layers.setCurrentItem(window.sim_layers.topLevelItem(0))
    window.cut_mode.setCurrentIndex(window.cut_mode.findData("laser"))

    # The form hides the (meaningless) depth input for a laser...
    assert not window._sim_form.isRowVisible(window.cut_depth)
    # ...but the layer panel still lists every layer and shows its depth.
    assert window.sim_layers.topLevelItemCount() == 2
    assert window.sim_layers.topLevelItem(0).text(3) != ""
    window.close()


def test_apply_to_all_layers_checkbox_keeps_every_layer_in_lockstep():
    _app()
    window = _two_layer_window()  # Carve @ 3 mm, Groove @ 9 mm â€” different recipes
    window.sim_layers.setCurrentItem(window.sim_layers.topLevelItem(0))

    # Checking it copies the selected layer's recipe onto every layer at once.
    window.apply_all_check.setChecked(True)
    assert {l.depth for l in window.editor.layers} == {3.0}

    # ...and further edits to the selected layer keep the others synced.
    # setValue fires valueChanged, not editingFinished; emit the commit a real
    # keystroke-then-focus-out would (tool spinboxes write on editingFinished now).
    window.cut_depth.setValue(5.0)
    window.cut_depth.editingFinished.emit()
    assert [l.depth for l in window.editor.layers] == [5.0, 5.0]

    # Unchecking frees the layers again: an edit no longer propagates.
    window.apply_all_check.setChecked(False)
    window.cut_depth.setValue(7.0)
    window.cut_depth.editingFinished.emit()
    depths = {l.name: l.depth for l in window.editor.layers}
    assert depths["Carve"] == 7.0 and depths["Groove"] == 5.0
    window.close()

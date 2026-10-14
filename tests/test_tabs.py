"""Four-tab restructure: tab shell, Process tab switch, settings round-trip."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from curvemill.app import MainWindow, SendToSolidWorksDialog
from curvemill.geometry import process_vectors
from curvemill.models import (
    ImportResult,
    LayerJob,
    ProcessOptions,
    Tool,
    ToolKind,
    TraceMode,
    VectorEntity,
)


def _app():
    return QApplication.instance() or QApplication([])


def test_process_log_records_the_cut_recipe():
    # The Log must say HOW a result was made -- mode, tool, diameter, depth, trace --
    # not just "Processing complete".
    _app()
    window = MainWindow()
    job = LayerJob(
        name="Cuts",
        depth=3.0,
        mode="profile",
        vectors=[],
        options=ProcessOptions(
            board_width=100, board_height=100, endmill_diameter=6.0, trace_mode=TraceMode.OUTSIDE
        ),
        tool=Tool("bit", ToolKind.FLAT, diameter=6.0),
    )
    window._log_process_recipe([job])
    text = window.log_view.toPlainText()
    assert "Cuts" in text and "Flat" in text and "6" in text
    assert "depth 3" in text and "outside" in text
    window.close()


def _window_with_square():
    window = MainWindow()
    square = VectorEntity(points=[(0, 0), (50, 0), (50, 50), (0, 50)], closed=True)
    window._on_import_done([(Path("t.dxf"), ImportResult([square], units="mm"))])
    return window, square


def test_four_tabs_editor_default_and_shared_sim_scene():
    _app()
    window = MainWindow()
    titles = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert titles == ["Editor", "Simulation", "Library", "Settings"]
    assert window.tabs.currentWidget() is window._editor_tab
    assert window.sim_view.scene() is window.view.scene
    window.close()


def test_process_completion_switches_to_simulation_tab():
    _app()
    window, square = _window_with_square()
    result = process_vectors([square], window._options(), lambda v, m: None)
    window._on_process_done(result)
    assert window.tabs.currentWidget() is window._sim_tab
    window.close()


def test_sim_view_canvas_controls_and_fit():
    _app()
    window, _ = _window_with_square()
    # Vector toggle shared with the Editor (same scene items); fit is sim-local.
    assert window.sim_view.vector_toggle_button.defaultAction() is window.show_vectors_action
    assert window.sim_view.fit_content_button.defaultAction() is window.sim_fit_action
    window.sim_fit_action.trigger()  # frames content without raising
    window.close()


def test_settings_round_trip_and_startup_defaults():
    _app()
    window = MainWindow()
    window.fit_samples_setting.setValue(7)
    window.corner_degrees_setting.setValue(25.0)
    window.default_units_setting.setCurrentText("mm")
    window.sw_send_mode_setting.setCurrentText("Sketch only")
    window.sw_cut_depth_setting.setValue(18.0)
    window.close()

    reopened = MainWindow()
    assert reopened.fit_samples_setting.value() == 7
    assert reopened.corner_degrees_setting.value() == 25.0
    assert reopened.units.currentText() == "mm"  # startup default applied
    assert reopened.sw_send_mode_setting.currentText() == "Sketch only"
    assert reopened.sw_cut_depth_setting.value() == 18.0
    reopened.close()


def test_send_dialog_honors_default_feature_and_depth():
    _app()
    # thickness unknown (plane) -> depth falls back to the settings default.
    dialog = SendToSolidWorksDialog(None, None, default_feature="Extruded Boss", default_depth_mm=18.0)
    assert dialog.feature.currentText() == "Extruded Boss"
    assert dialog.depth.value() == 18.0
    # a known board thickness still wins over the default fallback.
    known = SendToSolidWorksDialog(None, 25.0, default_feature="Extruded Boss", default_depth_mm=18.0)
    assert known.depth.value() == 25.0

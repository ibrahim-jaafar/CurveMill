"""Tool math, the Simulation tab's per-kind fields, and the Library tool table."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from math import radians, tan

import pytest
from PySide6.QtWidgets import QApplication

from curvemill.app import MainWindow
from curvemill.models import Tool, ToolKind


def _app():
    return QApplication.instance() or QApplication([])


def _select_kind(window, kind: ToolKind) -> None:
    # Laser is a cut mode now; the other kinds live under the Profile mode's tool list.
    if kind is ToolKind.LASER:
        window.cut_mode.setCurrentIndex(window.cut_mode.findData("laser"))
        return
    window.cut_mode.setCurrentIndex(window.cut_mode.findData("profile"))
    window.tool_combo.setCurrentIndex(window.tool_combo.findData(kind.value))


def test_effective_diameter_by_kind():
    assert Tool("f", ToolKind.FLAT, diameter=6).effective_diameter(10) == 6
    v = Tool("v", ToolKind.V_BIT, diameter=12.7, taper_angle_deg=30)
    assert v.effective_diameter(3) == pytest.approx(6 * tan(radians(30)))
    assert v.effective_diameter(1000) == 12.7  # capped at the widest diameter
    t = Tool("t", ToolKind.TAPERED, diameter=6, taper_angle_deg=5, tip_diameter=1)
    assert t.effective_diameter(0) == 1
    assert t.effective_diameter(2) == pytest.approx(1 + 4 * tan(radians(5)))
    b = Tool("b", ToolKind.BALL, diameter=6)
    assert b.effective_diameter(1.5) == pytest.approx(2 * (1.5 * 4.5) ** 0.5)
    assert b.effective_diameter(3) == 6
    assert b.effective_diameter(10) == 6
    laser = Tool("l", ToolKind.LASER, diameter=0.2)
    assert laser.effective_diameter(0) == laser.effective_diameter(50) == 0.2


def test_tool_json_round_trip():
    tool = Tool("Tapered", ToolKind.TAPERED, diameter=6, taper_angle_deg=5, tip_diameter=1, notes="dry, 2-flute")
    assert Tool.from_dict(tool.to_dict()) == tool


def test_add_new_tool_button_and_notes_column():
    _app()
    window = MainWindow()
    assert window.tools == []
    # Notes sits immediately right of Tip Ø.
    headers = [window.tool_table.horizontalHeaderItem(c).text() for c in range(window.tool_table.columnCount())]
    assert headers.index("Notes") == headers.index("Tip Ø") + 1

    window._add_blank_tool()  # the new button drops in an editable default row
    assert len(window.tools) == 1

    notes_col = headers.index("Notes")
    from PySide6.QtWidgets import QTableWidgetItem

    window.tool_table.setItem(0, notes_col, QTableWidgetItem("plywood only"))
    assert window.tools[0].notes == "plywood only"  # edits flow back into the tool
    window.close()


def test_kind_picker_shows_only_relevant_fields():
    _app()
    window = MainWindow()
    form = window._sim_form

    _select_kind(window, ToolKind.FLAT)
    assert not form.isRowVisible(window.tool_taper)
    assert not form.isRowVisible(window.tool_tip)
    assert form.isRowVisible(window.cut_depth)

    _select_kind(window, ToolKind.V_BIT)
    assert form.isRowVisible(window.tool_taper)
    assert not form.isRowVisible(window.tool_tip)

    _select_kind(window, ToolKind.TAPERED)
    assert form.isRowVisible(window.tool_taper)
    assert form.isRowVisible(window.tool_tip)

    _select_kind(window, ToolKind.LASER)
    # A laser has one kerf at any depth and no meaningful inside/outside offset.
    assert not form.isRowVisible(window.cut_depth)
    assert window.trace.currentText() == "center"
    assert not window.trace.isEnabled()
    window.close()


def test_effective_diameter_feeds_the_simulation():
    _app()
    window = MainWindow()
    _select_kind(window, ToolKind.V_BIT)
    window.endmill.setValue(12.7)
    window.tool_taper.setValue(30.0)
    window.cut_depth.setValue(3.0)
    options = window._options()
    assert options.tool_kind == "v_bit"
    assert options.endmill_diameter == pytest.approx(6 * tan(radians(30)))

    # Flat cuts its full diameter no matter how deep it goes.
    _select_kind(window, ToolKind.FLAT)
    window.endmill.setValue(6.0)
    assert window._options().endmill_diameter == pytest.approx(6.0)
    window.close()


def test_tool_library_starts_empty_saves_and_loads_back():
    _app()
    window = MainWindow()
    assert window.tools == []
    assert [window.library_sections.item(i).text() for i in range(window.library_sections.count())] == [
        "Patterns",
        "Tools",
    ]

    _select_kind(window, ToolKind.TAPERED)
    window.endmill.setValue(6.0)
    window.tool_taper.setValue(5.0)
    window.tool_tip.setValue(1.0)
    window._add_tool()
    assert len(window.tools) == 1
    assert window.tools[0].kind is ToolKind.TAPERED
    assert window.tools[0].tip_diameter == 1.0
    window.close()

    # Persisted through QSettings, and loading it back restores the sim fields.
    window2 = MainWindow()
    assert len(window2.tools) == 1
    _select_kind(window2, ToolKind.FLAT)
    window2.tool_table.setCurrentCell(0, 0)
    window2._use_selected_tool()
    assert window2.tool_combo.currentData() == "tapered"
    assert window2.tool_tip.value() == 1.0
    assert window2.tabs.currentWidget() is window2._sim_tab
    window2._remove_tool()
    assert window2.tools == []
    window2.close()

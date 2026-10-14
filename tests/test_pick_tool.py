"""A plain click on the default (Box Lasso) tool selects exactly one entity."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from curvemill.app import MainWindow
from curvemill.models import SplineEntity, VectorEntity


def _app():
    return QApplication.instance() or QApplication([])


def _click(view, scene_x, scene_y, modifiers=Qt.KeyboardModifier.NoModifier):
    pos = QPointF(view.mapFromScene(scene_x, scene_y))
    view.mousePressEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            modifiers,
        )
    )


def test_click_selects_single_vector():
    _app()
    window = MainWindow()
    a = VectorEntity(points=[(0, 0), (10, 0), (10, 10), (0, 10)], closed=True)
    b = VectorEntity(points=[(100, 100), (110, 100), (110, 110), (100, 110)], closed=True)
    window.editor.load([a, b], [])
    window.view.redraw()  # default tool is Box Lasso; a plain click still single-selects

    _click(window.view, 5.0, 0.0)
    assert window.editor.selected_ids == {window.editor.vectors[0].id}
    _click(window.view, 105.0, 100.0)
    assert window.editor.selected_ids == {window.editor.vectors[1].id}
    # Ctrl+click adds instead of replacing.
    _click(window.view, 5.0, 0.0, Qt.KeyboardModifier.ControlModifier)
    assert window.editor.selected_ids == {v.id for v in window.editor.vectors}
    # Clicking empty space clears.
    _click(window.view, 500.0, 500.0)
    assert window.editor.selected_ids == set()
    window.close()


def test_click_selects_spline():
    _app()
    window = MainWindow()
    curve = SplineEntity(control_points=[(0, 0), (10, 20), (20, -20), (30, 0)])
    window.editor.load([], [curve])
    window.view.redraw()

    # Click on the curve's start point (always on the spline).
    _click(window.view, 0.0, 0.0)
    assert window.editor.selected_spline_ids == {curve.id}
    _click(window.view, 500.0, 500.0)  # empty space clears
    assert window.editor.selected_spline_ids == set()
    window.close()


def test_drag_inside_selection_moves_outside_starts_box():
    # Move tool is gone: in Select, a drag from empty space INSIDE the selection
    # bounds moves it; a drag OUTSIDE starts a fresh box-select.
    _app()
    window = MainWindow()
    window.editor.load([VectorEntity(points=[(0, 0), (100, 0), (100, 50), (0, 50)], closed=True)], [])
    window.view.redraw()
    window.editor.select_all()

    _click(window.view, 50.0, 25.0)  # empty interior, inside the bbox
    assert window.view._mode == "move"
    window.view._cancel_drag()

    _click(window.view, 300.0, 300.0)  # outside the bbox
    assert window.view._mode == "box"
    window.close()


def test_free_lasso_moves_inside_selection_lassos_outside():
    # Free lasso now shares the box tool's path: drag inside the selection moves
    # it; drag from empty space traces a lasso.
    _app()
    window = MainWindow()
    window.editor.load([VectorEntity(points=[(0, 0), (100, 0), (100, 50), (0, 50)], closed=True)], [])
    window.view.redraw()
    window.free_lasso_tool_action.trigger()
    window.editor.select_all()

    _click(window.view, 50.0, 25.0)  # empty interior, inside the bbox
    assert window.view._mode == "move"
    window.view._cancel_drag()

    _click(window.view, 300.0, 300.0)  # outside the bbox
    assert window.view._mode == "free_lasso"
    window.view._cancel_drag()
    window.close()


def test_escape_clears_selection():
    _app()
    window = MainWindow()
    window.editor.load([VectorEntity(points=[(0, 0), (10, 0)])], [])
    window.view.redraw()
    window.editor.select_all()
    assert window.editor.selected_ids
    window.view.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    )
    assert not window.editor.selected_ids and not window.editor.selected_spline_ids
    window.close()


def test_move_tool_keeps_spline_multi_selection():
    _app()
    window = MainWindow()
    a = SplineEntity(control_points=[(0, 0), (10, 20), (20, -20), (30, 0)])
    b = SplineEntity(control_points=[(100, 100), (110, 120), (120, 80), (130, 100)])
    window.editor.load([], [a, b])
    window.view.redraw()
    window.editor.selected_spline_ids = {a.id, b.id}
    window.view._start_move_tool_drag(QPointF(0.0, 0.0), additive=False)
    assert window.editor.selected_spline_ids == {a.id, b.id}
    window.close()

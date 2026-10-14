"""Handle-resize of native splines must update the canvas items, not just the model."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from curvemill.app import MainWindow, _vector_path
from curvemill.models import SplineEntity


def _app():
    return QApplication.instance() or QApplication([])


def test_normalize_live_visuals_updates_spline_paths():
    _app()
    window = MainWindow()
    spline = SplineEntity(control_points=[(0, 0), (10, 0), (10, 10), (0, 10)], degree=3)
    window.editor.load([], [spline])
    window.view.redraw()
    sid = window.editor.splines[0].id
    window.editor.selected_spline_ids.add(sid)

    snapshot = window.editor.snapshot()
    assert window.editor.commit_scale_from_snapshot(snapshot, (0.0, 0.0), 2.0, 2.0)
    window.view._normalize_live_visuals()

    item = window.view._vector_items[sid]
    expected = _vector_path(window.editor.splines[0].flatten(0.5)).boundingRect()
    assert item.transform().isIdentity()
    assert item.path().boundingRect() == expected
    window.close()

"""Repair removes duplicate entities and the button gate includes them."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from curvemill.app import MainWindow
from curvemill.geometry import count_profile_issues
from curvemill.models import ImportResult, VectorEntity


def _app():
    return QApplication.instance() or QApplication([])


def test_repair_enabled_for_duplicates_and_removes_them():
    _app()
    window = MainWindow()
    square = VectorEntity(points=[(0, 0), (50, 0), (50, 50), (0, 50)], closed=True)
    dupe = VectorEntity(points=[(50, 50), (50, 0), (0, 0), (0, 50)], closed=True)
    window._on_import_done([(Path("t.dxf"), ImportResult([square, dupe], units="mm"))])

    # 0 open profiles but 1 duplicate: the button must not be greyed out.
    assert window.repair_button.isEnabled()
    window.repair_vectors()
    assert count_profile_issues(window.editor.all_visible_vectors()).duplicates == 0
    assert len(window.editor.vectors) == 1
    assert not window.repair_button.isEnabled()
    assert window.editor.undo()  # removal is a normal undo step
    assert len(window.editor.vectors) == 2
    window.close()

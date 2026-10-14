"""A library entry is clipart: saved from a selection, inserted into the drawing."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from curvemill import library
from curvemill.app import MainWindow
from curvemill.models import SplineEntity, VectorEntity


def _app():
    return QApplication.instance() or QApplication([])


def test_selection_saves_as_clipart_and_inserts_into_an_existing_drawing(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "library_dir", lambda: tmp_path)
    _app()
    window = MainWindow()
    square = VectorEntity(points=[(0, 0), (10, 0), (10, 10), (0, 10)], closed=True)
    other = VectorEntity(points=[(50, 50), (60, 50)], closed=False)
    window.editor.load([square, other], [SplineEntity(control_points=[(0, 0), (5, 9), (12, 3)])])
    window.editor.selected_ids = {window.editor.vectors[0].id}

    monkeypatch.setattr("curvemill.app.QInputDialog.getText", lambda *a, **k: ("Vine", True))
    window._save_to_library()

    assert [entry.stem for entry in library.entries()] == ["Vine"]
    assert window.pattern_list.count() == 1
    assert (tmp_path / "Vine.png").exists()  # thumbnail cached beside the entry
    # Only the selected piece is the pattern.
    saved_vectors, saved_splines = library.load_pattern(library.entries()[0])
    assert [v.points for v in saved_vectors] == [square.points]
    assert saved_splines == []

    # Inserting keeps the drawing that is already open and adds the pattern to it.
    before = len(window.editor.vectors)
    window._insert_library_entry(window.pattern_list.item(0))
    assert len(window.editor.vectors) == before + 1
    assert other.points in [v.points for v in window.editor.vectors]
    assert window.editor.splines  # the session's own spline survived
    window.close()


def test_insert_centers_the_pattern_on_the_board(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "library_dir", lambda: tmp_path)
    _app()
    window = MainWindow()
    window.board_width.setValue(400.0)
    window.board_height.setValue(300.0)
    library.save_pattern("Corner", [VectorEntity(points=[(0, 0), (10, 0), (10, 10), (0, 10)], closed=True)], [])
    window._refresh_pattern_library()

    window._insert_library_entry(window.pattern_list.item(0))

    points = window.editor.vectors[-1].points
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    assert ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2) == (200.0, 150.0)
    window.close()


def test_canvas_right_click_menu_offers_save_to_library():
    _app()
    window = MainWindow()
    assert window.save_to_library_action in window.view.context_actions
    window.close()

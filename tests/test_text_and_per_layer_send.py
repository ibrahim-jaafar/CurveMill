"""Text-to-curves insertion and per-layer Send to SolidWorks."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from curvemill.app import MainWindow, PerLayerSendDialog, _text_to_vectors
from curvemill.models import Layer, VectorEntity


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
    window.editor.layers = [Layer("Carve", depth=3.0), Layer("Groove", depth=9.0)]
    return window


def test_text_becomes_closed_curves_of_the_requested_height():
    _app()
    # "8" has an outer ring plus two counters, so hole handling gets exercised.
    vectors = _text_to_vectors("8", QFont(), 25.0, "Layer 1")
    assert vectors, "expected glyph outlines"
    assert all(v.closed for v in vectors)
    ys = [p[1] for v in vectors for p in v.points]
    assert abs((max(ys) - min(ys)) - 25.0) < 0.5  # scaled to the asked-for height


def test_inserted_text_lands_on_the_active_layer():
    _app()
    window = _two_layer_window()
    window.editor.set_active_layer("Groove")
    vectors = _text_to_vectors("A", QFont(), 20.0, window.editor.active_layer)
    before = len(window.editor.vectors)
    window.editor.paste_vectors(vectors, (100.0, 50.0))
    added = [v for v in window.editor.vectors if v.layer == "Groove"]
    assert len(window.editor.vectors) == before + len(vectors)
    assert all(v.layer == "Groove" for v in added if v not in window.editor.vectors[:before])
    window.close()


def test_sw_send_layers_lists_only_cutting_layers_with_geometry():
    _app()
    window = _two_layer_window()
    assert [l.name for l in window._sw_send_layers()] == ["Carve", "Groove"]
    window.editor.layers[0].cut = False
    assert [l.name for l in window._sw_send_layers()] == ["Groove"]
    window.close()


def test_per_layer_dialog_prefills_through_all_past_thickness_and_skips():
    _app()
    dialog = PerLayerSendDialog(None, [("Carve", 3.0), ("Groove", 9.0)], thickness_mm=6.0)
    # 3 mm into a 6 mm board -> Blind; 9 mm reaches through -> Through All.
    assert dialog._rows[0][2].currentText() == "Blind"
    assert dialog._rows[1][2].currentText() == "Through All"
    dialog._rows[0][1].setCurrentText("Skip")
    jobs = dialog.jobs()
    assert [(name, kind, cond) for name, kind, cond, _ in jobs] == [
        ("Groove", "cut", "Through All")
    ]
    assert abs(jobs[0][3] - 0.009) < 1e-9  # depth handed to the bridge is in meters

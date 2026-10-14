"""Single-instance launch handoff used by the SolidWorks add-in's two buttons."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from curvemill.app import MainWindow, _launch_message


def _app():
    return QApplication.instance() or QApplication([])


def test_launch_message_maps_the_send_flag():
    # "Send to CurveMill" passes --get-selection; "Open CurveMill" passes nothing.
    assert _launch_message([]) == "open"
    assert _launch_message(["--get-selection"]) == "get-selection"
    assert _launch_message(["--other"]) == "open"


def test_handle_launch_request_pulls_the_face_only_for_get_selection():
    _app()
    window = MainWindow()
    calls = []
    window._sw_get_board = lambda: calls.append("board")

    window.handle_launch_request("open")
    assert calls == []  # a plain "Open" foregrounds but never touches SolidWorks

    window.handle_launch_request("get-selection")
    assert calls == ["board"]  # "Send" foregrounds and pulls the selected face
    window.close()

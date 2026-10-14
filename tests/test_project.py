"""A .curvemill project reopens the session exactly as it was saved."""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from curvemill import project
from curvemill.app import MainWindow
from curvemill.geometry import count_profile_issues
from curvemill.models import Layer, SplineEntity, Tool, ToolKind, VectorEntity


def _app():
    return QApplication.instance() or QApplication([])


def test_project_round_trips_a_session(tmp_path):
    _app()
    window = MainWindow()
    square = VectorEntity(points=[(0, 0), (10, 0), (10, 10), (0, 10)], closed=True, layer="Cuts")
    curve = SplineEntity(control_points=[(0, 0), (5, 9), (12, 3)], layer="Carve")
    window.editor.load([square], [curve])
    # The tool/depth are properties of the layer now: the "Cuts" layer carries a
    # tapered bit at 4 mm, which the form loads back when the project reopens.
    cuts_tool = Tool("t", ToolKind.TAPERED, diameter=6.0, taper_angle_deg=30.0, tip_diameter=1.5)
    window.editor.layers = [
        Layer("Cuts", depth=4.0, tool=cuts_tool),
        Layer("Carve", visible=False),
        Layer("Empty"),
    ]
    window.editor.active_layer = "Carve"
    window.board_width.setValue(321.0)

    path = tmp_path / "session.curvemill"
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
    assert [v.points for v in reopened.editor.vectors] == [square.points]
    assert reopened.editor.vectors[0].closed is True
    assert reopened.editor.splines[0].control_points == curve.control_points
    # Empty layers and visibility flags survive; rebuilding from geometry loses both.
    assert [(layer.name, layer.visible) for layer in reopened.editor.layers] == [
        ("Cuts", True),
        ("Carve", False),
        ("Empty", True),
    ]
    assert reopened.editor.active_layer == "Carve"
    assert reopened.board_width.value() == 321.0
    # The Cuts layer is selected on open, so its tapered recipe fills the toolbar.
    assert reopened.editor.layers[0].tool.kind is ToolKind.TAPERED
    assert reopened.tool_combo.currentData() == "tapered"
    assert reopened.tool_tip.value() == 1.5
    assert reopened.cut_depth.value() == 4.0
    # Opening a project puts it at the top of the recent list.
    assert reopened._recent_projects()[0] == str(path)
    reopened.close()


def test_dimensions_survive_a_project_round_trip(tmp_path):
    # Dims live only in the window's _dim_store (never in the geometry), so save()
    # must serialize them or every Smart Dimension is lost on reopen.
    from curvemill.dimensions import Dimension, Feature

    dim = Dimension(
        feat1=Feature("pattern", "left", "center"),
        feat2=Feature("pattern", "right", "center"),
        axis="x", value=42.0, label_offset=3.0,
    )
    store = {frozenset({7, 9}): [dim]}
    path = tmp_path / "dims.curvemill"
    project.save(path, [], [], [], "", {}, store)

    *_, loaded = project.load(path)
    (ids, dims), = loaded.items()
    assert ids == frozenset({7, 9})
    got = dims[0]
    assert got.feat1 == Feature("pattern", "left", "center")
    assert got.feat2 == Feature("pattern", "right", "center")
    assert got.axis == "x" and got.value == 42.0 and got.label_offset == 3.0


def test_loading_advances_the_id_counter_past_saved_ids(tmp_path):
    # The id counter restarts at 1 each process; loading entities that kept high
    # saved ids must push it past them, or the next new entity re-mints a used id
    # and collides (breaking selection, grouping and dim_store keys).
    from curvemill.models import VectorEntity

    saved = [VectorEntity(points=[(0, 0), (1, 1)], id=5000)]
    path = tmp_path / "ids.curvemill"
    project.save(path, saved, [], [], "", {})

    loaded, *_ = project.load(path)
    fresh = VectorEntity(points=[(2, 2), (3, 3)])  # minted from the shared counter
    assert fresh.id > loaded[0].id  # no collision with the restored id


def test_autosave_survives_a_crash_and_restores(tmp_path):
    """Autosave writes on content; a fresh window reopens it; a clean exit clears it."""
    _app()
    window = MainWindow()
    # An empty editor must not write a file â€” that would trigger a spurious restore.
    window._autosave()
    assert not window._autosave_path.exists()

    square = VectorEntity(points=[(0, 0), (10, 0), (10, 10), (0, 10)], closed=True)
    window.editor.load([square], [])
    window._autosave()
    assert window._autosave_path.exists()  # content present -> recovery point written
    window.close()  # clean exit deletes it, so no restore is offered next launch
    assert not window._autosave_path.exists()

    # Simulate a crash: the file is there, and a new session recovers it without
    # polluting Recent or claiming a save location.
    window.editor.load([square], [])
    window._autosave()
    recovered = MainWindow()
    assert recovered._autosave_path.exists()  # same isolated dir via conftest
    recovered.open_project(recovered._autosave_path, remember=False)
    recovered.current_file = None
    assert [v.points for v in recovered.editor.vectors] == [square.points]
    assert recovered._recent_projects() == []
    recovered.close()


def test_saved_project_reports_the_same_faults_when_reopened(tmp_path):
    """A project must not invent open profiles or multi-vertex junctions.

    Geometry with a real open profile and a real three-way junction: the counts
    have to survive the JSON round trip exactly, in both directions.
    """
    _app()
    window = MainWindow()
    junction = [
        VectorEntity(points=[(0, 0), (10, 0)]),
        VectorEntity(points=[(10, 0), (20, 0)]),
        VectorEntity(points=[(10, 0), (10, 10)]),
        VectorEntity(points=[(40, 40), (50, 45)]),
    ]
    window.editor.load(junction, [SplineEntity(control_points=[(0, 0), (5, 9), (12, 3)])])
    window._update_open_profile_count()
    before = count_profile_issues(window.editor.all_visible_vectors())
    assert before.open_profiles and before.multi_vertex  # the fixture really is faulty

    path = tmp_path / "faults.curvemill"
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
    assert count_profile_issues(reopened.editor.all_visible_vectors()) == before
    reopened.close()


def test_moving_part_of_a_drawing_refreshes_the_fault_count(tmp_path):
    """Dragging a subset separates endpoints, so the count must recompute.

    Otherwise the canvas keeps showing the pre-move count and the faults only
    surface when the project is reopened.
    """
    _app()
    window = MainWindow()
    square = [
        VectorEntity(points=[(0, 0), (10, 0)]),
        VectorEntity(points=[(10, 0), (10, 10)]),
        VectorEntity(points=[(10, 10), (0, 10)]),
        VectorEntity(points=[(0, 10), (0, 0)]),
    ]
    window.editor.load(square, [])
    window._update_open_profile_count()
    assert window._open_profile_count == 0

    window.editor.selected_ids = {window.editor.vectors[0].id}
    window.editor.move_selected(3.0, 3.0)
    window._on_editor_changed(topology_changed=True, visuals_current=True)
    assert window._open_profile_count == 2
    window.close()


def test_load_reports_a_clear_error_for_a_damaged_file(tmp_path):
    # Not JSON at all.
    bad = tmp_path / "broken.curvemill"
    bad.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(ValueError):
        project.load(bad)

    # Valid JSON of the right version, but an entity is missing required keys.
    half = tmp_path / "half.curvemill"
    half.write_text(
        json.dumps({"format": project.FORMAT_VERSION, "vectors": [{"nope": 1}],
                    "splines": [], "layers": [], "active_layer": "0"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        project.load(half)

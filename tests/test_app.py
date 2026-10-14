import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QKeySequence, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from curvemill.app import MainWindow, _constrain_move_delta, _preserve_resize_aspect
from curvemill.dimensions import Dimension, Feature
from curvemill.geometry import process_vectors
from curvemill.models import ImportResult, ProcessOptions, ProcessResult, ProcessWarning, TraceMode, VectorEntity


def _app():
    return QApplication.instance() or QApplication([])


def test_editor_action_labels_shortcuts_and_layer_panel():
    _app()
    window = MainWindow()

    assert window.select_tool_action.text() == "Box Lasso (L)"
    assert window.select_tool_action.shortcut() == QKeySequence("L")
    assert window.free_lasso_tool_action.text() == "Free Lasso (F)"
    assert window.free_lasso_tool_action.shortcut() == QKeySequence("F")
    assert not hasattr(window, "move_tool_action")  # folded into Select: drag inside selection moves
    assert window.delete_action.text() == "Delete (DEL)"
    assert window.smooth_action.text() == "Smooth Vectors (S)"
    assert window.smooth_action.shortcut() == QKeySequence("S")
    assert window.open_button.text() == "Insert DXF Files"
    assert window.layer_list.topLevelItemCount() == 1
    window.close()


def test_warnings_dock_hidden_on_library_and_settings_tabs():
    _app()
    window = MainWindow()
    # Warnings/Log relate to geometry -- present on Editor/Simulation, gone on
    # Library/Settings, and the user's own choice restored on return.
    # isHidden() reads the widget's own flag (the window isn't shown in tests, so
    # isVisible() would be False for every child regardless).
    assert not window.warnings_dock.isHidden()
    window.tabs.setCurrentWidget(window._library_tab)
    assert window.warnings_dock.isHidden()
    window.tabs.setCurrentWidget(window._settings_tab)
    assert window.warnings_dock.isHidden()
    window.tabs.setCurrentWidget(window._sim_tab)
    assert not window.warnings_dock.isHidden()
    window.close()


def test_shift_move_constraint_and_repeated_imports_append_layers():
    origin = QPointF(10, 10)
    shift = Qt.KeyboardModifier.ShiftModifier
    assert _constrain_move_delta(origin, QPointF(30, 13), shift) == (20, 0)
    assert _constrain_move_delta(origin, QPointF(13, 30), shift) == (0, 20)

    _app()
    window = MainWindow()
    first = VectorEntity(points=[(0, 0), (10, 0)])
    second = VectorEntity(points=[(20, 0), (30, 0)])
    window._on_import_done([(Path("first.dxf"), ImportResult([first], units="mm"))])
    window._on_import_done([(Path("second.dxf"), ImportResult([second], units="mm"))])

    assert window.editor.layer_names() == ["first", "second"]
    assert [(vector.layer, vector.points) for vector in window.editor.vectors] == [
        ("first", first.points),
        ("second", second.points),
    ]
    window.close()


def test_optimize_replaces_geometry_in_editor_without_saving(monkeypatch):
    # Optimize is now a pure in-editor transform: swap the pattern for fitted
    # splines, refresh the error counts, and never open a save dialog. This is the
    # decoupling that lets the user see fit-introduced errors before sending.
    from curvemill.geometry import fit_vector_chains, join_spline_fragments
    _app()
    window = MainWindow()
    pts = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    soup = [VectorEntity(points=[a, b]) for a, b in zip(pts, pts[1:])]
    window.editor.load(soup)
    monkeypatch.setattr(
        "curvemill.app.QFileDialog.getSaveFileName",
        lambda *a, **k: pytest.fail("optimize must not open a save dialog"),
    )
    curves = fit_vector_chains(soup)
    window._on_optimize_done((curves, len(join_spline_fragments(curves))))

    assert window.editor.splines and not window.editor.vectors  # swapped in place
    window.close()


def test_optimize_only_reads_and_replaces_the_active_layer():
    # Optimize must operate on the active layer ALONE. It reads active-layer
    # geometry and writes the fit back onto the active layer; if it read all
    # visible layers instead, other layers' shapes would be merged onto the active
    # one and duplicated (they'd exist on both). Two visible layers, one active.
    _app()
    window = MainWindow()
    a = VectorEntity(points=[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)], layer="A")
    b = VectorEntity(points=[(20, 0), (30, 0), (30, 10), (20, 10), (20, 0)], layer="B")
    window.editor.load([a, b])  # -> visible layers "A" and "B", active = "A"
    assert window.editor.active_layer == "A"

    av, asp = window.editor.active_vectors_and_splines()
    assert [v.layer for v in av] == ["A"] and asp == []  # active layer only

    from curvemill.geometry import fit_vector_chains, join_spline_fragments
    curves = fit_vector_chains(av)
    window._on_optimize_done((curves, len(join_spline_fragments(curves))))

    # B is untouched; A's fitted splines all carry layer "A" -- nothing from B leaked.
    assert [v.layer for v in window.editor.vectors] == ["B"]
    assert {s.layer for s in window.editor.splines} == {"A"}
    window.close()


def test_replace_with_corrected_puts_milled_geometry_on_canvas():
    # 'Replace with Corrected' pushes the as-milled outlines onto the canvas so the
    # single Export/Send path uses them -- no separate corrected-export button.
    from curvemill.geometry import process_layers, result_export_vectors
    _app()
    window = MainWindow()
    square = VectorEntity(points=[(0, 0), (20, 0), (20, 20), (0, 20)], closed=True)
    window.editor.load([square])
    result = process_layers(window._layer_jobs())
    window.current_result = result
    corrected = result_export_vectors(result)
    assert corrected  # the sim produced tool-corrected outlines

    window.replace_with_corrected()
    assert len(window.editor.vectors) == len(corrected)
    assert window.editor.splines == []
    # The corrected geometry sits on its own layer -- that layer must be registered
    # and visible, or it filters out of the canvas and the sim (blank-canvas bug).
    assert window.editor.visible_vectors() == window.editor.vectors
    window.close()


def test_replace_with_simulated_keeps_layers_and_tools_separate():
    # Two layers must stay two layers, each keeping its own tool -- not merged onto
    # one CNC_CORRECTED layer, not reset to the default tool diameter.
    from curvemill.geometry import process_layers
    from curvemill.models import Layer, Tool
    _app()
    window = MainWindow()
    a = VectorEntity(points=[(0, 0), (20, 0), (20, 20), (0, 20)], closed=True, layer="A")
    b = VectorEntity(points=[(40, 0), (60, 0), (60, 20), (40, 20)], closed=True, layer="B")
    window.editor.load([a, b])
    window.editor.layers = [
        Layer("A", tool=Tool(name="Flat end", diameter=3)),
        Layer("B", tool=Tool(name="Flat end", diameter=5)),
    ]
    window.current_result = process_layers(window._layer_jobs())

    window.replace_with_corrected()

    assert {l.name for l in window.editor.layers} == {"A", "B"}  # not merged
    assert {v.layer for v in window.editor.vectors} == {"A", "B"}
    by_name = {l.name: l for l in window.editor.layers}
    assert by_name["A"].tool.diameter == 3 and by_name["B"].tool.diameter == 5  # tools kept
    window.close()


def test_save_overwrites_existing_project_without_prompting(tmp_path, monkeypatch):
    from curvemill import project
    _app()
    window = MainWindow()
    window.editor.load([VectorEntity(points=[(0, 0), (10, 0)])])
    target = tmp_path / "part.curvemill"
    calls = []

    def fake_dialog(*_args, **_kwargs):
        calls.append(1)
        return str(target), ""

    monkeypatch.setattr("curvemill.app.QFileDialog.getSaveFileName", fake_dialog)

    window.save_project()  # fresh import -> prompts once
    window.save_project()  # already a project -> overwrites, no second prompt
    assert len(calls) == 1
    assert target.exists()
    assert window.current_file == target

    # Save As on an already-saved project prompts again and writes a separate copy,
    # leaving the original in place.
    copy = tmp_path / "copy.curvemill"
    monkeypatch.setattr("curvemill.app.QFileDialog.getSaveFileName", lambda *a, **k: (str(copy), ""))
    window.save_project_as()
    assert copy.exists() and target.exists()
    assert window.current_file == copy
    window.close()


def test_save_button_greys_out_when_state_matches_last_save(tmp_path, monkeypatch):
    _app()
    window = MainWindow()
    # Fresh empty session is clean -> Save disabled.
    assert not window._is_dirty()
    assert not window.save_action.isEnabled()

    window.editor.load([VectorEntity(points=[(0, 0), (10, 0)])])
    window._sync_action_states()
    assert window._is_dirty()  # geometry added
    assert window.save_action.isEnabled()

    target = tmp_path / "part.curvemill"
    monkeypatch.setattr("curvemill.app.QFileDialog.getSaveFileName", lambda *a, **k: (str(target), ""))
    window.save_project()
    assert not window._is_dirty()  # live state now matches disk
    assert not window.save_action.isEnabled()

    # A later edit dirties it again.
    window.editor.load([VectorEntity(points=[(0, 0), (99, 0)])])
    window._sync_action_states()
    assert window._is_dirty() and window.save_action.isEnabled()
    window.close()


def test_selection_change_does_not_reserialize_the_project():
    # _is_dirty() serialises the whole project to JSON (~30ms on big files). It runs
    # inside _sync_action_states, which selection/zoom trigger constantly -- but
    # selection can't change what's on disk, so the selection path must NOT re-hash.
    # An edit still must. Guards the big-file selection-lag fix.
    _app()
    window = MainWindow()
    window.editor.load([VectorEntity(points=[(0, 0), (10, 0), (10, 10)], closed=True)])
    window._mark_saved()

    calls = []
    original = window._project_signature
    window._project_signature = lambda: (calls.append(1), original())[1]

    window.editor.select_all()
    window.view.refresh_selection()  # the selection hot path
    assert calls == [], "selecting must not re-serialise the project"

    window.editor.delete_selected()
    window._on_editor_changed(topology_changed=True)  # a real edit
    assert calls, "an edit must re-check dirtiness"
    assert window.save_action.isEnabled()  # doc now differs from the last save
    window.close()


def test_new_project_prompts_when_dirty_and_clears_on_confirm(monkeypatch):
    _app()
    window = MainWindow()
    window.editor.load([VectorEntity(points=[(0, 0), (10, 0)])])
    window._sync_action_states()

    # Stub _confirm_discard (the dialog is Qt-native and can't be clicked headless).
    # Cancel keeps the drawing.
    monkeypatch.setattr(MainWindow, "_confirm_discard", lambda self, q: False)
    window.new_project()
    assert window.editor.vectors  # untouched

    monkeypatch.setattr(MainWindow, "_confirm_discard", lambda self, q: True)
    window.new_project()
    assert not window.editor.vectors  # cleared
    assert window.current_file is None
    assert not window._is_dirty()  # empty session is the new clean baseline
    window.close()


def test_entity_count_column_shows_cached_sw_count():
    _app()
    window = MainWindow()
    square = VectorEntity(points=[(0, 0), (20, 0), (20, 20), (0, 20)], closed=True, layer="A")
    window.editor.load([square])
    window._layer_entity_counts = {"A": 7}
    window._refresh_layers()
    item = next(window.layer_list.topLevelItem(i) for i in range(window.layer_list.topLevelItemCount())
                if window.layer_list.topLevelItem(i).text(0) == "A")
    assert item.text(1) == "7"  # the Entities column shows the SW count, not the shape count
    window.close()


def test_geometry_change_triggers_background_sw_recount():
    _app()
    window = MainWindow()
    square = VectorEntity(points=[(0, 0), (20, 0), (20, 20), (0, 20)], closed=True, layer="A")
    window.editor.load([square])
    window._entity_recount_busy = False
    window._entity_recount_pending = False

    window._refresh()  # every geometry change/load routes through here
    assert window._entity_recount_busy or window._entity_recount_pending  # a fit was requested

    window.thread_pool.waitForDone(5000)
    for _ in range(20):
        QApplication.processEvents()
        if window._layer_entity_counts.get("A"):
            break
    assert window._layer_entity_counts.get("A", 0) > 0  # exact SW count landed off-thread
    window.close()


def test_hidden_layer_keeps_its_entity_count():
    # Hiding a layer must not change its Entities number: the count is a property
    # of the geometry, not visibility. The recount used to snapshot only visible
    # geometry, so a hidden layer dropped out and its row fell back to the raw
    # shape count -- the number visibly changed the moment you unchecked it.
    _app()
    window = MainWindow()
    a = VectorEntity(points=[(0, 0), (20, 0), (20, 20), (0, 20)], closed=True, layer="A")
    b = VectorEntity(points=[(0, 30), (20, 30), (20, 50), (0, 50)], closed=True, layer="B")
    window.editor.load([a, b])
    window.editor.set_layer_visibility("B", False)

    window._request_entity_recount()
    # A construction-time recount on the empty editor may still be queued; draining
    # each worker in turn (it chains the next from its done handler) reaches ours.
    for _ in range(50):
        window.thread_pool.waitForDone(200)
        QApplication.processEvents()
        if window._layer_entity_counts.get("B"):
            break

    assert window._layer_entity_counts.get("B", 0) > 0  # hidden layer still counted
    window.close()


def test_layer_visibility_updates_preview_and_open_profile_count():
    _app()
    window = MainWindow()
    visible = VectorEntity(points=[(0, 0), (10, 0)], layer="Visible")
    hidden = VectorEntity(points=[(0, 10), (10, 10)], layer="Hidden")
    window.editor.load([visible, hidden])
    window.editor.set_layer_visibility("Hidden", False)

    window._refresh(update_open_profiles=True)

    assert set(window.view._vector_items) == {visible.id}
    # The counts live on a canvas overlay now, and the hidden layer is excluded.
    assert window.view.count_labels["open_profiles"].text() == "Open profiles: 1"
    assert window.layer_list.topLevelItemCount() == 2
    window.close()


def test_canvas_overlay_counts_open_duplicate_and_multi_vertex_profiles():
    _app()
    window = MainWindow()
    # A closed square, drawn twice (the duplicate), plus three open segments that
    # all end at the same point -- the vertex SolidWorks refuses as over-used.
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    window.editor.load(
        [
            VectorEntity(points=list(square), closed=True),
            # Same square, opposite direction and a different start vertex: still a
            # duplicate, and the count has to see through both.
            VectorEntity(points=[(10, 10), (10, 0), (0, 0), (0, 10)], closed=True),
            VectorEntity(points=[(30, 30), (40, 40)]),
            VectorEntity(points=[(50, 30), (40, 40)]),
            VectorEntity(points=[(40, 60), (40, 40)]),
        ]
    )

    window._refresh(update_open_profiles=True)

    labels = window.view.count_labels
    assert labels["duplicates"].text() == "Duplicates: 1"
    assert labels["multi_vertex"].text() == "Multiple vertex usage: 1"
    # A chain has only two free ends, so two of the three segments join and the
    # third is stranded: the over-used vertex is exactly why this cannot close.
    assert labels["open_profiles"].text() == "Open profiles: 2"
    window.close()


def test_log_tab_records_actions_and_copies_selected_text(monkeypatch):
    _app()
    window = MainWindow()
    assert window.warnings_tabs.tabText(0) == "Warnings"
    assert window.warnings_tabs.tabText(1) == "Log"
    assert window.log_view.isReadOnly()

    window._finish_progress("Repair complete")
    # The error path pops a modal dialog, which would block a headless run.
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    window._on_worker_error("Could not process DXF", "board is too small")

    log = window.log_view.toPlainText()
    assert "INFO" in log and "Repair complete" in log
    assert "ERROR" in log and "Could not process DXF: board is too small" in log

    # Nothing selected copies the whole log.
    assert window._log_copy_text() == log
    # A selection copies out as real newlines, not Qt's U+2029 separators.
    window.log_view.selectAll()
    copied = window._log_copy_text()
    assert "\u2029" not in copied
    assert copied.splitlines() == log.splitlines()
    window.close()


def test_dimensions_drive_width_and_top_clearance():
    _app()
    window = MainWindow()
    flower = VectorEntity(points=[(10, 10), (20, 45), (35, 15)])
    window.editor.load([flower])
    window.editor.select_all()
    window._refresh()

    assert window.selection_layout_group.isEnabled()
    assert window.layout_readouts["top"].text() == "355.000 mm"
    key = frozenset(window.editor.selected_target_ids())
    width_dim = Dimension(
        Feature("pattern", "left", "center"), Feature("pattern", "right", "center"), axis="x", value=50.0
    )
    top_dim = Dimension(
        Feature("pattern", "center", "top"), Feature("board", "center", "top"), axis="y", value=3.0
    )
    window._dim_store[key] = [width_dim, top_dim]
    window._apply_dims_to_geometry()

    bounds = window.editor.selected_bounds()
    assert bounds is not None
    assert round(bounds[2] - bounds[0], 6) == 50
    assert round(window.board_height.value() - bounds[3], 6) == 3
    assert len(window.view._dim_items) == 2
    assert window.current_result is None
    window.close()


def test_align_keeps_the_moved_selection_on_screen():
    _app()
    window = MainWindow()
    # A DXF drawn far from the origin, zoomed in the way you would work on it.
    window.editor.load(
        [VectorEntity(points=[(12000, 8000), (12120, 8000), (12120, 8100), (12000, 8100)], closed=True)]
    )
    window.resize(1400, 900)
    window.show()
    window._refresh()
    window.view.fitInView(QRectF(11950, 7950, 220, 200), Qt.AspectRatioMode.KeepAspectRatio)
    window.editor.select_all()
    window.view.refresh_selection()

    window._align_selection("center", "center")

    # Centring teleports the pattern onto the board; the camera has to follow it,
    # or the pattern reads as having vanished from the canvas.
    x1, y1, x2, y2 = window.editor.selected_bounds()
    assert (round((x1 + x2) / 2, 6), round((y1 + y2) / 2, 6)) == (300.0, 200.0)
    visible = window.view.mapToScene(window.view.viewport().rect()).boundingRect()
    assert visible.intersects(QRectF(x1, y1, x2 - x1, y2 - y1))
    window.close()


def test_selection_layout_dock_fits_and_aligns_the_selected_extrema():
    _app()
    window = MainWindow()
    pattern = VectorEntity(points=[(10, 10), (30, 40), (50, 20)])
    window.editor.load([pattern])
    window.editor.select_all()
    window._refresh()

    assert window.selection_layout_group.parentWidget() is not None
    assert window.dockWidgetArea(window.layers_dock) == Qt.DockWidgetArea.RightDockWidgetArea
    assert window.fit_board_width_button.isEnabled()
    window._fit_selection_to_board("width")
    fitted = window.editor.selected_bounds()
    assert fitted is not None
    assert round(fitted[2] - fitted[0], 6) == window.board_width.value()
    assert round(fitted[3] - fitted[1], 6) == 450

    window._align_selection("center", "top")
    aligned = window.editor.selected_bounds()
    assert aligned is not None
    assert round((aligned[0] + aligned[2]) / 2, 6) == window.board_width.value() / 2
    assert round(aligned[3], 6) == window.board_height.value()
    window.close()


def test_cut_then_paste_shortcut_after_switching_layers():
    app = _app()
    window = MainWindow()
    window.show()
    window.activateWindow()
    app.processEvents()
    source = VectorEntity(points=[(0, 0), (10, 0)], layer="Source")
    window.editor.load([source])
    window.editor.add_layer("Target")
    window.editor.set_active_layer("Source")
    window.editor.select_all()
    window._refresh()

    window.view.setFocus()
    app.processEvents()
    QTest.keyClick(app.focusWidget(), Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()

    assert window.editor.vectors == []
    assert len(window.vector_clipboard) == 1

    target_item = next(
        window.layer_list.topLevelItem(index)
        for index in range(window.layer_list.topLevelItemCount())
        if window.layer_list.topLevelItem(index).text(0) == "Target"
    )
    window.layer_list.setCurrentItem(target_item)
    window.layer_list.setFocus()
    app.processEvents()
    QTest.keyClick(app.focusWidget(), Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)

    assert len(window.editor.vectors) == 1
    assert window.editor.vectors[0].layer == "Target"
    window.close()


def test_warning_balloons_toggle_do_not_overlap_and_survive_redraw():
    app = _app()
    window = MainWindow()
    window.show()
    tiny = VectorEntity(points=[(10, 10), (12, 10), (12, 12), (10, 12)], closed=True)
    open_path = VectorEntity(points=[(5, 5), (20, 5)])
    result = process_vectors(
        [tiny, open_path],
        ProcessOptions(endmill_diameter=10, trace_mode=TraceMode.INSIDE),
    )
    window._on_process_done(result)
    app.processEvents()

    assert window.warning_list.count() == 2
    first_item = window.warning_list.item(0)
    second_item = window.warning_list.item(1)
    center_before = window.view.mapToScene(window.view.viewport().rect().center())
    window._on_warning_clicked(first_item)
    window._on_warning_clicked(second_item)
    app.processEvents()

    assert len(window.view._warning_states) == 2
    center_after = window.view.mapToScene(window.view.viewport().rect().center())
    assert abs(center_after.x() - center_before.x()) <= 3
    assert abs(center_after.y() - center_before.y()) <= 3
    first_key = first_item.data(Qt.ItemDataRole.UserRole)
    second_key = second_item.data(Qt.ItemDataRole.UserRole)
    first_balloon = window.view._warning_items[first_key]
    second_balloon = window.view._warning_items[second_key]
    assert not first_balloon.sceneBoundingRect().intersects(second_balloon.sceneBoundingRect())
    assert window.view._warning_states[first_key].context_vectors

    first_balloon.setPos(QPointF(-1000, -1000))
    assert window.view.sceneRect().contains(first_balloon.sceneBoundingRect())
    original_second_position = second_balloon.pos()
    second_balloon.setPos(first_balloon.pos())
    assert second_balloon.pos() == original_second_position

    first_position = window.view._warning_states[first_key].position
    window.view.set_show_vectors(False)
    app.processEvents()
    assert first_key in window.view._warning_highlight_items
    assert window.view._warning_states[first_key].position == first_position

    arrow = window.view._warning_arrow_items[first_key].path()
    target = result.warning_details[0].path
    target_points = {(round(x, 6), round(y, 6)) for x, y in target.points}
    arrow_target = (round(arrow.elementAt(1).x, 6), round(arrow.elementAt(1).y, 6))
    assert arrow_target in target_points or target.bounds()[0] <= arrow_target[0] <= target.bounds()[2]

    window._on_warning_clicked(first_item)
    assert not window.view.has_warning_balloon(first_key)
    assert window.view.has_warning_balloon(second_key)
    window._clear_warning_balloons()
    assert not window.view._warning_states
    window.close()


def test_warning_state_clears_when_result_becomes_stale_and_pathless_rows_do_not_toggle():
    _app()
    window = MainWindow()
    path = VectorEntity(points=[(0, 0), (10, 0)])
    result = process_vectors(
        [path],
        ProcessOptions(endmill_diameter=2, trace_mode=TraceMode.INSIDE),
    )
    window._on_process_done(result)
    warning_item = window.warning_list.item(0)
    window._on_warning_clicked(warning_item)
    assert window.view._warning_states

    window._invalidate_approval()

    assert not window.view._warning_states
    assert window.warning_list.count() == 0

    window._set_warnings(["Ignored unsupported entity TEXT on layer 0."], [])
    pathless = window.warning_list.item(0)
    window._on_warning_clicked(pathless)
    assert not window.view._warning_states
    window.close()


def test_warning_balloons_keep_screen_size_through_zoom_and_select_all():
    app = _app()
    window = MainWindow()
    window.show()
    tiny = VectorEntity(points=[(10, 10), (12, 10), (12, 12), (10, 12)], closed=True)
    open_path = VectorEntity(points=[(5, 5), (20, 5)])
    result = process_vectors(
        [tiny, open_path],
        ProcessOptions(endmill_diameter=10, trace_mode=TraceMode.INSIDE),
    )
    window._on_process_done(result)
    window.select_all_warnings_button.click()
    app.processEvents()

    assert len(window.view._warning_states) == 2
    assert all(
        window.warning_list.item(index).checkState() == Qt.CheckState.Checked
        for index in range(window.warning_list.count())
    )
    # Process lands on the Simulation tab; this test measures editor-view zoom, so
    # move back so the editor view owns balloon sizing again.
    window.tabs.setCurrentWidget(window._editor_tab)
    app.processEvents()
    key = result.warning_details[0].key
    view_positions_before = window.view._warning_view_positions()
    before = window.view.viewportTransform().mapRect(window.view._warning_items[key].sceneBoundingRect())

    window.view.scale(0.2, 0.2)
    window.view._restore_warning_view_geometry()
    app.processEvents()
    after = window.view.viewportTransform().mapRect(window.view._warning_items[key].sceneBoundingRect())

    view_positions_after = window.view._warning_view_positions()
    assert any(view_positions_after[item] != view_positions_before[item] for item in view_positions_before)
    assert abs(after.width() - before.width()) <= 2
    assert abs(after.height() - before.height()) <= 2
    assert after.width() >= 275
    assert after.height() >= 205
    balloon_sizes = {
        (
            round(window.view.viewportTransform().mapRect(item.sceneBoundingRect()).width()),
            round(window.view.viewportTransform().mapRect(item.sceneBoundingRect()).height()),
        )
        for item in window.view._warning_items.values()
    }
    assert len(balloon_sizes) == 1
    balloon_rects = [
        window.view.viewportTransform().mapRect(item.sceneBoundingRect())
        for item in window.view._warning_items.values()
    ]
    assert all(
        not first.intersects(second)
        for index, first in enumerate(balloon_rects)
        for second in balloon_rects[index + 1 :]
    )
    window.close()


def test_canvas_icon_controls_toggle_vectors_and_fit_all_content():
    app = _app()
    window = MainWindow()
    window.show()
    distant = VectorEntity(points=[(5000, 3000), (5100, 3050)])
    window.editor.load([distant])
    window._refresh()
    app.processEvents()

    assert not window.show_vectors_action.icon().isNull()
    assert not window.fit_content_action.icon().isNull()
    assert window.view.vector_toggle_button.defaultAction() is window.show_vectors_action
    assert window.view.fit_content_button.defaultAction() is window.fit_content_action

    vector_items_before = dict(window.view._vector_items)
    center_before_toggle = window.view.mapToScene(window.view.viewport().rect().center())
    window.view.vector_toggle_button.click()
    assert not window.view.show_vectors
    assert window.view._vector_items == vector_items_before
    assert all(not item.isVisible() for item in window.view._vector_items.values())
    window.view.vector_toggle_button.click()
    assert window.view.show_vectors
    center_after_toggle = window.view.mapToScene(window.view.viewport().rect().center())
    assert center_after_toggle == center_before_toggle

    window.view.fit_content_button.click()
    app.processEvents()
    assert window.view._canvas_controls.isVisible()
    assert window.view.viewport().rect().contains(window.view._canvas_controls.geometry())
    fit_icon = window.fit_content_action.icon().pixmap(24, 24).toImage()
    assert any(
        fit_icon.pixelColor(x, y).alpha() > 0 and fit_icon.pixelColor(x, y).lightness() < 100
        for x in range(fit_icon.width())
        for y in range(fit_icon.height())
    )
    viewport = window.view.viewport().rect().adjusted(-2, -2, 2, 2)
    for point in [(0, 0), (window.view.board_width, window.view.board_height), (5000, 3000), (5100, 3050)]:
        assert viewport.contains(window.view.mapFromScene(QPointF(*point)))

    center_before_move = window.view.mapToScene(window.view.viewport().rect().center())
    window.editor.select_all()
    assert window.editor.move_selected(2000, 1000)
    window.view._update_scene_rect()
    center_after_move = window.view.mapToScene(window.view.viewport().rect().center())
    pixel_tolerance = 2.0 / max(abs(window.view.transform().m11()), 1e-9)
    assert abs(center_after_move.x() - center_before_move.x()) <= pixel_tolerance
    assert abs(center_after_move.y() - center_before_move.y()) <= pixel_tolerance
    assert window.view._canvas_controls.isVisible()
    window.close()


def test_canvas_controls_stay_fixed_while_panning_with_warning_balloons():
    app = _app()
    window = MainWindow()
    window.show()
    path = VectorEntity(points=[(0, 0), (1, 0)])
    details = [
        ProcessWarning(
            key=f"pan-warning:{index}",
            kind="test",
            message=f"Warning {index}",
            vector_id=index,
            path=path,
        )
        for index in range(8)
    ]
    window._set_warnings([detail.message for detail in details], details)
    window._select_all_warnings()
    app.processEvents()

    assert window.view._canvas_controls.parent() is window.view
    geometry_before = window.view._canvas_controls.geometry()
    horizontal = window.view.horizontalScrollBar()
    vertical = window.view.verticalScrollBar()
    horizontal.setValue(min(horizontal.value() + 100, horizontal.maximum()))
    vertical.setValue(min(vertical.value() + 100, vertical.maximum()))
    app.processEvents()

    assert window.view._canvas_controls.geometry() == geometry_before
    assert window.view._canvas_controls.isVisible()
    window.close()


def test_duplicate_message_warnings_get_distinct_balloon_keys():
    # Warnings routinely share identical text; keying rows by message collapsed
    # them onto one balloon key, so checking one lit every same-text row while
    # showing a single balloon ("selects all warnings under it").
    _app()
    window = MainWindow()
    path = VectorEntity(points=[(0, 0), (1, 0)])
    details = [
        ProcessWarning(key=f"dup:{i}", kind="test", message="same text", vector_id=i, path=path)
        for i in range(3)
    ]
    window._set_warnings([d.message for d in details], details)

    keys = [window.warning_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(3)]
    assert keys == ["dup:0", "dup:1", "dup:2"]  # each row its own key, no collision

    window._on_warning_clicked(window.warning_list.item(0))  # show only the first balloon
    checked = [window.warning_list.item(i).checkState() == Qt.CheckState.Checked for i in range(3)]
    assert checked == [True, False, False]  # exactly one row checked, not all under it
    window.close()


def test_warning_balloons_size_to_the_active_tab():
    # The Simulation tab shares the editor's scene but has its own zoom, so balloons
    # must size to whichever view is on screen -- else they render tiny in the Sim tab.
    _app()
    window = MainWindow()
    window.tabs.setCurrentWidget(window._sim_tab)
    assert window.view.sizing_view is window.sim_view
    window.tabs.setCurrentWidget(window._editor_tab)
    assert window.view.sizing_view is window.view
    window.close()


def test_lasso_drag_uses_full_repaint_and_restores_it_on_release():
    app = _app()
    window = MainWindow()
    window.show()
    app.processEvents()
    start = window.view.mapFromScene(QPointF(200, 150))
    end = window.view.mapFromScene(QPointF(350, 280))

    QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    assert window.view._mode == "box"
    assert window.view.viewportUpdateMode() == window.view.ViewportUpdateMode.FullViewportUpdate
    QTest.mouseMove(window.view.viewport(), end)
    QTest.mouseRelease(window.view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    app.processEvents()

    assert window.view.viewportUpdateMode() == window.view._normal_viewport_update_mode
    assert window.view._box_item is None
    window.close()


def test_free_lasso_selects_vectors_inside_drawn_polygon():
    app = _app()
    window = MainWindow()
    window.show()
    inside = VectorEntity(points=[(50, 50), (60, 50)], layer="Layer 1")
    outside = VectorEntity(points=[(150, 150), (160, 150)], layer="Layer 1")
    window.editor.load([inside, outside])
    window._refresh()
    window.view.fit_content()
    window.free_lasso_tool_action.trigger()
    app.processEvents()

    points = [
        window.view.mapFromScene(QPointF(40, 40)),
        window.view.mapFromScene(QPointF(70, 40)),
        window.view.mapFromScene(QPointF(70, 70)),
        window.view.mapFromScene(QPointF(40, 70)),
        window.view.mapFromScene(QPointF(40, 40)),
    ]
    QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, points[0])
    assert window.view._mode == "free_lasso"
    assert window.view.viewportUpdateMode() == window.view.ViewportUpdateMode.FullViewportUpdate
    for point in points[1:]:
        QTest.mouseMove(window.view.viewport(), point)
    QTest.mouseRelease(window.view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, points[-1])
    app.processEvents()

    assert window.editor.selected_ids == {inside.id}
    assert window.view.viewportUpdateMode() == window.view._normal_viewport_update_mode
    assert window.view._free_lasso_item is None
    window.close()


def test_refresh_selection_reverts_pen_when_selection_moves():
    # refresh_selection restyles only the delta against _styled_selected_ids (a full
    # re-pen of every item cost ~400ms on big scenes). The delta's risk is a stale
    # item keeping the selected pen after the selection moves off it -- guard that.
    _app()
    window = MainWindow()
    a = VectorEntity(points=[(0, 0), (10, 0)], layer="Layer 1")
    b = VectorEntity(points=[(50, 0), (60, 0)], layer="Layer 1")
    window.editor.load([a, b])
    window._refresh()

    selected = window.view._vector_items
    window.editor.selected_ids = {a.id}
    window.view.refresh_selection()
    assert window.view._styled_selected_ids == {a.id}
    sel_color = selected[a.id].pen().color().name()

    window.editor.selected_ids = {b.id}
    window.view.refresh_selection()
    assert window.view._styled_selected_ids == {b.id}
    assert selected[b.id].pen().color().name() == sel_color
    # a must have reverted to the unselected pen, not kept the selected one.
    assert selected[a.id].pen().color().name() != sel_color
    window.close()


def test_wheel_zoom_mid_move_keeps_selection_box_on_the_dragged_geometry():
    # Wheel-zoom during a move drag rebuilds the box/handles (to stay pixel-sized)
    # via refresh_selection -- which drew them at the committed bounds and dropped
    # them out of _live_items, so they froze at the pre-drag spot until release.
    app = _app()
    window = MainWindow()
    window.show()
    vector = VectorEntity(points=[(20, 20), (120, 20), (120, 100)])
    window.editor.load([vector])
    window.editor.select_all()
    window._refresh()
    window.view.fit_content()
    view = window.view

    # Begin a move drag and offset it, mirroring mouseMoveEvent's live update.
    view._mode = "move"
    view._move_origin = QPointF(50, 50)
    view._prepare_live_items()
    assert view._selection_items and all(i in view._live_items for i in view._selection_items)
    view._move_delta = (40.0, -25.0)
    for item in view._live_items:
        item.setPos(40.0, -25.0)

    # Wheel-zoom mid-drag.
    center = view.viewport().rect().center()
    wheel = QWheelEvent(
        QPointF(center), QPointF(view.viewport().mapToGlobal(center)),
        QPoint(0, 0), QPoint(0, 120),
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    view.wheelEvent(wheel)
    app.processEvents()

    # Rebuilt decorations must be re-registered and sit at the drag offset.
    assert view._selection_items
    assert all(i in view._live_items for i in view._selection_items)
    assert all(i.pos() == QPointF(40.0, -25.0) for i in view._selection_items)
    window.close()


def test_selected_stroke_and_resize_handles_keep_screen_size_when_zooming():
    app = _app()
    window = MainWindow()
    window.show()
    vector = VectorEntity(points=[(20, 20), (120, 20), (120, 100)])
    window.editor.load([vector])
    window.editor.select_all()
    window._refresh()
    app.processEvents()

    selected_item = window.view._vector_items[vector.id]
    assert selected_item.pen().isCosmetic()
    handle = window.view._selection_items[-1]
    before = window.view.viewportTransform().mapRect(handle.sceneBoundingRect())

    window.view.scale(2.0, 2.0)
    window.view.refresh_selection()
    app.processEvents()

    selected_item = window.view._vector_items[vector.id]
    handle = window.view._selection_items[-1]
    after = window.view.viewportTransform().mapRect(handle.sceneBoundingRect())
    assert selected_item.pen().isCosmetic()
    assert abs(after.width() - before.width()) <= 2
    assert abs(after.height() - before.height()) <= 2
    window.close()


def test_canvas_uses_dxf_y_up_orientation_without_changing_model_coordinates():
    app = _app()
    window = MainWindow()
    window.show()
    asymmetric = VectorEntity(points=[(20, 10), (35, 80), (70, 25)])
    original_points = list(asymmetric.points)
    window.editor.load([asymmetric])
    window._refresh()
    window.view.fit_content()
    app.processEvents()

    low_point = window.view.mapFromScene(QPointF(20, 10))
    high_point = window.view.mapFromScene(QPointF(35, 80))
    assert window.view.transform().m22() < 0
    assert high_point.y() < low_point.y()
    assert window.editor.vectors[0].points == original_points
    window.close()


def test_multiple_import_results_become_unique_file_layers():
    _app()
    window = MainWindow()
    first = ImportResult(
        vectors=[VectorEntity(points=[(0, 0), (10, 0)])],
        units="mm",
        warnings=["first warning"],
    )
    second = ImportResult(
        vectors=[VectorEntity(points=[(0, 10), (10, 10)])],
        units="mm",
        warnings=[],
    )

    window._on_import_done([(Path("pattern.dxf"), first), (Path("pattern.dxf"), second)])

    assert window.editor.layer_names() == ["pattern", "pattern 2"]
    assert [vector.layer for vector in window.editor.vectors] == ["pattern", "pattern 2"]
    assert window.warning_list.item(0).text() == "pattern.dxf: first warning"
    window.close()


def test_resize_preserves_aspect_by_default_and_shift_enables_free_resize():
    assert _preserve_resize_aspect(Qt.KeyboardModifier.NoModifier)
    assert not _preserve_resize_aspect(Qt.KeyboardModifier.ShiftModifier)


def test_selection_and_delete_do_not_nudge_canvas():
    _app()
    window = MainWindow()
    vector = VectorEntity(points=[(10, 10), (100, 10)])
    window.editor.load([vector])
    window._refresh()
    center_before = window.view.mapToScene(window.view.viewport().rect().center())

    window.editor.select_at((50, 10), 5)
    window.view.refresh_selection()
    assert window.view.mapToScene(window.view.viewport().rect().center()) == center_before

    window._delete()
    assert window.view.mapToScene(window.view.viewport().rect().center()) == center_before
    window.close()


def test_balloon_drag_defers_arrow_and_scene_extent_updates_until_drop():
    app = _app()
    window = MainWindow()
    window.show()
    result = process_vectors(
        [VectorEntity(points=[(0, 0), (10, 0)])],
        ProcessOptions(endmill_diameter=2, trace_mode=TraceMode.INSIDE),
    )
    window._on_process_done(result)
    detail = result.warning_details[0]
    window.view.show_warning_balloon(detail)
    app.processEvents()
    balloon = window.view._warning_items[detail.key]
    update_count = 0
    original_update = window.view._update_scene_rect

    def counted_update(*args, **kwargs):
        nonlocal update_count
        update_count += 1
        return original_update(*args, **kwargs)

    window.view._update_scene_rect = counted_update
    center_before = window.view.mapToScene(window.view.viewport().rect().center())
    start = window.view.mapFromScene(balloon.sceneBoundingRect().center())
    QTest.mousePress(
        window.view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        start,
    )
    assert window.view.viewportUpdateMode() == window.view.ViewportUpdateMode.FullViewportUpdate
    assert not window.view._warning_arrow_items[detail.key].isVisible()
    QTest.mouseMove(window.view.viewport(), start + QPointF(20, 20).toPoint())
    assert update_count == 0
    QTest.mouseRelease(
        window.view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        start + QPointF(20, 20).toPoint(),
    )
    app.processEvents()
    assert update_count == 0
    assert window.view.viewportUpdateMode() == window.view._normal_viewport_update_mode
    assert window.view._warning_arrow_items[detail.key].isVisible()
    assert window.view.mapToScene(window.view.viewport().rect().center()) == center_before
    window.close()


def test_select_all_warnings_limits_bulk_balloons_to_keep_ui_responsive():
    _app()
    window = MainWindow()
    path = VectorEntity(points=[(0, 0), (1, 0)])
    details = [
        ProcessWarning(
            key=f"warning:{index}",
            kind="test",
            message=f"Warning {index}",
            vector_id=index,
            path=path,
        )
        for index in range(75)
    ]
    window._set_warnings([detail.message for detail in details], details)
    requested: list[ProcessWarning] = []
    window.view.show_warning_balloons = lambda selected: requested.extend(selected)

    window._select_all_warnings()

    assert len(requested) == window.MAX_BULK_WARNING_BALLOONS
    assert "omitted to keep the canvas responsive" in window.progress_label.text()
    window.close()


def test_locate_next_balloon_brings_active_offscreen_warning_into_view():
    app = _app()
    window = MainWindow()
    window.show()
    path = VectorEntity(points=[(0, 0), (1, 0)])
    details = [
        ProcessWarning(
            key=f"warning:{index}",
            kind="test",
            message=f"Warning {index}",
            vector_id=index,
            path=path,
        )
        for index in range(8)
    ]
    window._set_warnings([detail.message for detail in details], details)
    window._select_all_warnings()
    app.processEvents()

    offscreen_keys = {
        detail.key
        for detail in details
        if not window.view.warning_balloon_is_visible(detail.key)
    }
    assert offscreen_keys
    zoom_before = (window.view.transform().m11(), window.view.transform().m22())

    window.locate_warning_button.click()
    app.processEvents()

    located_key = window._last_located_warning_key
    assert located_key in offscreen_keys
    assert window.view.has_warning_balloon(located_key)
    assert window.view.warning_balloon_is_visible(located_key)
    assert (window.view.transform().m11(), window.view.transform().m22()) == zoom_before
    assert "Located warning balloon" in window.progress_label.text()

    active_count = len(window.view._warning_states)
    window.locate_warning_button.click()
    assert len(window.view._warning_states) == active_count
    window.close()


def _square(size=100.0):
    return VectorEntity(points=[(0, 0), (size, 0), (size, size / 2), (0, size / 2)], closed=True)


def test_optimize_button_disabled_when_no_visible_geometry():
    _app()
    window = MainWindow()
    window._refresh()
    assert not window.optimize_button.isEnabled()  # empty canvas
    window.editor.load([_square()])
    window._refresh()
    assert window.optimize_button.isEnabled()
    window.close()


def test_dimension_tool_toggles_on_and_off_with_shortcut():
    _app()
    window = MainWindow()
    assert window.dimension_tool_action.shortcut() == QKeySequence("D")
    assert window.dimension_tool_action.isCheckable()
    window.dimension_tool_action.trigger()
    assert window.view.tool == "dimension"
    assert window.tool_group.checkedAction() is None
    # Triggering again toggles the tool off, back to the box lasso.
    window.dimension_tool_action.trigger()
    assert window.view.tool == "lasso"
    assert window.tool_group.checkedAction() is window.select_tool_action
    # Picking a toolbar tool while dimensioning also turns it off.
    window.dimension_tool_action.trigger()
    window.free_lasso_tool_action.trigger()
    assert window.view.tool == "free_lasso"
    assert not window.dimension_tool_action.isChecked()
    window.close()


def test_offset_group_replaced_by_dimensions():
    _app()
    window = MainWindow()
    # The offset anchor UI is gone; Smart Dim and the manual size spinboxes remain.
    assert not hasattr(window, "apply_layout_button")
    assert not hasattr(window, "layout_offset_x")
    assert not hasattr(window, "pattern_anchor_buttons")
    assert hasattr(window, "dimension_tool_action")
    window.close()


def test_size_spinbox_resizes_selection_on_editing_finished():
    _app()
    window = MainWindow()
    window.editor.load([_square()])
    window.editor.select_all()
    window._refresh()

    window.layout_width.setValue(200.0)
    window.layout_width.editingFinished.emit()

    bounds = window.editor.selected_bounds()
    assert (bounds[2] - bounds[0]) == pytest.approx(200.0, abs=0.01)
    window.close()


def test_dimensions_persist_across_reselection():
    _app()
    window = MainWindow()
    window.editor.load([_square()])
    window.editor.select_all()
    window._refresh()
    key = frozenset(window.editor.selected_target_ids())
    dim = Dimension(
        Feature("pattern", "left", "center"),
        Feature("pattern", "right", "center"),
        axis="x",
        value=100.0,
    )
    window._dim_store[key] = [dim]

    window.editor.clear_selection()
    window.view.refresh_selection()
    assert window._active_dims() == []

    window.editor.select_all()
    window.view.refresh_selection()
    assert window._active_dims() == [dim]
    window.close()


def test_dim_survives_delete_and_returns_on_undo():
    _app()
    window = MainWindow()
    window.editor.load([_square()])
    window.editor.select_all()
    window._refresh()
    key = frozenset(window.editor.selected_target_ids())
    dim = Dimension(
        Feature("pattern", "left", "center"), Feature("board", "left", "center"), axis="x", value=5.0
    )
    window._dim_store[key] = [dim]

    window._delete()
    # Deleting the pattern hides its dims but must not discard them...
    assert window._layer_dims() == []
    assert key in window._dim_store

    window._undo()
    # ...so Undo brings the geometry back and the dim reattaches to it.
    assert [d.id for d, _, _ in window._layer_dims()] == [dim.id]
    window.close()


def test_repair_heals_self_intersections_and_undo_restores():
    # Heal is folded into Repair Vectors: a bowtie has no open profiles or
    # duplicates, so Repair must still be enabled (for the self-intersection) and
    # heal it in one click -- the zo9yyqx7 case that passed locally but failed in SW.
    _app()
    window = MainWindow()
    bowtie = VectorEntity(points=[(0, 0), (10, 10), (10, 0), (0, 10)], closed=True)
    window.editor.load([bowtie])
    window._refresh(update_open_profiles=True)
    assert window._self_intersection_count == 1
    assert window._repair_enabled()

    window.repair_vectors()  # no open profiles -> heals synchronously
    assert window._self_intersection_count == 0

    window._undo()
    window._refresh(update_open_profiles=True)
    assert window._self_intersection_count == 1
    window.close()


def test_repair_heals_self_crossing_fit_spline_after_optimize():
    # After Optimize the geometry is native fit-splines, so a self-crossing profile
    # lives in editor.splines, not .vectors -- and Repair's snap step is what turns a
    # thin fit-spline into a crosser. The heal used to scan vectors only, so the fault
    # count SAW the crossing (splines are flattened when counting) while heal never
    # cleared it: self-intersections that stuck identically on every re-click (the
    # user's "hit repair again and the numbers stay the same" at 23).
    from curvemill.models import SplineEntity
    _app()
    window = MainWindow()
    window.editor.load([VectorEntity(points=[(0, 0), (1, 0)])])  # register a visible layer "0"
    # Emulate the post-Optimize / post-snap state: a closed fit-point spline whose
    # outline crosses itself (a bowtie), held as a spline with the vectors cleared.
    window.editor.vectors = []
    window.editor.splines = [
        SplineEntity(control_points=[], fit_points=[(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)], closed=True)
    ]
    window._refresh(update_open_profiles=True)
    assert window._self_intersection_count == 1
    assert window._repair_enabled()

    window.repair_vectors()  # no open profiles -> heals synchronously
    assert window._self_intersection_count == 0
    assert window.editor.splines == []  # the crossing spline was consumed, not left behind
    assert window.editor.vectors  # replaced by the split sub-loops
    window.close()


def test_repair_heals_crossing_assembled_from_multiple_spline_pieces():
    # Optimize corner-splits a profile into SEVERAL open spline pieces. A crossing
    # that only exists when the pieces chain into one profile is invisible to any
    # per-spline check -- the fault counter (which flattens everything together)
    # counted it while heal (which only flattened individually-crossing splines)
    # never touched it: the user's repair>optimize>repair stuck at 15. Heal must
    # see exactly what the counter sees; clean splines must still stay native.
    from curvemill.models import SplineEntity
    _app()
    window = MainWindow()
    window.editor.load([VectorEntity(points=[(0, 0), (1, 0)])])  # register a visible layer "0"
    clean = SplineEntity(
        control_points=[], fit_points=[(30, 0), (40, 0), (40, 10), (30, 10), (30, 0)], closed=True
    )
    window.editor.vectors = []
    window.editor.splines = [
        # Two open halves of a bowtie: neither crosses alone; chained they do.
        SplineEntity(control_points=[], fit_points=[(0, 0), (10, 10), (10, 0)], closed=False),
        SplineEntity(control_points=[], fit_points=[(10, 0), (0, 10), (0, 0)], closed=False),
        clean,
    ]
    window._refresh(update_open_profiles=True)
    assert window._self_intersection_count == 1
    assert window._repair_enabled()

    window.repair_vectors()  # halves chain closed -> no open profiles -> synchronous heal
    assert window._self_intersection_count == 0
    assert window.editor.splines == [clean]  # crossing pieces consumed, clean stays native
    assert window.editor.vectors  # the bowtie's split sub-loops
    window.close()


def test_flip_dim_moves_pattern_to_the_other_side():
    _app()
    window = MainWindow()
    window.editor.load([_square()])
    window.editor.select_all()
    window._refresh()
    window.board_width.setValue(600.0)
    key = frozenset(window.editor.selected_target_ids())
    dim = Dimension(
        Feature("board", "left", "center"), Feature("pattern", "left", "center"), axis="x", value=20.0
    )
    window._dim_store[key] = [dim]
    window._apply_dims_to_geometry()
    assert round(window.editor.selected_bounds()[0], 3) == 20.0

    window._flip_dim(dim.id)
    # Same 20 mm gap, opposite side of the board-left reference.
    assert round(window.editor.selected_bounds()[0], 3) == -20.0
    window.close()


def test_dims_track_the_selected_layer_not_the_selection():
    _app()
    window = MainWindow()
    window.editor.load([_square()])
    window.editor.select_all()
    window._refresh()
    home = window.editor.active_layer
    key = frozenset(window.editor.selected_target_ids())
    dim = Dimension(
        Feature("pattern", "left", "center"), Feature("pattern", "right", "center"), axis="x", value=100.0
    )
    window._dim_store[key] = [dim]

    # Deselecting keeps the dim visible while its layer is the one being worked on.
    window.editor.clear_selection()
    window.view.refresh_selection()
    assert [d.id for d, _, _ in window._layer_dims()] == [dim.id]

    # Switching to another layer hides it; switching back shows it again.
    window.editor.add_layer("Other")
    assert window._layer_dims() == []
    window.editor.set_active_layer(home)
    assert [d.id for d, _, _ in window._layer_dims()] == [dim.id]
    window.close()


def test_del_removes_a_canvas_selected_dim_not_the_geometry():
    _app()
    window = MainWindow()
    window.editor.load([_square()])
    window.editor.select_all()
    window._refresh()
    key = frozenset(window.editor.selected_target_ids())
    dim = Dimension(
        Feature("pattern", "left", "center"), Feature("pattern", "right", "center"), axis="x", value=100.0
    )
    window._dim_store[key] = [dim]
    window.view.refresh_selection()

    window.view._set_selected_dim(dim.id)
    window._delete()

    assert window._find_dim(dim.id) is None  # the dim went
    assert len(window.editor.vectors) == 1  # the square stayed
    window.close()


def test_editing_driving_dimension_moves_geometry():
    _app()
    window = MainWindow()
    window.editor.load([_square()])
    window.editor.select_all()
    window._refresh()
    key = frozenset(window.editor.selected_target_ids())
    dim = Dimension(
        Feature("pattern", "left", "center"),
        Feature("pattern", "right", "center"),
        axis="x",
        value=100.0,
    )
    window._dim_store[key] = [dim]

    dim.value = 200.0
    window._apply_dims_to_geometry()

    bounds = window.editor.selected_bounds()
    assert (bounds[2] - bounds[0]) == pytest.approx(200.0, abs=0.01)
    window.close()


def test_escape_cancels_dimension_pick():
    _app()
    window = MainWindow()
    window.editor.load([_square()])
    window.editor.select_all()
    window._refresh()
    window.dimension_tool_action.trigger()
    window.view._handle_dim_click(QPointF(0.0, 0.0))
    assert window.view._dim_pick1 is not None
    assert window.view._dim_pick_items
    QTest.keyClick(window.view, Qt.Key.Key_Escape)
    assert window.view._dim_pick1 is None
    assert window.view._dim_pick_items == []
    window.close()


def test_dimensions_tab_lists_and_deletes_dims():
    _app()
    window = MainWindow()
    window.editor.load([_square()])
    window.editor.select_all()
    window._refresh()
    key = frozenset(window.editor.selected_target_ids())
    dim = Dimension(
        Feature("pattern", "left", "center"),
        Feature("pattern", "right", "center"),
        axis="x",
        value=100.0,
    )
    window._dim_store[key] = [dim]
    window.view.refresh_selection()

    assert window.dim_list.count() == 1
    assert "100" in window.dim_list.item(0).text()

    window.dim_list.setCurrentRow(0)
    window._delete_selected_dim()
    assert window._active_dims() == []
    assert window.dim_list.count() == 0
    window.close()


def test_dim_labels_track_corner_scale():
    _app()
    window = MainWindow()
    window.editor.load([_square()])
    window.editor.select_all()
    window._refresh()
    key = frozenset(window.editor.selected_target_ids())
    dim = Dimension(
        Feature("pattern", "left", "center"),
        Feature("pattern", "right", "center"),
        axis="x",
        value=100.0,
    )
    window._dim_store[key] = [dim]

    snapshot = window.editor.snapshot()
    window.editor.commit_scale_from_snapshot(snapshot, (0.0, 0.0), 2.0, 2.0)
    window.view.redraw()

    assert any("200" in item.label for item in window.view._dim_items)
    window.close()


def test_right_click_cancels_dimension_pick():
    _app()
    window = MainWindow()
    window.editor.load([_square()])
    window.editor.select_all()
    window._refresh()
    window.dimension_tool_action.trigger()
    window.view._handle_dim_click(QPointF(0.0, 0.0))
    assert window.view._dim_pick1 is not None
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(5.0, 5.0),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.view.mousePressEvent(event)
    assert window.view._dim_pick1 is None
    assert window.view._dim_pick_items == []
    window.close()


def test_dim_label_offset_persists():
    _app()
    window = MainWindow()
    window.editor.load([_square()])
    window.editor.select_all()
    window._refresh()
    key = frozenset(window.editor.selected_target_ids())
    dim = Dimension(
        Feature("pattern", "left", "center"),
        Feature("pattern", "right", "center"),
        axis="x",
        value=100.0,
    )
    window._dim_store[key] = [dim]
    window._on_dim_label_moved(dim.id, 25.0)
    assert dim.label_along == 25.0
    window.view.refresh_selection()
    item = next(i for i in window.view._dim_items if i.dim_id == dim.id)
    assert item.label_along == 25.0
    window.close()


def test_dimension_tool_reveals_dims_hidden_by_simulation_preview():
    # After a Simulate the shared scene shows the milled preview (view.result
    # set), which hides the dims. Entering the dimension tool must drop that
    # preview so the dims reappear without needing to place one first.
    _app()
    window = MainWindow()
    window.editor.load([_square()])
    window.editor.select_all()
    window._refresh()
    key = frozenset(window.editor.selected_target_ids())
    dim = Dimension(
        Feature("pattern", "left", "center"),
        Feature("pattern", "right", "center"),
        axis="x",
        value=100.0,
    )
    window._dim_store[key] = [dim]
    empty = "GEOMETRYCOLLECTION EMPTY"
    window.view.set_result(ProcessResult([], [], empty, empty, empty))
    assert not any(i.isVisible() for i in window.view._dim_items)  # hidden by preview
    window.view.set_tool("dimension")
    assert window.view.result is None
    item = next(i for i in window.view._dim_items if i.dim_id == dim.id)
    assert item.isVisible()
    window.close()

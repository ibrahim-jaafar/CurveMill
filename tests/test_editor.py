import math

import pytest

from curvemill.editor import EditorModel
from curvemill.geometry import count_open_profiles, count_profile_issues, repair_geometry
from curvemill.models import SplineEntity, VectorEntity


def test_rotate_selection_turns_a_rectangle_on_its_side():
    rect = VectorEntity(points=[(0, 0), (20, 0), (20, 10), (0, 10)], closed=True)
    editor = EditorModel([rect], [])
    editor.selected_ids = {rect.id}
    assert editor.rotate_selected(math.radians(90))
    x1, y1, x2, y2 = editor.vectors[0].bounds()
    assert round(x2 - x1, 6) == 10 and round(y2 - y1, 6) == 20  # 20x10 spun to 10x20
    assert editor.undo()  # menu rotate rides the same undo stack as the drag
    x1, y1, x2, y2 = editor.vectors[0].bounds()
    assert round(x2 - x1, 6) == 20 and round(y2 - y1, 6) == 10


def test_flip_selection_mirrors_about_centre_and_is_reversible():
    tri = VectorEntity(points=[(0, 0), (20, 0), (0, 10)], closed=True)
    editor = EditorModel([tri], [])
    editor.selected_ids = {tri.id}
    assert editor.flip_selected(horizontal=True)  # centre x = 10, so x -> 20 - x
    assert editor.vectors[0].points == [(20, 0), (0, 0), (20, 10)]
    assert editor.flip_selected(horizontal=True)  # flipping again restores it
    assert editor.vectors[0].points == [(0, 0), (20, 0), (0, 10)]


def test_rotate_and_flip_no_op_without_a_selection():
    editor = EditorModel([VectorEntity(points=[(0, 0), (10, 0)])], [])
    assert not editor.rotate_selected(math.radians(90))
    assert not editor.flip_selected(horizontal=True)


def test_spline_flatten_cache_invalidates_on_edit():
    s = SplineEntity(control_points=[(0, 0), (10, 10), (20, 0)], degree=2)
    first = s.flatten(0.5)
    second = s.flatten(0.5)
    assert second.points == first.points  # cache hit: same geometry
    assert second is not first  # ...but a distinct clone, safe to mutate
    # A move/scale reassigns control_points to a fresh list -> cache must recompute.
    s.control_points = [(x + 100.0, y) for x, y in s.control_points]
    moved = s.flatten(0.5)
    assert moved.points != first.points
    assert moved.points[0][0] == first.points[0][0] + 100.0


def test_remove_duplicates_matches_overlay_count_and_undoes():
    square = VectorEntity(points=[(0, 0), (50, 0), (50, 50), (0, 50)], closed=True)
    # Same square drawn reversed from another start vertex -- still a duplicate.
    rotated_reverse = VectorEntity(points=[(50, 50), (50, 0), (0, 0), (0, 50)], closed=True)
    spline = SplineEntity(control_points=[(0, 0), (3, 8), (12, 9), (20, 0)], degree=3)
    spline_dupe = SplineEntity(control_points=[(0, 0), (3, 8), (12, 9), (20, 0)], degree=3)
    editor = EditorModel([square, rotated_reverse], [spline, spline_dupe])

    assert count_profile_issues(editor.all_visible_vectors()).duplicates == 2
    assert editor.remove_duplicates() == 2
    assert len(editor.vectors) == 1
    assert len(editor.splines) == 1
    assert count_profile_issues(editor.all_visible_vectors()).duplicates == 0
    assert editor.undo()
    assert len(editor.vectors) == 2
    assert len(editor.splines) == 2


def test_selection_to_new_layer_cut_and_copy():
    # EditorModel clones its inputs, so look entities up by id inside the editor.
    editor = EditorModel([VectorEntity(points=[(0, 0), (10, 0)]), VectorEntity(points=[(20, 0), (30, 0)])])
    a_id, b_id = editor.vectors[0].id, editor.vectors[1].id
    layer = lambda vid: next(v for v in editor.vectors if v.id == vid).layer  # noqa: E731
    base = editor.active_layer
    editor.selected_ids = {a_id}

    # Cut: a moves to a new active layer; b stays; no new entities.
    cut_name = editor.selection_to_new_layer(copy=False)
    assert cut_name is not None and editor.active_layer == cut_name
    assert layer(a_id) == cut_name and layer(b_id) == base
    assert len(editor.vectors) == 2
    assert editor.selected_ids == {a_id}
    assert editor.undo() and layer(a_id) == base  # single undo step

    # Copy: a is duplicated onto a new layer; original stays put; clone selected.
    editor.selected_ids = {a_id}
    copy_name = editor.selection_to_new_layer(copy=True)
    assert len(editor.vectors) == 3
    clone = next(v for v in editor.vectors if v.layer == copy_name)
    assert clone.id != a_id and clone.points == [(0, 0), (10, 0)]
    assert editor.selected_ids == {clone.id}
    assert layer(a_id) == base  # original untouched

    # Nothing selected -> no-op.
    editor.selected_ids = set()
    editor.selected_spline_ids = set()
    assert editor.selection_to_new_layer(copy=False) is None


def test_select_delete_undo_redo():
    a = VectorEntity(points=[(0, 0), (10, 0)])
    b = VectorEntity(points=[(20, 0), (30, 0)])
    editor = EditorModel([a, b])

    assert editor.select_at((5, 0), 0.5) == a.id
    assert editor.delete_selected()
    assert [v.id for v in editor.vectors] == [b.id]

    assert editor.undo()
    assert {v.id for v in editor.vectors} == {a.id, b.id}
    assert editor.redo()
    assert [v.id for v in editor.vectors] == [b.id]


def test_append_layers_preserves_existing_vectors_and_uses_unique_names():
    first = VectorEntity(points=[(0, 0), (10, 0)])
    second = VectorEntity(points=[(20, 0), (30, 0)])
    editor = EditorModel()
    editor.load_layers([("Pattern", [first])])

    assert editor.append_layers([("Pattern", [second])]) == ["Pattern 2"]
    assert editor.layer_names() == ["Pattern", "Pattern 2"]
    assert [(vector.layer, vector.points) for vector in editor.vectors] == [
        ("Pattern", first.points),
        ("Pattern 2", second.points),
    ]
    assert editor.undo()
    assert editor.layer_names() == ["Pattern"]
    assert len(editor.vectors) == 1


def test_group_move_and_scale_selected_vectors():
    a = VectorEntity(points=[(0, 0), (10, 0)])
    b = VectorEntity(points=[(0, 10), (10, 10)])
    editor = EditorModel([a, b])
    editor.select_all()

    group_id = editor.group_selected()
    assert group_id is not None
    assert all(v.group_id == group_id for v in editor.vectors)

    assert editor.move_selected(5, -5)
    assert editor.vectors[0].points == [(5, -5), (15, -5)]
    assert editor.vectors[1].points == [(5, 5), (15, 5)]

    assert editor.scale_selected((5, -5), 2)
    assert editor.vectors[0].points == [(5, -5), (25, -5)]
    assert editor.vectors[1].points == [(5, 15), (25, 15)]


def test_vertex_edit_is_undoable():
    vector = VectorEntity(points=[(0, 0), (10, 0)])
    editor = EditorModel([vector])

    assert editor.edit_vertex(vector.id, 1, (12, 3))
    assert editor.vectors[0].points[1] == (12, 3)

    assert editor.undo()
    assert editor.vectors[0].points[1] == (10, 0)


def test_live_move_and_scale_preview_commit_as_single_undo_step():
    vector = VectorEntity(points=[(0, 0), (10, 0)])
    editor = EditorModel([vector])
    editor.select_all()

    before_move = editor.snapshot()
    editor.preview_move_from_snapshot(before_move, 5, 2)
    editor.preview_move_from_snapshot(before_move, 8, 3)
    assert editor.vectors[0].points == [(8, 3), (18, 3)]
    assert editor.commit_live_edit(before_move)

    assert editor.undo()
    assert editor.vectors[0].points == [(0, 0), (10, 0)]

    before_scale = editor.snapshot()
    editor.preview_scale_from_snapshot(before_scale, (0, 0), 2, 3)
    assert editor.vectors[0].points == [(0, 0), (20, 0)]
    assert editor.commit_live_edit(before_scale)

    assert editor.undo()
    assert editor.vectors[0].points == [(0, 0), (10, 0)]


def test_fast_live_transform_commits_from_press_snapshot():
    vector = VectorEntity(points=[(0, 0), (10, 5)])
    editor = EditorModel([vector])
    editor.select_all()

    before_move = editor.snapshot()
    assert editor.commit_move_from_snapshot(before_move, 4, 3)
    assert editor.vectors[0].points == [(4, 3), (14, 8)]
    assert editor.undo()
    assert editor.vectors[0].points == [(0, 0), (10, 5)]

    before_scale = editor.snapshot()
    assert editor.commit_scale_from_snapshot(before_scale, (0, 0), 2, 3)
    assert editor.vectors[0].points == [(0, 0), (20, 15)]
    assert editor.undo()
    assert editor.vectors[0].points == [(0, 0), (10, 5)]


def test_rotate_about_center_is_exact_and_undoable():
    import math

    vector = VectorEntity(points=[(0, 0), (10, 0)])
    editor = EditorModel([vector])
    editor.select_all()

    before = editor.snapshot()
    # 90 deg CCW about the segment's midpoint (5, 0): the horizontal bar becomes
    # vertical, pivoting in place.
    assert editor.commit_rotate_from_snapshot(before, (5.0, 0.0), math.radians(90.0))
    rotated = editor.vectors[0].points
    assert math.dist(rotated[0], (5.0, -5.0)) < 1e-9
    assert math.dist(rotated[1], (5.0, 5.0)) < 1e-9

    assert editor.undo()
    assert editor.vectors[0].points == [(0, 0), (10, 0)]

    # A zero-angle rotation is a no-op: nothing to commit, nothing to undo.
    assert not editor.commit_rotate_from_snapshot(editor.snapshot(), (5.0, 0.0), 0.0)


def test_apply_selected_layout_uses_actual_extrema_and_is_undoable():
    flower = VectorEntity(points=[(3, 2), (6, 9), (11, 4)])
    editor = EditorModel([flower])
    editor.select_all()

    # The top petal at y=9, not a synthetic rectangle corner, is the reference.
    assert editor.apply_selected_layout(16, 14, (7, 9), (50, 97))
    bounds = editor.selected_bounds()
    assert bounds == (42, 83, 58, 97)

    assert editor.undo()
    assert editor.vectors[0].points == flower.points


def test_apply_selected_layout_ignores_hidden_selected_vectors():
    visible = VectorEntity(points=[(2, 2), (12, 8)], layer="Visible")
    hidden = VectorEntity(points=[(100, 100), (120, 120)], layer="Hidden")
    editor = EditorModel([visible, hidden])
    editor.select_all_visible()
    editor.set_layer_visibility("Hidden", False)

    assert editor.apply_selected_layout(20, 12, (7, 5), (50, 94))
    assert editor.vectors[0].bounds() == (40, 88, 60, 100)
    assert editor.vectors[1].points == hidden.points


def test_smooth_vectors_smooths_selection_and_is_undoable():
    selected = VectorEntity(points=[(0, 0), (10, 10), (20, 0)])
    untouched = VectorEntity(points=[(100, 0), (110, 10), (120, 0)])
    editor = EditorModel([selected, untouched])
    editor.selected_ids = {selected.id}

    assert editor.smooth_vectors()

    assert editor.vectors[0].points == [(0, 0), (2.5, 2.5), (7.5, 7.5), (12.5, 7.5), (17.5, 2.5), (20, 0)]
    assert editor.vectors[1].points == untouched.points

    assert editor.undo()
    assert editor.vectors[0].points == selected.points


def test_smooth_vectors_smooths_all_when_nothing_selected():
    a = VectorEntity(points=[(0, 0), (10, 10), (20, 0)])
    b = VectorEntity(points=[(100, 0), (110, 10), (120, 0)])
    editor = EditorModel([a, b])

    assert editor.smooth_vectors()

    assert len(editor.vectors[0].points) == 6
    assert len(editor.vectors[1].points) == 6


def test_active_layer_selection_and_all_visible_selection():
    first = VectorEntity(points=[(0, 0), (10, 0)], layer="First")
    second = VectorEntity(points=[(0, 10), (10, 10)], layer="Second")
    editor = EditorModel([first, second])

    assert editor.select_at((5, 10), 0.5) is None
    editor.select_all()
    assert editor.selected_ids == {first.id}

    assert editor.set_active_layer("Second")
    assert editor.select_at((5, 10), 0.5) == second.id
    editor.select_all_visible()
    assert editor.selected_ids == {first.id, second.id}


def test_layer_lifecycle_visibility_and_undo_redo():
    vector = VectorEntity(points=[(0, 0), (10, 0)], layer="Imported")
    editor = EditorModel([vector])

    added = editor.add_layer()
    assert added == "Layer 1"
    assert editor.active_layer == "Layer 1"
    assert editor.rename_layer(added, "Edits") == "Edits"

    assert editor.set_layer_visibility("Imported", False)
    assert editor.visible_vectors() == []
    assert editor.delete_layer("Imported")
    assert all(item.layer != "Imported" for item in editor.vectors)

    assert editor.undo()
    assert any(item.layer == "Imported" for item in editor.vectors)
    assert editor.is_layer_visible("Imported") is False
    assert editor.undo()
    assert editor.is_layer_visible("Imported") is True
    assert editor.redo()
    assert editor.is_layer_visible("Imported") is False


def test_deleting_last_layer_creates_empty_default_layer():
    vector = VectorEntity(points=[(0, 0), (10, 0)], layer="Only")
    editor = EditorModel([vector])

    assert editor.delete_layer("Only")

    assert editor.layer_names() == ["Layer 1"]
    assert editor.active_layer == "Layer 1"
    assert editor.vectors == []


def test_clone_layer_assigns_new_vector_and_group_ids():
    first = VectorEntity(points=[(0, 0), (10, 0)], layer="Original", group_id=7)
    second = VectorEntity(points=[(0, 10), (10, 10)], layer="Original", group_id=7)
    editor = EditorModel([first, second])

    clone_name = editor.clone_layer()
    cloned = [vector for vector in editor.vectors if vector.layer == clone_name]

    assert clone_name == "Original copy"
    assert {vector.id for vector in cloned}.isdisjoint({first.id, second.id})
    assert len({vector.group_id for vector in cloned}) == 1
    assert cloned[0].group_id != first.group_id
    assert [vector.points for vector in cloned] == [first.points, second.points]


def test_copy_and_cursor_centered_paste_into_active_layer():
    first = VectorEntity(points=[(0, 0), (10, 0)], layer="Source", group_id=2)
    second = VectorEntity(points=[(0, 10), (10, 10)], layer="Source", group_id=2)
    editor = EditorModel([first, second])
    editor.select_all()
    copied = editor.copy_selected()
    target = editor.add_layer("Target")

    pasted_ids = editor.paste_vectors(copied, (100, 50))
    pasted = [vector for vector in editor.vectors if vector.id in pasted_ids]

    assert target == "Target"
    assert all(vector.layer == "Target" for vector in pasted)
    assert {vector.id for vector in pasted}.isdisjoint({first.id, second.id})
    assert len({vector.group_id for vector in pasted}) == 1
    assert pasted[0].group_id != first.group_id
    assert editor.selected_ids == set(pasted_ids)
    xs = [point[0] for vector in pasted for point in vector.points]
    ys = [point[1] for vector in pasted for point in vector.points]
    assert ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2) == (100, 50)


def test_paste_reveals_hidden_active_layer_and_is_undoable():
    source = VectorEntity(points=[(0, 0), (10, 0)], layer="Source")
    editor = EditorModel([source])
    editor.select_all()
    copied = editor.copy_selected()
    editor.set_layer_visibility("Source", False)

    pasted_ids = editor.paste_vectors(copied, (20, 20))

    assert pasted_ids
    assert editor.is_layer_visible("Source") is True
    assert editor.undo()
    assert editor.is_layer_visible("Source") is False
    assert [vector.id for vector in editor.vectors] == [source.id]


def test_smooth_without_selection_only_changes_active_visible_layer():
    first = VectorEntity(points=[(0, 0), (10, 10), (20, 0)], layer="First")
    second = VectorEntity(points=[(100, 0), (110, 10), (120, 0)], layer="Second")
    editor = EditorModel([first, second])

    assert editor.smooth_vectors()

    assert len(editor.vectors[0].points) == 6
    assert editor.vectors[1].points == second.points


def test_all_spline_file_reports_geometry_and_counts_per_layer():
    # An Inkscape-style export is all SPLINE entities and zero vectors. Splines are
    # first-class geometry, so the editor must still report them for the layer
    # counts and for Process/Repair/Approve gating (regression: an all-spline file
    # showed "0 vectors" on every layer and left processing disabled).
    control = [(0, 0), (5, 10), (10, -5), (15, 0)]
    first = SplineEntity(control_points=control, degree=3, layer="Curves")
    second = SplineEntity(control_points=control, degree=3, layer="Curves")
    editor = EditorModel(splines=[first, second])

    assert editor.vectors == []
    assert editor.has_visible_geometry()
    assert editor.geometry_count_by_layer()["Curves"] == 2

    # The Process feed flattens disposable copies while the stored splines stay NURBS.
    feed = editor.all_visible_vectors()
    assert len(feed) == 2
    assert all(len(v.points) >= 2 for v in feed)
    assert len(editor.splines) == 2
    assert editor.splines[0].control_points == control

    # A hidden layer must hide its splines from the gate as well.
    editor.set_layer_visibility("Curves", False)
    assert not editor.has_visible_geometry()


def test_open_spline_count_matches_process_and_repairs_natively():
    # Regression: the "Open profiles" label counted only vectors, so an all-spline
    # file reported 0 while Process (which flattens splines) warned about every
    # open path. The count must see the same geometry Process does, and Repair
    # must close open splines by snapping their end control points -- natively,
    # without converting the NURBS to polylines.
    first = SplineEntity(control_points=[(0, 0), (3, 8), (12, 9), (20, 0.2)], degree=3, layer="Curves")
    second = SplineEntity(
        control_points=[(20.3, 0.1), (12, -9), (3, -8), (0.2, 0.25)], degree=3, layer="Curves"
    )
    editor = EditorModel(splines=[first, second])

    # The label counts open profiles on the flattened feed, so splines are seen.
    assert count_open_profiles(editor.all_visible_vectors()) == 2

    repaired_vectors, repaired_splines = repair_geometry([], editor.visible_splines(), 0.5)
    assert editor.replace_geometry_subset(repaired_vectors, repaired_splines)

    # The gap is closed, so the profiles now assemble and Process stops warning.
    assert count_open_profiles(editor.all_visible_vectors()) == 0

    # Repaired curves are still native NURBS: same type, degree and interior
    # control points; only the end control points moved.
    spline = editor.splines[0]
    assert isinstance(spline, SplineEntity)
    assert spline.degree == 3
    assert spline.control_points[1:3] == [(3, 8), (12, 9)]
    assert spline.control_points[-1] != (20, 0.2)

    assert editor.undo()
    assert editor.splines[0].control_points[-1] == (20, 0.2)


def test_all_spline_selection_reports_bounds_and_frames():
    # Regression: on an all-spline file, selecting curves turned them red but the
    # selection had no reportable bounds, so the layout panel stayed disabled after
    # a wheel-zoom, zoom-to-content ignored the geometry, and free lasso found
    # nothing. Bounds and framing must include native splines.
    control = [(0, 0), (5, 10), (10, -5), (15, 0)]
    editor = EditorModel(
        splines=[SplineEntity(control_points=control, degree=3, layer="Curves")]
    )

    # Framing bounds include splines, measured by the flattened CURVE (not the
    # control net, which bulges outside the curve -- see SplineEntity.bounds).
    curve = (0.0, -1.0416666, 15.0, 3.515625)
    assert editor.visible_content_bounds() == pytest.approx(curve)

    # Box lasso over the extent selects the spline and yields real selected bounds
    # (this is what gates the layout panel through selected_bounds()).
    editor.select_box(-1, -6, 16, 11)
    assert editor.selected_spline_ids
    assert editor.selected_bounds() == pytest.approx(curve)

    # Free lasso: a polygon enclosing the curve must select the spline, not nothing.
    editor.clear_selection()
    polygon = [(-1, -6), (16, -6), (16, 11), (-1, 11)]
    editor.select_lasso(polygon)
    assert editor.selected_spline_ids
    assert editor.selected_bounds() is not None

    # A lasso well clear of the curve selects nothing.
    editor.clear_selection()
    editor.select_lasso([(100, 100), (110, 100), (110, 110), (100, 110)])
    assert not editor.selected_spline_ids
    assert editor.selected_bounds() is None


def test_remove_degenerate_deletes_junk_but_keeps_chain_bridges():
    # Sub-tolerance fragments are junk ONLY when they dead-end, sit on a >=3-way
    # junction, or form a tiny closed ring. A tiny segment joined end-to-end to
    # exactly one neighbour is legitimate curve sampling (pattern soup is
    # thousands of sub-tolerance LINEs) -- deleting it punches a hole in the
    # chain, which is exactly the regression this rule prevents.
    editor = EditorModel()
    bridge = VectorEntity(points=[(10, 0), (10.05, 0)])  # tiny, valence-2 both ends
    chain_a = VectorEntity(points=[(0, 0), (10, 0)])
    chain_b = VectorEntity(points=[(10.05, 0), (20, 0)])
    stub = VectorEntity(points=[(10, 0), (10.02, 0.02)])  # tiny, dead end + junction
    ring = VectorEntity(points=[(50, 50), (50.05, 50), (50.05, 50.05)], closed=True)
    isolated = VectorEntity(points=[(80, 80), (80.03, 80.03)])  # tiny, both ends free
    keeper = VectorEntity(points=[(0, 30), (40, 30)])
    editor.load([bridge, chain_a, chain_b, stub, ring, isolated, keeper])

    removed = editor.remove_degenerate(0.25)

    assert removed == 3  # stub, ring, isolated
    kept_ids = {v.id for v in editor.vectors}
    assert {bridge.id, chain_a.id, chain_b.id, keeper.id} <= kept_ids
    assert stub.id not in kept_ids and ring.id not in kept_ids and isolated.id not in kept_ids

    editor.undo()
    assert len(editor.vectors) == 7


def test_box_and_lasso_return_include_selected_spline_ids():
    # An all-spline selection put ids into selected_spline_ids but the return only
    # listed vectors -- any caller trusting it saw nothing. The return must include
    # the splines it selected, like select_at does.
    editor = EditorModel()
    editor.load([], [SplineEntity(control_points=[(0, 0), (5, 5), (10, 0)])])
    spline_id = editor.splines[0].id

    assert spline_id in editor.select_box(-1, -1, 100, 100)

    editor.selected_ids.clear()
    editor.selected_spline_ids.clear()
    lasso = [(-1, -1), (100, -1), (100, 100), (-1, 100)]
    assert spline_id in editor.select_lasso(lasso)

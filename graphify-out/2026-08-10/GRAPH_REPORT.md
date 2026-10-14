# Graph Report - DXF-CNC-Optimizer  (2026-08-10)

## Corpus Check
- 56 files · ~77,660 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1245 nodes · 3934 edges · 62 communities (52 shown, 10 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 285 edges (avg confidence: 0.56)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Main Window UI Handlers
- Canvas View & Dimensions
- Geometry & Toolpath Engine
- Smart Dimensions
- App Entry & SW Dialog
- Editor Model Selection
- SolidWorks COM Bridge
- Spline Fit & Cloning
- Raster Autotrace (Potrace)
- SolidWorks Spike Script
- test_tabs.py
- Editor Geometry Helpers
- Worker
- BoardView
- Edit Undo & Transforms
- SolidWorks Export Rules Docs
- PNG Rasterizer
- ProcessOptions
- Spike Preview Image
- COM Early Binding Docs
- Test Settings Fixture
- Sketch Picture Crash Fix
- .visible_layer_names
- SVG Path Export
- FeatureCut4 Reference
- Package Root
- models.py
- ._set_progress
- combined_bounds
- Layer
- ._active_dims
- render_to_png
- CLAUDE.md
- ._update_warning_arrow
- test_text_and_per_layer_send.py
- combined_bounds
- .redraw
- test_text_and_per_layer_send.py
- ._build_ui
- project.py
- .is_position
- count_profile_issues
- build_toolpaths
- vcarve_layer
- _rotate_transform
- _scaled_bounds
- count_profile_issues
- ._add_tool
- .geometry_count_by_layer
- Feature
- test_layer_depth.py
- .to_svg_path
- SolidWorks Add-in Buttons Greyed Out on Startup
- ProcessResult
- .clone
- join_spline_fragments
- test_worker_gc_guard.py
- ._populate_tool_table

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 293 edges
2. `VectorEntity` - 225 edges
3. `EditorModel` - 126 edges
4. `SplineEntity` - 113 edges
5. `BoardView` - 90 edges
6. `_app()` - 59 edges
7. `Tool` - 50 edges
8. `Dimension` - 48 edges
9. `Layer` - 48 edges
10. `ProcessOptions` - 48 edges

## Surprising Connections (you probably didn't know these)
- `Potrace v2 Raster Import Plan (PNG/JPEG to Vectors)` --conceptually_related_to--> `Potrace --tight Output Placement Mode`  [INFERRED]
  README.md → tools/potrace-1.16.win64/placement.pdf
- `test_effective_diameter_by_kind()` --calls--> `Tool`  [EXTRACTED]
  tests/test_tools.py → curvemill/models.py
- `_Feat` --uses--> `VectorEntity`  [INFERRED]
  tests/test_solidworks_bridge.py → curvemill/models.py
- `_TreeModel` --uses--> `VectorEntity`  [INFERRED]
  tests/test_solidworks_bridge.py → curvemill/models.py
- `_Feat` --uses--> `SplineEntity`  [INFERRED]
  tests/test_solidworks_bridge.py → curvemill/models.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Optimize for SolidWorks End-to-End Pipeline** — readme_optimize_for_solidworks_feature, docs_solidworks_dxf_import_fit_point_rule, readme_fit_point_spline_export, docs_solidworks_dxf_import_path545 [INFERRED 0.85]
- **SolidWorks DXF Element Counting Rules** — docs_solidworks_dxf_import_fit_point_rule, docs_solidworks_dxf_import_control_point_split, docs_solidworks_dxf_import_exact_g1_threshold [EXTRACTED 1.00]
- **SolidWorks COM Early Binding and Performance Pattern** — docs_solidworks_com_api_early_binding, docs_solidworks_com_api_cast_function, docs_solidworks_com_api_six_flag_recipe [INFERRED 0.85]

## Communities (62 total, 10 thin omitted)

### Community 0 - "Main Window UI Handlers"
Cohesion: 0.13
Nodes (22): Feature picker for Send to SolidWorks -- mirrors SW's own extrude UI., Type text, pick a font + height -> closed curves on the active layer., Pick a fillet radius and which corners to round., RoundCornersDialog, SendToSolidWorksDialog, TextToCurvesDialog, WarningOverlayState, Worker (+14 more)

### Community 1 - "Canvas View & Dimensions"
Cohesion: 0.09
Nodes (65): _constrain_move_delta(), MainWindow, Dimension, ProcessWarning, QMainWindow, _app(), _square(), test_align_keeps_the_moved_selection_on_screen() (+57 more)

### Community 2 - "Geometry & Toolpath Engine"
Cohesion: 0.11
Nodes (4): Clear the session back to an empty board, prompting first if unsaved., Fit the pattern into native splines and replace it in place -- no save., Ask for a fresh SolidWorks entity count. Coalesces bursts: if a fit is, QListWidgetItem

### Community 3 - "Smart Dimensions"
Cohesion: 0.11
Nodes (6): _effective_units(), Exception, Record what each layer was cut with, so the Log says how a result was         p, Import the COM bridge lazily so the editor runs without SolidWorks., Cutting layers that carry geometry, in feature-order (editor order)., (feature kind, end condition, depth in meters, flip).

### Community 4 - "App Entry & SW Dialog"
Cohesion: 0.12
Nodes (6): BoardView, _format_layout_value(), _lasso_screen_span(), _view_tolerance(), _view_units_for_pixels(), QGraphicsView

### Community 5 - "Editor Model Selection"
Cohesion: 0.09
Nodes (38): EditorModel, Count entities (vectors + native splines) on each layer for the layer list., Layer that owns these ids (a dimensioned pattern lives on one layer)., count_open_profiles(), Snap nearby endpoints of open vectors AND open native splines.      Splines are, repair_geometry(), Produce an SVG path d-string from the polyline points., VectorEntity (+30 more)

### Community 6 - "SolidWorks COM Bridge"
Cohesion: 0.12
Nodes (4): _anchor_point(), Swap the canvas for the tool-corrected (as-milled) outlines from the         la, Swap the active layer's fragments for one native spline per shape.          In, QTreeWidgetItem

### Community 8 - "Raster Autotrace (Potrace)"
Cohesion: 0.09
Nodes (45): Cubic, _dist_sq(), _find_potrace(), _line_to_cubic(), _parse_svg_paths(), _png_to_pbm(), Point, ProgressCallback (+37 more)

### Community 9 - "SolidWorks Spike Script"
Cohesion: 0.08
Nodes (39): Advance the dim-id counter past every id in ``dims`` (see the twin in     models, sync_dim_id_counter(), entries(), library_dir(), load_pattern(), Path, The pattern library: clipart, not projects.  An entry is a piece of artwork — ge, _render() (+31 more)

### Community 10 - "test_tabs.py"
Cohesion: 0.09
Nodes (43): _arc_points(), _circle_points(), _curve_steps(), _doc_units(), _entity_to_vectors(), export_process_result(), export_vectors(), import_dxf() (+35 more)

### Community 11 - "Editor Geometry Helpers"
Cohesion: 0.09
Nodes (14): Geometry on the active layer only -- Optimize writes back to just this         l, Write repaired vectors and natively repaired splines back as one undo step., _spline_geometry_equal(), Point, A native NURBS/parametric spline curve preserved from DXF import., Approximate this spline as a polyline of straight segments.          Cached: re-, Evaluate bezier curve using De Casteljau's algorithm (for cubic bezier subsets)., Simple De Casteljau evaluation for bezier-style splines. (+6 more)

### Community 12 - "Worker"
Cohesion: 0.11
Nodes (23): _arc_interior(), _chaikin_points(), _distance(), _distance_to_polyline(), _distance_to_segment(), _normalize_angle(), _point_in_polygon(), Point (+15 more)

### Community 13 - "BoardView"
Cohesion: 0.11
Nodes (13): ComRegisterFunction, ComUnregisterFunction, CurveMill, DateTime, HashSet, ICommandManager, int, ISldWorks (+5 more)

### Community 14 - "Edit Undo & Transforms"
Cohesion: 0.11
Nodes (3): Dims to draw/list: every stored dim whose pattern lives on the layer         cu, Make a stored dim's pattern the current selection, so an edit/flip can, Force ``axis`` to ``scale`` for the aspect lock, re-solving its         transla

### Community 15 - "SolidWorks Export Rules Docs"
Cohesion: 0.17
Nodes (13): Fit-Point Count Rule Verified on Sketch API Path, Control-Point SPLINE Splits at G1 Tangent Breaks, Exact G1 Tangent Threshold Is Not a Tolerance, Fit-Point SPLINE = 1 Sketch Element Rule, path545.dxf Optimization Result (3383 to 540 Elements), Probe-Based Black-Box Reverse Engineering Methodology, DXF CNC Optimizer Application, Fit-Point SPLINE Export for SolidWorks Element Count Parity (+5 more)

### Community 16 - "PNG Rasterizer"
Cohesion: 0.10
Nodes (7): Path, A stable string of everything a save would write. Two sessions with the same, Ask before throwing away unsaved changes. Returns True if it is OK to proceed, Always prompt for a location -- keeps the original when saving a copy., Write the full session to path in the .curvemill format (save + autosave)., If the last run left a crash log, warn and offer to open it., If an autosave survived (previous session crashed), offer to reopen it.

### Community 17 - "ProcessOptions"
Cohesion: 0.21
Nodes (23): _as_polygons(), build_toolpaths(), process_vectors(), ProgressCallback, repair_vectors(), split_islands(), ProcessOptions, _circle() (+15 more)

### Community 18 - "Spike Preview Image"
Cohesion: 0.60
Nodes (5): sw_spike_preview.png (SolidWorks test picture), InsertSketchPicture (SolidWorks API method), SolidWorks Live Preview Groundwork, SolidWorks API Spike, Test Visual Content (F letter, red square, blue circle)

### Community 19 - "COM Early Binding Docs"
Cohesion: 0.67
Nodes (3): cast() COM Typed Wrapper Function, SolidWorks COM Early Binding Requirement, Six-Flag Bulk Sketch Insertion Recipe (50x Speedup)

### Community 22 - ".visible_layer_names"
Cohesion: 0.27
Nodes (15): _depth_shade(), Cut-floor colour: the surface tone darkened in proportion to depth., process_layers(), Machine each layer in its own mode/depth, then composite one board.      Profile, _app(), Depth belongs to the layer: one part, several depths, one preview., test_a_depth_past_the_solidworks_board_thickness_is_flagged(), test_a_laser_layer_still_shows_its_depth_in_the_panel() (+7 more)

### Community 23 - "SVG Path Export"
Cohesion: 0.10
Nodes (37): _add_path_warning(), assemble_closed_profiles(), _bezier_end_dir(), _bezier_start_dir(), _buffer_toolpaths(), _build_chains(), _canonical_path(), _chain_is_closed() (+29 more)

### Community 25 - "Package Root"
Cohesion: 0.44
Nodes (10): QImage, _arrow(), _curve(), main(), _mill(), _new(), _open_cell(), QPainter (+2 more)

### Community 26 - "models.py"
Cohesion: 0.12
Nodes (15): _arrow_path(), _distance_to_segment_qt(), _free_lasso_path(), _path_midpoint(), _point_distance(), _preserve_resize_aspect(), Show a cross over the rotate ring (just outside a corner handle) so the, True when the cursor is in the rotation ring: outside the selection box and (+7 more)

### Community 27 - "._set_progress"
Cohesion: 0.12
Nodes (7): Return flattened vectors (includes spline approximations for display/processing), Combined bounds of all visible geometry without flattening splines.          Use, True when any visible layer holds a vector or a native spline.          Splines, Combined bounds of the vectors/splines with these ids, ignoring selection., Delete visible junk entities whose whole extent fits inside the tolerance., Resize the visible selection to ``width`` x ``height`` and move its         ``pa, combined_bounds()

### Community 28 - "combined_bounds"
Cohesion: 0.18
Nodes (4): _closest_rect_edge_point(), Read-only Simulation-tab view sharing the editor's scene.      The processed b, SimView, QRectF

### Community 29 - "Layer"
Cohesion: 0.32
Nodes (3): A SolidWorks-style board-relative dimension on the Y-up DXF canvas.      Draws, Hit-test for right-click/select: label, flip glyph, or the dim line., SmartDimItem

### Community 30 - "._active_dims"
Cohesion: 0.11
Nodes (20): Cutting width at the given depth below the surface., A V-carve varies Z to change the cut width; flat mills and lasers can't., Depth at which this tool cuts the given width -- inverse of         effective_di, Tool, test_tool_json_round_trip(), _app(), V-Carve: width<->depth inversion, iso-depth bands, hazards, and UI gating., _square() (+12 more)

### Community 31 - "render_to_png"
Cohesion: 0.38
Nodes (9): _app(), Four-tab restructure: tab shell, Process tab switch, settings round-trip., test_four_tabs_editor_default_and_shared_sim_scene(), test_process_completion_switches_to_simulation_tab(), test_process_log_records_the_cut_recipe(), test_send_dialog_honors_default_feature_and_depth(), test_settings_round_trip_and_startup_defaults(), test_sim_view_canvas_controls_and_fit() (+1 more)

### Community 33 - "._update_warning_arrow"
Cohesion: 0.24
Nodes (6): _vector_path(), WarningBalloonItem, QGraphicsItem, _app(), Handle-resize of native splines must update the canvas items, not just the model, test_normalize_live_visuals_updates_spline_paths()

### Community 34 - "test_text_and_per_layer_send.py"
Cohesion: 0.25
Nodes (13): _add_geometry(), _cosmetic_pen(), _fit_content_icon(), _preview_vector_path(), QPainter, _selected_vector_pen(), _vector_pen(), _view_vectors_icon() (+5 more)

### Community 35 - "combined_bounds"
Cohesion: 0.09
Nodes (6): _next_group_id(), Append imported vectors and splines as a new layer., Move (cut) or duplicate (copy) the current selection onto a fresh layer., Assign a shared group id to the visible selection (vectors and         splines)., Append imported DXF files as new, independently named layers., Layer

### Community 36 - ".redraw"
Cohesion: 0.42
Nodes (9): _app(), _click(), A plain click on the default (Box Lasso) tool selects exactly one entity., test_click_selects_single_vector(), test_click_selects_spline(), test_drag_inside_selection_moves_outside_starts_box(), test_escape_clears_selection(), test_free_lasso_moves_inside_selection_lassos_outside() (+1 more)

### Community 37 - "test_text_and_per_layer_send.py"
Cohesion: 0.21
Nodes (13): PerLayerSendDialog, Glyph outlines -> closed vectors, scaled so the text is `height_mm` tall., One sketch + feature per cutting layer, prefilled from layer depths.      Feat, (layer name, feature kind, end condition, depth in meters) per non-skipped row., _text_to_vectors(), QFont, _app(), Text-to-curves insertion and per-layer Send to SolidWorks. (+5 more)

### Community 38 - "._build_ui"
Cohesion: 0.07
Nodes (48): Curve, BridgeError, cast(), _connect(), curves_from_entities(), _delete_preview_sketch(), _fix_all_sketch_entities(), get_selection() (+40 more)

### Community 39 - "project.py"
Cohesion: 0.14
Nodes (35): Axis, Bounds, board_features(), edge_segment(), Feature, feature_coord(), feature_point(), is_edge() (+27 more)

### Community 40 - ".is_position"
Cohesion: 0.14
Nodes (8): EditorSnapshot, Centre of the visible selection's bounding box (groups expanded),         comput, Rotate the visible selection by ``angle`` radians about its centre.         Menu, Mirror the visible selection about its centre. ``horizontal`` swaps         left, Selected, currently-visible vector and spline ids (groups expanded)., Clear the group id from every selected vector and spline. Returns         ``True, Rotate the selection by ``angle`` radians about ``center``. Mirrors         comm, _snapshots_equal()

### Community 41 - "count_profile_issues"
Cohesion: 0.42
Nodes (8): _app(), Tool math, the Simulation tab's per-kind fields, and the Library tool table., _select_kind(), test_add_new_tool_button_and_notes_column(), test_effective_diameter_by_kind(), test_effective_diameter_feeds_the_simulation(), test_kind_picker_shows_only_relevant_fields(), test_tool_library_starts_empty_saves_and_loads_back()

### Community 43 - "vcarve_layer"
Cohesion: 0.31
Nodes (9): _finished_edges(), _nest_profiles(), Preview a V-carve: the bit dips deeper where the shape is wide, so carved     de, Turn overlapping closed profiles into shell+holes regions (even-odd rule)., The cut-side wall of every shape after tool compensation -- the edge the     mac, _VCarve, vcarve_layer(), _without_duplicate_close() (+1 more)

### Community 45 - "_scaled_bounds"
Cohesion: 0.52
Nodes (5): _resume_gc_for_worker(), _suspend_gc_for_worker(), The worker-thread GC guard: automatic cyclic GC must stay suspended for as long, test_gc_suspended_while_workers_run_and_restored_after(), test_resume_does_not_collect_on_worker_thread()

### Community 47 - "count_profile_issues"
Cohesion: 0.12
Nodes (29): fit_vector_chains(), Rebuild loose LINE segments into one native spline per smooth run.      Pattern, Convert control-point splines to fit-point splines for SolidWorks export.      S, A two-point run is a straight line; express it as an exact cubic., _straight_cubic(), to_fit_splines(), Tests for rebuilding loose LINE soup into native splines., A smooth closed curve must not shatter into the straight-segment fallback. (+21 more)

### Community 49 - ".geometry_count_by_layer"
Cohesion: 0.22
Nodes (6): _demo_rotate_transform(), Re-sync the selection box/handles to an in-progress drag.          A wheel-zoo, Rotate by ``angle`` radians about ``center``. Built directly from the matrix, _rotate_transform(), _scale_transform(), QTransform

### Community 51 - "test_layer_depth.py"
Cohesion: 0.16
Nodes (11): Delete visible entities that trace the same path as an earlier one.          Mat, count_profile_issues(), count_self_intersections(), duplicate_vector_indices(), Count open profiles, duplicate entities and over-used vertices.      A duplicate, Indices of entities tracing the same path as an earlier one.      Shared by the, test_heal_deletes_zero_area_self_crossing_specks(), test_heal_splits_at_crossing_preserving_every_vertex() (+3 more)

### Community 57 - "SolidWorks Add-in Buttons Greyed Out on Startup"
Cohesion: 0.15
Nodes (12): Confirmed *irrelevant* — do not waste time here, Methodology lessons, Related, SolidWorks Add-in Buttons Greyed Out on Startup, The diagnostic method (this is what cracked it), The problem that started it, The rules (measured), The short version (+4 more)

### Community 59 - "ProcessResult"
Cohesion: 0.51
Nodes (9): result_export_vectors(), ProcessResult, _dense_circle_wkt(), Regression: tool-corrected geometry must be simplified before it reaches the edi, _result(), test_corrected_geometry_is_simplified_not_dense(), test_fitting_corrected_geometry_does_not_explode(), test_optimize_reported_count_matches_solidworks_entity_count() (+1 more)

### Community 60 - ".clone"
Cohesion: 0.20
Nodes (11): _basis_functions(), _default_knots(), _find_span(), ImportResult, Evaluate a NURBS curve at parameter t using Cox-deBoor formula., Generate clamped knot vector for a bezier-like NURBS curve., Find the knot span index for parameter u (Cox-deBoor)., Compute non-vanishing basis functions at parameter u. (+3 more)

### Community 61 - "join_spline_fragments"
Cohesion: 0.20
Nodes (15): _bezier_chains(), _Chain, join_spline_fragments(), Merge single-bezier SPLINE fragments into one native spline per shape.      Inks, A list of bezier control-point tuples that remembers its source layer., Walk single-bezier fragments into end-to-end chains, in geometric order.      En, list, _bezier() (+7 more)

### Community 62 - "test_worker_gc_guard.py"
Cohesion: 0.11
Nodes (22): _demo_scaled_bounds(), _diag_dir(), _enable_crash_log(), _feature_text(), _hand_off_to_running_instance(), _install_ipc_server(), _launch_message(), main() (+14 more)

### Community 65 - "._populate_tool_table"
Cohesion: 0.10
Nodes (5): Export whatever is on the canvas -- optimized splines, corrected         geomet, Show only the tools that fit the current cut mode.          V-Carve drops flat, Field visibility, labels and settings for the current tool — no writes., Rebuild the read-only layer panel; reload the form only on a new pick., One job per cutting layer, each with its own tool/mode/depth.

## Knowledge Gaps
- **25 isolated node(s):** `curvemill`, `CurveMill`, `graphify`, `The short version`, `The problem that started it` (+20 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `Canvas View & Dimensions` to `Main Window UI Handlers`, `Geometry & Toolpath Engine`, `Smart Dimensions`, `App Entry & SW Dialog`, `Editor Model Selection`, `SolidWorks COM Bridge`, `Spline Fit & Cloning`, `SolidWorks Spike Script`, `Editor Geometry Helpers`, `Edit Undo & Transforms`, `PNG Rasterizer`, `ProcessOptions`, `.visible_layer_names`, `combined_bounds`, `._active_dims`, `render_to_png`, `._update_warning_arrow`, `combined_bounds`, `.redraw`, `test_text_and_per_layer_send.py`, `project.py`, `.is_position`, `count_profile_issues`, `build_toolpaths`, `_rotate_transform`, `._refresh_dim_list`, `test_layer_depth.py`, `ProcessResult`, `.clone`, `test_worker_gc_guard.py`, `._populate_tool_table`?**
  _High betweenness centrality (0.311) - this node is a cross-community bridge._
- **Why does `VectorEntity` connect `Editor Model Selection` to `Main Window UI Handlers`, `Canvas View & Dimensions`, `Geometry & Toolpath Engine`, `App Entry & SW Dialog`, `SolidWorks Spike Script`, `test_tabs.py`, `Editor Geometry Helpers`, `Worker`, `ProcessOptions`, `.visible_layer_names`, `SVG Path Export`, `models.py`, `._set_progress`, `combined_bounds`, `Layer`, `._active_dims`, `render_to_png`, `._update_warning_arrow`, `test_text_and_per_layer_send.py`, `combined_bounds`, `.redraw`, `test_text_and_per_layer_send.py`, `._build_ui`, `.is_position`, `vcarve_layer`, `count_profile_issues`, `test_layer_depth.py`, `ProcessResult`, `.clone`, `join_spline_fragments`, `test_worker_gc_guard.py`?**
  _High betweenness centrality (0.182) - this node is a cross-community bridge._
- **Why does `SplineEntity` connect `Editor Geometry Helpers` to `Main Window UI Handlers`, `Canvas View & Dimensions`, `App Entry & SW Dialog`, `Editor Model Selection`, `Raster Autotrace (Potrace)`, `SolidWorks Spike Script`, `test_tabs.py`, `Worker`, `SVG Path Export`, `._set_progress`, `combined_bounds`, `Layer`, `._update_warning_arrow`, `combined_bounds`, `.redraw`, `test_text_and_per_layer_send.py`, `._build_ui`, `.is_position`, `vcarve_layer`, `count_profile_issues`, `test_layer_depth.py`, `.clone`, `join_spline_fragments`, `test_worker_gc_guard.py`?**
  _High betweenness centrality (0.169) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `MainWindow` (e.g. with `Dimension` and `Feature`) actually correct?**
  _`MainWindow` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `VectorEntity` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`VectorEntity` has 21 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `EditorModel` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`EditorModel` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `SplineEntity` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`SplineEntity` has 21 INFERRED edges - model-reasoned connections that need verification._
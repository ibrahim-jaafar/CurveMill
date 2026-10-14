# Graph Report - DXF-CNC-Optimizer  (2026-08-08)

## Corpus Check
- 55 files · ~75,650 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1220 nodes · 3844 edges · 56 communities (44 shown, 12 thin omitted)
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
- Tab UI Tests
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
- .geometry_count_by_layer
- .redraw
- test_text_and_per_layer_send.py
- ._build_ui
- .is_position
- count_profile_issues
- build_toolpaths
- test_project.py
- ._refresh_dim_list
- count_profile_issues
- ._add_tool
- .geometry_count_by_layer
- .append_layers
- test_vcarve.py
- .to_svg_path
- SolidWorks Add-in Buttons Greyed Out on Startup
- test_project.py
- test_worker_gc_guard.py

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 284 edges
2. `VectorEntity` - 221 edges
3. `EditorModel` - 119 edges
4. `SplineEntity` - 108 edges
5. `BoardView` - 90 edges
6. `_app()` - 57 edges
7. `Tool` - 48 edges
8. `Layer` - 48 edges
9. `Dimension` - 47 edges
10. `ProcessOptions` - 46 edges

## Surprising Connections (you probably didn't know these)
- `Potrace v2 Raster Import Plan (PNG/JPEG to Vectors)` --conceptually_related_to--> `Potrace --tight Output Placement Mode`  [INFERRED]
  README.md → tools/potrace-1.16.win64/placement.pdf
- `test_resize_preserves_aspect_by_default_and_shift_enables_free_resize()` --calls--> `_preserve_resize_aspect()`  [EXTRACTED]
  tests/test_app.py → curvemill/app.py
- `test_effective_diameter_by_kind()` --calls--> `Tool`  [EXTRACTED]
  tests/test_tools.py → curvemill/models.py
- `_Feat` --uses--> `VectorEntity`  [INFERRED]
  tests/test_solidworks_bridge.py → curvemill/models.py
- `_TreeModel` --uses--> `VectorEntity`  [INFERRED]
  tests/test_solidworks_bridge.py → curvemill/models.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Optimize for SolidWorks End-to-End Pipeline** — readme_optimize_for_solidworks_feature, docs_solidworks_dxf_import_fit_point_rule, readme_fit_point_spline_export, docs_solidworks_dxf_import_path545 [INFERRED 0.85]
- **SolidWorks DXF Element Counting Rules** — docs_solidworks_dxf_import_fit_point_rule, docs_solidworks_dxf_import_control_point_split, docs_solidworks_dxf_import_exact_g1_threshold [EXTRACTED 1.00]
- **SolidWorks COM Early Binding and Performance Pattern** — docs_solidworks_com_api_early_binding, docs_solidworks_com_api_cast_function, docs_solidworks_com_api_six_flag_recipe [INFERRED 0.85]

## Communities (56 total, 12 thin omitted)

### Community 0 - "Main Window UI Handlers"
Cohesion: 0.11
Nodes (3): BoardView, _format_layout_value(), QGraphicsItem

### Community 1 - "Canvas View & Dimensions"
Cohesion: 0.05
Nodes (98): Axis, Bounds, _feature_text(), board_features(), Dimension, edge_segment(), Feature, feature_coord() (+90 more)

### Community 3 - "Smart Dimensions"
Cohesion: 0.12
Nodes (6): _effective_units(), Exception, Import the COM bridge lazily so the editor runs without SolidWorks., Cutting layers that carry geometry, in feature-order (editor order)., (feature kind, end condition, depth in meters, flip)., (layer name, feature kind, end condition, depth in meters) per non-skipped row.

### Community 4 - "App Entry & SW Dialog"
Cohesion: 0.12
Nodes (16): _constrain_move_delta(), _demo_rotate_transform(), _lasso_screen_span(), _point_distance(), _preserve_resize_aspect(), Re-sync the selection box/handles to an in-progress drag.          A wheel-zoo, Signed rotation (radians) from the drag's start bearing to the cursor's.     Sh, Rotate by ``angle`` radians about ``center``. Built directly from the matrix (+8 more)

### Community 5 - "Editor Model Selection"
Cohesion: 0.09
Nodes (33): EditorModel, _next_group_id(), Count entities (vectors + native splines) on each layer for the layer list., Layer that owns these ids (a dimensioned pattern lives on one layer)., count_open_profiles(), Produce an SVG path d-string from the polyline points., VectorEntity, test_active_layer_selection_and_all_visible_selection() (+25 more)

### Community 7 - "Spline Fit & Cloning"
Cohesion: 0.18
Nodes (4): _anchor_point(), _double(), QAction, QWidget

### Community 8 - "Raster Autotrace (Potrace)"
Cohesion: 0.08
Nodes (46): Cubic, _dist_sq(), _find_potrace(), _line_to_cubic(), _parse_svg_paths(), _png_to_pbm(), Point, ProgressCallback (+38 more)

### Community 9 - "SolidWorks Spike Script"
Cohesion: 0.47
Nodes (4): _vector_path(), _app(), Handle-resize of native splines must update the canvas items, not just the model, test_normalize_live_visuals_updates_spline_paths()

### Community 10 - "test_tabs.py"
Cohesion: 0.15
Nodes (30): _arc_points(), _circle_points(), _curve_steps(), _doc_units(), _entity_to_vectors(), export_process_result(), export_vectors(), import_dxf() (+22 more)

### Community 11 - "Editor Geometry Helpers"
Cohesion: 0.07
Nodes (21): Geometry on the active layer only -- Optimize writes back to just this         l, Write repaired vectors and natively repaired splines back as one undo step., _spline_geometry_equal(), _basis_functions(), _default_knots(), _find_span(), Point, A native NURBS/parametric spline curve preserved from DXF import. (+13 more)

### Community 12 - "Worker"
Cohesion: 0.13
Nodes (21): _arc_interior(), _chaikin_points(), _distance(), _distance_to_polyline(), _distance_to_segment(), _normalize_angle(), _point_in_polygon(), Point (+13 more)

### Community 13 - "BoardView"
Cohesion: 0.11
Nodes (13): ComRegisterFunction, ComUnregisterFunction, CurveMill, DateTime, HashSet, ICommandManager, int, ISldWorks (+5 more)

### Community 14 - "Edit Undo & Transforms"
Cohesion: 0.10
Nodes (8): MainWindow, A stable string of everything a save would write. Two sessions with the same, Ask before throwing away unsaved changes. Returns True if it is OK to proceed, Show only the tools that fit the current cut mode.          V-Carve drops flat, Field visibility, labels and settings for the current tool — no writes., Rebuild the read-only layer panel; reload the form only on a new pick., One job per cutting layer, each with its own tool/mode/depth., QMainWindow

### Community 15 - "SolidWorks Export Rules Docs"
Cohesion: 0.17
Nodes (13): Fit-Point Count Rule Verified on Sketch API Path, Control-Point SPLINE Splits at G1 Tangent Breaks, Exact G1 Tangent Threshold Is Not a Tolerance, Fit-Point SPLINE = 1 Sketch Element Rule, path545.dxf Optimization Result (3383 to 540 Elements), Probe-Based Black-Box Reverse Engineering Methodology, DXF CNC Optimizer Application, Fit-Point SPLINE Export for SolidWorks Element Count Parity (+5 more)

### Community 16 - "PNG Rasterizer"
Cohesion: 0.13
Nodes (6): Path, Clear the session back to an empty board, prompting first if unsaved., Always prompt for a location -- keeps the original when saving a copy., Write the full session to path in the .curvemill format (save + autosave)., If the last run left a crash log, warn and offer to open it., If an autosave survived (previous session crashed), offer to reopen it.

### Community 18 - "Spike Preview Image"
Cohesion: 0.60
Nodes (5): sw_spike_preview.png (SolidWorks test picture), InsertSketchPicture (SolidWorks API method), SolidWorks Live Preview Groundwork, SolidWorks API Spike, Test Visual Content (F letter, red square, blue circle)

### Community 19 - "COM Early Binding Docs"
Cohesion: 0.67
Nodes (3): cast() COM Typed Wrapper Function, SolidWorks COM Early Binding Requirement, Six-Flag Bulk Sketch Insertion Recipe (50x Speedup)

### Community 23 - "SVG Path Export"
Cohesion: 0.10
Nodes (40): assemble_closed_profiles(), _bezier_chains(), _bezier_end_dir(), _bezier_start_dir(), _build_chains(), _chain_is_closed(), count_self_intersections(), _densify() (+32 more)

### Community 25 - "Package Root"
Cohesion: 0.24
Nodes (16): ProgressCallback, Render DXF vectors and splines to a PNG image for auto-tracing., Render all geometry to a PNG image in memory.      Args:         vectors: Lis, render_to_png(), _report(), _report_loop(), QImage, _arrow() (+8 more)

### Community 26 - "models.py"
Cohesion: 0.22
Nodes (7): _nearest_selected_vertex(), _opposite_corner(), Show a cross over the rotate ring (just outside a corner handle) so the, True when the cursor is in the rotation ring: outside the selection box and, _rotate_zone(), _scale_corner_at(), _view_tolerance()

### Community 27 - "._set_progress"
Cohesion: 0.11
Nodes (9): Return flattened vectors (includes spline approximations for display/processing), Combined bounds of all visible geometry without flattening splines.          Use, True when any visible layer holds a vector or a native spline.          Splines, Delete visible entities that trace the same path as an earlier one.          Mat, Delete visible junk entities whose whole extent fits inside the tolerance., _canonical_path(), duplicate_vector_indices(), Indices of entities tracing the same path as an earlier one.      Shared by the (+1 more)

### Community 29 - "Layer"
Cohesion: 0.18
Nodes (8): _arrow_path(), _closest_rect_edge_point(), _distance_to_segment_qt(), _path_midpoint(), A SolidWorks-style board-relative dimension on the Y-up DXF canvas.      Draws, Hit-test for right-click/select: label, flip glyph, or the dim line., SmartDimItem, QPointF

### Community 30 - "._active_dims"
Cohesion: 0.10
Nodes (26): process_layers(), Machine each layer in its own mode/depth, then composite one board.      Profile, Preview a V-carve: the bit dips deeper where the shape is wide, so carved     de, vcarve_layer(), Layer, Cutting width at the given depth below the surface., A V-carve varies Z to change the cut width; flat mills and lasers can't., Depth at which this tool cuts the given width -- inverse of         effective_di (+18 more)

### Community 31 - "render_to_png"
Cohesion: 0.42
Nodes (8): _app(), Four-tab restructure: tab shell, Process tab switch, settings round-trip., test_four_tabs_editor_default_and_shared_sim_scene(), test_process_completion_switches_to_simulation_tab(), test_send_dialog_honors_default_feature_and_depth(), test_settings_round_trip_and_startup_defaults(), test_sim_view_canvas_controls_and_fit(), _window_with_square()

### Community 33 - "._update_warning_arrow"
Cohesion: 0.12
Nodes (4): Append imported vectors and splines as a new layer., Move (cut) or duplicate (copy) the current selection onto a fresh layer., Assign a shared group id to the visible selection (vectors and         splines)., Append imported DXF files as new, independently named layers.

### Community 34 - "test_text_and_per_layer_send.py"
Cohesion: 0.21
Nodes (15): _add_geometry(), _cosmetic_pen(), _fit_content_icon(), _free_lasso_path(), _polygons(), _preview_vector_path(), QPainter, _selected_vector_pen() (+7 more)

### Community 36 - ".redraw"
Cohesion: 0.42
Nodes (9): _app(), _click(), The Select tool picks exactly one vector per click., test_drag_inside_selection_moves_outside_starts_box(), test_escape_clears_selection(), test_free_lasso_moves_inside_selection_lassos_outside(), test_move_tool_keeps_spline_multi_selection(), test_pick_tool_selects_single_vector() (+1 more)

### Community 37 - "test_text_and_per_layer_send.py"
Cohesion: 0.32
Nodes (10): Glyph outlines -> closed vectors, scaled so the text is `height_mm` tall., _text_to_vectors(), QFont, _app(), Text-to-curves insertion and per-layer Send to SolidWorks., test_inserted_text_lands_on_the_active_layer(), test_per_layer_dialog_prefills_through_all_past_thickness_and_skips(), test_sw_send_layers_lists_only_cutting_layers_with_geometry() (+2 more)

### Community 38 - "._build_ui"
Cohesion: 0.06
Nodes (61): Curve, _depth_shade(), Cut-floor colour: the surface tone darkened in proportion to depth., BridgeError, cast(), _connect(), curves_from_entities(), _delete_preview_sketch() (+53 more)

### Community 40 - ".is_position"
Cohesion: 0.26
Nodes (3): EditorSnapshot, Rotate the selection by ``angle`` radians about ``center``. Mirrors         comm, _snapshots_equal()

### Community 41 - "count_profile_issues"
Cohesion: 0.42
Nodes (8): _app(), Tool math, the Simulation tab's per-kind fields, and the Library tool table., _select_kind(), test_add_new_tool_button_and_notes_column(), test_effective_diameter_by_kind(), test_effective_diameter_feeds_the_simulation(), test_kind_picker_shows_only_relevant_fields(), test_tool_library_starts_empty_saves_and_loads_back()

### Community 42 - "build_toolpaths"
Cohesion: 0.22
Nodes (21): _buffer_toolpaths(), process_vectors(), repair_vectors(), split_islands(), ProcessOptions, _circle(), _path_radius(), A circle inside a circle is material in between: inside shrinks the outer     ed (+13 more)

### Community 43 - "test_project.py"
Cohesion: 0.15
Nodes (16): count_profile_issues(), Count open profiles, duplicate entities and over-used vertices.      A duplicate, Duplicates must not mask open profiles or inflate multi-vertex counts., test_open_profile_not_masked_by_duplicates(), _app(), A .curvemill project reopens the session exactly as it was saved., Autosave writes on content; a fresh window reopens it; a clean exit clears it., A project must not invent open profiles or multi-vertex junctions.      Geometry (+8 more)

### Community 47 - "count_profile_issues"
Cohesion: 0.08
Nodes (50): _fit_self_crosses(), fit_vector_chains(), join_spline_fragments(), Rebuild loose LINE segments into one native spline per smooth run.      Pattern, Convert control-point splines to fit-point splines for SolidWorks export.      S, Merge single-bezier SPLINE fragments into one native spline per shape.      Inks, A two-point run is a straight line; express it as an exact cubic., True when a CLOSED chain's fitted curve crosses itself but its raw polyline (+42 more)

### Community 48 - "._add_tool"
Cohesion: 0.13
Nodes (14): _diag_dir(), _enable_crash_log(), _hand_off_to_running_instance(), _install_ipc_server(), _launch_message(), main(), Directory for crash logs — beside the settings ini so tests redirect it too., Point faulthandler at a log file; return the prior run's crash log if any. (+6 more)

### Community 49 - ".geometry_count_by_layer"
Cohesion: 0.12
Nodes (36): _demo_scaled_bounds(), PerLayerSendDialog, Read-only Simulation-tab view sharing the editor's scene.      The processed b, Bounds after _scale_transform(origin, sx, sy), normalized (min/max)., Feature picker for Send to SolidWorks -- mirrors SW's own extrude UI., Type text, pick a font + height -> closed curves on the active layer., Pick a fillet radius and which corners to round., One sketch + feature per cutting layer, prefilled from layer depths.      Feat (+28 more)

### Community 50 - ".append_layers"
Cohesion: 0.15
Nodes (5): Combined bounds of the vectors/splines with these ids, ignoring selection., Selected, currently-visible vector and spline ids (groups expanded)., Resize the visible selection to ``width`` x ``height`` and move its         ``pa, Clear the group id from every selected vector and spline. Returns         ``True, combined_bounds()

### Community 51 - "test_vcarve.py"
Cohesion: 0.26
Nodes (13): _add_path_warning(), _as_polygons(), build_toolpaths(), flatten_splines(), _nest_profiles(), ProgressCallback, Convert all native splines to polylines for Shapely-based processing., Snap nearby endpoints of open vectors AND open native splines.      Splines are (+5 more)

### Community 57 - "SolidWorks Add-in Buttons Greyed Out on Startup"
Cohesion: 0.15
Nodes (12): Confirmed *irrelevant* — do not waste time here, Methodology lessons, Related, SolidWorks Add-in Buttons Greyed Out on Startup, The diagnostic method (this is what cracked it), The problem that started it, The rules (measured), The short version (+4 more)

### Community 58 - "test_project.py"
Cohesion: 0.11
Nodes (29): Advance the dim-id counter past every id in ``dims`` (see the twin in     models, sync_dim_id_counter(), entries(), library_dir(), load_pattern(), Path, The pattern library: clipart, not projects.  An entry is a piece of artwork — ge, _render() (+21 more)

### Community 62 - "test_worker_gc_guard.py"
Cohesion: 0.52
Nodes (5): _resume_gc_for_worker(), _suspend_gc_for_worker(), The worker-thread GC guard: automatic cyclic GC must stay suspended for as long, test_gc_suspended_while_workers_run_and_restored_after(), test_resume_does_not_collect_on_worker_thread()

## Knowledge Gaps
- **25 isolated node(s):** `curvemill`, `CurveMill`, `graphify`, `The short version`, `The problem that started it` (+20 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `Edit Undo & Transforms` to `Main Window UI Handlers`, `Canvas View & Dimensions`, `Geometry & Toolpath Engine`, `Smart Dimensions`, `Editor Model Selection`, `SolidWorks COM Bridge`, `Spline Fit & Cloning`, `SolidWorks Spike Script`, `Editor Geometry Helpers`, `PNG Rasterizer`, `Tab UI Tests`, `.visible_layer_names`, `._active_dims`, `render_to_png`, `.redraw`, `test_text_and_per_layer_send.py`, `._build_ui`, `.is_position`, `count_profile_issues`, `build_toolpaths`, `test_project.py`, `._refresh_dim_list`, `._add_tool`, `.geometry_count_by_layer`, `test_project.py`?**
  _High betweenness centrality (0.275) - this node is a cross-community bridge._
- **Why does `VectorEntity` connect `Editor Model Selection` to `Main Window UI Handlers`, `Canvas View & Dimensions`, `Geometry & Toolpath Engine`, `SolidWorks Spike Script`, `test_tabs.py`, `Editor Geometry Helpers`, `Worker`, `Edit Undo & Transforms`, `SVG Path Export`, `Package Root`, `._set_progress`, `Layer`, `._active_dims`, `render_to_png`, `._update_warning_arrow`, `test_text_and_per_layer_send.py`, `.geometry_count_by_layer`, `.redraw`, `test_text_and_per_layer_send.py`, `._build_ui`, `.is_position`, `build_toolpaths`, `test_project.py`, `count_profile_issues`, `.geometry_count_by_layer`, `.append_layers`, `test_vcarve.py`, `test_project.py`?**
  _High betweenness centrality (0.217) - this node is a cross-community bridge._
- **Why does `SplineEntity` connect `Editor Geometry Helpers` to `Main Window UI Handlers`, `Canvas View & Dimensions`, `Geometry & Toolpath Engine`, `Editor Model Selection`, `Raster Autotrace (Potrace)`, `SolidWorks Spike Script`, `test_tabs.py`, `Worker`, `Edit Undo & Transforms`, `SVG Path Export`, `Package Root`, `._set_progress`, `Layer`, `._update_warning_arrow`, `.redraw`, `._build_ui`, `.is_position`, `test_project.py`, `count_profile_issues`, `.geometry_count_by_layer`, `.append_layers`, `test_vcarve.py`, `test_project.py`?**
  _High betweenness centrality (0.155) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `MainWindow` (e.g. with `Dimension` and `Feature`) actually correct?**
  _`MainWindow` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `VectorEntity` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`VectorEntity` has 21 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `EditorModel` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`EditorModel` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `SplineEntity` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`SplineEntity` has 21 INFERRED edges - model-reasoned connections that need verification._
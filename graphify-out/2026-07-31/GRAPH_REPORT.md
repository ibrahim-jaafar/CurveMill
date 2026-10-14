# Graph Report - DXF-CNC-Optimizer  (2026-07-30)

## Corpus Check
- 51 files · ~66,865 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1099 nodes · 3468 edges · 59 communities (50 shown, 9 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 262 edges (avg confidence: 0.56)
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
- QRectF
- ._set_progress
- combined_bounds
- Layer
- ._active_dims
- render_to_png
- CLAUDE.md
- ._update_warning_arrow
- test_text_and_per_layer_send.py
- .geometry_count_by_layer
- test_pick_tool.py
- models.py
- ._build_ui
- ImportResult
- test_pick_tool.py
- build_toolpaths
- ._evaluate_nurbs
- test_tools.py
- render_to_png
- test_tabs.py
- count_profile_issues
- ._add_tool
- .geometry_count_by_layer
- _build_chains
- test_vcarve.py
- .to_svg_path
- SolidWorks Add-in Buttons Greyed Out on Startup
- _view_units_for_pixels

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 260 edges
2. `VectorEntity` - 200 edges
3. `EditorModel` - 111 edges
4. `SplineEntity` - 101 edges
5. `BoardView` - 87 edges
6. `_app()` - 47 edges
7. `Tool` - 45 edges
8. `ProcessOptions` - 45 edges
9. `Layer` - 44 edges
10. `Dimension` - 42 edges

## Surprising Connections (you probably didn't know these)
- `Potrace v2 Raster Import Plan (PNG/JPEG to Vectors)` --conceptually_related_to--> `Potrace --tight Output Placement Mode`  [INFERRED]
  README.md → tools/potrace-1.16.win64/placement.pdf
- `Fit-Point SPLINE Export for SolidWorks Element Count Parity` --conceptually_related_to--> `Fit-Point SPLINE = 1 Sketch Element Rule`  [INFERRED]
  README.md → docs/solidworks-dxf-import.md
- `test_align_keeps_the_moved_selection_on_screen()` --calls--> `MainWindow`  [EXTRACTED]
  tests/test_app.py → curvemill/app.py
- `test_balloon_drag_defers_arrow_and_scene_extent_updates_until_drop()` --calls--> `MainWindow`  [EXTRACTED]
  tests/test_app.py → curvemill/app.py
- `test_canvas_controls_stay_fixed_while_panning_with_warning_balloons()` --calls--> `MainWindow`  [EXTRACTED]
  tests/test_app.py → curvemill/app.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Optimize for SolidWorks End-to-End Pipeline** — readme_optimize_for_solidworks_feature, docs_solidworks_dxf_import_fit_point_rule, readme_fit_point_spline_export, docs_solidworks_dxf_import_path545 [INFERRED 0.85]
- **SolidWorks DXF Element Counting Rules** — docs_solidworks_dxf_import_fit_point_rule, docs_solidworks_dxf_import_control_point_split, docs_solidworks_dxf_import_exact_g1_threshold [EXTRACTED 1.00]
- **SolidWorks COM Early Binding and Performance Pattern** — docs_solidworks_com_api_early_binding, docs_solidworks_com_api_cast_function, docs_solidworks_com_api_six_flag_recipe [INFERRED 0.85]

## Communities (59 total, 9 thin omitted)

### Community 0 - "Main Window UI Handlers"
Cohesion: 0.22
Nodes (7): Worker, WorkerSignals, ProfileIssues, The sketch faults SolidWorks' Check Sketch for Feature reports., QGraphicsScene, QObject, QRunnable

### Community 2 - "Geometry & Toolpath Engine"
Cohesion: 0.06
Nodes (87): Axis, Bounds, _constrain_move_delta(), _preserve_resize_aspect(), board_features(), Dimension, edge_segment(), Feature (+79 more)

### Community 3 - "Smart Dimensions"
Cohesion: 0.24
Nodes (12): _view_bounds(), geometry_from_wkt(), _geometry_to_vectors(), process_layers(), Machine each layer in its own mode/depth, then composite one board.      Profile, result_export_vectors(), _VCarve, LayerJob (+4 more)

### Community 4 - "App Entry & SW Dialog"
Cohesion: 0.20
Nodes (12): _demo_scaled_bounds(), _feature_text(), _hand_off_to_running_instance(), _install_ipc_server(), main(), _polygons(), Bounds after _scale_transform(origin, sx, sy), normalized (min/max)., _scaled_bounds() (+4 more)

### Community 5 - "Editor Model Selection"
Cohesion: 0.10
Nodes (30): EditorModel, Count entities (vectors + native splines) on each layer for the layer list., Layer that owns these ids (a dimensioned pattern lives on one layer)., count_open_profiles(), Produce an SVG path d-string from the polyline points., VectorEntity, test_active_layer_selection_and_all_visible_selection(), test_all_spline_file_reports_geometry_and_counts_per_layer() (+22 more)

### Community 6 - "SolidWorks COM Bridge"
Cohesion: 0.18
Nodes (4): _effective_units(), Exception, Import the COM bridge lazily so the editor runs without SolidWorks., Cutting layers that carry geometry, in feature-order (editor order).

### Community 7 - "Spline Fit & Cloning"
Cohesion: 0.22
Nodes (3): _double(), QAction, QWidget

### Community 8 - "Raster Autotrace (Potrace)"
Cohesion: 0.08
Nodes (46): Cubic, _dist_sq(), _find_potrace(), _line_to_cubic(), _parse_svg_paths(), _png_to_pbm(), Point, ProgressCallback (+38 more)

### Community 9 - "SolidWorks Spike Script"
Cohesion: 0.35
Nodes (10): join_spline_fragments(), Merge single-bezier SPLINE fragments into one native spline per shape.      Inks, _bezier(), Tests for joining Inkscape's fragmented bezier SPLINEs back into whole shapes., The whole point: joining must not move the curve., test_hard_corners_split_into_one_spline_per_side(), test_join_is_lossless(), test_joins_fragments_into_one_spline_per_shape() (+2 more)

### Community 10 - "test_tabs.py"
Cohesion: 0.15
Nodes (29): _arc_points(), _circle_points(), _curve_steps(), _doc_units(), _entity_to_vectors(), export_process_result(), export_vectors(), import_dxf() (+21 more)

### Community 11 - "Editor Geometry Helpers"
Cohesion: 0.19
Nodes (12): WarningBalloonItem, WarningOverlayState, _basis_functions(), _default_knots(), _find_span(), Generate clamped knot vector for a bezier-like NURBS curve., Find the knot span index for parameter u (Cox-deBoor)., Compute non-vanishing basis functions at parameter u. (+4 more)

### Community 12 - "Worker"
Cohesion: 0.17
Nodes (11): _chaikin_points(), _distance(), _distance_to_polyline(), _distance_to_segment(), _point_in_polygon(), Point, Write repaired vectors and natively repaired splines back as one undo step., _smooth_vector() (+3 more)

### Community 13 - "BoardView"
Cohesion: 0.11
Nodes (13): ComRegisterFunction, ComUnregisterFunction, CurveMill, DateTime, HashSet, ICommandManager, int, ISldWorks (+5 more)

### Community 14 - "Edit Undo & Transforms"
Cohesion: 0.11
Nodes (7): MainWindow, Dims to draw/list: every stored dim whose pattern lives on the layer         cu, Show only the tools that fit the current cut mode.          V-Carve drops flat, Field visibility, labels and settings for the current tool — no writes., Rebuild the read-only layer panel; reload the form only on a new pick., QMainWindow, QTreeWidgetItem

### Community 15 - "SolidWorks Export Rules Docs"
Cohesion: 0.17
Nodes (13): Fit-Point Count Rule Verified on Sketch API Path, Control-Point SPLINE Splits at G1 Tangent Breaks, Exact G1 Tangent Threshold Is Not a Tolerance, Fit-Point SPLINE = 1 Sketch Element Rule, path545.dxf Optimization Result (3383 to 540 Elements), Probe-Based Black-Box Reverse Engineering Methodology, DXF CNC Optimizer Application, Fit-Point SPLINE Export for SolidWorks Element Count Parity (+5 more)

### Community 16 - "PNG Rasterizer"
Cohesion: 0.16
Nodes (4): Path, Write the full session to path in the .curvemill format (save + autosave)., If an autosave survived (previous session crashed), offer to reopen it., QListWidgetItem

### Community 18 - "Spike Preview Image"
Cohesion: 0.60
Nodes (5): sw_spike_preview.png (SolidWorks test picture), InsertSketchPicture (SolidWorks API method), SolidWorks Live Preview Groundwork, SolidWorks API Spike, Test Visual Content (F letter, red square, blue circle)

### Community 19 - "COM Early Binding Docs"
Cohesion: 0.67
Nodes (3): cast() COM Typed Wrapper Function, SolidWorks COM Early Binding Requirement, Six-Flag Bulk Sketch Insertion Recipe (50x Speedup)

### Community 22 - ".visible_layer_names"
Cohesion: 0.20
Nodes (14): _add_geometry(), _cosmetic_pen(), _fit_content_icon(), _free_lasso_path(), _preview_vector_path(), QPainter, _selected_vector_pen(), _vector_pen() (+6 more)

### Community 23 - "SVG Path Export"
Cohesion: 0.11
Nodes (7): Move (cut) or duplicate (copy) the current selection onto a fresh layer., Combined bounds of the vectors/splines with these ids, ignoring selection., Selected, currently-visible vector and spline ids (groups expanded)., Resize the visible selection to ``width`` x ``height`` and move its         ``pa, Assign a shared group id to the visible selection (vectors and         splines)., Clear the group id from every selected vector and spline. Returns         ``True, combined_bounds()

### Community 25 - "Package Root"
Cohesion: 0.24
Nodes (16): ProgressCallback, Render DXF vectors and splines to a PNG image for auto-tracing., Render all geometry to a PNG image in memory.      Args:         vectors: Lis, render_to_png(), _report(), _report_loop(), QImage, _arrow() (+8 more)

### Community 26 - "QRectF"
Cohesion: 0.10
Nodes (12): Point, A native NURBS/parametric spline curve preserved from DXF import., Approximate this spline as a polyline of straight segments.          Cached: re-, Evaluate bezier curve using De Casteljau's algorithm (for cubic bezier subsets)., Simple De Casteljau evaluation for bezier-style splines., Evaluate a NURBS curve at parameter t using Cox-deBoor formula., Produce an SVG path d-string including bezier curves where possible., SplineEntity (+4 more)

### Community 27 - "._set_progress"
Cohesion: 0.17
Nodes (4): Return flattened vectors (includes spline approximations for display/processing), Combined bounds of all visible geometry without flattening splines.          Use, True when any visible layer holds a vector or a native spline.          Splines, Delete visible junk entities whose whole extent fits inside the tolerance.

### Community 28 - "combined_bounds"
Cohesion: 0.16
Nodes (3): Read-only Simulation-tab view sharing the editor's scene.      The processed b, SimView, QRectF

### Community 29 - "Layer"
Cohesion: 0.13
Nodes (4): _next_group_id(), Append imported vectors and splines as a new layer., Append imported DXF files as new, independently named layers., Layer

### Community 30 - "._active_dims"
Cohesion: 0.10
Nodes (27): Cutting width at the given depth below the surface., A V-carve varies Z to change the cut width; flat mills and lasers can't., Depth at which this tool cuts the given width -- inverse of         effective_di, Tool, _app(), Tool math, the Simulation tab's per-kind fields, and the Library tool table., _select_kind(), test_add_new_tool_button_and_notes_column() (+19 more)

### Community 31 - "render_to_png"
Cohesion: 0.29
Nodes (3): _arrow_path(), _closest_rect_edge_point(), _path_midpoint()

### Community 34 - "test_text_and_per_layer_send.py"
Cohesion: 0.18
Nodes (8): _distance_to_segment_qt(), _format_layout_value(), A SolidWorks-style board-relative dimension on the Y-up DXF canvas.      Draws, Hit-test for right-click/select: label, flip glyph, or the dim line., _scale_corner_at(), SmartDimItem, QGraphicsItem, QPointF

### Community 36 - "test_pick_tool.py"
Cohesion: 0.11
Nodes (3): _anchor_point(), Swap the canvas for the tool-corrected (as-milled) outlines from the         la, Swap the active layer's fragments for one native spline per shape.          In

### Community 37 - "models.py"
Cohesion: 0.24
Nodes (13): PerLayerSendDialog, Glyph outlines -> closed vectors, scaled so the text is `height_mm` tall., One sketch + feature per cutting layer, prefilled from layer depths.      Feat, (layer name, feature kind, end condition, depth in meters) per non-skipped row., _text_to_vectors(), QFont, _app(), Text-to-curves insertion and per-layer Send to SolidWorks. (+5 more)

### Community 38 - "._build_ui"
Cohesion: 0.08
Nodes (52): Curve, _depth_shade(), Cut-floor colour: the surface tone darkened in proportion to depth., BridgeError, cast(), _connect(), curves_from_entities(), _delete_preview_sketch() (+44 more)

### Community 39 - "ImportResult"
Cohesion: 0.24
Nodes (14): entries(), library_dir(), load_pattern(), Path, The pattern library: clipart, not projects.  An entry is a piece of artwork — ge, _render(), save_pattern(), thumbnail() (+6 more)

### Community 41 - "test_pick_tool.py"
Cohesion: 0.42
Nodes (9): _app(), _click(), The Select tool picks exactly one vector per click., test_drag_inside_selection_moves_outside_starts_box(), test_escape_clears_selection(), test_free_lasso_moves_inside_selection_lassos_outside(), test_move_tool_keeps_spline_multi_selection(), test_pick_tool_selects_single_vector() (+1 more)

### Community 42 - "build_toolpaths"
Cohesion: 0.16
Nodes (28): _as_polygons(), _finished_edges(), process_vectors(), The cut-side wall of every shape after tool compensation -- the edge the     mac, repair_vectors(), split_islands(), ProcessOptions, test_balloon_drag_defers_arrow_and_scene_extent_updates_until_drop() (+20 more)

### Community 43 - "._evaluate_nurbs"
Cohesion: 0.19
Nodes (10): Delete visible entities that trace the same path as an earlier one.          Mat, count_profile_issues(), duplicate_vector_indices(), Count open profiles, duplicate entities and over-used vertices.      A duplicate, Indices of entities tracing the same path as an earlier one.      Shared by the, Duplicates must not mask open profiles or inflate multi-vertex counts., test_open_profile_not_masked_by_duplicates(), _app() (+2 more)

### Community 44 - "test_tools.py"
Cohesion: 0.19
Nodes (14): load(), _points(), Path, The .curvemill project file: a paused session, resumed later.  DXF export alone, save(), _app(), A .curvemill project reopens the session exactly as it was saved., Dragging a subset separates endpoints, so the count must recompute.      Otherwi (+6 more)

### Community 45 - "render_to_png"
Cohesion: 0.23
Nodes (7): Feature picker for Send to SolidWorks -- mirrors SW's own extrude UI., (feature kind, end condition, depth in meters, flip)., Type text, pick a font + height -> closed curves on the active layer., SendToSolidWorksDialog, TextToCurvesDialog, QDialog, QDoubleSpinBox

### Community 46 - "test_tabs.py"
Cohesion: 0.42
Nodes (8): _app(), Four-tab restructure: tab shell, Process tab switch, settings round-trip., test_four_tabs_editor_default_and_shared_sim_scene(), test_process_completion_switches_to_simulation_tab(), test_send_dialog_honors_default_feature_and_depth(), test_settings_round_trip_and_startup_defaults(), test_sim_view_canvas_controls_and_fit(), _window_with_square()

### Community 47 - "count_profile_issues"
Cohesion: 0.14
Nodes (25): fit_vector_chains(), Rebuild loose LINE segments into one native spline per smooth run.      Pattern, Convert control-point splines to fit-point splines for SolidWorks export.      S, A two-point run is a straight line; express it as an exact cubic., _straight_cubic(), to_fit_splines(), Tests for rebuilding loose LINE soup into native splines., SolidWorks counts a fit-point spline as ONE element; the samples we hand     it (+17 more)

### Community 48 - "._add_tool"
Cohesion: 0.47
Nodes (5): _launch_message(), _app(), Single-instance launch handoff used by the SolidWorks add-in's two buttons., test_handle_launch_request_pulls_the_face_only_for_get_selection(), test_launch_message_maps_the_send_flag()

### Community 49 - ".geometry_count_by_layer"
Cohesion: 0.12
Nodes (8): BoardView, _nearest_selected_vertex(), _opposite_corner(), _point_distance(), _scale_factors(), _scale_transform(), _view_tolerance(), QTransform

### Community 50 - "_build_chains"
Cohesion: 0.25
Nodes (15): _add_path_warning(), build_toolpaths(), flatten_splines(), _nest_profiles(), ProgressCallback, Convert all native splines to polylines for Shapely-based processing., Preview a V-carve: the bit dips deeper where the shape is wide, so carved     de, Snap nearby endpoints of open vectors AND open native splines.      Splines are (+7 more)

### Community 51 - "test_vcarve.py"
Cohesion: 0.10
Nodes (39): assemble_closed_profiles(), _bezier_chains(), _bezier_end_dir(), _bezier_start_dir(), _buffer_toolpaths(), _build_chains(), _canonical_path(), _Chain (+31 more)

### Community 57 - "SolidWorks Add-in Buttons Greyed Out on Startup"
Cohesion: 0.15
Nodes (12): Confirmed *irrelevant* — do not waste time here, Methodology lessons, Related, SolidWorks Add-in Buttons Greyed Out on Startup, The diagnostic method (this is what cracked it), The problem that started it, The rules (measured), The short version (+4 more)

### Community 58 - "_view_units_for_pixels"
Cohesion: 0.67
Nodes (3): _lasso_screen_span(), _view_units_for_pixels(), QGraphicsView

## Knowledge Gaps
- **25 isolated node(s):** `curvemill`, `CurveMill`, `graphify`, `The short version`, `The problem that started it` (+20 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `Edit Undo & Transforms` to `Main Window UI Handlers`, `Canvas View & Dimensions`, `Geometry & Toolpath Engine`, `Smart Dimensions`, `App Entry & SW Dialog`, `Editor Model Selection`, `SolidWorks COM Bridge`, `Spline Fit & Cloning`, `Editor Geometry Helpers`, `PNG Rasterizer`, `Tab UI Tests`, `QRectF`, `combined_bounds`, `Layer`, `._active_dims`, `._update_warning_arrow`, `.geometry_count_by_layer`, `test_pick_tool.py`, `models.py`, `._build_ui`, `ImportResult`, `test_pick_tool.py`, `build_toolpaths`, `._evaluate_nurbs`, `test_tools.py`, `test_tabs.py`, `._add_tool`, `.geometry_count_by_layer`, `._on_warning_clicked`?**
  _High betweenness centrality (0.288) - this node is a cross-community bridge._
- **Why does `VectorEntity` connect `Editor Model Selection` to `Main Window UI Handlers`, `Canvas View & Dimensions`, `Geometry & Toolpath Engine`, `Smart Dimensions`, `App Entry & SW Dialog`, `test_tabs.py`, `Editor Geometry Helpers`, `Worker`, `Edit Undo & Transforms`, `.visible_layer_names`, `SVG Path Export`, `Package Root`, `QRectF`, `._set_progress`, `combined_bounds`, `Layer`, `._active_dims`, `render_to_png`, `._update_warning_arrow`, `test_text_and_per_layer_send.py`, `test_pick_tool.py`, `models.py`, `._build_ui`, `ImportResult`, `.is_position`, `test_pick_tool.py`, `build_toolpaths`, `._evaluate_nurbs`, `test_tools.py`, `render_to_png`, `test_tabs.py`, `count_profile_issues`, `.geometry_count_by_layer`, `_build_chains`, `test_vcarve.py`?**
  _High betweenness centrality (0.208) - this node is a cross-community bridge._
- **Why does `EditorModel` connect `Editor Model Selection` to `Main Window UI Handlers`, `._update_warning_arrow`, `test_text_and_per_layer_send.py`, `App Entry & SW Dialog`, `models.py`, `Spline Fit & Cloning`, `Editor Geometry Helpers`, `Worker`, `render_to_png`, `Edit Undo & Transforms`, `._evaluate_nurbs`, `.geometry_count_by_layer`, `SVG Path Export`, `QRectF`, `._set_progress`, `combined_bounds`, `Layer`?**
  _High betweenness centrality (0.139) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `MainWindow` (e.g. with `Dimension` and `Feature`) actually correct?**
  _`MainWindow` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `VectorEntity` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`VectorEntity` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `EditorModel` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`EditorModel` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `SplineEntity` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`SplineEntity` has 18 INFERRED edges - model-reasoned connections that need verification._
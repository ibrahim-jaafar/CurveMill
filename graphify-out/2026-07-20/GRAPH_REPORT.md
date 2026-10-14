# Graph Report - DXF-CNC-Optimizer  (2026-07-20)

## Corpus Check
- 42 files · ~46,863 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 863 nodes · 2726 edges · 42 communities (29 shown, 13 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 188 edges (avg confidence: 0.57)
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
- Layer Management
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
- Layer Geometry Count
- SVG Path Export
- FeatureCut4 Reference
- Package Root
- QRectF
- ._set_progress
- Tool
- ._update_warning_arrow
- ._active_dims
- render_to_png
- CLAUDE.md
- .mouseMoveEvent
- test_tabs.py
- ._on_warning_clicked
- test_pick_tool.py
- _Chain
- ImportResult
- count_profile_issues
- build_toolpaths

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 202 edges
2. `VectorEntity` - 164 edges
3. `EditorModel` - 103 edges
4. `SplineEntity` - 88 edges
5. `BoardView` - 80 edges
6. `ProcessOptions` - 37 edges
7. `Feature` - 35 edges
8. `Dimension` - 35 edges
9. `_app()` - 35 edges
10. `process_vectors()` - 30 edges

## Surprising Connections (you probably didn't know these)
- `Potrace v2 Raster Import Plan (PNG/JPEG to Vectors)` --conceptually_related_to--> `Potrace --tight Output Placement Mode`  [INFERRED]
  README.md → tools/potrace-1.16.win64/placement.pdf
- `Fit-Point SPLINE Export for SolidWorks Element Count Parity` --conceptually_related_to--> `Fit-Point SPLINE = 1 Sketch Element Rule`  [INFERRED]
  README.md → docs/solidworks-dxf-import.md
- `test_layer_depths_survive_a_project_round_trip()` --calls--> `MainWindow`  [EXTRACTED]
  tests/test_layer_depth.py → dxf_cnc_optimizer/app.py
- `_two_layer_window()` --calls--> `MainWindow`  [EXTRACTED]
  tests/test_layer_depth.py → dxf_cnc_optimizer/app.py
- `test_canvas_right_click_menu_offers_save_to_library()` --calls--> `MainWindow`  [EXTRACTED]
  tests/test_library.py → dxf_cnc_optimizer/app.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Optimize for SolidWorks End-to-End Pipeline** — readme_optimize_for_solidworks_feature, docs_solidworks_dxf_import_fit_point_rule, readme_fit_point_spline_export, docs_solidworks_dxf_import_path545 [INFERRED 0.85]
- **SolidWorks DXF Element Counting Rules** — docs_solidworks_dxf_import_fit_point_rule, docs_solidworks_dxf_import_control_point_split, docs_solidworks_dxf_import_exact_g1_threshold [EXTRACTED 1.00]
- **SolidWorks COM Early Binding and Performance Pattern** — docs_solidworks_com_api_early_binding, docs_solidworks_com_api_cast_function, docs_solidworks_com_api_six_flag_recipe [INFERRED 0.85]

## Communities (42 total, 13 thin omitted)

### Community 0 - "Main Window UI Handlers"
Cohesion: 0.15
Nodes (8): _format_layout_value(), _free_lasso_path(), _nearest_selected_vertex(), _opposite_corner(), _point_distance(), _scale_corner_at(), _scale_factors(), QPointF

### Community 1 - "Canvas View & Dimensions"
Cohesion: 0.16
Nodes (7): _lasso_screen_span(), _preserve_resize_aspect(), _view_tolerance(), _view_units_for_pixels(), KeyboardModifier, QGraphicsView, test_resize_preserves_aspect_by_default_and_shift_enables_free_resize()

### Community 2 - "Geometry & Toolpath Engine"
Cohesion: 0.16
Nodes (7): Read-only Simulation-tab view sharing the editor's scene.      The processed b, _scale_transform(), SimView, ProfileIssues, The sketch faults SolidWorks' Check Sketch for Feature reports., QGraphicsScene, QTransform

### Community 3 - "Smart Dimensions"
Cohesion: 0.09
Nodes (45): Axis, Bounds, Feature picker for Send to SolidWorks -- mirrors SW's own extrude UI., SendToSolidWorksDialog, WarningOverlayState, WorkerSignals, board_features(), Dimension (+37 more)

### Community 4 - "App Entry & SW Dialog"
Cohesion: 0.14
Nodes (32): _arc_points(), _circle_points(), _curve_steps(), _doc_units(), _entity_to_vectors(), export_process_result(), export_vectors(), import_dxf() (+24 more)

### Community 5 - "Editor Model Selection"
Cohesion: 0.12
Nodes (26): EditorModel, Count entities (vectors + native splines) on each layer for the layer list., count_open_profiles(), Produce an SVG path d-string from the polyline points., VectorEntity, test_active_layer_selection_and_all_visible_selection(), test_all_spline_file_reports_geometry_and_counts_per_layer(), test_all_spline_selection_reports_bounds_and_frames() (+18 more)

### Community 6 - "SolidWorks COM Bridge"
Cohesion: 0.11
Nodes (36): Curve, BridgeError, cast(), _connect(), curves_from_entities(), _delete_preview_sketch(), get_selection(), insert_preview() (+28 more)

### Community 8 - "Raster Autotrace (Potrace)"
Cohesion: 0.08
Nodes (46): Cubic, _dist_sq(), _find_potrace(), _line_to_cubic(), _parse_svg_paths(), _png_to_pbm(), Point, ProgressCallback (+38 more)

### Community 9 - "SolidWorks Spike Script"
Cohesion: 0.14
Nodes (41): _constrain_move_delta(), MainWindow, ImportResult, ProcessWarning, QMainWindow, _app(), _square(), test_align_keeps_the_moved_selection_on_screen() (+33 more)

### Community 10 - "Layer Management"
Cohesion: 0.24
Nodes (9): _fit_content_icon(), A SolidWorks-style board-relative dimension on the Y-up DXF canvas.      Draws, SmartDimItem, _view_vectors_icon(), QColor, QGraphicsItem, QIcon, QPainter (+1 more)

### Community 11 - "Editor Geometry Helpers"
Cohesion: 0.17
Nodes (11): _chaikin_points(), _distance(), _distance_to_polyline(), _distance_to_segment(), _point_in_polygon(), Point, Write repaired vectors and natively repaired splines back as one undo step., _smooth_vector() (+3 more)

### Community 12 - "Worker"
Cohesion: 0.19
Nodes (5): Run the full Optimize for SolidWorks pipeline:         1. Join fragmented bezie, Handle completion of the join + fit step., One processing job per cutting layer, each at its own effective width., Worker, QRunnable

### Community 13 - "BoardView"
Cohesion: 0.15
Nodes (8): _arrow_path(), _closest_rect_edge_point(), _path_midpoint(), _preview_vector_path(), _view_bounds(), WarningBalloonItem, geometry_from_wkt(), QRectF

### Community 15 - "SolidWorks Export Rules Docs"
Cohesion: 0.17
Nodes (13): Fit-Point Count Rule Verified on Sketch API Path, Control-Point SPLINE Splits at G1 Tangent Breaks, Exact G1 Tangent Threshold Is Not a Tolerance, Fit-Point SPLINE = 1 Sketch Element Rule, path545.dxf Optimization Result (3383 to 540 Elements), Probe-Based Black-Box Reverse Engineering Methodology, DXF CNC Optimizer Application, Fit-Point SPLINE Export for SolidWorks Element Count Parity (+5 more)

### Community 16 - "PNG Rasterizer"
Cohesion: 0.23
Nodes (11): _add_geometry(), _cosmetic_pen(), _depth_shade(), main(), _polygons(), Cut-floor colour: the surface tone darkened in proportion to depth., _selected_vector_pen(), _vector_path() (+3 more)

### Community 17 - "Tab UI Tests"
Cohesion: 0.17
Nodes (5): Return flattened vectors (includes spline approximations for display/processing), True when any visible layer holds a vector or a native spline.          Splines, Delete visible entities that trace the same path as an earlier one.          Mat, duplicate_vector_indices(), Indices of entities tracing the same path as an earlier one.      Shared by the

### Community 18 - "Spike Preview Image"
Cohesion: 0.60
Nodes (5): sw_spike_preview.png (SolidWorks test picture), InsertSketchPicture (SolidWorks API method), SolidWorks Live Preview Groundwork, SolidWorks API Spike, Test Visual Content (F letter, red square, blue circle)

### Community 19 - "COM Early Binding Docs"
Cohesion: 0.67
Nodes (3): cast() COM Typed Wrapper Function, SolidWorks COM Early Binding Requirement, Six-Flag Bulk Sketch Insertion Recipe (50x Speedup)

### Community 22 - "Layer Geometry Count"
Cohesion: 0.12
Nodes (5): Append imported vectors and splines as a new layer., Selected, currently-visible vector and spline ids (groups expanded)., Resize the visible selection to ``width`` x ``height`` and move its         ``pa, Assign a shared group id to the visible selection (vectors and         splines)., Clear the group id from every selected vector and spline. Returns         ``True

### Community 26 - "QRectF"
Cohesion: 0.13
Nodes (17): _next_group_id(), Append imported DXF files as new, independently named layers., Layer, A native NURBS/parametric spline curve preserved from DXF import., SplineEntity, load(), _points(), Path (+9 more)

### Community 28 - "Tool"
Cohesion: 0.08
Nodes (32): _basis_functions(), _default_knots(), _find_span(), Evaluate a NURBS curve at parameter t using Cox-deBoor formula., Generate clamped knot vector for a bezier-like NURBS curve., Find the knot span index for parameter u (Cox-deBoor)., Compute non-vanishing basis functions at parameter u., Cutting width at the given depth below the surface. (+24 more)

### Community 29 - "._update_warning_arrow"
Cohesion: 0.16
Nodes (5): Point, Approximate this spline as a polyline of straight segments., Evaluate bezier curve using De Casteljau's algorithm (for cubic bezier subsets)., Simple De Casteljau evaluation for bezier-style splines., Produce an SVG path d-string including bezier curves where possible.

### Community 31 - "render_to_png"
Cohesion: 0.17
Nodes (9): Exception, Import the COM bridge lazily so the editor runs without SolidWorks., (feature kind, end condition, depth in meters, flip)., ProgressCallback, Render DXF vectors and splines to a PNG image for auto-tracing., Render all geometry to a PNG image in memory.      Args:         vectors: Lis, render_to_png(), _report() (+1 more)

### Community 34 - "test_tabs.py"
Cohesion: 0.46
Nodes (7): _app(), Four-tab restructure: tab shell, Process tab switch, settings round-trip., test_four_tabs_editor_default_and_shared_sim_scene(), test_process_completion_switches_to_simulation_tab(), test_settings_round_trip_and_startup_defaults(), test_sim_view_canvas_controls_and_fit(), _window_with_square()

### Community 36 - "test_pick_tool.py"
Cohesion: 0.52
Nodes (6): _app(), _click(), The Select tool picks exactly one vector per click., test_move_tool_keeps_spline_multi_selection(), test_pick_tool_selects_single_vector(), test_pick_tool_selects_spline()

### Community 38 - "_Chain"
Cohesion: 0.05
Nodes (84): _add_path_warning(), _as_polygons(), assemble_closed_profiles(), _bezier_chains(), _buffer_toolpaths(), _build_chains(), build_toolpaths(), _canonical_path() (+76 more)

### Community 39 - "ImportResult"
Cohesion: 0.22
Nodes (15): DXF CNC Optimizer package., entries(), library_dir(), load_pattern(), Path, The pattern library: clipart, not projects.  An entry is a piece of artwork — ge, _render(), save_pattern() (+7 more)

### Community 40 - "count_profile_issues"
Cohesion: 0.27
Nodes (7): count_profile_issues(), Count open profiles, duplicate entities and over-used vertices.      A duplicate, Duplicates must not mask open profiles or inflate multi-vertex counts., test_open_profile_not_masked_by_duplicates(), _app(), Repair removes duplicate entities and the button gate includes them., test_repair_enabled_for_duplicates_and_removes_them()

## Knowledge Gaps
- **14 isolated node(s):** `dxf-cnc-optimizer`, `graphify`, `CNC Endmill Milling Simulation`, `cast() COM Typed Wrapper Function`, `Six-Flag Bulk Sketch Insertion Recipe (50x Speedup)` (+9 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `SolidWorks Spike Script` to `Canvas View & Dimensions`, `Geometry & Toolpath Engine`, `Smart Dimensions`, `App Entry & SW Dialog`, `Editor Model Selection`, `Spline Fit & Cloning`, `Worker`, `Edit Undo & Transforms`, `PNG Rasterizer`, `SVG Path Export`, `QRectF`, `._set_progress`, `Tool`, `._active_dims`, `render_to_png`, `.mouseMoveEvent`, `test_tabs.py`, `test_pick_tool.py`, `._add_tool`, `_Chain`, `ImportResult`, `count_profile_issues`, `build_toolpaths`?**
  _High betweenness centrality (0.288) - this node is a cross-community bridge._
- **Why does `VectorEntity` connect `Editor Model Selection` to `Geometry & Toolpath Engine`, `Smart Dimensions`, `App Entry & SW Dialog`, `SolidWorks COM Bridge`, `Spline Fit & Cloning`, `SolidWorks Spike Script`, `Layer Management`, `Editor Geometry Helpers`, `Worker`, `BoardView`, `Edit Undo & Transforms`, `PNG Rasterizer`, `Tab UI Tests`, `Layer Geometry Count`, `QRectF`, `._set_progress`, `Tool`, `._update_warning_arrow`, `render_to_png`, `test_tabs.py`, `._on_warning_clicked`, `test_pick_tool.py`, `_Chain`, `ImportResult`, `count_profile_issues`?**
  _High betweenness centrality (0.240) - this node is a cross-community bridge._
- **Why does `SplineEntity` connect `QRectF` to `Geometry & Toolpath Engine`, `Smart Dimensions`, `App Entry & SW Dialog`, `Editor Model Selection`, `SolidWorks COM Bridge`, `Spline Fit & Cloning`, `Raster Autotrace (Potrace)`, `SolidWorks Spike Script`, `Layer Management`, `Editor Geometry Helpers`, `Worker`, `BoardView`, `Edit Undo & Transforms`, `PNG Rasterizer`, `Tab UI Tests`, `Layer Geometry Count`, `Tool`, `._update_warning_arrow`, `render_to_png`, `._on_warning_clicked`, `test_pick_tool.py`, `_Chain`, `ImportResult`, `count_profile_issues`?**
  _High betweenness centrality (0.183) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `MainWindow` (e.g. with `Dimension` and `Feature`) actually correct?**
  _`MainWindow` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `VectorEntity` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`VectorEntity` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `EditorModel` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`EditorModel` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `SplineEntity` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`SplineEntity` has 15 INFERRED edges - model-reasoned connections that need verification._
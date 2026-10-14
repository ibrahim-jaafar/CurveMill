# Graph Report - DXF-CNC-Optimizer  (2026-07-19)

## Corpus Check
- 32 files · ~41,073 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 747 nodes · 2327 edges · 33 communities (25 shown, 8 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 170 edges (avg confidence: 0.57)
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
- NURBS Math & Models
- Selection Grouping & Layout
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
- SmartDimItem
- .mouseReleaseEvent
- ._update_warning_arrow
- .mouseMoveEvent
- .__init__
- CLAUDE.md

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 151 edges
2. `VectorEntity` - 140 edges
3. `EditorModel` - 101 edges
4. `BoardView` - 77 edges
5. `SplineEntity` - 74 edges
6. `Feature` - 35 edges
7. `Dimension` - 35 edges
8. `_app()` - 35 edges
9. `ProcessOptions` - 34 edges
10. `process_vectors()` - 31 edges

## Surprising Connections (you probably didn't know these)
- `Potrace v2 Raster Import Plan (PNG/JPEG to Vectors)` --conceptually_related_to--> `Potrace --tight Output Placement Mode`  [INFERRED]
  README.md → tools/potrace-1.16.win64/placement.pdf
- `Fit-Point SPLINE Export for SolidWorks Element Count Parity` --conceptually_related_to--> `Fit-Point SPLINE = 1 Sketch Element Rule`  [INFERRED]
  README.md → docs/solidworks-dxf-import.md
- `test_align_keeps_the_moved_selection_on_screen()` --calls--> `MainWindow`  [EXTRACTED]
  tests/test_app.py → dxf_cnc_optimizer/app.py
- `test_balloon_drag_defers_arrow_and_scene_extent_updates_until_drop()` --calls--> `MainWindow`  [EXTRACTED]
  tests/test_app.py → dxf_cnc_optimizer/app.py
- `test_canvas_controls_stay_fixed_while_panning_with_warning_balloons()` --calls--> `MainWindow`  [EXTRACTED]
  tests/test_app.py → dxf_cnc_optimizer/app.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Optimize for SolidWorks End-to-End Pipeline** — readme_optimize_for_solidworks_feature, docs_solidworks_dxf_import_fit_point_rule, readme_fit_point_spline_export, docs_solidworks_dxf_import_path545 [INFERRED 0.85]
- **SolidWorks DXF Element Counting Rules** — docs_solidworks_dxf_import_fit_point_rule, docs_solidworks_dxf_import_control_point_split, docs_solidworks_dxf_import_exact_g1_threshold [EXTRACTED 1.00]
- **SolidWorks COM Early Binding and Performance Pattern** — docs_solidworks_com_api_early_binding, docs_solidworks_com_api_cast_function, docs_solidworks_com_api_six_flag_recipe [INFERRED 0.85]

## Communities (33 total, 8 thin omitted)

### Community 0 - "Main Window UI Handlers"
Cohesion: 0.05
Nodes (15): _anchor_point(), _double(), _effective_units(), MainWindow, Exception, Run the full Optimize for SolidWorks pipeline:         1. Join fragmented bezie, Handle completion of the join + fit step., Import the COM bridge lazily so the editor runs without SolidWorks. (+7 more)

### Community 1 - "Canvas View & Dimensions"
Cohesion: 0.12
Nodes (4): BoardView, _format_layout_value(), _path_midpoint(), QGraphicsItem

### Community 2 - "Geometry & Toolpath Engine"
Cohesion: 0.05
Nodes (84): main(), Read-only Simulation-tab view sharing the editor's scene.      The processed b, Feature picker for Send to SolidWorks -- mirrors SW's own extrude UI., (feature kind, end condition, depth in meters, flip)., SendToSolidWorksDialog, SimView, _view_bounds(), WarningBalloonItem (+76 more)

### Community 3 - "Smart Dimensions"
Cohesion: 0.13
Nodes (39): Axis, Bounds, _feature_text(), board_features(), Dimension, edge_segment(), Feature, feature_coord() (+31 more)

### Community 4 - "App Entry & SW Dialog"
Cohesion: 0.12
Nodes (36): _arc_points(), _circle_points(), _curve_steps(), _doc_units(), _entity_to_vectors(), export_process_result(), export_vectors(), import_dxf() (+28 more)

### Community 5 - "Editor Model Selection"
Cohesion: 0.11
Nodes (24): EditorModel, Return flattened vectors (includes spline approximations for display/processing), True when any visible layer holds a vector or a native spline.          Splines, VectorEntity, test_active_layer_selection_and_all_visible_selection(), test_all_spline_file_reports_geometry_and_counts_per_layer(), test_all_spline_selection_reports_bounds_and_frames(), test_append_layers_preserves_existing_vectors_and_uses_unique_names() (+16 more)

### Community 6 - "SolidWorks COM Bridge"
Cohesion: 0.11
Nodes (36): Curve, BridgeError, cast(), _connect(), curves_from_entities(), _delete_preview_sketch(), get_selection(), insert_preview() (+28 more)

### Community 7 - "Spline Fit & Cloning"
Cohesion: 0.11
Nodes (9): Write repaired vectors and natively repaired splines back as one undo step., _spline_geometry_equal(), Point, A native NURBS/parametric spline curve preserved from DXF import., Approximate this spline as a polyline of straight segments., Evaluate bezier curve using De Casteljau's algorithm (for cubic bezier subsets)., Simple De Casteljau evaluation for bezier-style splines., Produce an SVG path d-string including bezier curves where possible. (+1 more)

### Community 8 - "Raster Autotrace (Potrace)"
Cohesion: 0.08
Nodes (46): Cubic, _dist_sq(), _find_potrace(), _line_to_cubic(), _parse_svg_paths(), _png_to_pbm(), Point, ProgressCallback (+38 more)

### Community 9 - "SolidWorks Spike Script"
Cohesion: 0.11
Nodes (42): _constrain_move_delta(), _preserve_resize_aspect(), ImportResult, KeyboardModifier, QPointF, _app(), _square(), test_align_keeps_the_moved_selection_on_screen() (+34 more)

### Community 10 - "Layer Management"
Cohesion: 0.18
Nodes (4): _next_group_id(), Append imported vectors and splines as a new layer., Append imported DXF files as new, independently named layers., Layer

### Community 11 - "Editor Geometry Helpers"
Cohesion: 0.19
Nodes (9): _chaikin_points(), _distance(), _distance_to_polyline(), _distance_to_segment(), _point_in_polygon(), Point, _smooth_vector(), _vector_geometry_equal() (+1 more)

### Community 12 - "NURBS Math & Models"
Cohesion: 0.25
Nodes (7): _basis_functions(), _default_knots(), _find_span(), Evaluate a NURBS curve at parameter t using Cox-deBoor formula., Generate clamped knot vector for a bezier-like NURBS curve., Find the knot span index for parameter u (Cox-deBoor)., Compute non-vanishing basis functions at parameter u.

### Community 13 - "Selection Grouping & Layout"
Cohesion: 0.12
Nodes (6): Combined bounds of all visible geometry without flattening splines.          Use, Selected, currently-visible vector and spline ids (groups expanded)., Resize the visible selection to ``width`` x ``height`` and move its         ``pa, Assign a shared group id to the visible selection (vectors and         splines)., Clear the group id from every selected vector and spline. Returns         ``True, combined_bounds()

### Community 15 - "SolidWorks Export Rules Docs"
Cohesion: 0.17
Nodes (13): Fit-Point Count Rule Verified on Sketch API Path, Control-Point SPLINE Splits at G1 Tangent Breaks, Exact G1 Tangent Threshold Is Not a Tolerance, Fit-Point SPLINE = 1 Sketch Element Rule, path545.dxf Optimization Result (3383 to 540 Elements), Probe-Based Black-Box Reverse Engineering Methodology, DXF CNC Optimizer Application, Fit-Point SPLINE Export for SolidWorks Element Count Parity (+5 more)

### Community 16 - "PNG Rasterizer"
Cohesion: 0.52
Nodes (6): ProgressCallback, Render DXF vectors and splines to a PNG image for auto-tracing., Render all geometry to a PNG image in memory.      Args:         vectors: Lis, render_to_png(), _report(), _report_loop()

### Community 17 - "Tab UI Tests"
Cohesion: 0.18
Nodes (19): fit_vector_chains(), Rebuild loose LINE segments into one native spline per smooth run.      Pattern, Convert control-point splines to fit-point splines for SolidWorks export.      S, to_fit_splines(), Tests for rebuilding loose LINE soup into native splines., One VectorEntity per segment -- how pattern DXFs actually arrive., Re-imported optimized files have no control net; canvas and milling     both go, The whole point: reducing entity count must not move the geometry. (+11 more)

### Community 18 - "Spike Preview Image"
Cohesion: 0.60
Nodes (5): sw_spike_preview.png (SolidWorks test picture), InsertSketchPicture (SolidWorks API method), SolidWorks Live Preview Groundwork, SolidWorks API Spike, Test Visual Content (F letter, red square, blue circle)

### Community 19 - "COM Early Binding Docs"
Cohesion: 0.67
Nodes (3): cast() COM Typed Wrapper Function, SolidWorks COM Early Binding Requirement, Six-Flag Bulk Sketch Insertion Recipe (50x Speedup)

### Community 23 - "SVG Path Export"
Cohesion: 0.18
Nodes (8): _cosmetic_pen(), _nearest_selected_vertex(), _opposite_corner(), _scale_corner_at(), _scale_factors(), _selected_vector_pen(), _vector_pen(), PenStyle

### Community 27 - "SmartDimItem"
Cohesion: 0.28
Nodes (8): _fit_content_icon(), A SolidWorks-style board-relative dimension on the Y-up DXF canvas.      Draws, SmartDimItem, _view_vectors_icon(), QColor, QIcon, QPainter, QPen

### Community 28 - ".mouseReleaseEvent"
Cohesion: 0.21
Nodes (5): _lasso_screen_span(), _view_tolerance(), _view_units_for_pixels(), QGraphicsView, QTransform

### Community 29 - "._update_warning_arrow"
Cohesion: 0.38
Nodes (5): _arrow_path(), _closest_rect_edge_point(), _preview_vector_path(), _vector_path(), QPainterPath

### Community 30 - ".mouseMoveEvent"
Cohesion: 0.33
Nodes (3): _free_lasso_path(), _point_distance(), _scale_transform()

### Community 31 - ".__init__"
Cohesion: 0.40
Nodes (3): _add_geometry(), _polygons(), QGraphicsScene

## Knowledge Gaps
- **14 isolated node(s):** `dxf-cnc-optimizer`, `graphify`, `CNC Endmill Milling Simulation`, `cast() COM Typed Wrapper Function`, `Six-Flag Bulk Sketch Insertion Recipe (50x Speedup)` (+9 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `Main Window UI Handlers` to `Geometry & Toolpath Engine`, `Smart Dimensions`, `App Entry & SW Dialog`, `Editor Model Selection`, `Spline Fit & Cloning`, `SolidWorks Spike Script`, `Edit Undo & Transforms`, `.mouseReleaseEvent`?**
  _High betweenness centrality (0.245) - this node is a cross-community bridge._
- **Why does `VectorEntity` connect `Editor Model Selection` to `Main Window UI Handlers`, `Canvas View & Dimensions`, `Geometry & Toolpath Engine`, `App Entry & SW Dialog`, `SolidWorks COM Bridge`, `Spline Fit & Cloning`, `SolidWorks Spike Script`, `Layer Management`, `Editor Geometry Helpers`, `Selection Grouping & Layout`, `Edit Undo & Transforms`, `PNG Rasterizer`, `Tab UI Tests`, `Layer Geometry Count`, `SmartDimItem`, `._update_warning_arrow`?**
  _High betweenness centrality (0.235) - this node is a cross-community bridge._
- **Why does `SplineEntity` connect `Spline Fit & Cloning` to `Main Window UI Handlers`, `Canvas View & Dimensions`, `Geometry & Toolpath Engine`, `App Entry & SW Dialog`, `Editor Model Selection`, `SolidWorks COM Bridge`, `Raster Autotrace (Potrace)`, `Layer Management`, `Editor Geometry Helpers`, `NURBS Math & Models`, `Selection Grouping & Layout`, `Edit Undo & Transforms`, `PNG Rasterizer`, `Tab UI Tests`, `SmartDimItem`?**
  _High betweenness centrality (0.199) - this node is a cross-community bridge._
- **Are the 12 inferred relationships involving `MainWindow` (e.g. with `Dimension` and `Feature`) actually correct?**
  _`MainWindow` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `VectorEntity` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`VectorEntity` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `EditorModel` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`EditorModel` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `BoardView` (e.g. with `Dimension` and `Feature`) actually correct?**
  _`BoardView` has 12 INFERRED edges - model-reasoned connections that need verification._
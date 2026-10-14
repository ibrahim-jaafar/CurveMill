# Graph Report - DXF-CNC-Optimizer  (2026-07-27)

## Corpus Check
- 43 files · ~51,154 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 940 nodes · 3023 edges · 47 communities (34 shown, 13 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 230 edges (avg confidence: 0.56)
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
- .visible_layer_names
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
- ._update_warning_arrow
- test_tabs.py
- test_pick_tool.py
- ._add_tool
- _Chain
- ImportResult
- .open_project
- repair_geometry
- ._handle_dim_click
- ._set_warnings
- ._evaluate_nurbs
- .is_position
- .is_size

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 224 edges
2. `VectorEntity` - 177 edges
3. `EditorModel` - 107 edges
4. `SplineEntity` - 90 edges
5. `BoardView` - 86 edges
6. `Dimension` - 42 edges
7. `Feature` - 40 edges
8. `ProcessOptions` - 39 edges
9. `_app()` - 39 edges
10. `Layer` - 36 edges

## Surprising Connections (you probably didn't know these)
- `Potrace v2 Raster Import Plan (PNG/JPEG to Vectors)` --conceptually_related_to--> `Potrace --tight Output Placement Mode`  [INFERRED]
  README.md → tools/potrace-1.16.win64/placement.pdf
- `test_resize_preserves_aspect_by_default_and_shift_enables_free_resize()` --calls--> `_preserve_resize_aspect()`  [EXTRACTED]
  tests/test_app.py → dxf_cnc_optimizer/app.py
- `Fit-Point SPLINE Export for SolidWorks Element Count Parity` --conceptually_related_to--> `Fit-Point SPLINE = 1 Sketch Element Rule`  [INFERRED]
  README.md → docs/solidworks-dxf-import.md
- `test_layer_depths_survive_a_project_round_trip()` --calls--> `MainWindow`  [EXTRACTED]
  tests/test_layer_depth.py → dxf_cnc_optimizer/app.py
- `_two_layer_window()` --calls--> `MainWindow`  [EXTRACTED]
  tests/test_layer_depth.py → dxf_cnc_optimizer/app.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Optimize for SolidWorks End-to-End Pipeline** — readme_optimize_for_solidworks_feature, docs_solidworks_dxf_import_fit_point_rule, readme_fit_point_spline_export, docs_solidworks_dxf_import_path545 [INFERRED 0.85]
- **SolidWorks DXF Element Counting Rules** — docs_solidworks_dxf_import_fit_point_rule, docs_solidworks_dxf_import_control_point_split, docs_solidworks_dxf_import_exact_g1_threshold [EXTRACTED 1.00]
- **SolidWorks COM Early Binding and Performance Pattern** — docs_solidworks_com_api_early_binding, docs_solidworks_com_api_cast_function, docs_solidworks_com_api_six_flag_recipe [INFERRED 0.85]

## Communities (47 total, 13 thin omitted)

### Community 0 - "Main Window UI Handlers"
Cohesion: 0.14
Nodes (36): Axis, Bounds, _feature_text(), board_features(), edge_segment(), Feature, feature_coord(), feature_point() (+28 more)

### Community 1 - "Canvas View & Dimensions"
Cohesion: 0.25
Nodes (19): process_vectors(), repair_vectors(), split_islands(), ProcessOptions, _circle(), _path_radius(), A circle inside a circle is material in between: inside shrinks the outer     ed, test_center_cut_removes_material_from_board() (+11 more)

### Community 2 - "Geometry & Toolpath Engine"
Cohesion: 0.13
Nodes (44): MainWindow, Dimension, QMainWindow, _app(), _square(), test_align_keeps_the_moved_selection_on_screen(), test_balloon_drag_defers_arrow_and_scene_extent_updates_until_drop(), test_canvas_controls_stay_fixed_while_panning_with_warning_balloons() (+36 more)

### Community 3 - "Smart Dimensions"
Cohesion: 0.11
Nodes (19): _add_geometry(), _anchor_point(), _constrain_move_delta(), _demo_scaled_bounds(), main(), _opposite_corner(), _point_distance(), _polygons() (+11 more)

### Community 4 - "App Entry & SW Dialog"
Cohesion: 0.11
Nodes (38): _arc_points(), _circle_points(), _curve_steps(), _doc_units(), _entity_to_vectors(), export_process_result(), export_vectors(), import_dxf() (+30 more)

### Community 5 - "Editor Model Selection"
Cohesion: 0.11
Nodes (26): EditorModel, Count entities (vectors + native splines) on each layer for the layer list., Layer that owns these ids (a dimensioned pattern lives on one layer)., Produce an SVG path d-string from the polyline points., VectorEntity, test_active_layer_selection_and_all_visible_selection(), test_all_spline_file_reports_geometry_and_counts_per_layer(), test_all_spline_selection_reports_bounds_and_frames() (+18 more)

### Community 6 - "SolidWorks COM Bridge"
Cohesion: 0.08
Nodes (47): Curve, _depth_shade(), Cut-floor colour: the surface tone darkened in proportion to depth., BridgeError, cast(), _connect(), curves_from_entities(), _delete_preview_sketch() (+39 more)

### Community 8 - "Raster Autotrace (Potrace)"
Cohesion: 0.08
Nodes (46): Cubic, _dist_sq(), _find_potrace(), _line_to_cubic(), _parse_svg_paths(), _png_to_pbm(), Point, ProgressCallback (+38 more)

### Community 9 - "SolidWorks Spike Script"
Cohesion: 0.29
Nodes (10): Glyph outlines -> closed vectors, scaled so the text is `height_mm` tall., _text_to_vectors(), QFont, _app(), Text-to-curves insertion and per-layer Send to SolidWorks., test_inserted_text_lands_on_the_active_layer(), test_per_layer_dialog_prefills_through_all_past_thickness_and_skips(), test_sw_send_layers_lists_only_cutting_layers_with_geometry() (+2 more)

### Community 10 - "Layer Management"
Cohesion: 0.19
Nodes (15): _distance_to_segment_qt(), _fit_content_icon(), _free_lasso_path(), _preview_vector_path(), A SolidWorks-style board-relative dimension on the Y-up DXF canvas.      Draws, Hit-test for right-click/select: label, flip glyph, or the dim line., SmartDimItem, _view_vectors_icon() (+7 more)

### Community 11 - "Editor Geometry Helpers"
Cohesion: 0.17
Nodes (11): _chaikin_points(), _distance(), _distance_to_polyline(), _distance_to_segment(), _point_in_polygon(), Point, Write repaired vectors and natively repaired splines back as one undo step., _smooth_vector() (+3 more)

### Community 12 - "Worker"
Cohesion: 0.12
Nodes (5): Run the full Optimize for SolidWorks pipeline:         1. Join fragmented bezie, Handle completion of the join + fit step., One processing job per cutting layer, each at its own effective width., Worker, QRunnable

### Community 13 - "BoardView"
Cohesion: 0.11
Nodes (20): _next_group_id(), Append imported vectors and splines as a new layer., Append imported DXF files as new, independently named layers., Layer, A native NURBS/parametric spline curve preserved from DXF import., SplineEntity, load(), _points() (+12 more)

### Community 15 - "SolidWorks Export Rules Docs"
Cohesion: 0.17
Nodes (13): Fit-Point Count Rule Verified on Sketch API Path, Control-Point SPLINE Splits at G1 Tangent Breaks, Exact G1 Tangent Threshold Is Not a Tolerance, Fit-Point SPLINE = 1 Sketch Element Rule, path545.dxf Optimization Result (3383 to 540 Elements), Probe-Based Black-Box Reverse Engineering Methodology, DXF CNC Optimizer Application, Fit-Point SPLINE Export for SolidWorks Element Count Parity (+5 more)

### Community 16 - "PNG Rasterizer"
Cohesion: 0.23
Nodes (10): count_open_profiles(), count_profile_issues(), count_self_intersections(), Count open profiles, duplicate entities and over-used vertices.      A duplicate, test_self_intersection_counted_and_healed(), Duplicates must not mask open profiles or inflate multi-vertex counts., test_open_profile_not_masked_by_duplicates(), _app() (+2 more)

### Community 17 - "Tab UI Tests"
Cohesion: 0.13
Nodes (25): fit_vector_chains(), Rebuild loose LINE segments into one native spline per smooth run.      Pattern, Convert control-point splines to fit-point splines for SolidWorks export.      S, to_fit_splines(), Tests for rebuilding loose LINE soup into native splines., One VectorEntity per segment -- how pattern DXFs actually arrive., Re-imported optimized files have no control net; canvas and milling     both go, The whole point: reducing entity count must not move the geometry. (+17 more)

### Community 18 - "Spike Preview Image"
Cohesion: 0.60
Nodes (5): sw_spike_preview.png (SolidWorks test picture), InsertSketchPicture (SolidWorks API method), SolidWorks Live Preview Groundwork, SolidWorks API Spike, Test Visual Content (F letter, red square, blue circle)

### Community 19 - "COM Early Binding Docs"
Cohesion: 0.67
Nodes (3): cast() COM Typed Wrapper Function, SolidWorks COM Early Binding Requirement, Six-Flag Bulk Sketch Insertion Recipe (50x Speedup)

### Community 22 - ".visible_layer_names"
Cohesion: 0.14
Nodes (6): Return flattened vectors (includes spline approximations for display/processing), Combined bounds of all visible geometry without flattening splines.          Use, True when any visible layer holds a vector or a native spline.          Splines, Delete visible entities that trace the same path as an earlier one.          Mat, duplicate_vector_indices(), Indices of entities tracing the same path as an earlier one.      Shared by the

### Community 23 - "SVG Path Export"
Cohesion: 0.06
Nodes (21): _double(), _effective_units(), PerLayerSendDialog, Exception, Import the COM bridge lazily so the editor runs without SolidWorks., Cutting layers that carry geometry, in feature-order (editor order)., Feature picker for Send to SolidWorks -- mirrors SW's own extrude UI., (feature kind, end condition, depth in meters, flip). (+13 more)

### Community 28 - "Tool"
Cohesion: 0.21
Nodes (18): Read-only Simulation-tab view sharing the editor's scene.      The processed b, Type text, pick a font + height -> closed curves on the active layer., SimView, TextToCurvesDialog, WarningOverlayState, WorkerSignals, _Chain, ProfileIssues (+10 more)

### Community 29 - "._update_warning_arrow"
Cohesion: 0.16
Nodes (5): Point, Approximate this spline as a polyline of straight segments., Evaluate bezier curve using De Casteljau's algorithm (for cubic bezier subsets)., Simple De Casteljau evaluation for bezier-style splines., Produce an SVG path d-string including bezier curves where possible.

### Community 31 - "render_to_png"
Cohesion: 0.25
Nodes (7): _basis_functions(), _default_knots(), _find_span(), Evaluate a NURBS curve at parameter t using Cox-deBoor formula., Generate clamped knot vector for a bezier-like NURBS curve., Find the knot span index for parameter u (Cox-deBoor)., Compute non-vanishing basis functions at parameter u.

### Community 33 - "._update_warning_arrow"
Cohesion: 0.18
Nodes (4): _arrow_path(), _closest_rect_edge_point(), _path_midpoint(), WarningBalloonItem

### Community 34 - "test_tabs.py"
Cohesion: 0.18
Nodes (10): Cutting width at the given depth below the surface., Tool, _app(), Tool math, the Simulation tab's per-kind fields, and the Library tool table., _select_kind(), test_effective_diameter_by_kind(), test_effective_diameter_feeds_the_simulation(), test_kind_picker_shows_only_relevant_fields() (+2 more)

### Community 36 - "test_pick_tool.py"
Cohesion: 0.23
Nodes (8): _cosmetic_pen(), _lasso_screen_span(), _selected_vector_pen(), _vector_pen(), _view_units_for_pixels(), PenStyle, QGraphicsItem, QGraphicsView

### Community 37 - "._add_tool"
Cohesion: 0.11
Nodes (4): Selected, currently-visible vector and spline ids (groups expanded)., Resize the visible selection to ``width`` x ``height`` and move its         ``pa, Assign a shared group id to the visible selection (vectors and         splines)., Clear the group id from every selected vector and spline. Returns         ``True

### Community 38 - "_Chain"
Cohesion: 0.13
Nodes (29): assemble_closed_profiles(), _bezier_chains(), _buffer0_rings(), _buffer_toolpaths(), _build_chains(), _canonical_path(), _chain_is_closed(), _dist() (+21 more)

### Community 39 - "ImportResult"
Cohesion: 0.22
Nodes (15): DXF CNC Optimizer package., entries(), library_dir(), load_pattern(), Path, The pattern library: clipart, not projects.  An entry is a piece of artwork — ge, _render(), save_pattern() (+7 more)

### Community 40 - ".open_project"
Cohesion: 0.20
Nodes (3): Path, Write the full session to path in the .curvemill format (save + autosave)., If an autosave survived (previous session crashed), offer to reopen it.

### Community 41 - "repair_geometry"
Cohesion: 0.20
Nodes (16): _add_path_warning(), _as_polygons(), build_toolpaths(), flatten_splines(), geometry_from_wkt(), _nest_profiles(), process_layers(), ProgressCallback (+8 more)

### Community 42 - "._handle_dim_click"
Cohesion: 0.11
Nodes (5): BoardView, _format_layout_value(), _nearest_selected_vertex(), _scale_corner_at(), _view_tolerance()

### Community 44 - "._evaluate_nurbs"
Cohesion: 0.36
Nodes (9): join_spline_fragments(), Merge single-bezier SPLINE fragments into one native spline per shape.      Inks, _bezier(), Tests for joining Inkscape's fragmented bezier SPLINEs back into whole shapes., The whole point: joining must not move the curve., test_closed_shape_is_flagged_closed_and_shapes_stay_separate(), test_join_is_lossless(), test_joins_fragments_into_one_spline_per_shape() (+1 more)

## Knowledge Gaps
- **14 isolated node(s):** `dxf-cnc-optimizer`, `graphify`, `CNC Endmill Milling Simulation`, `cast() COM Typed Wrapper Function`, `Six-Flag Bulk Sketch Insertion Recipe (50x Speedup)` (+9 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `Geometry & Toolpath Engine` to `Main Window UI Handlers`, `Canvas View & Dimensions`, `Smart Dimensions`, `App Entry & SW Dialog`, `Editor Model Selection`, `SolidWorks COM Bridge`, `Spline Fit & Cloning`, `SolidWorks Spike Script`, `Worker`, `BoardView`, `Edit Undo & Transforms`, `PNG Rasterizer`, `Tab UI Tests`, `SVG Path Export`, `._set_progress`, `Tool`, `._active_dims`, `test_tabs.py`, `Tool`, `ImportResult`, `.open_project`, `._set_warnings`?**
  _High betweenness centrality (0.296) - this node is a cross-community bridge._
- **Why does `VectorEntity` connect `Editor Model Selection` to `Canvas View & Dimensions`, `Geometry & Toolpath Engine`, `Smart Dimensions`, `App Entry & SW Dialog`, `SolidWorks COM Bridge`, `SolidWorks Spike Script`, `Layer Management`, `Editor Geometry Helpers`, `Worker`, `BoardView`, `Edit Undo & Transforms`, `PNG Rasterizer`, `Tab UI Tests`, `.visible_layer_names`, `SVG Path Export`, `QRectF`, `Tool`, `._update_warning_arrow`, `._update_warning_arrow`, `._add_tool`, `_Chain`, `ImportResult`, `repair_geometry`, `._handle_dim_click`?**
  _High betweenness centrality (0.239) - this node is a cross-community bridge._
- **Why does `SplineEntity` connect `BoardView` to `Geometry & Toolpath Engine`, `Smart Dimensions`, `App Entry & SW Dialog`, `Editor Model Selection`, `SolidWorks COM Bridge`, `Raster Autotrace (Potrace)`, `Layer Management`, `Editor Geometry Helpers`, `Worker`, `Edit Undo & Transforms`, `Tab UI Tests`, `.visible_layer_names`, `SVG Path Export`, `QRectF`, `Tool`, `._update_warning_arrow`, `render_to_png`, `._update_warning_arrow`, `._add_tool`, `_Chain`, `ImportResult`, `repair_geometry`, `._handle_dim_click`, `._evaluate_nurbs`?**
  _High betweenness centrality (0.168) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `MainWindow` (e.g. with `Dimension` and `Feature`) actually correct?**
  _`MainWindow` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `VectorEntity` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`VectorEntity` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `EditorModel` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`EditorModel` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `SplineEntity` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`SplineEntity` has 17 INFERRED edges - model-reasoned connections that need verification._
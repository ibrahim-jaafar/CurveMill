# Graph Report - DXF-CNC-Optimizer  (2026-07-28)

## Corpus Check
- 43 files · ~58,991 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1018 nodes · 3317 edges · 55 communities (42 shown, 13 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 253 edges (avg confidence: 0.55)
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
- Tool
- test_pick_tool.py
- models.py
- ._build_ui
- ImportResult
- .is_position
- test_pick_tool.py
- build_toolpaths
- ._evaluate_nurbs
- test_tools.py
- render_to_png
- _scaled_bounds
- count_profile_issues
- ._add_tool
- .geometry_count_by_layer
- _build_chains
- test_vcarve.py
- ._add_tool
- .layer_of_ids
- .to_svg_path

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 256 edges
2. `VectorEntity` - 198 edges
3. `EditorModel` - 111 edges
4. `SplineEntity` - 98 edges
5. `BoardView` - 87 edges
6. `_app()` - 46 edges
7. `Tool` - 45 edges
8. `Layer` - 43 edges
9. `ProcessOptions` - 43 edges
10. `Dimension` - 42 edges

## Surprising Connections (you probably didn't know these)
- `Potrace v2 Raster Import Plan (PNG/JPEG to Vectors)` --conceptually_related_to--> `Potrace --tight Output Placement Mode`  [INFERRED]
  README.md → tools/potrace-1.16.win64/placement.pdf
- `test_depth_for_width_inverts_effective_diameter()` --calls--> `Tool`  [EXTRACTED]
  tests/test_vcarve.py → curvemill/models.py
- `test_spline_flatten_cache_invalidates_on_edit()` --calls--> `SplineEntity`  [EXTRACTED]
  tests/test_editor.py → curvemill/models.py
- `Fit-Point SPLINE Export for SolidWorks Element Count Parity` --conceptually_related_to--> `Fit-Point SPLINE = 1 Sketch Element Rule`  [INFERRED]
  README.md → docs/solidworks-dxf-import.md
- `test_layer_depths_survive_a_project_round_trip()` --calls--> `MainWindow`  [EXTRACTED]
  tests/test_layer_depth.py → curvemill/app.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Optimize for SolidWorks End-to-End Pipeline** — readme_optimize_for_solidworks_feature, docs_solidworks_dxf_import_fit_point_rule, readme_fit_point_spline_export, docs_solidworks_dxf_import_path545 [INFERRED 0.85]
- **SolidWorks DXF Element Counting Rules** — docs_solidworks_dxf_import_fit_point_rule, docs_solidworks_dxf_import_control_point_split, docs_solidworks_dxf_import_exact_g1_threshold [EXTRACTED 1.00]
- **SolidWorks COM Early Binding and Performance Pattern** — docs_solidworks_com_api_early_binding, docs_solidworks_com_api_cast_function, docs_solidworks_com_api_six_flag_recipe [INFERRED 0.85]

## Communities (55 total, 13 thin omitted)

### Community 1 - "Canvas View & Dimensions"
Cohesion: 0.18
Nodes (12): _next_group_id(), Append imported DXF files as new, independently named layers., Layer, _app(), V-Carve: width<->depth inversion, iso-depth bands, hazards, and UI gating., test_depth_for_width_inverts_effective_diameter(), test_laser_mode_shows_only_the_laser_tool(), test_layers_carry_independent_recipes_and_survive_a_round_trip() (+4 more)

### Community 2 - "Geometry & Toolpath Engine"
Cohesion: 0.12
Nodes (51): MainWindow, Dimension, Feature, QMainWindow, _app(), _square(), test_align_keeps_the_moved_selection_on_screen(), test_balloon_drag_defers_arrow_and_scene_extent_updates_until_drop() (+43 more)

### Community 3 - "Smart Dimensions"
Cohesion: 0.15
Nodes (14): _constrain_move_delta(), _distance_to_segment_qt(), _free_lasso_path(), _lasso_screen_span(), _opposite_corner(), _point_distance(), _preserve_resize_aspect(), _scale_corner_at() (+6 more)

### Community 5 - "Editor Model Selection"
Cohesion: 0.11
Nodes (27): _nearest_selected_vertex(), EditorModel, Count entities (vectors + native splines) on each layer for the layer list., test_active_layer_selection_and_all_visible_selection(), test_all_spline_file_reports_geometry_and_counts_per_layer(), test_all_spline_selection_reports_bounds_and_frames(), test_append_layers_preserves_existing_vectors_and_uses_unique_names(), test_apply_selected_layout_ignores_hidden_selected_vectors() (+19 more)

### Community 6 - "SolidWorks COM Bridge"
Cohesion: 0.10
Nodes (5): Export whatever is on the canvas -- optimized splines, corrected         geomet, Show only the tools that fit the current cut mode.          V-Carve drops flat, Field visibility, labels and settings for the current tool — no writes., Rebuild the read-only layer panel; reload the form only on a new pick., One job per cutting layer, each with its own tool/mode/depth.

### Community 7 - "Spline Fit & Cloning"
Cohesion: 0.13
Nodes (4): _double(), QAction, QDoubleSpinBox, QWidget

### Community 8 - "Raster Autotrace (Potrace)"
Cohesion: 0.08
Nodes (46): Cubic, _dist_sq(), _find_potrace(), _line_to_cubic(), _parse_svg_paths(), _png_to_pbm(), Point, ProgressCallback (+38 more)

### Community 9 - "SolidWorks Spike Script"
Cohesion: 0.36
Nodes (9): join_spline_fragments(), Merge single-bezier SPLINE fragments into one native spline per shape.      Inks, _bezier(), Tests for joining Inkscape's fragmented bezier SPLINEs back into whole shapes., The whole point: joining must not move the curve., test_closed_shape_is_flagged_closed_and_shapes_stay_separate(), test_join_is_lossless(), test_joins_fragments_into_one_spline_per_shape() (+1 more)

### Community 10 - "test_tabs.py"
Cohesion: 0.10
Nodes (41): _arc_points(), _circle_points(), _curve_steps(), _doc_units(), _entity_to_vectors(), export_process_result(), export_vectors(), import_dxf() (+33 more)

### Community 12 - "Worker"
Cohesion: 0.16
Nodes (11): _chaikin_points(), _distance(), _distance_to_polyline(), _distance_to_segment(), _point_in_polygon(), Point, Write repaired vectors and natively repaired splines back as one undo step., _smooth_vector() (+3 more)

### Community 13 - "BoardView"
Cohesion: 0.20
Nodes (4): _arrow_path(), _closest_rect_edge_point(), _path_midpoint(), QRectF

### Community 15 - "SolidWorks Export Rules Docs"
Cohesion: 0.17
Nodes (13): Fit-Point Count Rule Verified on Sketch API Path, Control-Point SPLINE Splits at G1 Tangent Breaks, Exact G1 Tangent Threshold Is Not a Tolerance, Fit-Point SPLINE = 1 Sketch Element Rule, path545.dxf Optimization Result (3383 to 540 Elements), Probe-Based Black-Box Reverse Engineering Methodology, DXF CNC Optimizer Application, Fit-Point SPLINE Export for SolidWorks Element Count Parity (+5 more)

### Community 16 - "PNG Rasterizer"
Cohesion: 0.15
Nodes (3): Path, Write the full session to path in the .curvemill format (save + autosave)., If an autosave survived (previous session crashed), offer to reopen it.

### Community 17 - "Tab UI Tests"
Cohesion: 0.13
Nodes (34): Axis, Bounds, board_features(), edge_segment(), feature_coord(), feature_point(), is_edge(), is_overconstrained() (+26 more)

### Community 18 - "Spike Preview Image"
Cohesion: 0.60
Nodes (5): sw_spike_preview.png (SolidWorks test picture), InsertSketchPicture (SolidWorks API method), SolidWorks Live Preview Groundwork, SolidWorks API Spike, Test Visual Content (F letter, red square, blue circle)

### Community 19 - "COM Early Binding Docs"
Cohesion: 0.67
Nodes (3): cast() COM Typed Wrapper Function, SolidWorks COM Early Binding Requirement, Six-Flag Bulk Sketch Insertion Recipe (50x Speedup)

### Community 22 - ".visible_layer_names"
Cohesion: 0.34
Nodes (9): _add_geometry(), _fit_content_icon(), _preview_vector_path(), _view_vectors_icon(), QColor, QIcon, QPainter, QPainterPath (+1 more)

### Community 23 - "SVG Path Export"
Cohesion: 0.17
Nodes (5): _cosmetic_pen(), _selected_vector_pen(), _vector_path(), _vector_pen(), PenStyle

### Community 25 - "Package Root"
Cohesion: 0.23
Nodes (4): _effective_units(), Exception, Import the COM bridge lazily so the editor runs without SolidWorks., Cutting layers that carry geometry, in feature-order (editor order).

### Community 26 - "QRectF"
Cohesion: 0.11
Nodes (11): Append imported vectors and splines as a new layer., Point, A native NURBS/parametric spline curve preserved from DXF import., Approximate this spline as a polyline of straight segments.          Cached: re-, Evaluate bezier curve using De Casteljau's algorithm (for cubic bezier subsets)., Simple De Casteljau evaluation for bezier-style splines., Produce an SVG path d-string including bezier curves where possible., SplineEntity (+3 more)

### Community 27 - "._set_progress"
Cohesion: 0.13
Nodes (5): Return flattened vectors (includes spline approximations for display/processing), Combined bounds of all visible geometry without flattening splines.          Use, True when any visible layer holds a vector or a native spline.          Splines, Delete visible entities that trace the same path as an earlier one.          Mat, Delete visible junk entities whose whole extent fits inside the tolerance.

### Community 28 - "combined_bounds"
Cohesion: 0.29
Nodes (4): A SolidWorks-style board-relative dimension on the Y-up DXF canvas.      Draws, Hit-test for right-click/select: label, flip glyph, or the dim line., SmartDimItem, QGraphicsItem

### Community 29 - "Layer"
Cohesion: 0.19
Nodes (14): load(), _points(), Path, The .curvemill project file: a paused session, resumed later.  DXF export alone, save(), _app(), A .curvemill project reopens the session exactly as it was saved., Dragging a subset separates endpoints, so the count must recompute.      Otherwi (+6 more)

### Community 30 - "._active_dims"
Cohesion: 0.20
Nodes (11): _basis_functions(), _default_knots(), _find_span(), Evaluate a NURBS curve at parameter t using Cox-deBoor formula., Generate clamped knot vector for a bezier-like NURBS curve., Find the knot span index for parameter u (Cox-deBoor)., Compute non-vanishing basis functions at parameter u., ToolKind (+3 more)

### Community 31 - "render_to_png"
Cohesion: 0.22
Nodes (3): _feature_text(), Dims to draw/list: every stored dim whose pattern lives on the layer         cu, QListWidgetItem

### Community 34 - "test_text_and_per_layer_send.py"
Cohesion: 0.36
Nodes (10): Glyph outlines -> closed vectors, scaled so the text is `height_mm` tall., _text_to_vectors(), QFont, _app(), Text-to-curves insertion and per-layer Send to SolidWorks., test_inserted_text_lands_on_the_active_layer(), test_per_layer_dialog_prefills_through_all_past_thickness_and_skips(), test_sw_send_layers_lists_only_cutting_layers_with_geometry() (+2 more)

### Community 35 - "Tool"
Cohesion: 0.27
Nodes (12): assemble_closed_profiles(), _build_chains(), _chain_is_closed(), _dist(), _fit_self_crosses(), _match_chain(), _open_chains(), Point (+4 more)

### Community 36 - "test_pick_tool.py"
Cohesion: 0.13
Nodes (3): Swap the canvas for the tool-corrected (as-milled) outlines from the         la, Swap the active layer's fragments for one native spline per shape.          In, QTreeWidgetItem

### Community 37 - "models.py"
Cohesion: 0.10
Nodes (31): _demo_scaled_bounds(), main(), PerLayerSendDialog, _polygons(), Read-only Simulation-tab view sharing the editor's scene.      The processed b, Bounds after _scale_transform(origin, sx, sy), normalized (min/max)., Feature picker for Send to SolidWorks -- mirrors SW's own extrude UI., (feature kind, end condition, depth in meters, flip). (+23 more)

### Community 38 - "._build_ui"
Cohesion: 0.08
Nodes (52): Curve, _depth_shade(), Cut-floor colour: the surface tone darkened in proportion to depth., BridgeError, cast(), _connect(), curves_from_entities(), _delete_preview_sketch() (+44 more)

### Community 39 - "ImportResult"
Cohesion: 0.18
Nodes (16): Combined bounds of the vectors/splines with these ids, ignoring selection., entries(), library_dir(), load_pattern(), Path, The pattern library: clipart, not projects.  An entry is a piece of artwork — ge, _render(), save_pattern() (+8 more)

### Community 40 - ".is_position"
Cohesion: 0.17
Nodes (3): _scale_transform(), QGraphicsScene, QTransform

### Community 41 - "test_pick_tool.py"
Cohesion: 0.42
Nodes (9): _app(), _click(), The Select tool picks exactly one vector per click., test_drag_inside_selection_moves_outside_starts_box(), test_escape_clears_selection(), test_free_lasso_moves_inside_selection_lassos_outside(), test_move_tool_keeps_spline_multi_selection(), test_pick_tool_selects_single_vector() (+1 more)

### Community 42 - "build_toolpaths"
Cohesion: 0.15
Nodes (26): _add_path_warning(), count_open_profiles(), process_vectors(), repair_vectors(), ProcessOptions, Produce an SVG path d-string from the polyline points., VectorEntity, test_export_process_result_reopens() (+18 more)

### Community 43 - "._evaluate_nurbs"
Cohesion: 0.22
Nodes (8): _canonical_path(), count_profile_issues(), duplicate_vector_indices(), Count open profiles, duplicate entities and over-used vertices.      A duplicate, Indices of entities tracing the same path as an earlier one.      Shared by the, Return a path identity that ignores direction, and start vertex when closed., Duplicates must not mask open profiles or inflate multi-vertex counts., test_open_profile_not_masked_by_duplicates()

### Community 44 - "test_tools.py"
Cohesion: 0.14
Nodes (14): Cutting width at the given depth below the surface., A V-carve varies Z to change the cut width; flat mills and lasers can't., Depth at which this tool cuts the given width -- inverse of         effective_di, Tool, _app(), Tool math, the Simulation tab's per-kind fields, and the Library tool table., _select_kind(), test_add_new_tool_button_and_notes_column() (+6 more)

### Community 45 - "render_to_png"
Cohesion: 0.52
Nodes (6): ProgressCallback, Render DXF vectors and splines to a PNG image for auto-tracing., Render all geometry to a PNG image in memory.      Args:         vectors: Lis, render_to_png(), _report(), _report_loop()

### Community 46 - "_scaled_bounds"
Cohesion: 0.33
Nodes (3): Selected, currently-visible vector and spline ids (groups expanded)., Resize the visible selection to ``width`` x ``height`` and move its         ``pa, Clear the group id from every selected vector and spline. Returns         ``True

### Community 47 - "count_profile_issues"
Cohesion: 0.14
Nodes (25): fit_vector_chains(), Rebuild loose LINE segments into one native spline per smooth run.      Pattern, Convert control-point splines to fit-point splines for SolidWorks export.      S, A two-point run is a straight line; express it as an exact cubic., _straight_cubic(), to_fit_splines(), Tests for rebuilding loose LINE soup into native splines., SolidWorks counts a fit-point spline as ONE element; the samples we hand     it (+17 more)

### Community 48 - "._add_tool"
Cohesion: 0.40
Nodes (5): _bezier_chains(), _Chain, A list of bezier control-point tuples that remembers its source layer., Walk single-bezier fragments into end-to-end chains, in geometric order.      En, list

### Community 50 - "_build_chains"
Cohesion: 0.18
Nodes (24): _as_polygons(), build_toolpaths(), flatten_splines(), geometry_from_wkt(), _geometry_to_vectors(), _nest_profiles(), process_layers(), ProgressCallback (+16 more)

### Community 51 - "test_vcarve.py"
Cohesion: 0.20
Nodes (14): _buffer_toolpaths(), count_self_intersections(), heal_self_intersections(), _profile_ring(), Assembled closed profiles whose outline crosses itself.      SolidWorks rejects, Sub-loops of a self-crossing outline, split exactly at the crossing point(s)., Replace self-crossing closed profiles with sub-loops split at the crossing., _ring_to_vector() (+6 more)

## Knowledge Gaps
- **14 isolated node(s):** `curvemill`, `graphify`, `CNC Endmill Milling Simulation`, `cast() COM Typed Wrapper Function`, `Six-Flag Bulk Sketch Insertion Recipe (50x Speedup)` (+9 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `Geometry & Toolpath Engine` to `Canvas View & Dimensions`, `App Entry & SW Dialog`, `Editor Model Selection`, `SolidWorks COM Bridge`, `Spline Fit & Cloning`, `test_tabs.py`, `Edit Undo & Transforms`, `PNG Rasterizer`, `Tab UI Tests`, `Package Root`, `QRectF`, `Layer`, `._active_dims`, `render_to_png`, `test_text_and_per_layer_send.py`, `test_pick_tool.py`, `models.py`, `._build_ui`, `ImportResult`, `.is_position`, `test_pick_tool.py`, `build_toolpaths`, `._evaluate_nurbs`, `test_tools.py`?**
  _High betweenness centrality (0.304) - this node is a cross-community bridge._
- **Why does `VectorEntity` connect `build_toolpaths` to `Main Window UI Handlers`, `Canvas View & Dimensions`, `Geometry & Toolpath Engine`, `App Entry & SW Dialog`, `Editor Model Selection`, `test_tabs.py`, `Editor Geometry Helpers`, `Worker`, `BoardView`, `.visible_layer_names`, `SVG Path Export`, `QRectF`, `._set_progress`, `combined_bounds`, `Layer`, `._active_dims`, `._update_warning_arrow`, `test_text_and_per_layer_send.py`, `Tool`, `models.py`, `._build_ui`, `ImportResult`, `test_pick_tool.py`, `._evaluate_nurbs`, `render_to_png`, `count_profile_issues`, `._add_tool`, `_build_chains`, `test_vcarve.py`?**
  _High betweenness centrality (0.214) - this node is a cross-community bridge._
- **Why does `SplineEntity` connect `QRectF` to `Main Window UI Handlers`, `Canvas View & Dimensions`, `Geometry & Toolpath Engine`, `Editor Model Selection`, `Raster Autotrace (Potrace)`, `SolidWorks Spike Script`, `test_tabs.py`, `Editor Geometry Helpers`, `Worker`, `._set_progress`, `combined_bounds`, `Layer`, `._active_dims`, `Tool`, `models.py`, `._build_ui`, `ImportResult`, `test_pick_tool.py`, `._evaluate_nurbs`, `render_to_png`, `count_profile_issues`, `._add_tool`, `_build_chains`?**
  _High betweenness centrality (0.164) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `MainWindow` (e.g. with `Dimension` and `Feature`) actually correct?**
  _`MainWindow` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `VectorEntity` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`VectorEntity` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `EditorModel` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`EditorModel` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `SplineEntity` (e.g. with `BoardView` and `MainWindow`) actually correct?**
  _`SplineEntity` has 18 INFERRED edges - model-reasoned connections that need verification._
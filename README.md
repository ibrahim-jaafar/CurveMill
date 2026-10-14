# CurveMill

A local desktop tool for loading 2D DXF files, editing imported vectors, previewing how a round CNC endmill cuts a wood board, and exporting an approved corrected DXF.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### Potrace (optional, not used by v1)

"Optimize for SolidWorks" works purely on the vector geometry and needs no external tools.
[Potrace](https://potrace.sourceforge.net/) is kept for the planned v2 raster import (PNG/JPEG
â†’ traced vectors). To enable it then, extract `potrace-1.16.win64.zip` into this project's
`tools\` folder (so the exe sits at `tools\potrace-1.16.win64\potrace.exe`), or install it
anywhere on `PATH` or in `C:\Program Files\potrace\`.

## Run

```powershell
.\.venv\Scripts\python.exe -m curvemill
```

## What v1 supports

- Imports one or multiple DXF files in one operation, placing each file on its own uniquely named layer.
- Supports `LINE`, `ARC`, `CIRCLE`, `LWPOLYLINE`, `POLYLINE`, and native `SPLINE` DXF entities.
- Preserves splines as real NURBS curves through import and export (deriving control points for fit-point-only splines, and keeping their knot vectors) to keep element counts low for downstream CAD tools.
- Treats native splines as first-class geometry throughout the editor: layer counts, selection (box lasso and free lasso), zoom-to-content framing, the selection layout panel, and Process/Repair/Export all work on spline-only files (such as Inkscape exports) even when they contain zero plain vectors. Splines are flattened only on disposable copies to feed the milling simulation, so the exported curves stay native NURBS.
- Skips zero-length and degenerate entities on import (such as the node-marker `LINE`s some editors emit at spline endpoints) so they are not miscounted as open profiles.
- Selects vectors on the active layer with `Lasso (L)` by clicking or dragging a rectangular selection box.
- Switches to `Move (M)`, deletes with `Delete (DEL)`, and smooths with `Smooth Vectors (S)`.
- Organizes edits in ordered layers that can be added, renamed, cloned, hidden, shown, and deleted.
- Consolidates each imported DXF into one initial layer named after the file.
- Uses `Ctrl+A` for the active visible layer and `Ctrl+Shift+A` for all visible layers.
- Supports `Ctrl+C`, `Ctrl+X`, and `Ctrl+V`; pasted vectors are centered under the mouse and placed on the active layer.
- Excludes hidden layers from selection, repair, open-profile counts, CNC processing, preview bounds, and corrected export.
- Presents Layers, Selection Layout, and Warnings & Log as separate docks that can each be resized, moved, floated, or closed, and reopened from the View menu.
- Tabs a Log beside the Warnings list, timestamping every action, warning, and error. The log is read-only but selectable, so text can be copied with `Ctrl+C`, the right-click menu, or the Copy Selected button (which copies the whole log when nothing is selected).
- Lists processing warnings in a clickable dock and shows path-linked warnings as draggable canvas balloons.
- Magnifies the failed path with nearby vectors for context, highlights the source path, and draws an arrow to it.
- Supports multiple non-overlapping warning balloons and clears them together with the Clear Balloons button.
- Keeps warning balloons readable at a fixed screen size while zooming, with a larger path preview and guarded bulk selection that prevents thousands of balloons from freezing the UI.
- Deletes, groups, ungroups, moves, scales, and vertex-edits imported vectors.
- Smooths selected vectors, or all vectors when nothing is selected, with the Smooth Vectors toolbar action.
- Moves the active selection with the Move Tool by dragging anywhere on the board.
- Scales the active selection proportionally by default; hold Shift while dragging a corner handle for free horizontal and vertical scaling.
- Hides or shows the vector overlay from an icon control on the canvas and provides a canvas Zoom to Content control.
- Displays DXF geometry in native CAD orientation with positive Y upward, without changing model or export coordinates.
- Draws removed material as the background color so processed cut-through areas are easy to inspect.
- Repairs endpoint gaps within a user tolerance, for plain vectors and for native splines alike.
- Repairs open splines natively: because a clamped NURBS begins at its first control point and ends at its last, Repair snaps those end control points to close the gap. Degree, knot vector and interior control points are untouched, so a repaired curve is still a real spline on export and element counts stay low.
- Counts open profiles on the same geometry Process consumes (splines included), so the reported count always matches the open-path warnings Process produces.
- Overlays the sketch fault counts on the top-left of the canvas, highlighting any that are non-zero: open profiles, duplicates (entities retracing an earlier path, ignoring direction and start vertex), and multiple vertex usage (points where three or more entity ends meet). These are the faults SolidWorks' Check Sketch for Feature rejects, surfaced before the DXF is exported.
- Repairs gaps only when the Repair Vectors button is clicked.
- Joins repaired connected open segments into closed profiles for inside/outside tracing.
- Simulates center, inside, and outside endmill tracing.
- Hides cut islands disconnected from the board boundary by removing them from the processed preview.
- Exports the approved edited/corrected DXF.
- Optimizes for SolidWorks: joins fragmented spline segments and chains loose LINE soup into whole native curves (losslessly â€” no decimation), then exports each curve as a fit-point SPLINE. SolidWorks refits those and counts **one sketch element per curve**, so the entity count shown in the app is the count SolidWorks reports on Select All. Measured: `path545.dxf` 3383 â†’ 540, a 7014-LINE pattern â†’ 274. See [docs/solidworks-dxf-import.md](docs/solidworks-dxf-import.md) for the probe-measured import rules behind this.

from __future__ import annotations

import os
from math import ceil, cos, pi, radians, sin, tau
from pathlib import Path
from typing import Iterable

os.environ.setdefault("XDG_CACHE_HOME", str(Path.cwd() / ".cache"))

import ezdxf

from .geometry import result_export_vectors
from .models import ImportResult, Point, ProcessResult, SplineEntity, VectorEntity
from .progress import ProgressCallback, report as _report, report_loop as _report_loop

UNIT_CODES = {
    0: "unitless",
    1: "in",
    2: "ft",
    4: "mm",
    5: "cm",
    6: "m",
}

UNIT_TO_MM = {
    "unitless": 1.0,
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
    "ft": 304.8,
}


def import_dxf(
    path: str | Path,
    units_override: str = "dxf",
    curve_tolerance: float = 0.2,
    progress: ProgressCallback | None = None,
) -> ImportResult:
    _report(progress, 2, "Reading DXF file")
    doc = ezdxf.readfile(path)
    _report(progress, 12, "Reading DXF units")
    source_units = _doc_units(doc)
    target_units = source_units if units_override == "dxf" else units_override
    target_units = "mm" if target_units == "unitless" else target_units
    scale = _unit_scale(source_units, target_units)
    warnings: list[str] = []
    vectors: list[VectorEntity] = []
    splines: list[SplineEntity] = []
    degenerate_count = 0
    entities = list(doc.modelspace())
    for entity_index, entity in enumerate(entities):
        imported_vectors, imported_splines = _entity_to_vectors(entity, curve_tolerance, warnings)
        for vector in imported_vectors:
            vector.points = [(x * scale, y * scale) for x, y in vector.points]
            if _is_degenerate_vector(vector):
                # Editors such as Inkscape emit zero-length LINEs (start == end)
                # as node markers. Kept as vectors they masquerade as open
                # profiles and spawn empty warning balloons, so drop them here.
                degenerate_count += 1
                continue
            vectors.append(vector)
        for spline in imported_splines:
            spline.control_points = [(x * scale, y * scale) for x, y in spline.control_points]
            spline.fit_points = [(x * scale, y * scale) for x, y in spline.fit_points]
            if _is_degenerate_spline(spline):
                # Same node-marker cleanup as vectors: a spline whose every point
                # sits at one spot has no real curve and would just draw a dot.
                degenerate_count += 1
                continue
            splines.append(spline)
        _report_loop(progress, 12, 96, entity_index + 1, len(entities), "Importing DXF entities")
    if degenerate_count:
        noun = "shape" if degenerate_count == 1 else "shapes"
        warnings.append(f"Skipped {degenerate_count} tiny {noun} that have no real size.")
    _report(progress, 100, "DXF loaded")
    return ImportResult(vectors=vectors, splines=splines, units=target_units, warnings=warnings)


def export_vectors(
    path: str | Path,
    vectors: Iterable[VectorEntity],
    splines: Iterable[SplineEntity] | None = None,
    units: str = "mm",
    dxf_format: str = "R2000",
    progress: ProgressCallback | None = None,
) -> None:
    """Write vectors and splines to a DXF file.

    Defaults to ``R2000`` (AC1015), the successor to the R14 format that keeps
    element counts low for downstream CAD tools by writing splines as native
    ``SPLINE`` entities instead of flattening them into many short segments.
    """
    _report(progress, 2, "Creating DXF document")
    doc = ezdxf.new(dxf_format)
    doc.header["$INSUNITS"] = _units_code(units)
    msp = doc.modelspace()
    vector_list = list(vectors)
    for vector_index, vector in enumerate(vector_list):
        _report_loop(progress, 10, 50, vector_index + 1, len(vector_list), "Writing DXF vectors")
        if len(vector.points) < 2:
            continue
        layer = vector.layer or "0"
        if layer not in doc.layers:
            doc.layers.add(layer)
        msp.add_lwpolyline(vector.points, close=vector.closed, dxfattribs={"layer": layer})

    spline_list = list(splines) if splines is not None else []
    for spline_index, spline in enumerate(spline_list):
        _report_loop(progress, 55, 90, spline_index + 1, len(spline_list), "Writing DXF splines")
        layer = spline.layer or "0"
        if layer not in doc.layers:
            doc.layers.add(layer)
        dxfattribs = {"layer": layer}
        if spline.control_points:
            # Preserve the native NURBS geometry via control points + knots.
            degree = min(spline.degree, len(spline.control_points) - 1)
            knots = spline.knots if spline.knots else None
            try:
                entity = msp.add_open_spline(
                    spline.control_points,
                    degree=degree,
                    knots=knots,
                    dxfattribs=dxfattribs,
                )
            except Exception:
                # Fall back to ezdxf-computed uniform knots if the stored
                # knot vector does not match this control-point count.
                entity = msp.add_open_spline(
                    spline.control_points,
                    degree=degree,
                    dxfattribs=dxfattribs,
                )
            if spline.closed:
                entity.closed = True
        elif spline.fit_points:
            msp.add_spline(
                spline.fit_points,
                degree=spline.degree,
                dxfattribs=dxfattribs,
            )

    _report(progress, 92, "Saving DXF file")
    doc.saveas(path)
    _report(progress, 100, "Export complete")


def export_process_result(
    path: str | Path,
    result: ProcessResult,
    units: str = "mm",
    dxf_format: str = "R2000",
    progress: ProgressCallback | None = None,
) -> None:
    _report(progress, 2, "Converting corrected geometry")
    vectors = result_export_vectors(result)
    export_vectors(
        path,
        vectors,
        units=units,
        dxf_format=dxf_format,
        progress=lambda value, message: _report(progress, 10 + int(value * 0.90), message),
    )


def _entity_to_vectors(entity, curve_tolerance: float, warnings: list[str]) -> tuple[list[VectorEntity], list[SplineEntity]]:
    entity_type = entity.dxftype()
    layer = getattr(entity.dxf, "layer", "0")
    try:
        if entity_type == "LINE":
            return ([VectorEntity(points=[_xy(entity.dxf.start), _xy(entity.dxf.end)], layer=layer, source_type=entity_type)], [])
        if entity_type == "ARC":
            return ([VectorEntity(points=_arc_points(entity.dxf.center, entity.dxf.radius, entity.dxf.start_angle, entity.dxf.end_angle, curve_tolerance), layer=layer, source_type=entity_type)], [])
        if entity_type == "CIRCLE":
            return ([VectorEntity(points=_circle_points(entity.dxf.center, entity.dxf.radius, curve_tolerance), closed=True, layer=layer, source_type=entity_type)], [])
        if entity_type == "LWPOLYLINE":
            return (_lwpolyline_vectors(entity, curve_tolerance, layer), [])
        if entity_type == "POLYLINE":
            points = [_xy(vertex.dxf.location) for vertex in entity.vertices]
            if len(points) >= 2:
                return ([VectorEntity(points=points, closed=bool(entity.is_closed), layer=layer, source_type=entity_type)], [])
            return ([], [])
        if entity_type == "SPLINE":
            spline = _spline_from_entity(entity, layer)
            if spline is not None:
                return ([], [spline])
            return ([], [])
    except Exception:  # noqa: BLE001 - DXF files in the wild are often partially malformed.
        warnings.append(f"Couldn't read a {entity_type} shape on layer '{layer}', so it was skipped.")
        return ([], [])
    warnings.append(f"Skipped an unsupported {entity_type} shape on layer '{layer}'.")
    return ([], [])


def _spline_from_entity(entity, layer: str) -> SplineEntity | None:
    """Read a DXF SPLINE entity as a native SplineEntity without flattening."""
    try:
        control_pts = [_xy(p) for p in entity.control_points]
        fit_pts = [_xy(p) for p in entity.fit_points] if hasattr(entity, 'fit_points') and entity.fit_points else []
        # ezdxf exposes the knot vector as ``entity.knots`` (an array); older code
        # looked for ``knot_values``, which never existed, so knots were dropped.
        raw_knots = getattr(entity, 'knots', None)
        knots = list(raw_knots) if raw_knots is not None and len(raw_knots) else None
        degree = int(entity.dxf.degree) if hasattr(entity.dxf, 'degree') else 3
        if not control_pts:
            # Fit-point-only spline: derive control points (and knots) so the
            # curve is preserved as a real spline instead of being dropped.
            if not fit_pts:
                return None
            curve = entity.construction_tool()
            control_pts = [_xy(p) for p in curve.control_points]
            knots = list(curve.knots()) if hasattr(curve, "knots") else knots
            degree = int(curve.degree)
            if not control_pts:
                return None
        closed = bool(entity.closed) if hasattr(entity, 'closed') else False
        periodic = bool(entity.dxf.flags & 1) if hasattr(entity.dxf, 'flags') else False
        return SplineEntity(
            control_points=control_pts,
            fit_points=fit_pts,
            degree=degree,
            knots=knots,
            closed=closed,
            periodic=periodic,
            layer=layer,
        )
    except Exception:
        return None


def _lwpolyline_vectors(entity, curve_tolerance: float, layer: str) -> list[VectorEntity]:
    if entity.has_arc:
        vectors: list[VectorEntity] = []
        points: list[Point] = []
        for virtual in entity.virtual_entities():
            part, _ = _entity_to_vectors(virtual, curve_tolerance, [])
            if not part:
                continue
            segment = part[0].points
            if not points:
                points.extend(segment)
            else:
                points.extend(segment[1:] if points[-1] == segment[0] else segment)
        if len(points) >= 2:
            return [VectorEntity(points=points, closed=bool(entity.closed), layer=layer, source_type="LWPOLYLINE")]
        return vectors
    points = [(float(p[0]), float(p[1])) for p in entity.get_points("xy")]
    return [VectorEntity(points=points, closed=bool(entity.closed), layer=layer, source_type="LWPOLYLINE")] if len(points) >= 2 else []


def _arc_points(center, radius: float, start_angle: float, end_angle: float, tolerance: float) -> list[Point]:
    start = radians(start_angle)
    end = radians(end_angle)
    if end <= start:
        # <=, not <: some tools store a full 360 deg circle as an ARC with equal
        # start/end angles. With '<' that became a 0.001 rad sliver (the shape
        # vanished); a wrap turns it back into the full circle it represents.
        end += tau
    span = max(end - start, 0.001)
    steps = _curve_steps(radius, span, tolerance)
    cx, cy = _xy(center)
    return [(cx + radius * cos(start + span * i / steps), cy + radius * sin(start + span * i / steps)) for i in range(steps + 1)]


def _circle_points(center, radius: float, tolerance: float) -> list[Point]:
    steps = _curve_steps(radius, tau, tolerance)
    cx, cy = _xy(center)
    return [(cx + radius * cos(tau * i / steps), cy + radius * sin(tau * i / steps)) for i in range(steps)]


def _curve_steps(radius: float, span: float, tolerance: float) -> int:
    if radius <= 0:
        return 8
    tolerance = max(tolerance, 0.01)
    full_steps = max(16, int(ceil(pi / max(0.01, (2 * tolerance / radius) ** 0.5))))
    return max(4, int(ceil(full_steps * span / tau)))


def _is_degenerate_vector(vector: VectorEntity, tolerance: float = 1e-4) -> bool:
    """True when a vector has no real extent (a point or coincident endpoints).

    Such entities carry two or more points, so they pass ``is_valid`` and would
    otherwise be counted as open profiles and drawn as empty warning balloons.
    The default tolerance is sub-micron: it only ever collapses entities whose
    every vertex sits at effectively the same coordinate, so real geometry (where
    at least one vertex is farther out) is never flagged.
    """
    points = vector.points
    if len(points) < 2:
        return True
    x0, y0 = points[0]
    for x, y in points[1:]:
        if abs(x - x0) > tolerance or abs(y - y0) > tolerance:
            return False
    return True


def _is_degenerate_spline(spline: SplineEntity, tolerance: float = 1e-4) -> bool:
    """True when a spline's every defining point sits at effectively one spot.

    Mirrors _is_degenerate_vector: sub-micron tolerance, so only a genuine
    point-marker collapses -- any spline with real extent keeps at least one
    point farther out and is never flagged.
    """
    points = spline.control_points or spline.fit_points
    if len(points) < 2:
        return True
    x0, y0 = points[0]
    for x, y in points[1:]:
        if abs(x - x0) > tolerance or abs(y - y0) > tolerance:
            return False
    return True


def _xy(point) -> Point:
    return float(point[0]), float(point[1])


def _doc_units(doc) -> str:
    return UNIT_CODES.get(int(doc.header.get("$INSUNITS", 0)), "unitless")


def _unit_scale(source: str, target: str) -> float:
    source_mm = UNIT_TO_MM.get(source, 1.0)
    target_mm = UNIT_TO_MM.get(target, 1.0)
    return source_mm / target_mm


def _units_code(units: str) -> int:
    for code, label in UNIT_CODES.items():
        if label == units:
            return code
    return 4



from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from itertools import count
from math import hypot, radians, sqrt, tan
from typing import Iterable

Point = tuple[float, float]

_id_counter = count(1)


def sync_id_counter(*entity_lists: "Iterable") -> None:
    """Advance the shared entity-id counter past every id in ``entity_lists``.

    Ids restored from a saved project keep their original values, but the counter
    restarts at 1 each process, so without this the next paste/draw/insert
    re-mints an already-used id and two entities collide (breaking selection,
    grouping and dim_store keys). Mirrors EditorModel's group-id sync on load.
    """
    global _id_counter
    nxt = next(_id_counter)  # peek+consume; the skipped value is a harmless gap
    highest = max((e.id for entities in entity_lists for e in entities), default=0)
    _id_counter = count(max(nxt, highest + 1))


class TraceMode(str, Enum):
    CENTER = "center"
    INSIDE = "inside"
    OUTSIDE = "outside"


class ToolKind(str, Enum):
    FLAT = "flat"
    BALL = "ball"
    V_BIT = "v_bit"
    TAPERED = "tapered"
    LASER = "laser"


@dataclass(slots=True)
class Tool:
    name: str
    kind: ToolKind = ToolKind.FLAT
    diameter: float = 6.0  # widest cutting diameter; for lasers this is the kerf
    taper_angle_deg: float = 0.0  # per-side angle (v_bit/tapered)
    tip_diameter: float = 0.0
    notes: str = ""  # free text: which machine, stock, feeds -- library reference only

    def effective_diameter(self, depth: float) -> float:
        """Cutting width at the given depth below the surface."""
        depth = max(depth, 0.0)
        if self.kind in (ToolKind.V_BIT, ToolKind.TAPERED):
            width = self.tip_diameter + 2.0 * depth * tan(radians(self.taper_angle_deg))
            return min(width, self.diameter)
        if self.kind is ToolKind.BALL:
            if depth >= self.diameter / 2.0:
                return self.diameter
            # Chord width of the sphere at the cutting depth.
            return 2.0 * sqrt(depth * (self.diameter - depth))
        # Flat end mills and lasers cut the same width at any depth.
        return self.diameter

    @property
    def can_vcarve(self) -> bool:
        """A V-carve varies Z to change the cut width; flat mills and lasers can't."""
        return self.kind not in (ToolKind.FLAT, ToolKind.LASER)

    def depth_for_width(self, width: float) -> float:
        """Depth at which this tool cuts the given width -- inverse of
        effective_diameter. V-carve preview reads it: a point `width/2` from the
        edge opens to `width`, so the bit must plunge to this depth there.
        """
        width = max(width, 0.0)
        if self.kind in (ToolKind.V_BIT, ToolKind.TAPERED):
            slope = 2.0 * tan(radians(self.taper_angle_deg))
            if slope <= 0:
                return 0.0
            return max((width - self.tip_diameter) / slope, 0.0)
        if self.kind is ToolKind.BALL:
            w = min(width, self.diameter)
            # Shallow root of width = 2*sqrt(depth*(D-depth)).
            return (self.diameter - sqrt(max(self.diameter**2 - w**2, 0.0))) / 2.0
        raise ValueError(f"{self.kind.value} tools cut a constant width and cannot V-carve")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "diameter": self.diameter,
            "taper_angle_deg": self.taper_angle_deg,
            "tip_diameter": self.tip_diameter,
            "notes": self.notes,
        }

    @staticmethod
    def from_dict(data: dict) -> "Tool":
        return Tool(
            name=str(data.get("name", "Tool")),
            kind=ToolKind(data.get("kind", "flat")),
            diameter=float(data.get("diameter", 6.0)),
            taper_angle_deg=float(data.get("taper_angle_deg", 0.0)),
            tip_diameter=float(data.get("tip_diameter", 0.0)),
            notes=str(data.get("notes", "")),
        )


@dataclass(slots=True)
class Layer:
    name: str
    visible: bool = True
    # Depth is a property of the layer, not of the session: one part carves a
    # vine 3 mm deep, grooves 6 mm and cuts the outline through. Send to
    # SolidWorks reads the same numbers, so simulation and cut never drift.
    depth: float = 3.0
    cut: bool = True
    # How this layer is machined: "profile" (flat-bottom sweep at one depth),
    # "vcarve" (Z varies with width; depth is the *max* depth) or "laser".
    mode: str = "profile"
    # Each layer owns its full machining recipe, so one part can laser-engrave
    # one layer and V-carve another and preview them together. Edited from the
    # Simulation tab's left toolbar; the right-hand layer panel only displays it.
    tool: Tool = field(default_factory=lambda: Tool(name="Flat end", kind=ToolKind.FLAT))

    def clone(self) -> "Layer":
        return Layer(self.name, self.visible, self.depth, self.cut, self.mode, replace(self.tool))

    def to_dict(self) -> dict:
        # Custom (de)serialization: the nested Tool would otherwise reach
        # Layer(**data) as a plain dict. Keeps the .curvemill JSON flat and safe.
        return {
            "name": self.name,
            "visible": self.visible,
            "depth": self.depth,
            "cut": self.cut,
            "mode": self.mode,
            "tool": self.tool.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict) -> "Layer":
        tool = data.get("tool")
        return Layer(
            name=str(data.get("name", "0")),
            visible=bool(data.get("visible", True)),
            depth=float(data.get("depth", 3.0)),
            cut=bool(data.get("cut", True)),
            mode=str(data.get("mode", "profile")),
            tool=Tool.from_dict(tool) if tool else Tool(name="Flat end", kind=ToolKind.FLAT),
        )


@dataclass(slots=True)
class ProcessOptions:
    board_width: float = 600.0
    board_height: float = 400.0
    units: str = "mm"
    endmill_diameter: float = 6.0
    trace_mode: TraceMode = TraceMode.CENTER
    repair_tolerance: float = 0.25
    auto_repair: bool = False
    hide_islands: bool = False
    curve_tolerance: float = 0.2
    # Kind of the active tool ("flat" when the user types a manual diameter);
    # only warning wording depends on it — the sweep uses endmill_diameter,
    # which the UI sets to the tool's effective diameter at the cut depth.
    tool_kind: str = "flat"


@dataclass(slots=True)
class VectorEntity:
    points: list[Point]
    closed: bool = False
    layer: str = "0"
    source_type: str = "POLYLINE"
    id: int = field(default_factory=lambda: next(_id_counter))
    group_id: int | None = None

    def clone(self) -> "VectorEntity":
        return VectorEntity(
            points=list(self.points),
            closed=self.closed,
            layer=self.layer,
            source_type=self.source_type,
            id=self.id,
            group_id=self.group_id,
        )

    def copy_with_new_id(self) -> "VectorEntity":
        return VectorEntity(
            points=list(self.points),
            closed=self.closed,
            layer=self.layer,
            source_type=self.source_type,
            group_id=self.group_id,
        )

    @property
    def is_valid(self) -> bool:
        return len(self.points) >= 3 if self.closed else len(self.points) >= 2

    def bounds(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return min(xs), min(ys), max(xs), max(ys)

    def translated(self, dx: float, dy: float) -> "VectorEntity":
        copy = self.clone()
        copy.points = [(x + dx, y + dy) for x, y in copy.points]
        return copy

    def scaled(self, origin: Point, sx: float, sy: float | None = None) -> "VectorEntity":
        sy = sx if sy is None else sy
        ox, oy = origin
        copy = self.clone()
        copy.points = [(ox + (x - ox) * sx, oy + (y - oy) * sy) for x, y in copy.points]
        return copy

    def set_vertex(self, index: int, point: Point) -> "VectorEntity":
        if index < 0 or index >= len(self.points):
            raise IndexError(index)
        copy = self.clone()
        copy.points[index] = point
        return copy

    def length(self) -> float:
        if len(self.points) < 2:
            return 0.0
        pairs = zip(self.points, self.points[1:])
        total = sum(hypot(b[0] - a[0], b[1] - a[1]) for a, b in pairs)
        if self.closed and len(self.points) > 2:
            a, b = self.points[-1], self.points[0]
            total += hypot(b[0] - a[0], b[1] - a[1])
        return total

    def to_svg_path(self) -> str:
        """Produce an SVG path d-string from the polyline points."""
        if not self.points:
            return ""
        parts = [f"M {self.points[0][0]},{self.points[0][1]}"]
        for x, y in self.points[1:]:
            parts.append(f"L {x},{y}")
        if self.closed:
            parts.append("Z")
        return " ".join(parts)


@dataclass(slots=True)
class SplineEntity:
    """A native NURBS/parametric spline curve preserved from DXF import."""
    control_points: list[Point]
    fit_points: list[Point] = field(default_factory=list)
    degree: int = 3
    knots: list[float] | None = None
    closed: bool = False
    periodic: bool = False
    layer: str = "0"
    id: int = field(default_factory=lambda: next(_id_counter))
    group_id: int | None = None
    # (point_list, fit_list, tolerance, flattened) memo for flatten(); excluded
    # from init/eq/repr and stripped before serialization (see project.save).
    _flat_cache: object = field(default=None, init=False, compare=False, repr=False)

    def clone(self) -> "SplineEntity":
        return SplineEntity(
            control_points=list(self.control_points),
            fit_points=list(self.fit_points),
            degree=self.degree,
            knots=list(self.knots) if self.knots is not None else None,
            closed=self.closed,
            periodic=self.periodic,
            layer=self.layer,
            id=self.id,
            group_id=self.group_id,
        )

    def copy_with_new_id(self) -> "SplineEntity":
        return SplineEntity(
            control_points=list(self.control_points),
            fit_points=list(self.fit_points),
            degree=self.degree,
            knots=list(self.knots) if self.knots is not None else None,
            closed=self.closed,
            periodic=self.periodic,
            layer=self.layer,
            group_id=self.group_id,
        )

    @property
    def is_valid(self) -> bool:
        return len(self.control_points) >= 2

    def bounds(self) -> tuple[float, float, float, float]:
        # Measure the curve, not the control net. NURBS control points bulge
        # OUTSIDE the curve (convex-hull property), so a control-point bbox
        # over-reports the real extent -- that inflation was the dashed-selection
        # gap AND made size dimensions under-scale the export (solve_axis uses
        # s = value / bbox_span, so an inflated span shrinks the pattern by a
        # fraction of a mm). flatten(0.5) hugs the true curve and hits the same
        # cache slot the selection/redraw paths already warm.
        # ponytail: flatten samples at 8 segs/span, so bounds under-report by the
        # tiny inter-sample sag (micrometres) -- negligible vs the control-point
        # overshoot this fixes. Sample denser if a sub-micron export ever matters.
        return self.flatten(0.5).bounds()

    def translated(self, dx: float, dy: float) -> "SplineEntity":
        copy = self.clone()
        copy.control_points = [(x + dx, y + dy) for x, y in copy.control_points]
        copy.fit_points = [(x + dx, y + dy) for x, y in copy.fit_points]
        return copy

    def scaled(self, origin: Point, sx: float, sy: float | None = None) -> "SplineEntity":
        sy = sx if sy is None else sy
        ox, oy = origin
        copy = self.clone()
        copy.control_points = [(ox + (x - ox) * sx, oy + (y - oy) * sy) for x, y in copy.control_points]
        copy.fit_points = [(ox + (x - ox) * sx, oy + (y - oy) * sy) for x, y in copy.fit_points]
        return copy

    def flatten(self, tolerance: float = 0.2) -> VectorEntity:
        """Approximate this spline as a polyline of straight segments.

        Cached: re-evaluating the NURBS on every hit-test/redraw dominated
        selection on optimized files (hundreds of splines). The key is the
        point-list *identity* -- every in-place edit (move/scale) and every
        clone reassigns a fresh list -- so the cache self-invalidates with no
        dirty flag. A clone is returned so callers keep the pre-cache "fresh
        object per call" contract and can't corrupt the stored master.
        ponytail: single slot; the interactive path is all tolerance=0.5, so it
        hits. Mixed tolerances on one spline just recompute -- upgrade to a
        per-tolerance dict only if that ever lands in a hot loop.
        """
        cache = self._flat_cache
        if (
            cache is not None
            and cache[0] is self.control_points
            and cache[1] is self.fit_points
            and cache[2] == tolerance
        ):
            return cache[3].clone()
        result = self._flatten_uncached(tolerance)
        self._flat_cache = (self.control_points, self.fit_points, tolerance, result)
        return result.clone()

    def _flatten_uncached(self, tolerance: float = 0.2) -> VectorEntity:
        if len(self.control_points) < 2:
            # A fit-point-only spline (e.g. re-imported from an optimized export)
            # has no control net; its fit points are dense samples on the curve.
            if len(self.fit_points) >= 2:
                return VectorEntity(
                    points=list(self.fit_points),
                    closed=self.closed,
                    layer=self.layer,
                    source_type="SPLINE_APPROX",
                )
            return VectorEntity(points=self.control_points[:], closed=self.closed, layer=self.layer)

        num_segments = max(16, int((len(self.control_points) - 1) * 8))
        evaluated: list[Point] = []
        for i in range(num_segments + 1):
            t = i / num_segments
            evaluated.append(self._evaluate(t))
        if self.closed and evaluated and evaluated[0] == evaluated[-1]:
            evaluated = evaluated[:-1]
        return VectorEntity(
            points=evaluated,
            closed=self.closed,
            layer=self.layer,
            source_type="SPLINE_APPROX",
        )

    def to_de_casteljau(self, t: float) -> Point:
        """Evaluate bezier curve using De Casteljau's algorithm (for cubic bezier subsets)."""
        pts = list(self.control_points)
        while len(pts) > 1:
            pts = [( (1 - t) * pts[i][0] + t * pts[i + 1][0],
                     (1 - t) * pts[i][1] + t * pts[i + 1][1] ) for i in range(len(pts) - 1)]
        return pts[0]

    def _evaluate(self, t: float) -> Point:
        """Simple De Casteljau evaluation for bezier-style splines."""
        if self.knots is not None and len(self.knots) > 0 and self.degree > 0:
            # t runs 0..1, but a knot vector spans its own domain: a single imported
            # bezier ends at 1.0, while a joined multi-segment spline ends at its
            # segment count. Feeding raw t would draw only the first segment.
            low = self.knots[self.degree]
            high = self.knots[len(self.knots) - self.degree - 1]
            return self._evaluate_nurbs(low + t * (high - low))
        return self.to_de_casteljau(t)

    def _evaluate_nurbs(self, t: float) -> Point:
        """Evaluate a NURBS curve at parameter t using Cox-deBoor formula."""
        n = len(self.control_points) - 1
        p = self.degree
        knots = self.knots or _default_knots(n + 1, p)

        span = _find_span(n, p, t, knots)
        basis = _basis_functions(span, t, p, knots)

        x = sum(basis[i] * self.control_points[span - p + i][0] for i in range(p + 1))
        y = sum(basis[i] * self.control_points[span - p + i][1] for i in range(p + 1))
        return (x, y)

    def to_svg_path(self, tolerance: float = 0.2) -> str:
        """Produce an SVG path d-string including bezier curves where possible."""
        if not self.control_points:
            return ""
        start = self.control_points[0]
        parts = [f"M {start[0]},{start[1]}"]
        # For degree 3 cubic bezier with 4 control points, output a C command
        if self.degree == 3 and len(self.control_points) == 4:
            c1, c2, end = self.control_points[1], self.control_points[2], self.control_points[3]
            parts.append(f"C {c1[0]},{c1[1]} {c2[0]},{c2[1]} {end[0]},{end[1]}")
        else:
            evaluated = self.flatten(tolerance).points
            for x, y in evaluated[1:]:
                parts.append(f"L {x},{y}")
        if self.closed:
            parts.append("Z")
        return " ".join(parts)


def _default_knots(num_control: int, degree: int) -> list[float]:
    """Generate clamped knot vector for a bezier-like NURBS curve."""
    n = num_control - 1
    knots = [0.0] * (degree + 1)
    interior = max(n - degree + 1, 2)
    for i in range(1, interior):
        knots.append(i / interior)
    knots.extend([1.0] * (degree + 1))
    return knots


def _find_span(n: int, p: int, u: float, knots: list[float]) -> int:
    """Find the knot span index for parameter u (Cox-deBoor)."""
    if u >= knots[n + 1]:
        return n
    if u <= knots[p]:
        return p
    low, high = p, n + 1
    while low < high - 1:
        mid = (low + high) // 2
        if u < knots[mid]:
            high = mid
        else:
            low = mid
    return low


def _basis_functions(span: int, u: float, p: int, knots: list[float]) -> list[float]:
    """Compute non-vanishing basis functions at parameter u."""
    left = [0.0] * (p + 1)
    right = [0.0] * (p + 1)
    N = [0.0] * (p + 1)
    N[0] = 1.0
    for j in range(1, p + 1):
        left[j] = u - knots[span + 1 - j]
        right[j] = knots[span + j] - u
        saved = 0.0
        for r in range(j):
            temp = N[r] / (right[r + 1] + left[j - r])
            N[r] = saved + right[r + 1] * temp
            saved = left[j - r] * temp
        N[j] = saved
    return N


@dataclass(slots=True)
class ImportResult:
    vectors: list[VectorEntity]
    splines: list[SplineEntity] = field(default_factory=list)
    units: str = "mm"
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProcessWarning:
    key: str
    kind: str
    message: str
    vector_id: int
    path: VectorEntity

    def clone(self) -> "ProcessWarning":
        return ProcessWarning(
            key=self.key,
            kind=self.kind,
            message=self.message,
            vector_id=self.vector_id,
            path=self.path.clone(),
        )


@dataclass(slots=True)
class ProcessResult:
    repaired_vectors: list[VectorEntity]
    toolpaths: list[VectorEntity]
    removed_wkt: str
    remaining_wkt: str
    hidden_islands_wkt: str
    warnings: list[str] = field(default_factory=list)
    warning_details: list[ProcessWarning] = field(default_factory=list)
    # (layer name, depth, removed WKT) per layer, shallowest first — the preview
    # shades these so a multi-depth part reads at a glance. A V-carve layer
    # contributes one entry per iso-depth band instead of a single flat cut.
    depth_cuts: list[tuple[str, float, str]] = field(default_factory=list)
    # (kind, WKT) overlays flagging where a V-carve can't be cut cleanly:
    # "flat_bottom" (wider than the tool at max depth — needs a clearing pass)
    # and "unreachable" (narrower than the tool tip — the tip can't reach bottom).
    vcarve_hazards: list[tuple[str, str]] = field(default_factory=list)
    # The tool-compensated cut-side wall of every shape (WKT): the nominal profile
    # with corners the endmill can't reach rounded to its radius. This is what
    # 'Replace with Corrected' / corrected export emit — one curve per shape, no
    # stock outline, no scrap-side groove wall.
    corrected_wkt: str = ""
    # The same corrected walls as corrected_wkt but kept split per source layer,
    # so 'Replace with Simulated' can put each layer's milled shape back on its own
    # layer instead of merging them all onto one. Profile layers only (V-carve
    # layers shade depth bands and have no single corrected wall).
    corrected_by_layer: list[tuple[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class LayerJob:
    """One layer queued for simulation: its depth, how it's machined, and the
    tool (V-carve needs the tool to invert width->depth)."""
    name: str
    depth: float
    mode: str  # "profile" | "vcarve"
    vectors: list["VectorEntity"]
    options: ProcessOptions
    tool: Tool


def combined_bounds(vectors: Iterable[VectorEntity]) -> tuple[float, float, float, float] | None:
    items = list(vectors)
    if not items:
        return None
    mins_x, mins_y, maxs_x, maxs_y = zip(*(v.bounds() for v in items))
    return min(mins_x), min(mins_y), max(maxs_x), max(maxs_y)
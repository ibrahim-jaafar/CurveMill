from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from math import acos, ceil, degrees, hypot

from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Polygon, box
from shapely.ops import polygonize, unary_union
from shapely import wkt

from .models import LayerJob, Point, ProcessOptions, ProcessResult, ProcessWarning, SplineEntity, Tool, TraceMode, VectorEntity
from .progress import ProgressCallback, report as _report, report_loop as _report_loop

# Turn sharper than this is a real corner, not curvature: a spline interpolated
# straight through it would round it off, so a chain gets cut there instead.
CORNER_DEGREES = 40.0


def join_spline_fragments(
    splines: list[SplineEntity],
    tolerance: float = 1e-4,
    corner_degrees: float = CORNER_DEGREES,
    progress: ProgressCallback | None = None,
) -> list[SplineEntity]:
    """Merge single-bezier SPLINE fragments into one native spline per shape.

    Inkscape's DXF exporter writes every bezier segment of a path as its own
    SPLINE entity, so a 540-shape drawing arrives as 3383 entities and SolidWorks
    counts each one. The fragments share exact endpoints, so chaining them back
    into one cubic B-spline per shape is lossless (verified to ~1e-12 mm) and
    needs no rasterizing.

    Only pure cubic beziers (degree 3, 4 control points) can be chained this way;
    anything else passes through untouched. The default tolerance is 0.1 micron:
    far below any CAD/CNC precision, but loose enough to absorb the float noise
    exporters leave between segments that are meant to meet.
    """
    from ezdxf.math import Bezier4P, Vec2, bezier_to_bspline

    _report(progress, 0, "Finding spline fragments")
    fragments: list[SplineEntity] = []
    result: list[SplineEntity] = []
    for spline in splines:
        if spline.degree == 3 and len(spline.control_points) == 4 and not spline.periodic:
            fragments.append(spline)
        else:
            result.append(spline)

    _report(progress, 20, "Chaining fragments")
    for index, chain in enumerate(_bezier_chains(fragments, tolerance)):
        _report_loop(progress, 20, 90, index + 1, max(len(fragments), 1), "Joining curves")
        # Cut the chain at genuine corners before joining. A joined spline is
        # later resampled into a fit-point spline (to_fit_splines), and the
        # consumer -- a DXF reader or SolidWorks -- re-interpolates a *smooth*
        # curve through those samples. It cannot keep a tangent break, so it
        # rounds every corner and overshoots into the adjacent sides, and the
        # straight edges of a hard-cornered shape come out wavy. fit_vector_chains
        # already splits its line runs here for the same reason; do the same for
        # joined bezier fragments so a corner stays a corner (one spline per
        # smooth run, meeting at coincident endpoints).
        for run in _split_bezier_chain_at_corners(chain, corner_degrees):
            bspline = bezier_to_bspline([Bezier4P([Vec2(p) for p in seg]) for seg in run])
            control_points = [(p.x, p.y) for p in bspline.control_points]
            result.append(SplineEntity(
                control_points=control_points,
                degree=bspline.degree,
                knots=list(bspline.knots()),
                closed=_dist(control_points[0], control_points[-1]) <= tolerance,
                layer=chain.layer,
            ))

    _report(progress, 100, "Curves joined")
    return result


class _Chain(list):
    """A list of bezier control-point tuples that remembers its source layer."""
    layer: str = "0"


def _bezier_chains(fragments: list[SplineEntity], tolerance: float) -> list[_Chain]:
    """Walk single-bezier fragments into end-to-end chains, in geometric order.

    Endpoints are bucketed on a spatial hash so lookup stays near-linear instead
    of rescanning every unused fragment (the same reason _build_chains uses one).
    Neighbouring cells are searched too: two endpoints can sit within tolerance
    of each other yet fall on opposite sides of a cell boundary.
    """
    cell_size = max(tolerance, 1e-9)

    def cell_of(point: Point) -> tuple[int, int]:
        return (int(point[0] // cell_size), int(point[1] // cell_size))

    endpoint_cells: dict[tuple[int, int], list[int]] = {}
    for index, fragment in enumerate(fragments):
        for point in (fragment.control_points[0], fragment.control_points[-1]):
            endpoint_cells.setdefault(cell_of(point), []).append(index)

    def nearby(point: Point) -> list[int]:
        cx, cy = cell_of(point)
        found: list[int] = []
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                found.extend(endpoint_cells.get((cx + ox, cy + oy), ()))
        return found

    used = [False] * len(fragments)
    chains: list[_Chain] = []
    for seed in range(len(fragments)):
        if used[seed]:
            continue
        used[seed] = True
        chain = _Chain([list(fragments[seed].control_points)])
        chain.layer = fragments[seed].layer
        # Grow from the tail, then flip and grow what was the head.
        for _ in range(2):
            extended = True
            while extended:
                extended = False
                tail = chain[-1][-1]
                for index in nearby(tail):
                    if used[index]:
                        continue
                    segment = list(fragments[index].control_points)
                    if _dist(segment[0], tail) > tolerance:
                        if _dist(segment[-1], tail) > tolerance:
                            continue  # a cell neighbour, but not actually touching
                        segment.reverse()  # this bezier runs the other way
                    used[index] = True
                    chain.append(segment)
                    extended = True
                    break
            flipped = _Chain([seg[::-1] for seg in reversed(chain)])
            flipped.layer = chain.layer
            chain = flipped
        chains.append(chain)
    return chains


def _bezier_start_dir(seg: list[Point]) -> Point | None:
    """Direction a cubic bezier leaves its start point (first non-degenerate leg)."""
    p0 = seg[0]
    for p in seg[1:]:
        d = (p[0] - p0[0], p[1] - p0[1])
        if d[0] or d[1]:
            return d
    return None


def _bezier_end_dir(seg: list[Point]) -> Point | None:
    """Direction a cubic bezier arrives at its end point (last non-degenerate leg)."""
    p3 = seg[-1]
    for p in reversed(seg[:-1]):
        d = (p3[0] - p[0], p3[1] - p[1])
        if d[0] or d[1]:
            return d
    return None


def _split_bezier_chain_at_corners(
    chain: list[list[Point]], corner_degrees: float
) -> list[list[list[Point]]]:
    """Break a chain of cubic-bezier segments wherever two consecutive segments
    meet at a tangent break sharper than corner_degrees -- the same corners
    fit_vector_chains cuts, so a later fit-point resample can't round them off."""
    runs: list[list[list[Point]]] = [[chain[0]]]
    for prev, seg in zip(chain, chain[1:]):
        incoming, outgoing = _bezier_end_dir(prev), _bezier_start_dir(seg)
        if incoming and outgoing:
            scale = hypot(*incoming) * hypot(*outgoing)
            cosine = max(-1.0, min(1.0, (incoming[0] * outgoing[0] + incoming[1] * outgoing[1]) / scale))
            if degrees(acos(cosine)) > corner_degrees:
                runs.append([seg])  # corner: start a new run
                continue
        runs[-1].append(seg)
    return runs


def fit_vector_chains(
    vectors: list[VectorEntity],
    tolerance: float = 1e-4,
    corner_degrees: float = CORNER_DEGREES,
    progress: ProgressCallback | None = None,
) -> list[SplineEntity]:
    """Rebuild loose LINE segments into one native spline per smooth run.

    Pattern DXFs often arrive as thousands of tiny disconnected LINEs that are
    really a polygonal sampling of smooth curves (measured: 7014 LINEs = 89
    shapes, 96% of joints turning under 30 degrees). SolidWorks counts one
    sketch element per line, so the file is unusable; one SPLINE is a single
    element no matter how many control points it carries. Chaining the segments
    and interpolating a cubic through them collapses 7014 elements to 274.

    This is lossless: the fitted curve passes exactly through every original
    point, and it does not oscillate between them (measured arc/chord = 1.0005).
    No decimation, so there is no tolerance to trade away -- the only cuts are
    at genuine corners, which must stay sharp.
    """
    from ezdxf.math import fit_points_to_cubic_bezier

    _report(progress, 0, "Chaining line segments")
    # A closed vector's final edge is implicit (points[0] is not repeated) and
    # _build_chains only sees the point list, so feeding it closed entities
    # drops that edge and reopens the shape -- Repair's healed sub-loops arrived
    # here closed and left Optimize as open profiles with a gap the size of the
    # lost edge (and a ring's seam ends could even be grafted into another
    # chain, drawing a path through the shape). A closed entity is already a
    # complete chain: emit its ring directly, repeated final point included.
    chains = [
        (v.points + [v.points[0]], [v])
        for v in vectors
        if v.closed and len(v.points) >= 3
    ]
    chains += _build_chains(
        [v for v in vectors if not v.closed and len(v.points) >= 2], tolerance
    )

    _report(progress, 30, "Fitting curves")
    result: list[SplineEntity] = []
    for index, (points, members) in enumerate(chains):
        _report_loop(progress, 30, 95, index + 1, max(len(chains), 1), "Fitting curves")
        layer = members[0].layer if members else "0"
        # A closed chain keeps its repeated final point, so the fit closes the loop.
        fitted: list[SplineEntity] = []
        for piece in _split_at_corners(points, corner_degrees):
            if len(piece) < 3:
                control_points = _straight_cubic(piece[0], piece[-1])
                knots = None
            else:
                bspline = fit_points_to_cubic_bezier(_densify(piece))
                control_points = [(p.x, p.y) for p in bspline.control_points]
                knots = list(bspline.knots())
            fitted.append(SplineEntity(
                control_points=control_points,
                degree=3,
                knots=knots,
                closed=_dist(control_points[0], control_points[-1]) <= tolerance,
                layer=layer,
            ))
        if _fit_self_crosses(points, fitted, tolerance):
            # ponytail: on a thin shape the smoothed fit bulges ~0.1mm off the
            # polyline at the corner-split tangents, the two sides overlap, and the
            # profile crosses itself -- SolidWorks refuses to cut a self-intersecting
            # contour ("no solution found"). The raw polyline doesn't cross, and SW
            # re-smooths ANY fit-point spline (measured: even dense fit points through
            # the source points re-cross on 6/10 real cases), so this shape must reach
            # SW as straight segments. Emit one straight cubic per source segment:
            # colinear fit points stay straight through SW's refit, guaranteeing a
            # simple, cuttable contour. Costs elements on these few thin shapes only;
            # correctness beats the count there.
            result.extend(
                SplineEntity(control_points=_straight_cubic(a, b), degree=3,
                             knots=None, closed=False, layer=layer)
                for a, b in zip(points, points[1:])
            )
        else:
            result.extend(fitted)

    _report(progress, 100, "Curves fitted")
    return result


def to_fit_splines(
    splines: list[SplineEntity],
    per_segment: int = 4,
    max_step: float = 0.1,
    max_points: int = 800,
) -> list[SplineEntity]:
    """Convert control-point splines to fit-point splines for SolidWorks export.

    SolidWorks splits an imported control-point SPLINE at every joint that is
    not bit-exactly tangent-continuous (probe-measured: even an 8.5e-7 degree
    break splits, and a closed loop always counts at least 2). A fit-point
    SPLINE is refit by SolidWorks and always counts as ONE element (probes
    p21/p24: 540 shapes -> 540 elements). The fit points are exact samples of
    the source curve.

    Sampling is arc-length-based, not a flat count per segment: a fixed
    per-segment count under-samples LONG segments (a 28mm border edge got the
    same 4 points as a 1mm curl), and SolidWorks' interpolating refit then
    overshoots the sparse points into 'dog bone' bulges -- a straight border
    ballooned ~1mm on a 6mm shape. Placing a sample at least every ``max_step``
    mm keeps the refit on the curve (~0.1mm worst-case here). ``per_segment``
    stays a floor for short/curvy segments.
    ponytail: max_points caps runaway sampling on a huge part; past it the
    spacing grows and overshoot can creep back -- raise the cap (or lower
    max_step) only if a metre-scale smooth loop ever dog-bones.
    """
    result = []
    for spline in splines:
        segments = max(len(set(spline.knots)) - 1 if spline.knots else 1, 1)
        # Arc length via a dense uniform pass (curve length is scale, so the mm
        # step below is comparable across small curls and long edges alike).
        dense = [spline._evaluate(i / 256) for i in range(257)]
        length = sum(hypot(dense[i + 1][0] - dense[i][0], dense[i + 1][1] - dense[i][1]) for i in range(256))
        count = max(per_segment * segments, ceil(length / max_step) if max_step > 0 else 0)
        count = max(min(count, max_points), 1)
        points = [spline._evaluate(i / count) for i in range(count + 1)]
        if spline.closed:
            points[-1] = points[0]  # bit-identical seam so the loop closes
        result.append(SplineEntity(
            control_points=[],
            fit_points=points,
            degree=3,
            closed=spline.closed,
            layer=spline.layer,
        ))
    return result


def _straight_cubic(start: Point, end: Point) -> list[Point]:
    """A two-point run is a straight line; express it as an exact cubic."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    return [
        start,
        (start[0] + dx / 3, start[1] + dy / 3),
        (start[0] + 2 * dx / 3, start[1] + 2 * dy / 3),
        end,
    ]


def _fit_self_crosses(
    points: list[Point], fitted: list[SplineEntity], tolerance: float
) -> bool:
    """True when a CLOSED chain's fitted curve crosses itself but its raw polyline
    does not -- i.e. the smoothing *introduced* a self-intersection.

    Only closed chains form the profiles SolidWorks has to cut. An open run, or one
    whose raw polyline already crosses, is a source fault the Repair Vectors button
    heals -- not the fit artefact this guard exists to catch.
    """
    if _dist(points[0], points[-1]) > tolerance:
        return False
    raw = points if points[0] == points[-1] else points + [points[0]]
    if not LineString(raw).is_simple:
        return False  # source already crosses -- not our regression to fix
    flat: list[Point] = []
    for spline in fitted:
        flat.extend(spline.flatten(0.05).points)
    return len(flat) >= 4 and not LineString(flat).is_simple


def _densify(points: list[Point], max_gap: float = 2.0, max_inserts: int = 60) -> list[Point]:
    """Subdivide long segments with colinear points so the interpolating fit can't bulge.

    fit_points_to_cubic_bezier interpolates every point, so on the long,
    unevenly-spaced segments Douglas-Peucker leaves behind (Replace-with-Simulated
    thins straights to 2 points, keeps curve clusters) the cubic has slack to bulge
    *between* points -- it overshoots the milled wall by ~0.2mm entering a tight
    radius (the "wave", up to ~1.3mm on a sparse straight). Splitting each long
    segment into pieces no longer than ``max_gap`` pins the fit to the wall: measured
    0.195mm -> 0.022mm on a real tip, and the shape stays ONE spline (one SolidWorks
    element) -- unlike dropping the corner angle, which shatters a smooth run.

    Inserts sit exactly on the source segment, so the fit still passes through every
    original vertex: no accuracy traded, only overshoot removed.

    Two properties make this robust to any tool size / sampling a user throws at it:

      * EVEN spacing, not fixed-step-from-the-start. A fixed step drops its last
        insert a hair before the segment end whenever the length is not a clean
        multiple (a 2.005mm chord got a point 0.005mm from the vertex); that near-
        duplicate makes the cubic kink into a microscopic self-loop, which trips
        _fit_self_crosses into the straight-segment fallback (one element per
        segment). Splitting into ``ceil(gap/max_gap)`` EQUAL pieces never lands a
        point near an existing one, so clean smooth curves at any sampling density
        stay a single spline (fixed measured circle explosions at R8/R20 @ ~2mm
        chords: 25-62 splines -> 1). Even spacing also pins big-part straights right
        up to the junction: a 4x part's tip went 0.79mm -> 0.038mm.
      * ``max_gap`` stays COARSE (2mm) and segments already shorter than it are left
        untouched (ceil gives one piece = no inserts). Tight curve clusters are
        already sampled finer than 2mm, so they pass through as-fit -- densifying a
        tight tip finer than its own samples is what produced the self-loops in the
        first place. Curvature-varying the step was measured strictly worse (bigger
        overshoot, no fewer splines), so the spacing is deliberately uniform.
    """
    n = len(points)
    if max_gap <= 0 or n < 2:
        return points
    dense: list[Point] = [points[0]]
    for start, end in zip(points, points[1:]):
        gap = hypot(end[0] - start[0], end[1] - start[1])
        pieces = min(ceil(gap / max_gap) if gap > 1e-12 else 1, max_inserts + 1)
        for k in range(1, pieces):
            t = k / pieces
            dense.append((start[0] + t * (end[0] - start[0]),
                          start[1] + t * (end[1] - start[1])))
        dense.append(end)
    return dense


def _split_at_corners(points: list[Point], corner_degrees: float) -> list[list[Point]]:
    """Cut a chain wherever it turns hard enough to be a corner rather than a curve."""
    pieces: list[list[Point]] = []
    run: list[Point] = [points[0]]
    for index in range(1, len(points) - 1):
        before, here, after = points[index - 1], points[index], points[index + 1]
        run.append(here)
        first = (here[0] - before[0], here[1] - before[1])
        second = (after[0] - here[0], after[1] - here[1])
        scale = hypot(*first) * hypot(*second)
        if not scale:
            continue  # a repeated point says nothing about direction
        cosine = max(-1.0, min(1.0, (first[0] * second[0] + first[1] * second[1]) / scale))
        if degrees(acos(cosine)) > corner_degrees:
            pieces.append(run)
            run = [here]  # the corner belongs to both sides
    run.append(points[-1])
    pieces.append(run)
    return [piece for piece in pieces if len(piece) >= 2]


def flatten_splines(
    splines: list[SplineEntity],
    tolerance: float = 0.2,
    progress: ProgressCallback | None = None,
) -> list[VectorEntity]:
    """Convert all native splines to polylines for Shapely-based processing."""
    _report(progress, 0, "Flattening splines")
    result: list[VectorEntity] = []
    for index, spline in enumerate(splines):
        _report_loop(progress, 0, 100, index + 1, len(splines), "Flattening splines")
        if spline.is_valid:
            result.append(spline.flatten(tolerance))
    _report(progress, 100, "Splines flattened")
    return result


def process_vectors(
    vectors: list[VectorEntity],
    options: ProcessOptions,
    progress: ProgressCallback | None = None,
) -> ProcessResult:
    warnings: list[str] = []
    warning_details: list[ProcessWarning] = []
    _report(progress, 2, "Preparing vectors")
    if options.auto_repair:
        repaired = repair_vectors(
            vectors,
            options.repair_tolerance,
            lambda value, message: _report(progress, 2 + int(value * 0.18), message),
        )
    else:
        repaired = [v.clone() for v in vectors]
    _report(progress, 20, "Building cutter paths")
    toolpaths = build_toolpaths(
        repaired,
        options,
        warnings,
        lambda value, message: _report(progress, 20 + int(value * 0.30), message),
        warning_details,
    )
    _report(progress, 55, "Sweeping the endmill")
    removed = _buffer_toolpaths(toolpaths, max(options.endmill_diameter / 2.0, 0.001))
    _report(progress, 72, "Clipping cuts to the board")
    board = box(0, 0, options.board_width, options.board_height)
    removed_on_board = removed.intersection(board)
    _report(progress, 84, "Calculating remaining wood")
    remaining = board.difference(removed_on_board)
    hidden = GeometryCollection()
    if options.hide_islands:
        _report(progress, 92, "Hiding disconnected islands")
        visible, hidden = split_islands(remaining, board)
        remaining = visible
        if not hidden.is_empty:
            removed_on_board = unary_union([removed_on_board, hidden])
    result = ProcessResult(
        repaired_vectors=repaired,
        toolpaths=toolpaths,
        removed_wkt=removed_on_board.wkt,
        remaining_wkt=remaining.wkt,
        hidden_islands_wkt=hidden.wkt,
        warnings=warnings,
        warning_details=warning_details,
        corrected_wkt=_finished_edges(repaired, options).wkt,
    )
    _report(progress, 100, "Processing complete")
    return result


def process_layers(
    jobs: list[LayerJob],
    progress: ProgressCallback | None = None,
) -> ProcessResult:
    """Machine each layer in its own mode/depth, then composite one board.

    Profile layers sweep a fixed-width buffer (the caller sets the width from the
    layer's depth); V-carve layers shade graduated iso-depth bands. The wood left
    over is what survives every layer's cut; islands are a board-wide question, so
    they are decided once at the end rather than per layer.
    """
    if not jobs:
        raise ValueError("No layer is set to cut.")
    board_options = jobs[0].options
    removed_parts = []
    corrected_parts = []
    depth_cuts: list[tuple[str, float, str]] = []
    corrected_by_layer: list[tuple[str, str]] = []
    hazards: list[tuple[str, str]] = []
    repaired: list[VectorEntity] = []
    toolpaths: list[VectorEntity] = []
    warnings: list[str] = []
    warning_details: list[ProcessWarning] = []
    span = 100.0 / len(jobs)
    for index, job in enumerate(jobs):
        base = index * span
        report = lambda value, message, base=base, name=job.name: _report(
            progress, int(base + value * span / 100.0), f"{name}: {message}"
        )
        if job.mode == "vcarve":
            carve = vcarve_layer(job.vectors, job.tool, job.depth, board_options, report)
            removed_parts.append(geometry_from_wkt(carve.removed_wkt))
            depth_cuts.extend((job.name, depth, wkt_value) for depth, wkt_value in carve.bands)
            hazards.extend(carve.hazards)
            warnings.extend(carve.warnings)
            repaired.extend(v.clone() for v in job.vectors)
        else:
            result = process_vectors(job.vectors, replace(job.options, hide_islands=False), report)
            removed_parts.append(geometry_from_wkt(result.removed_wkt))
            corrected_parts.append(geometry_from_wkt(result.corrected_wkt))
            corrected_by_layer.append((job.name, result.corrected_wkt))
            depth_cuts.append((job.name, job.depth, result.removed_wkt))
            repaired.extend(result.repaired_vectors)
            toolpaths.extend(result.toolpaths)
            warnings.extend(result.warnings)
            warning_details.extend(result.warning_details)
    board = box(0, 0, board_options.board_width, board_options.board_height)
    removed = unary_union(removed_parts) if removed_parts else GeometryCollection()
    corrected_parts = [g for g in corrected_parts if not g.is_empty]
    corrected = unary_union(corrected_parts) if corrected_parts else GeometryCollection()
    remaining = board.difference(removed)
    hidden = GeometryCollection()
    if board_options.hide_islands:
        remaining, hidden = split_islands(remaining, board)
        if not hidden.is_empty:
            removed = unary_union([removed, hidden])
    _report(progress, 100, "Processing complete")
    return ProcessResult(
        repaired_vectors=repaired,
        toolpaths=toolpaths,
        removed_wkt=removed.wkt,
        remaining_wkt=remaining.wkt,
        hidden_islands_wkt=hidden.wkt,
        warnings=warnings,
        warning_details=warning_details,
        depth_cuts=sorted(depth_cuts, key=lambda c: c[1]),
        vcarve_hazards=hazards,
        corrected_wkt=corrected.wkt,
        corrected_by_layer=corrected_by_layer,
    )


@dataclass(slots=True)
class _VCarve:
    removed_wkt: str
    bands: list[tuple[float, str]]  # (depth, WKT), shallowest first
    hazards: list[tuple[str, str]]  # (kind, WKT)
    warnings: list[str]


def vcarve_layer(
    vectors: list[VectorEntity],
    tool: Tool,
    max_depth: float,
    options: ProcessOptions,
    progress: ProgressCallback | None = None,
    steps: int = 12,
) -> _VCarve:
    """Preview a V-carve: the bit dips deeper where the shape is wide, so carved
    depth at a point = depth_for_width(2 * distance-to-edge), capped at max_depth.

    Built from successive negative buffers (iso-depth rings), the same shapely
    machinery the profile sweep uses. Previews the carved region + depth shading,
    not a medial-axis toolpath (that's CAM's job).
    ponytail: fixed 12 bands; raise `steps` only if the gradient ever looks banded.
    """
    _report(progress, 5, "Reading closed profiles")
    assembly_tolerance = options.repair_tolerance if options.auto_repair else 1e-9
    solids: list[tuple[Polygon, VectorEntity]] = []
    open_shapes = 0
    for vector in assemble_closed_profiles(vectors, assembly_tolerance):
        if not vector.closed or len(vector.points) < 3:
            open_shapes += 1
            continue
        polygon = Polygon(_without_duplicate_close(vector.points))
        if polygon.is_valid and polygon.area > 0:
            solids.append((polygon, vector))

    warnings: list[str] = []
    if open_shapes:
        warnings.append("Some open shapes were skipped — V-carve needs closed outlines.")
    region = unary_union([shell for shell, _ in _nest_profiles(solids)])
    if region.is_empty:
        return _VCarve(region.wkt, [], [], warnings)

    # Tool half-width at max depth: beyond this distance the cut floor goes flat.
    max_reach = max(tool.effective_diameter(max_depth) / 2.0, 1e-6)
    # Bands are preview-only shading (never exported), so coarse buffer arcs plus
    # a simplify pass keep their vertex count sane — a spline-heavy pattern
    # otherwise emits megabyte rings that freeze the canvas and lag every zoom.
    # Simplifying `inner` (not the ring) keeps adjacent rings sharing the exact
    # same boundary, so no hairline gaps show between bands.
    band_tolerance = max_reach / steps / 4.0
    bands: list[tuple[float, str]] = []
    previous = region
    for i in range(1, steps + 1):
        _report(progress, 5 + int(90 * i / steps), "Carving depth bands")
        distance = max_reach * i / steps
        inner = region.buffer(-distance, join_style="round", quad_segs=4).simplify(band_tolerance)
        ring = previous.difference(inner)
        if not ring.is_empty:
            depth = min(tool.depth_for_width(2.0 * distance), max_depth)
            bands.append((depth, ring.wkt))
        previous = inner
        if inner.is_empty:
            break

    hazards: list[tuple[str, str]] = []
    # Anything eroded past max_reach bottoms out flat at max depth.
    if not previous.is_empty:
        bands.append((max_depth, previous.wkt))
        hazards.append(("flat_bottom", previous.wkt))
        warnings.append("Wide areas bottom out flat at the max depth — they need a clearing pass.")
    # A tool tip that's `tip_diameter` wide can't fit into a neck narrower than it;
    # a morphological opening drops exactly those unreachable slivers.
    tip_radius = tool.tip_diameter / 2.0
    if tip_radius > 0:
        opening = region.buffer(-tip_radius, join_style="round", quad_segs=4).buffer(
            tip_radius, join_style="round", quad_segs=4
        )
        unreachable = region.difference(opening)
        if not unreachable.is_empty and unreachable.area > 1e-9:
            hazards.append(("unreachable", unreachable.wkt))
            warnings.append(
                f"Narrow areas are thinner than the {tool.tip_diameter:g} mm tip — "
                "this tool can't reach the bottom there."
            )
    _report(progress, 100, "V-carve preview ready")
    return _VCarve(region.wkt, bands, hazards, warnings)


def repair_vectors(
    vectors: list[VectorEntity],
    tolerance: float,
    progress: ProgressCallback | None = None,
) -> list[VectorEntity]:
    repaired, _ = repair_geometry(vectors, [], tolerance, progress)
    return repaired


def repair_geometry(
    vectors: list[VectorEntity],
    splines: list[SplineEntity],
    tolerance: float,
    progress: ProgressCallback | None = None,
) -> tuple[list[VectorEntity], list[SplineEntity]]:
    """Snap nearby endpoints of open vectors AND open native splines.

    Splines are repaired natively: a clamped NURBS starts exactly at its first
    control point and ends exactly at its last, so snapping those two points
    moves the curve ends without flattening. Degree, knots and interior control
    points are untouched, so export still writes the original NURBS geometry.
    """
    _report(progress, 0, "Scanning endpoints")
    if tolerance <= 0:
        repaired_vectors = [v.clone() for v in vectors]
        repaired_splines = [s.clone() for s in splines]
        _report(progress, 100, "Repair complete")
        return repaired_vectors, repaired_splines
    # Each endpoint is keyed by (entity_key, point_index) where entity_key is
    # ('v', index) for vectors and ('s', index) for splines.
    EntityKey = tuple[str, int]
    endpoints: list[tuple[EntityKey, int, Point]] = []
    for vector_index, vector in enumerate(vectors):
        # Closed profiles are already complete geometry and must not be moved by
        # endpoint snapping intended to repair open profiles.
        if vector.closed or not vector.points:
            continue
        endpoints.append((("v", vector_index), 0, vector.points[0]))
        if len(vector.points) > 1:
            endpoints.append((("v", vector_index), len(vector.points) - 1, vector.points[-1]))
    for spline_index, spline in enumerate(splines):
        # Only open, non-periodic splines have free endpoints to snap.
        if spline.closed or spline.periodic or len(spline.control_points) < 2:
            continue
        endpoints.append((("s", spline_index), 0, spline.control_points[0]))
        endpoints.append(
            (("s", spline_index), len(spline.control_points) - 1, spline.control_points[-1])
        )
    _report(progress, 20, "Finding nearby endpoints")

    parent = list(range(len(endpoints)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    cell_size = tolerance
    cells: dict[tuple[int, int], list[int]] = {}
    for idx, (_, _, point) in enumerate(endpoints):
        cell = (int(point[0] // cell_size), int(point[1] // cell_size))
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                for other_idx in cells.get((cell[0] + ox, cell[1] + oy), []):
                    if _dist(point, endpoints[other_idx][2]) <= tolerance:
                        union(idx, other_idx)
        cells.setdefault(cell, []).append(idx)
        _report_loop(progress, 20, 55, idx + 1, len(endpoints), "Finding nearby endpoints")

    _report(progress, 60, "Calculating snap positions")
    clusters: dict[int, list[int]] = {}
    for idx in range(len(endpoints)):
        clusters.setdefault(find(idx), []).append(idx)
    snapped: dict[tuple[EntityKey, int], Point] = {}
    for cluster in clusters.values():
        xs = [endpoints[i][2][0] for i in cluster]
        ys = [endpoints[i][2][1] for i in cluster]
        average = (sum(xs) / len(xs), sum(ys) / len(ys))
        for i in cluster:
            entity_key, point_index, _ = endpoints[i]
            snapped[(entity_key, point_index)] = average

    repaired: list[VectorEntity] = []
    total = len(vectors) + len(splines)
    for vector_index, vector in enumerate(vectors):
        copy = vector.clone()
        copy.points = [
            snapped.get((("v", vector_index), i), p) for i, p in enumerate(copy.points)
        ]
        if len(copy.points) > 2 and not copy.closed and _dist(copy.points[0], copy.points[-1]) <= tolerance:
            copy.closed = True
            copy.points = copy.points[:-1]
        repaired.append(copy)
        _report_loop(progress, 75, 98, vector_index + 1, total, "Applying endpoint repairs")
    repaired_splines: list[SplineEntity] = []
    for spline_index, spline in enumerate(splines):
        copy = spline.clone()
        key = ("s", spline_index)
        last = len(copy.control_points) - 1
        start = snapped.get((key, 0))
        end = snapped.get((key, last))
        if start is not None or end is not None:
            # Move only the end control points; the interior of the NURBS (and its
            # knot vector) stays exactly as imported, so the curve is repaired
            # without any conversion to polylines.
            if start is not None:
                copy.control_points[0] = start
            if end is not None:
                copy.control_points[last] = end
            # Fit points no longer describe the edited curve; drop them so
            # export writes the (updated) control points instead of stale fits.
            if copy.fit_points:
                copy.fit_points = []
            if (
                not copy.closed
                and last >= 2
                and _dist(copy.control_points[0], copy.control_points[last]) <= tolerance
            ):
                # Ends now coincide: mark the spline closed so downstream
                # profile assembly and DXF export treat it as a closed curve.
                copy.control_points[last] = copy.control_points[0]
                copy.closed = True
        repaired_splines.append(copy)
        _report_loop(
            progress, 75, 98, len(vectors) + spline_index + 1, total, "Applying endpoint repairs"
        )
    _report(progress, 100, "Repair complete")
    return repaired, repaired_splines


def build_toolpaths(
    vectors: list[VectorEntity],
    options: ProcessOptions,
    warnings: list[str] | None = None,
    progress: ProgressCallback | None = None,
    warning_details: list[ProcessWarning] | None = None,
) -> list[VectorEntity]:
    warnings = warnings if warnings is not None else []
    radius = max(options.endmill_diameter / 2.0, 0.001)
    if options.trace_mode == TraceMode.CENTER:
        toolpaths = [v.clone() for v in vectors if v.is_valid]
        _report(progress, 100, "Center toolpaths ready")
        return toolpaths

    _report(progress, 5, "Assembling closed profiles")
    assembly_tolerance = options.repair_tolerance if options.auto_repair else 1e-9
    vectors = assemble_closed_profiles(vectors, assembly_tolerance)
    toolpaths: list[VectorEntity] = []
    solids: list[tuple[Polygon, VectorEntity]] = []
    for vector_index, vector in enumerate(vectors):
        _report_loop(progress, 10, 50, vector_index + 1, len(vectors), "Reading closed profiles")
        if not vector.closed or len(vector.points) < 3:
            _add_path_warning(
                warnings,
                warning_details,
                "open_path_fallback",
                f"This shape isn't fully closed, so the cutter follows its line directly instead of the {options.trace_mode.value} edge.",
                vector,
            )
            toolpaths.append(vector.clone())
            continue
        polygon = Polygon(_without_duplicate_close(vector.points))
        if not polygon.is_valid or polygon.area == 0:
            _add_path_warning(
                warnings,
                warning_details,
                "invalid_closed_path",
                f"This shape crosses over itself or has no area, so the cutter follows its line directly instead of the {options.trace_mode.value} edge.",
                vector,
            )
            toolpaths.append(vector.clone())
            continue
        solids.append((polygon, vector))

    offset_distance = -radius if options.trace_mode == TraceMode.INSIDE else radius
    families = _nest_profiles(solids)
    for family_index, (region, vector) in enumerate(families):
        _report_loop(progress, 50, 98, family_index + 1, len(families), "Offsetting closed profiles")
        boundary = region.buffer(offset_distance, join_style="round").boundary
        converted = _geometry_to_vectors(boundary, vector.layer, vector.source_type)
        if not converted:
            _add_path_warning(
                warnings,
                warning_details,
                "offset_removed_path",
                f"This shape is narrower than the {options.endmill_diameter:g} mm kerf, so it was skipped."
                if options.tool_kind == "laser"
                else f"This shape is smaller than the {options.endmill_diameter:g} mm endmill, so the cutter can't fit inside it and it was skipped.",
                vector,
            )
        toolpaths.extend(converted)
    _report(progress, 100, "Toolpaths ready")
    return toolpaths


def _nest_profiles(solids: list[tuple[Polygon, VectorEntity]]) -> list[tuple[Polygon, VectorEntity]]:
    """Turn overlapping closed profiles into shell+holes regions (even-odd rule).

    A circle inside a circle is a ring of material, not two independent discs, so
    offsetting must shrink the outer edge and grow the inner one. Buffering the
    region with its holes does exactly that for both trace modes.
    """
    # ponytail: O(n^2) containment test; swap in an STRtree if profile counts grow.
    parents: list[int | None] = []
    for index, (polygon, _) in enumerate(solids):
        best: int | None = None
        for other_index, (other, _) in enumerate(solids):
            if other_index == index or not other.contains(polygon):
                continue
            if best is None or other.area < solids[best][0].area:
                best = other_index
        parents.append(best)

    depths: list[int] = []
    for index in range(len(solids)):
        depth, parent = 0, parents[index]
        while parent is not None:
            depth += 1
            parent = parents[parent]
        depths.append(depth)

    regions: list[tuple[Polygon, VectorEntity]] = []
    for index, (polygon, vector) in enumerate(solids):
        if depths[index] % 2:
            continue  # odd depth = a hole in its parent, handled with that parent
        holes = [
            solids[other][0].exterior
            for other, parent in enumerate(parents)
            if parent == index and depths[other] % 2
        ]
        regions.append((Polygon(polygon.exterior, holes), vector))
    return regions


def _finished_edges(vectors: list[VectorEntity], options: ProcessOptions):
    """The cut-side wall of every shape after tool compensation -- the edge the
    machine actually leaves.

    Straight runs stay on the nominal line; only corners the endmill can't reach
    round off to its radius (outside cuts round the part's concave corners, inside
    cuts round the pocket's). A center cut isn't offset, so it hands back the
    nominal line. One curve per shape -- no stock outline, no scrap-side groove
    wall -- which is what 'Replace with Corrected'/corrected export want.
    """
    assembly_tolerance = options.repair_tolerance if options.auto_repair else 1e-9
    profiles = assemble_closed_profiles(vectors, assembly_tolerance)
    if options.trace_mode == TraceMode.CENTER:
        lines = []
        for vector in profiles:
            pts = vector.points
            if vector.closed and pts and pts[0] != pts[-1]:
                pts = pts + [pts[0]]
            if len(pts) >= 2:
                lines.append(LineString(pts))
        return unary_union(lines) if lines else GeometryCollection()
    radius = max(options.endmill_diameter / 2.0, 0.001)
    offset = -radius if options.trace_mode == TraceMode.INSIDE else radius
    solids: list[tuple[Polygon, VectorEntity]] = []
    for vector in profiles:
        if not vector.closed or len(vector.points) < 3:
            continue
        polygon = Polygon(_without_duplicate_close(vector.points))
        if polygon.is_valid and polygon.area > 0:
            solids.append((polygon, vector))
    walls = []
    for region, _ in _nest_profiles(solids):
        # Buffer out-then-back (or in-then-back): the tool sweep's material-side
        # wall. Convex corners survive, unreachable corners fillet to the radius.
        finished = region.buffer(offset, join_style="round").buffer(-offset, join_style="round")
        if not finished.is_empty:
            walls.append(finished.boundary)
    return unary_union(walls) if walls else GeometryCollection()


def _add_path_warning(
    warnings: list[str],
    warning_details: list[ProcessWarning] | None,
    kind: str,
    message: str,
    vector: VectorEntity,
) -> None:
    warnings.append(message)
    if warning_details is None:
        return
    warning_details.append(
        ProcessWarning(
            key=f"{kind}:{vector.id}:{len(warning_details)}",
            kind=kind,
            message=message,
            vector_id=vector.id,
            path=vector.clone(),
        )
    )


def assemble_closed_profiles(vectors: list[VectorEntity], tolerance: float) -> list[VectorEntity]:
    closed = [v.clone() for v in vectors if v.closed and v.is_valid]
    open_vectors = [v.clone() for v in vectors if not v.closed and v.is_valid]
    if not open_vectors:
        return closed

    join_tolerance = max(tolerance, 1e-9)
    assembled: list[VectorEntity] = []
    leftovers: list[VectorEntity] = []
    for chain_points, chain_members in _build_chains(open_vectors, join_tolerance):
        if _chain_is_closed(chain_points, join_tolerance):
            assembled.append(
                VectorEntity(
                    points=chain_points[:-1],
                    closed=True,
                    layer=chain_members[0].layer,
                    source_type="JOINED",
                )
            )
        else:
            leftovers.extend(chain_members)
    return closed + assembled + leftovers


def count_open_profiles(vectors: list[VectorEntity], tolerance: float = 1e-9) -> int:
    return len(_open_chains(vectors, tolerance))


@dataclass(frozen=True, slots=True)
class ProfileIssues:
    """The sketch faults SolidWorks' Check Sketch for Feature reports."""

    open_profiles: int = 0
    duplicates: int = 0
    multi_vertex: int = 0
    self_intersections: int = 0


def _profile_ring(vector: VectorEntity) -> LineString:
    points = list(vector.points)
    if points[0] != points[-1]:
        points = points + [points[0]]
    return LineString(points)


def self_intersecting_profiles(
    vectors: list[VectorEntity], tolerance: float = 1e-9
) -> list[VectorEntity]:
    """Assembled closed profiles whose outline crosses itself.

    SolidWorks rejects a contour that intersects itself even when every segment
    is joined end-to-end, so open segment-soup that chains into a self-crossing
    loop is a fault our open/duplicate/multi-vertex counts miss. Assembling first
    catches the common case where the crossing lives *between* two segments of one
    profile, not inside a single polyline.
    """
    join = max(tolerance, 1e-9)
    return [
        profile
        for profile in assemble_closed_profiles(vectors, join)
        if profile.closed and not _profile_ring(profile).is_simple
    ]


def count_self_intersections(vectors: list[VectorEntity], tolerance: float = 1e-9) -> int:
    return len(self_intersecting_profiles(vectors, tolerance))


def _split_self_crossing_rings(points: list[Point]) -> list[list[Point]]:
    """Sub-loops of a self-crossing outline, split exactly at the crossing point(s).

    unary_union nodes the ring at its self-intersections -- inserting the crossing
    point but MOVING no existing vertex -- and polygonize reassembles the minimal
    closed faces, keeping every lobe. Unlike buffer(0), it reconstructs no area and
    shifts no shared endpoint, so neighbouring profiles that share those endpoints
    stay closed (buffer(0)'s vertex drift was opening them). A bowtie yields one
    ring per lobe; interior faces come out as their own rings, which the even-odd
    nesting pass already expects.
    """
    ring = points if points[0] == points[-1] else points + [points[0]]
    rings: list[list[Point]] = []
    for poly in polygonize(unary_union(LineString(ring))):
        rings.append(list(poly.exterior.coords))
        rings.extend(list(interior.coords) for interior in poly.interiors)
    return rings


def _ring_to_vector(coords: list[Point], layer: str) -> VectorEntity:
    # shapely rings repeat the first point at the end; closed VectorEntity does not.
    return VectorEntity(points=coords[:-1], closed=True, layer=layer, source_type="HEALED")


def heal_self_intersections(
    vectors: list[VectorEntity], tolerance: float = 1e-9
) -> tuple[list[VectorEntity], int]:
    """Replace self-crossing closed profiles with sub-loops split at the crossing.

    Only profiles that fail the self-intersection test are rewritten; every other
    entity (open leftovers, clean loops, invalid stubs) is returned untouched with
    its original identity. Returns the new vector list and how many profiles healed.
    """
    join = max(tolerance, 1e-9)
    invalid = [v for v in vectors if not v.is_valid]
    closed = [v for v in vectors if v.is_valid and v.closed]
    open_vectors = [v for v in vectors if v.is_valid and not v.closed]

    kept: list[VectorEntity] = list(invalid)
    healed = 0

    # Originally-closed profiles that cross themselves.
    for vector in closed:
        if _profile_ring(vector).is_simple:
            kept.append(vector)
            continue
        # No rings back means the noded outline encloses no face at all: a
        # zero-area speck (endpoint snapping welds a sub-tolerance fragment into
        # a crossing loop) or a retraced line. SolidWorks can't cut either, and
        # keeping it made the self-intersection count stick on every re-repair,
        # so deletion IS the heal. A genuine crossing always polygonizes into
        # its lobes and is split instead.
        rings = _split_self_crossing_rings(vector.points)
        kept.extend(_ring_to_vector(ring, vector.layer) for ring in rings)
        healed += 1

    # Open segments that chain into a self-intersecting closed loop.
    for chain_points, members in _build_chains(open_vectors, join):
        if _chain_is_closed(chain_points, join) and not LineString(chain_points).is_simple:
            rings = _split_self_crossing_rings(chain_points)
            kept.extend(_ring_to_vector(ring, members[0].layer) for ring in rings)
            healed += 1
            continue
        kept.extend(members)  # open leftover, or clean loop kept as its own segments

    return kept, healed


def count_profile_issues(vectors: list[VectorEntity], tolerance: float = 1e-9) -> ProfileIssues:
    """Count open profiles, duplicate entities and over-used vertices.

    A duplicate is an entity tracing the same path as an earlier one, ignoring
    direction (and, for closed profiles, start vertex); only the redundant copies
    are counted. A multi-vertex is a point where three or more entity ends meet,
    which SolidWorks rejects because it cannot tell which branch the profile
    follows.
    """
    grid = max(tolerance, 1e-9)

    def key_of(point: Point) -> tuple[int, int]:
        return (round(point[0] / grid), round(point[1] / grid))

    # Count opens/multi-vertex on de-duplicated geometry: an opened entity and
    # its identical copy chain end-to-end into a fake closed loop (masking the
    # open profile), and doubled endpoints inflate the vertex-use counts.
    duplicates = duplicate_vector_indices(vectors, tolerance)
    duplicate_set = set(duplicates)
    deduped = [vector for index, vector in enumerate(vectors) if index not in duplicate_set]

    vertex_uses: Counter[tuple[int, int]] = Counter()
    for vector in deduped:
        if not vector.is_valid or vector.closed:
            continue
        vertex_uses[key_of(vector.points[0])] += 1
        vertex_uses[key_of(vector.points[-1])] += 1
    return ProfileIssues(
        open_profiles=count_open_profiles(deduped, tolerance),
        duplicates=len(duplicates),
        multi_vertex=sum(1 for uses in vertex_uses.values() if uses > 2),
        # ponytail: assembles chains a second time (count_open_profiles already
        # chained once); near-linear spatial-hash chaining, fine at edit cadence.
        # Merge the two passes only if profiling shows it matters on huge files.
        self_intersections=count_self_intersections(deduped, tolerance),
    )


def duplicate_vector_indices(vectors: list[VectorEntity], tolerance: float = 1e-9) -> list[int]:
    """Indices of entities tracing the same path as an earlier one.

    Shared by the fault counter and Repair's duplicate removal so the count
    shown on the canvas always equals the number of entities Repair deletes.
    """
    grid = max(tolerance, 1e-9)
    seen: set[tuple[bool, tuple[tuple[int, int], ...]]] = set()
    duplicates: list[int] = []
    for index, vector in enumerate(vectors):
        if not vector.is_valid:
            continue
        keys = [(round(point[0] / grid), round(point[1] / grid)) for point in vector.points]
        canonical = (vector.closed, _canonical_path(keys, vector.closed))
        if canonical in seen:
            duplicates.append(index)
        else:
            seen.add(canonical)
    return duplicates


def _canonical_path(keys: list[tuple[int, int]], closed: bool) -> tuple[tuple[int, int], ...]:
    """Return a path identity that ignores direction, and start vertex when closed."""
    candidates = [keys, list(reversed(keys))]
    if closed:
        # A closed profile drawn from a different start vertex is the same profile,
        # so rotate each direction to begin at its lowest point before comparing.
        candidates = [path[path.index(min(path)) :] + path[: path.index(min(path))] for path in candidates]
    return min(tuple(path) for path in candidates)


def _open_chains(vectors: list[VectorEntity], tolerance: float) -> list[list[VectorEntity]]:
    open_vectors = [v.clone() for v in vectors if not v.closed and v.is_valid]
    join_tolerance = max(tolerance, 1e-9)
    return [
        members
        for chain_points, members in _build_chains(open_vectors, join_tolerance)
        if not _chain_is_closed(chain_points, join_tolerance)
    ]


def _chain_is_closed(chain_points: list[Point], tolerance: float) -> bool:
    return len(chain_points) >= 4 and _dist(chain_points[0], chain_points[-1]) <= tolerance


def _build_chains(
    open_vectors: list[VectorEntity], tolerance: float
) -> list[tuple[list[Point], list[VectorEntity]]]:
    """Greedily join open vectors end-to-end into chains.

    Candidates are found through a spatial hash of endpoints rather than by
    rescanning every unused vector, which keeps this near-linear. The previous
    scan was O(n^2) and cost seconds on spline-heavy files (thousands of open
    paths), freezing the open-profile count and Process.
    """
    cell_size = max(tolerance, 1e-9)

    def cell_of(point: Point) -> tuple[int, int]:
        return (int(point[0] // cell_size), int(point[1] // cell_size))

    endpoint_cells: dict[tuple[int, int], list[int]] = {}
    for index, vector in enumerate(open_vectors):
        for point in (vector.points[0], vector.points[-1]):
            endpoint_cells.setdefault(cell_of(point), []).append(index)

    def nearby(point: Point) -> list[int]:
        cx, cy = cell_of(point)
        found: list[int] = []
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                found.extend(endpoint_cells.get((cx + ox, cy + oy), ()))
        return found

    used = [False] * len(open_vectors)
    chains: list[tuple[list[Point], list[VectorEntity]]] = []
    for seed_index, seed in enumerate(open_vectors):
        if used[seed_index]:
            continue
        used[seed_index] = True
        chain_points = list(seed.points)
        chain_members = [seed]
        extended = True
        while extended:
            extended = False
            # Only the chain's two free ends can accept another vector, so look
            # for candidates around those two points alone.
            for endpoint in (chain_points[-1], chain_points[0]):
                for candidate_index in nearby(endpoint):
                    if used[candidate_index]:
                        continue
                    match = _match_chain(
                        chain_points, open_vectors[candidate_index].points, tolerance
                    )
                    if match is None:
                        continue
                    chain_points = match
                    chain_members.append(open_vectors[candidate_index])
                    used[candidate_index] = True
                    extended = True
                    break
                if extended:
                    break
        # ponytail: weld a closed chain's seam bit-exact. The greedy join only
        # brings the two free ends within `tolerance` (0.1um); SolidWorks' endpoint
        # merge is tighter, so an unwelded seam reads as an OPEN profile there (5
        # opens on a real corner-split pattern) even though our own count -- using
        # this same loose join -- treats it closed. Snapping the last point onto the
        # first closes it for SolidWorks and leaves every tolerance-based count
        # identical (dist stays 0 <= tolerance).
        if (
            len(chain_points) > 2
            and chain_points[0] != chain_points[-1]
            and _dist(chain_points[0], chain_points[-1]) <= tolerance
        ):
            chain_points[-1] = chain_points[0]
        chains.append((chain_points, chain_members))
    return chains


def split_islands(remaining, board):
    boundary = board.boundary.buffer(1e-7)
    visible = []
    hidden = []
    polygons = _as_polygons(remaining)
    for polygon in polygons:
        if polygon.intersects(boundary):
            visible.append(polygon)
        else:
            hidden.append(polygon)
    return unary_union(visible) if visible else GeometryCollection(), unary_union(hidden) if hidden else GeometryCollection()


def geometry_from_wkt(value: str):
    return wkt.loads(value) if value else GeometryCollection()


# Tool-compensated walls come out of Shapely ~100x over-sampled (measured 0.17mm
# median segment, 12k pts on one shape). Fitting a cubic through that many
# near-touching points self-crosses, and fit_vector_chains' anti-self-cross guard
# then emits one straight segment PER POINT -- 88k pts -> 88k SolidWorks entities.
# Douglas-Peucker at 0.02mm (finer than the 0.2mm flatten and SW's own ~0.05mm
# refit, so no real accuracy lost) collapses each shape to a few hundred points, so
# the fit stays stable and one shape -> one clean spline. preserve_topology keeps
# the ring simple, which is what stops the self-cross in the first place.
_CORRECTED_SIMPLIFY_TOL = 0.02


def _simplified(geometry, tolerance: float = _CORRECTED_SIMPLIFY_TOL):
    if geometry.is_empty or tolerance <= 0:
        return geometry
    return geometry.simplify(tolerance, preserve_topology=True)


def result_export_vectors(result: ProcessResult, tolerance: float = _CORRECTED_SIMPLIFY_TOL) -> list[VectorEntity]:
    corrected = geometry_from_wkt(result.corrected_wkt) if result.corrected_wkt else GeometryCollection()
    return _geometry_to_vectors(_simplified(corrected, tolerance), "CNC_CORRECTED", "POLYLINE")


def result_corrected_vectors_by_layer(result: ProcessResult, tolerance: float = _CORRECTED_SIMPLIFY_TOL) -> list[VectorEntity]:
    """Corrected walls split back onto their source layers, so 'Replace with
    Simulated' keeps each layer separate instead of merging them onto one."""
    vectors: list[VectorEntity] = []
    for name, wkt in result.corrected_by_layer:
        if not wkt:
            continue
        vectors.extend(_geometry_to_vectors(_simplified(geometry_from_wkt(wkt), tolerance), name, "POLYLINE"))
    return vectors


def _buffer_toolpaths(toolpaths: list[VectorEntity], radius: float):
    lines = []
    for vector in toolpaths:
        points = vector.points
        if vector.closed and points and points[0] != points[-1]:
            points = points + [points[0]]
        if len(points) >= 2:
            lines.append(LineString(points))
    if not lines:
        return GeometryCollection()
    return unary_union(lines).buffer(radius, cap_style="round", join_style="round")


def _geometry_to_vectors(geometry, layer: str, source_type: str) -> list[VectorEntity]:
    if geometry.is_empty:
        return []
    vectors: list[VectorEntity] = []
    if isinstance(geometry, LineString):
        points = [(float(x), float(y)) for x, y in geometry.coords]
        closed = len(points) > 2 and points[0] == points[-1]
        if closed:
            points = points[:-1]
        if len(points) >= 2:
            vectors.append(VectorEntity(points=points, closed=closed, layer=layer, source_type=source_type))
    elif isinstance(geometry, MultiLineString):
        for line in geometry.geoms:
            vectors.extend(_geometry_to_vectors(line, layer, source_type))
    elif isinstance(geometry, Polygon):
        vectors.extend(_geometry_to_vectors(geometry.exterior, layer, source_type))
        for ring in geometry.interiors:
            vectors.extend(_geometry_to_vectors(LineString(ring.coords), layer, source_type))
    elif isinstance(geometry, MultiPolygon | GeometryCollection):
        for part in geometry.geoms:
            vectors.extend(_geometry_to_vectors(part, layer, source_type))
    return vectors


def _as_polygons(geometry) -> list[Polygon]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    if isinstance(geometry, GeometryCollection):
        polygons: list[Polygon] = []
        for part in geometry.geoms:
            polygons.extend(_as_polygons(part))
        return polygons
    return []


def _without_duplicate_close(points: list[Point]) -> list[Point]:
    if len(points) > 1 and points[0] == points[-1]:
        return points[:-1]
    return points


def _match_chain(chain: list[Point], candidate: list[Point], tolerance: float) -> list[Point] | None:
    if len(chain) < 2 or len(candidate) < 2:
        return None
    chain_start = chain[0]
    chain_end = chain[-1]
    candidate_start = candidate[0]
    candidate_end = candidate[-1]
    if _dist(chain_end, candidate_start) <= tolerance:
        return chain + candidate[1:]
    if _dist(chain_end, candidate_end) <= tolerance:
        return chain + list(reversed(candidate[:-1]))
    if _dist(chain_start, candidate_end) <= tolerance:
        return candidate[:-1] + chain
    if _dist(chain_start, candidate_start) <= tolerance:
        return list(reversed(candidate[1:])) + chain
    return None


def _dist(a: Point, b: Point) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])
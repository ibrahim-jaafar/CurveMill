"""Auto-trace bitmap images to vector paths using Potrace.

This module provides an interface to Potrace (the open-source bitmap tracer
used by Inkscape) for converting rasterized DXF geometry back into simplified
vector paths.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from io import BytesIO

from .models import Point, SplineEntity
from .progress import ProgressCallback, report as _report

# One traced contour = one cubic B-spline. Each bezier is a 4-point tuple.
Cubic = tuple[Point, Point, Point, Point]

# Regex to parse Potrace SVG output path data
_SVG_PATH_RE = re.compile(r'd="([^"]*)"')
# Potrace wraps all paths in a group transform mapping its units to SVG pixels.
_SVG_TRANSFORM_RE = re.compile(
    r'transform="translate\(([-\d.eE+]+),([-\d.eE+]+)\)\s*scale\(([-\d.eE+]+),([-\d.eE+]+)\)"'
)
_SVG_HEIGHT_RE = re.compile(r'height="([\d.]+)')


def _find_potrace() -> str | None:
    """Locate the Potrace executable on the system.

    Filesystem checks only: spawning probe subprocesses from a GUI worker
    thread hangs/crashes on Windows, so never run potrace just to find it.
    """
    project_tools = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools")
    candidates = [
        shutil.which("potrace"),
        os.path.join(project_tools, "potrace.exe"),
        os.path.join(project_tools, "potrace-1.16.win64", "potrace.exe"),
        r"C:\Program Files\potrace\potrace.exe",
        r"C:\Program Files (x86)\potrace\potrace.exe",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def trace_png(
    png_bytes: bytes,
    tolerance: float = 1.0,
    turdsize: int = 2,
    alphamax: float = 1.0,
    opticurve: bool = True,
    opttolerance: float = 0.2,
    dpi: float = 300.0,
    progress: ProgressCallback | None = None,
) -> list[SplineEntity]:
    """Trace a PNG image to native spline curves using Potrace.

    Args:
        png_bytes: PNG image data bytes.
        tolerance: Curve simplification tolerance (higher = fewer points).
        turdsize: Suppress speckles smaller than this many pixels.
        alphamax: Corner threshold parameter (1.0 = no corners, 0 = many corners).
        opticurve: Optimize the curve path.
        opttolerance: Optimization tolerance.
        dpi: Resolution the PNG was rendered at; maps traced pixels back to mm.
        progress: Optional progress callback.

    Returns:
        List of SplineEntity objects, one native cubic B-spline per contour.

    Raises:
        RuntimeError: If Potrace is not found or tracing fails.
    """
    _report(progress, 0, "Locating Potrace")

    potrace_path = _find_potrace()
    if potrace_path is None:
        raise RuntimeError(
            "Potrace not found. Please install Potrace:\n"
            "  - Windows: Download from https://potrace.sourceforge.net/\n"
            "  - Linux: sudo apt install potrace\n"
            "  - macOS: brew install potrace"
        )

    _report(progress, 10, "Converting PNG to PBM")

    # Convert PNG to PBM (Portable BitMap) using Python's built-in capabilities
    # We write a simple PBM from the PNG data
    pbm_data = _png_to_pbm(png_bytes)

    _report(progress, 25, "Running Potrace trace")

    # Build Potrace command
    cmd = [
        potrace_path,
        "--svg",  # Output SVG format
        "--turdsize", str(turdsize),
        "--alphamax", str(alphamax),
        "--opttolerance", str(opttolerance),
    ]
    # Curve optimization is Potrace's default; --longcurve is the off switch
    # (there is no --opticurve flag).
    if not opticurve:
        cmd.append("--longcurve")

    # Run Potrace with PBM data on stdin
    try:
        result = subprocess.run(
            cmd,
            input=pbm_data,
            capture_output=True,
            text=False,
            timeout=60,
            # Keep Windows from popping a console window for the child process.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Potrace timed out after 60 seconds") from None
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Potrace execution failed: {exc}") from None

    if result.returncode != 0:
        error_msg = result.stderr.decode("utf-8", errors="replace") if result.stderr else "Unknown error"
        raise RuntimeError(f"Potrace failed (exit code {result.returncode}): {error_msg}")

    svg_content = result.stdout.decode("utf-8", errors="replace")

    _report(progress, 60, "Parsing Potrace output")

    # Parse the SVG output into native splines, in mm with DXF Y-up
    splines = _parse_svg_paths(svg_content, px_to_mm=25.4 / dpi)

    _report(progress, 100, f"Trace complete: {len(splines)} curves")
    return splines


def _png_to_pbm(png_bytes: bytes) -> bytes:
    """Convert PNG bytes to PBM (Portable BitMap) format.

    Uses Python's built-in ppm/pbm support via a simple approach:
    reads the PNG, converts to grayscale, thresholds to black/white.
    """
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError(
            "Pillow is required for PNG to PBM conversion. "
            "Install it with: pip install Pillow"
        ) from None

    # The PNG is rendered by this app, not loaded from an untrusted file, so
    # PIL's decompression-bomb guard only produces noise on big boards at 300dpi.
    Image.MAX_IMAGE_PIXELS = None

    with Image.open(BytesIO(png_bytes)) as img:
        # Convert to grayscale
        gray = img.convert("L")
        # Threshold at 50%. PBM stores 1 = black, so dark strokes must map to
        # set bits or Potrace traces the inverted image (background + border).
        bw = gray.point(lambda x: 255 if x < 128 else 0, mode="1")

        # Write PBM format (P4 = binary PBM)
        width, height = bw.size
        pixels = bw.tobytes()

        # PBM header: P4, width height, then raw bits
        header = f"P4\n{width} {height}\n".encode("ascii")
        return header + pixels


def _parse_svg_paths(svg_content: str, px_to_mm: float = 1.0) -> list[SplineEntity]:
    """Parse Potrace SVG output into one native SplineEntity per contour.

    Potrace outputs SVG paths with M/L/C/Z commands. Its bezier curves are kept
    as curves: sampling them into line segments is what made SolidWorks choke,
    because every sample becomes a separate sketch element. The group transform
    that maps Potrace units to image pixels is applied, plus a Y flip (SVG is
    y-down, DXF y-up) and a pixel-to-mm scale. Both are affine, so applying them
    to the bezier control points is exact.
    """
    from ezdxf.math import Bezier4P, Vec2, bezier_to_bspline

    transform = _SVG_TRANSFORM_RE.search(svg_content)
    tx, ty, sx, sy = (
        tuple(float(group) for group in transform.groups()) if transform else (0.0, 0.0, 1.0, 1.0)
    )
    height = _SVG_HEIGHT_RE.search(svg_content)
    height_px = float(height.group(1)) if height else 0.0

    def to_mm(point: Point) -> Vec2:
        x, y = point
        return Vec2(
            (tx + sx * x) * px_to_mm,
            (height_px - (ty + sy * y)) * px_to_mm,
        )

    splines: list[SplineEntity] = []
    # Each path d-attribute may hold several contours (outline + holes).
    contours = [
        contour
        for match in _SVG_PATH_RE.finditer(svg_content)
        for contour in _svg_path_to_contours(match.group(1))
    ]
    for contour in contours:
        curves = [Bezier4P([to_mm(p) for p in cubic]) for cubic in contour]
        bspline = bezier_to_bspline(curves)
        control_points = [(p.x, p.y) for p in bspline.control_points]
        # Potrace only emits closed contours, so the chain returns to its start.
        closed = _dist_sq(control_points[0], control_points[-1]) < 1e-9
        splines.append(SplineEntity(
            control_points=control_points,
            degree=bspline.degree,
            knots=list(bspline.knots()),
            closed=closed,
            layer="0",
        ))

    return splines


def _dist_sq(a: Point, b: Point) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _line_to_cubic(start: Point, end: Point) -> Cubic:
    """Express a straight segment as a cubic bezier (exact, controls at thirds)."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    return (
        start,
        (start[0] + dx / 3.0, start[1] + dy / 3.0),
        (start[0] + 2.0 * dx / 3.0, start[1] + 2.0 * dy / 3.0),
        end,
    )


def _svg_path_to_contours(d: str) -> list[list[Cubic]]:
    """Convert an SVG path d-string to bezier chains, one per subpath.

    Handles M (move), L (line), C (cubic bezier), and Z (close) commands. Lines
    become exact cubics so a contour is one uniform chain of curves. Each M
    starts a new contour: Potrace packs a shape's outer contour and its holes
    into one path element, and joining them would draw a spurious jump segment.
    Implicit commands inherit the relativity of the preceding command (SVG spec).
    """
    contours: list[list[Cubic]] = []
    curves: list[Cubic] = []
    current_pos: Point = (0.0, 0.0)
    start_pos: Point = (0.0, 0.0)

    # Tokenize: split on commands and numbers
    tokens = re.findall(r'[MLCZmlcz]|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', d)
    i = 0
    last_command = ""
    last_relative = False

    while i < len(tokens):
        token = tokens[i]
        if token.upper() in ('M', 'L', 'C', 'Z'):
            command = token.upper()
            relative = token.islower()
            last_relative = relative
            i += 1
            last_command = command
        else:
            command = last_command
            relative = last_relative

        if command == 'Z':
            if curves and _dist_sq(current_pos, start_pos) > 1e-12:
                curves.append(_line_to_cubic(current_pos, start_pos))
            current_pos = start_pos
            continue

        if command == 'M':
            if i + 1 < len(tokens):
                x = float(tokens[i])
                y = float(tokens[i + 1])
                i += 2
                if relative:
                    x += current_pos[0]
                    y += current_pos[1]
                if curves:
                    contours.append(curves)
                curves = []
                current_pos = (x, y)
                start_pos = current_pos
            last_command = 'L'  # Subsequent coords are lines

        elif command == 'L':
            if i + 1 < len(tokens):
                x = float(tokens[i])
                y = float(tokens[i + 1])
                i += 2
                if relative:
                    x += current_pos[0]
                    y += current_pos[1]
                if _dist_sq(current_pos, (x, y)) > 1e-12:
                    curves.append(_line_to_cubic(current_pos, (x, y)))
                current_pos = (x, y)

        elif command == 'C':
            if i + 5 < len(tokens):
                c1x = float(tokens[i])
                c1y = float(tokens[i + 1])
                c2x = float(tokens[i + 2])
                c2y = float(tokens[i + 3])
                ex = float(tokens[i + 4])
                ey = float(tokens[i + 5])
                i += 6
                if relative:
                    c1x += current_pos[0]
                    c1y += current_pos[1]
                    c2x += current_pos[0]
                    c2y += current_pos[1]
                    ex += current_pos[0]
                    ey += current_pos[1]
                curves.append((current_pos, (c1x, c1y), (c2x, c2y), (ex, ey)))
                current_pos = (ex, ey)

        else:
            i += 1  # Skip unknown tokens

    if curves:
        contours.append(curves)
    return contours
"""Render DXF vectors and splines to a PNG image for auto-tracing."""

from __future__ import annotations

from math import ceil

from PySide6.QtCore import QBuffer, Qt
from PySide6.QtGui import QColor, QImage, QImageWriter, QPainter, QPainterPath, QPen

from .models import SplineEntity, VectorEntity
from .progress import ProgressCallback, report as _report, report_loop as _report_loop


def render_to_png(
    vectors: list[VectorEntity],
    splines: list[SplineEntity] | None = None,
    board_width: float = 600.0,
    board_height: float = 400.0,
    dpi: int = 300,
    line_width_mm: float = 0.2,
    progress: ProgressCallback | None = None,
    transparent: bool = False,
) -> bytes:
    """Render all geometry to a PNG image in memory.

    Args:
        vectors: List of polyline vectors to render.
        splines: Optional list of native splines to render.
        board_width: Board width in mm.
        board_height: Board height in mm.
        dpi: Output image resolution.
        line_width_mm: Line thickness in mm for the rendered strokes.
        progress: Optional progress callback.

    Returns:
        PNG image bytes.
    """
    _report(progress, 0, "Preparing render")

    # Convert mm to pixels at the given DPI
    mm_to_px = dpi / 25.4
    width_px = max(1, int(ceil(board_width * mm_to_px)))
    height_px = max(1, int(ceil(board_height * mm_to_px)))

    # Create a high-resolution image with white background
    image = QImage(width_px, height_px, QImage.Format.Format_ARGB32_Premultiplied)
    image.setDotsPerMeterX(int(dpi / 0.0254))
    image.setDotsPerMeterY(int(dpi / 0.0254))
    image.fill(0 if transparent else QColor("#ffffff").rgb())

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # Set up the coordinate system: Y-up like DXF, origin at bottom-left
    painter.scale(mm_to_px, -mm_to_px)
    painter.translate(0, -board_height)

    pen = QPen(QColor("#000000"), line_width_mm)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    total = len(vectors) + len(splines or [])
    count = 0

    # Draw polylines
    for vector in vectors:
        if len(vector.points) < 2:
            continue
        path = QPainterPath()
        path.moveTo(vector.points[0][0], vector.points[0][1])
        for x, y in vector.points[1:]:
            path.lineTo(x, y)
        if vector.closed:
            path.closeSubpath()
        painter.drawPath(path)
        count += 1
        _report_loop(progress, 5, 50, count, total, "Rendering vectors")

    # Draw splines (flattened for rendering)
    for spline in (splines or []):
        if not spline.is_valid:
            continue
        flattened = spline.flatten(0.1)
        if len(flattened.points) < 2:
            continue
        path = QPainterPath()
        path.moveTo(flattened.points[0][0], flattened.points[0][1])
        for x, y in flattened.points[1:]:
            path.lineTo(x, y)
        if flattened.closed:
            path.closeSubpath()
        painter.drawPath(path)
        count += 1
        _report_loop(progress, 50, 95, count, total, "Rendering splines")

    painter.end()

    _report(progress, 98, "Encoding PNG")
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    # QImage.save(device) is broken in PySide6 6.11.1 bindings; QImageWriter works.
    QImageWriter(buffer, b"PNG").write(image)
    buffer.close()
    _report(progress, 100, "Render complete")
    return bytes(buffer.data())
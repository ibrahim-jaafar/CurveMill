"""Generate the SolidWorks add-in toolbar/menu icons.

SolidWorks wants one PNG *per size* (20/32/40/64/96/128 px). The toolbar
IconList files are horizontal sprite strips -- one square cell per button, in
command order (0 = Open, 1 = Send). The MainIconList files are single square
icons for the command group. Re-run this whenever the artwork changes:

    uv run python swaddin/Resources/generate_icons.py

The two buttons share a blue "milled curve" so they read as one family; the
Open button adds an end-mill over the crest, Send adds an arrow feeding into it.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen

SIZES = (20, 32, 40, 64, 96, 128)
BLUE = QColor("#1F6FEB")   # the curve / brand
STEEL = QColor("#37474F")  # the end-mill body
ORANGE = QColor("#FF8C1A")  # the feed arrow / cut accent
OUT = Path(__file__).parent


def _new(size: int) -> tuple[QImage, QPainter]:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    return img, p


def _curve(p: QPainter, s: int) -> None:
    path = QPainterPath()
    path.moveTo(0.10 * s, 0.72 * s)
    path.cubicTo(0.30 * s, 0.34 * s, 0.52 * s, 0.98 * s, 0.90 * s, 0.56 * s)
    pen = QPen(BLUE, max(2.0, 0.15 * s))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.strokePath(path, pen)


def _mill(p: QPainter, s: int) -> None:
    # Vertical end-mill diving onto the crest of the curve, tip -> orange spark.
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(STEEL))
    body = QRectF(0.50 * s, 0.06 * s, 0.20 * s, 0.34 * s)
    p.drawRoundedRect(body, 0.05 * s, 0.05 * s)
    tip = QPainterPath()
    tip.moveTo(0.50 * s, 0.40 * s)
    tip.lineTo(0.70 * s, 0.40 * s)
    tip.lineTo(0.60 * s, 0.54 * s)
    tip.closeSubpath()
    p.drawPath(tip)
    p.setBrush(QBrush(ORANGE))
    p.drawEllipse(QPointF(0.60 * s, 0.58 * s), 0.06 * s, 0.06 * s)


def _arrow(p: QPainter, s: int) -> None:
    # Bold orange arrow feeding a selection into the curve from the left.
    p.setPen(QPen(ORANGE, max(2.0, 0.14 * s), Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawLine(QPointF(0.06 * s, 0.30 * s), QPointF(0.44 * s, 0.30 * s))
    head = QPainterPath()
    head.moveTo(0.34 * s, 0.18 * s)
    head.lineTo(0.50 * s, 0.30 * s)
    head.lineTo(0.34 * s, 0.42 * s)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(ORANGE))
    p.drawPath(head)


def _open_cell(p: QPainter, s: int) -> None:
    _curve(p, s)
    _mill(p, s)


def _send_cell(p: QPainter, s: int) -> None:
    _curve(p, s)
    _arrow(p, s)


def main() -> None:
    for s in SIZES:
        # Toolbar strip: [open | send], one s-px cell each.
        strip = QImage(2 * s, s, QImage.Format.Format_ARGB32)
        strip.fill(Qt.GlobalColor.transparent)
        sp = QPainter(strip)
        sp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for idx, draw in ((0, _open_cell), (1, _send_cell)):
            sp.save()
            sp.translate(idx * s, 0)
            draw(sp, s)
            sp.restore()
        sp.end()
        strip.save(str(OUT / f"curvemill_toolbar_{s}.png"))

        # Main group icon: the Open artwork on its own.
        img, mp = _new(s)
        _open_cell(mp, s)
        mp.end()
        img.save(str(OUT / f"curvemill_main_{s}.png"))
    print("wrote icons to", OUT)


if __name__ == "__main__":
    main()

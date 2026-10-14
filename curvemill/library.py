"""The pattern library: clipart, not projects.

An entry is a piece of artwork — geometry only, no board size, tool or layer
state — so inserting one drops it into the drawing you already have instead of
replacing your session. It reuses the .curvemill JSON writer to avoid a second
serializer; the board/tool half of that payload is simply left empty.

The folder IS the library — no database, so entries stay visible, backupable and
syncable, and files dropped in via Explorer just appear.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPen, QPixmap, QPolygonF

from . import project
from .models import combined_bounds

THUMBNAIL_SIZE = 160


def library_dir() -> Path:
    path = Path.home() / "Documents" / "CurveMill" / "Library"
    path.mkdir(parents=True, exist_ok=True)
    return path


def entries() -> list[Path]:
    return sorted(library_dir().glob(f"*{project.SUFFIX}"))


def save_pattern(name: str, vectors, splines) -> Path:
    path = library_dir() / f"{name}{project.SUFFIX}"
    project.save(path, vectors, splines, [], "", {})
    path.with_suffix(".png").unlink(missing_ok=True)  # a re-save must redraw its tile
    return path


def load_pattern(entry: Path):
    vectors, splines, *_ = project.load(entry)
    return vectors, splines


def thumbnail(entry: Path) -> QPixmap:
    cache = entry.with_suffix(".png")
    if cache.exists() and cache.stat().st_mtime >= entry.stat().st_mtime:
        cached = QPixmap(str(cache))
        if not cached.isNull():
            return cached
    # ponytail: rendered on the UI thread; move to a worker if libraries get big
    # enough that opening the tab stutters.
    pixmap = _render(entry)
    pixmap.save(str(cache), "PNG")
    return pixmap


def _render(entry: Path) -> QPixmap:
    pixmap = QPixmap(THUMBNAIL_SIZE, THUMBNAIL_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    try:
        vectors, splines = load_pattern(entry)
    except (OSError, ValueError, KeyError, TypeError):
        return pixmap  # a broken entry gets a blank tile, not a crash
    paths = [v for v in vectors if len(v.points) >= 2]
    paths += [s.flatten(0.5) for s in splines]
    bounds = combined_bounds(paths)
    if not bounds:
        return pixmap
    min_x, min_y, max_x, max_y = bounds
    margin = 6
    scale = (THUMBNAIL_SIZE - 2 * margin) / max(max_x - min_x, max_y - min_y, 1e-9)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(Qt.GlobalColor.black, 1))
    for path in paths:
        # Y flips: DXF counts up, the screen counts down.
        polygon = QPolygonF(
            [
                QPointF(margin + (x - min_x) * scale, THUMBNAIL_SIZE - margin - (y - min_y) * scale)
                for x, y in path.points
            ]
        )
        if path.closed:
            painter.drawPolygon(polygon)
        else:
            painter.drawPolyline(polygon)
    painter.end()
    return pixmap

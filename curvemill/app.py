from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import gc
import json
from math import atan2, cos, hypot, radians, sin
import sys
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, QRunnable, QSettings, QSize, QThreadPool, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QBrush, QColor, QCursor, QDesktopServices, QFont, QFontMetricsF, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QStackedWidget,
    QTabWidget,
    QPushButton,
    QPlainTextEdit,
    QDoubleSpinBox,
    QSpinBox,
    QInputDialog,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QToolBar,
    QTextEdit,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon, box
from shapely.strtree import STRtree

from . import dimensions
from . import library, project
from .dimensions import Dimension, Feature, OverConstrainedError
from .dxf_io import export_vectors, import_dxf
from .editor import EditorModel, EditorSnapshot
from .geometry import (
    ProfileIssues,
    count_profile_issues,
    fit_vector_chains,
    heal_self_intersections,
    geometry_from_wkt,
    join_spline_fragments,
    process_layers,
    repair_geometry,
    result_corrected_vectors_by_layer,
    to_fit_splines,
)
from .models import (
    Layer,
    LayerJob,
    ProcessOptions,
    ProcessResult,
    ProcessWarning,
    SplineEntity,
    Tool,
    ToolKind,
    TraceMode,
    VectorEntity,
)
from .rasterize import render_to_png


@dataclass(slots=True)
class WarningOverlayState:
    detail: ProcessWarning
    context_vectors: list[VectorEntity]
    preview_bounds: tuple[float, float, float, float]
    width: float
    height: float
    position: QPointF


class WarningBalloonItem(QGraphicsItem):
    BASE_WIDTH = 280.0
    BASE_HEIGHT = 210.0

    def __init__(self, owner: "BoardView", state: WarningOverlayState) -> None:
        super().__init__()
        self.owner = owner
        self.state = state
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setZValue(40)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)

    def boundingRect(self) -> QRectF:  # noqa: N802 - Qt override
        return QRectF(0, 0, self.state.width, self.state.height)

    def set_scene_size(self, width: float, height: float) -> None:
        if abs(self.state.width - width) <= 1e-9 and abs(self.state.height - height) <= 1e-9:
            return
        self.prepareGeometryChange()
        self.state.width = width
        self.state.height = height
        self.update()

    def paint(self, painter: QPainter, _option, _widget=None) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # The canvas is Y-up like DXF; counter-flip screen-oriented balloon content.
        painter.translate(0, self.state.height)
        painter.scale(1, -1)
        painter.scale(self.state.width / self.BASE_WIDTH, self.state.height / self.BASE_HEIGHT)
        painter.setPen(QPen(QColor("#b7791f"), 1.5))
        painter.setBrush(QBrush(QColor("#fff8dc")))
        painter.drawRoundedRect(QRectF(0.75, 0.75, 278.5, 208.5), 6, 6)

        title_font = QFont()
        title_font.setPixelSize(11)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#6b3f00"))
        painter.drawText(QRectF(10, 7, 260, 17), Qt.AlignmentFlag.AlignLeft, f"Path {self.state.detail.vector_id}")

        message_font = QFont()
        message_font.setPixelSize(9)
        painter.setFont(message_font)
        painter.setPen(QColor("#4a3920"))
        painter.drawText(
            QRectF(10, 24, 260, 37),
            Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft,
            self.state.detail.message,
        )

        preview_rect = QRectF(10, 65, 260, 135)
        painter.setPen(QPen(QColor("#d6c7a2"), 1))
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawRect(preview_rect)
        painter.setClipRect(preview_rect.adjusted(2, 2, -2, -2))
        for vector in self.state.context_vectors:
            painter.setPen(QPen(QColor("#9aa0a6"), 1))
            painter.drawPath(_preview_vector_path(vector, self.state.preview_bounds, preview_rect))
        painter.setPen(QPen(QColor("#d62828"), 2.25))
        painter.drawPath(_preview_vector_path(self.state.detail.path, self.state.preview_bounds, preview_rect))
        painter.restore()

    def itemChange(self, change, value):  # noqa: N802 - Qt override
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene() is not None:
            if not self.owner._can_move_warning(self.state.detail.key, value, self.state.width, self.state.height):
                return self.pos()
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene() is not None:
            self.state.position = QPointF(value)
            self.owner._warning_item_moved(self.state.detail.key)
        return super().itemChange(change, value)


def _distance_to_segment_qt(p: QPointF, a: QPointF, b: QPointF) -> float:
    dx, dy = b.x() - a.x(), b.y() - a.y()
    if dx == 0 and dy == 0:
        return ((p.x() - a.x()) ** 2 + (p.y() - a.y()) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / (dx * dx + dy * dy)))
    return ((p.x() - a.x() - t * dx) ** 2 + (p.y() - a.y() - t * dy) ** 2) ** 0.5


class SmartDimItem(QGraphicsItem):
    """A SolidWorks-style board-relative dimension on the Y-up DXF canvas.

    Draws extension lines from the two feature points to a dimension line placed
    ``offset`` scene-units off their midline, with arrowheads and a value label.
    Arrowheads, label and pen stay a constant pixel size at any zoom.
    """

    def __init__(
        self,
        view: QGraphicsView,
        p1: QPointF,
        p2: QPointF,
        axis: str,
        offset: float,
        label: str,
        driven: bool,
        dim_id: int,
        label_along: float = 0.0,
        flippable: bool = False,
        selected: bool = False,
    ) -> None:
        super().__init__()
        # Scene-units-per-pixel is frozen at construction: a boundingRect that
        # tracks the live view zoom corrupts the scene's BSP index (hard crash
        # on the next removeItem). Items are rebuilt on every zoom instead.
        self._unit = _view_units_for_pixels(view, 1.0)
        self.p1 = p1
        self.p2 = p2
        self.axis = axis
        self.offset = offset
        self.label = label
        self.driven = driven
        self.dim_id = dim_id
        self.label_along = label_along
        self.flippable = flippable  # location dim: draw a SolidWorks-style flip glyph
        self.selected = selected
        self.setZValue(22)

    def _endpoints(self) -> tuple[QPointF, QPointF]:
        if self.axis == "x":
            level = (self.p1.y() + self.p2.y()) / 2.0 + self.offset
            return QPointF(self.p1.x(), level), QPointF(self.p2.x(), level)
        level = (self.p1.x() + self.p2.x()) / 2.0 + self.offset
        return QPointF(level, self.p1.y()), QPointF(level, self.p2.y())

    def _label_mid(self) -> QPointF:
        a1, a2 = self._endpoints()
        mid = (a1 + a2) / 2.0
        if self.axis == "x":
            return QPointF(mid.x() + self.label_along, mid.y())
        return QPointF(mid.x(), mid.y() + self.label_along)

    def _label_rect(self) -> QRectF:
        mid = self._label_mid()
        w = self._unit * max(38, 7 * len(self.label))
        h = self._unit * 18
        return QRectF(mid.x() - w / 2, mid.y() - h / 2, w, h)

    def label_rect_contains(self, point: QPointF) -> bool:
        return self._label_rect().contains(point)

    def _glyph_center(self) -> QPointF:
        # Always just right of the label box, so the flip control sits in the same
        # spot whether the dimension is horizontal or vertical (was +axis-side,
        # which put it above vertical-line dims and beside horizontal-line ones).
        mid = self._label_mid()
        gap = self._label_rect().width() / 2.0 + self._unit * 11
        return QPointF(mid.x() + gap, mid.y())

    def _glyph_rect(self) -> QRectF:
        c = self._glyph_center()
        r = self._unit * 11
        return QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)

    def flip_glyph_contains(self, point: QPointF) -> bool:
        return self.flippable and self._glyph_rect().contains(point)

    def contains_point(self, point: QPointF) -> bool:
        """Hit-test for right-click/select: label, flip glyph, or the dim line."""
        if self._label_rect().contains(point) or self.flip_glyph_contains(point):
            return True
        a1, a2 = self._endpoints()
        return _distance_to_segment_qt(point, a1, a2) <= self._unit * 6

    def boundingRect(self) -> QRectF:  # noqa: N802 - Qt override
        a1, a2 = self._endpoints()
        rect = QRectF(self.p1, self.p2).normalized().united(QRectF(a1, a2).normalized())
        rect = rect.united(self._label_rect())
        if self.flippable:
            rect = rect.united(self._glyph_rect())
        return rect.adjusted(-8, -8, 8, 8)

    def paint(self, painter: QPainter, _option, _widget=None) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor("#9ca3af") if self.driven else QColor("#7c3aed")
        a1, a2 = self._endpoints()
        ext_pen = QPen(color, 0, Qt.PenStyle.DashLine)
        ext_pen.setCosmetic(True)
        painter.setPen(ext_pen)
        painter.drawLine(self.p1, a1)
        painter.drawLine(self.p2, a2)
        dim_pen = QPen(color, 0)
        dim_pen.setCosmetic(True)
        painter.setPen(dim_pen)
        painter.drawLine(a1, a2)
        cap = self._unit * 8
        self._arrow(painter, a1, a2, cap, color)
        self._arrow(painter, a2, a1, cap, color)

        mid = self._label_mid()
        if abs(self.label_along) > self._unit:
            # Leader from the dim-line centre to a moved label, like SolidWorks.
            painter.drawLine((a1 + a2) / 2.0, mid)
        font = QFont()
        font.setPixelSize(11)
        painter.setFont(font)
        label_width = QFontMetricsF(font).horizontalAdvance(self.label)
        painter.translate(mid)
        # Scale by scene-units-per-pixel so the label is drawn in pixel space
        # and keeps a constant on-screen size at any zoom (items are rebuilt
        # on zoom, refreshing self._unit).
        painter.scale(self._unit, -self._unit)
        border = QColor("#f97316") if self.selected else (QColor("#6b7280") if self.driven else QColor("#5b21b6"))
        painter.setPen(QPen(border, 2 if self.selected else 0))
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawRoundedRect(QRectF(-label_width / 2 - 4, -9, label_width + 8, 18), 2, 2)
        painter.drawText(QRectF(-label_width / 2, -7, label_width, 14), Qt.AlignmentFlag.AlignCenter, self.label)
        painter.restore()

        if self.flippable:
            self._paint_flip_glyph(painter, color)

    def _paint_flip_glyph(self, painter: QPainter, color: QColor) -> None:
        # A double-headed arrow (SolidWorks' flip control), drawn in pixel space
        # so it keeps a constant on-screen size at any zoom, like the label.
        painter.save()
        painter.translate(self._glyph_center())
        painter.scale(self._unit, -self._unit)
        painter.setPen(QPen(QColor("#94a3b8"), 0))
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawRoundedRect(QRectF(-9, -8, 18, 16), 3, 3)
        pen = QPen(color, 1.4)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QBrush(color))
        painter.drawLine(QPointF(-6, 0), QPointF(6, 0))
        for tip, d in ((QPointF(-6, 0), 1), (QPointF(6, 0), -1)):
            head = QPainterPath(tip)
            head.lineTo(tip.x() + 4 * d, tip.y() + 3)
            head.lineTo(tip.x() + 4 * d, tip.y() - 3)
            head.closeSubpath()
            painter.drawPath(head)
        painter.restore()

    def _arrow(self, painter: QPainter, tip: QPointF, tail: QPointF, size: float, color: QColor) -> None:
        angle = atan2(tip.y() - tail.y(), tip.x() - tail.x())
        left = QPointF(tip.x() - size * cos(angle - 0.35), tip.y() - size * sin(angle - 0.35))
        right = QPointF(tip.x() - size * cos(angle + 0.35), tip.y() - size * sin(angle + 0.35))
        path = QPainterPath(tip)
        path.lineTo(left)
        path.lineTo(right)
        path.closeSubpath()
        painter.setPen(QPen(color, 0))
        painter.setBrush(QBrush(color))
        painter.drawPath(path)


_CANVAS_CONTROLS_QSS = (
    "#canvas_controls { background: #ffffff; border: 1px solid #8f99a5; border-radius: 5px; }"
    " QToolButton { background: #ffffff; border: 0; padding: 5px; margin: 1px; }"
    " QToolButton:hover { background: #e9edf2; border-radius: 3px; }"
    " QToolButton:checked { background: #dceaf5; border-radius: 3px; }"
)


class BoardView(QGraphicsView):
    def __init__(self, editor: EditorModel, parent=None) -> None:
        super().__init__(parent)
        self.editor = editor
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        # Without mouse tracking, mouseMoveEvent only fires while a button is
        # held, so the smart-dimension hover marker never appears on plain hover.
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.context_actions: list[QAction] = []  # filled by MainWindow once its actions exist
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setTransform(QTransform(1, 0, 0, -1, 0, 0))
        self.board_width = 600.0
        self.board_height = 400.0
        self.result: ProcessResult | None = None
        self.tool = "lasso"
        self.show_vectors = True
        self.on_changed = lambda _topology_changed=False, _visuals_current=False: None
        self.on_selection_changed = lambda: None
        self.background_color = QColor("#f3f1eb")
        self._drag_start: QPointF | None = None
        self._box_item: QGraphicsRectItem | None = None
        self._free_lasso_item: QGraphicsPathItem | None = None
        self._free_lasso_points: list[QPointF] = []
        self._mode: str | None = None
        self._pan_start: QPointF | None = None
        self._move_origin: QPointF | None = None
        self._move_delta: tuple[float, float] | None = None
        self._scale_origin: tuple[float, float] | None = None
        self._scale_start_bounds: tuple[float, float, float, float] | None = None
        self._scale_corner: str | None = None
        # Live bounds while a resize is in progress: decorations redraw here so
        # handles stay pixel-sized instead of being scaled with the geometry.
        self._scale_live_bounds: tuple[float, float, float, float] | None = None
        # Rotate-about-selection-centre drag, engaged by hovering just OUTSIDE a
        # corner handle (scale is on the handle, rotate is the ring past it).
        self._rotate_center: tuple[float, float] | None = None
        self._rotate_start_angle: float = 0.0
        self._rotate_angle: float = 0.0
        self._hover_rotate = False  # cursor is currently the rotate-ring cross
        self._vertex_target: tuple[int, int] | None = None
        self._vector_items: dict[int, QGraphicsPathItem] = {}
        # ids currently drawn with the selected pen. refresh_selection restyles only
        # the delta against this set instead of re-penning every item each click.
        self._styled_selected_ids: set[int] = set()
        self._selection_items: list[QGraphicsItem] = []
        self._dim_items: list[SmartDimItem] = []
        self.layout_units = "mm"
        # Smart-dimension tool: two feature picks then a placement click. Callbacks
        # are wired by MainWindow; defaults keep the view standalone-safe.
        self._dim_pick1: tuple[Feature, QPointF] | None = None
        self._dim_pick2: tuple[Feature, QPointF] | None = None
        self._dim_preview_pos: QPointF | None = None
        self._dim_preview_item: SmartDimItem | None = None
        self._dim_hover_item: QGraphicsItem | None = None
        self._dim_pick_items: list[QGraphicsItem] = []
        self._dim_label_drag_id: int | None = None
        self._dim_label_drag_start_cursor: QPointF | None = None
        self._dim_label_drag_start_along: float = 0.0
        self._selected_dim_id: int | None = None  # canvas-selected dim, deletable via Del
        self.dim_context = lambda: None
        # Dims shown on the canvas: the currently-selected layer's dims, each with
        # its own pattern bounds (decoupled from the on-canvas selection).
        self.layer_dims = lambda: []
        self.on_dim_placed = lambda _f1, _f2, _axis, _offset: None
        self.on_dim_edit = lambda _dim_id: None
        self.on_dim_label_moved = lambda _id, _offset: None
        self.on_dim_flip = lambda _dim_id: None
        self.on_dim_delete = lambda _dim_id: None
        self._live_items: list[QGraphicsItem] = []
        # Geometry-only subset of _live_items: scale transforms hit these, not the
        # decorations (which would balloon the handle boxes).
        self._live_geometry: list[QGraphicsItem] = []
        self._live_snapshot: EditorSnapshot | None = None
        self._normal_viewport_update_mode = self.viewportUpdateMode()
        self._warning_states: dict[str, WarningOverlayState] = {}
        self._warning_items: dict[str, WarningBalloonItem] = {}
        self._warning_arrow_items: dict[str, QGraphicsPathItem] = {}
        self._warning_highlight_items: dict[str, QGraphicsPathItem] = {}
        self._warning_source_vectors: list[VectorEntity] = []
        self._warning_tree: STRtree | None = None
        self._warning_tree_vectors: list[VectorEntity] = []
        self._warning_drag_item: WarningBalloonItem | None = None
        self._updating_warning_geometry = False
        # Balloons live in the shared scene but must size to the view actually on
        # screen. The Simulation tab (SimView) has its own zoom, so its balloons
        # were sized for the editor's zoom and came out tiny. sizing_view is swapped
        # to the active view on tab change; defaults to the editor view.
        self.sizing_view: QGraphicsView = self
        self._canvas_controls = QWidget(self)
        self._canvas_controls.setObjectName("canvas_controls")
        self._canvas_controls.setStyleSheet(_CANVAS_CONTROLS_QSS)
        canvas_controls_layout = QHBoxLayout(self._canvas_controls)
        canvas_controls_layout.setContentsMargins(2, 2, 2, 2)
        canvas_controls_layout.setSpacing(1)
        self.vector_toggle_button = QToolButton(self._canvas_controls)
        self.vector_toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.vector_toggle_button.setAutoRaise(False)
        self.fit_content_button = QToolButton(self._canvas_controls)
        self.fit_content_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.fit_content_button.setAutoRaise(False)
        canvas_controls_layout.addWidget(self.vector_toggle_button)
        canvas_controls_layout.addWidget(self.fit_content_button)
        self._canvas_controls.adjustSize()

        self._canvas_counts = QWidget(self)
        self._canvas_counts.setObjectName("canvas_counts")
        self._canvas_counts.setStyleSheet(
            "#canvas_counts { background: #ffffff; border: 1px solid #8f99a5; border-radius: 5px; }"
            " QLabel { border: 0; padding: 0; }"
        )
        counts_layout = QVBoxLayout(self._canvas_counts)
        counts_layout.setContentsMargins(8, 5, 8, 5)
        counts_layout.setSpacing(1)
        self.count_labels: dict[str, QLabel] = {}
        for key, caption in (
            ("open_profiles", "Open profiles"),
            ("duplicates", "Duplicates"),
            ("multi_vertex", "Multiple vertex usage"),
            ("self_intersections", "Self-intersections"),
        ):
            label = QLabel(f"{caption}: 0", self._canvas_counts)
            self.count_labels[key] = label
            counts_layout.addWidget(label)
        self.set_profile_counts(ProfileIssues())
        self._position_canvas_controls()

    def set_profile_counts(self, issues: ProfileIssues) -> None:
        # A non-zero count is a fault the user has to fix before SolidWorks will
        # accept the sketch, so colour it instead of leaving it to be read past.
        for key, caption in (
            ("open_profiles", "Open profiles"),
            ("duplicates", "Duplicates"),
            ("multi_vertex", "Multiple vertex usage"),
            ("self_intersections", "Self-intersections"),
        ):
            count = getattr(issues, key)
            label = self.count_labels[key]
            label.setText(f"{caption}: {count}")
            label.setStyleSheet("color: #b91c1c; font-weight: bold;" if count else "color: #374151;")
        self._position_canvas_controls()

    def set_canvas_actions(self, vector_action: QAction, fit_action: QAction) -> None:
        self.vector_toggle_button.setDefaultAction(vector_action)
        self.vector_toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.vector_toggle_button.setToolTip("Show or hide vectors")
        self.fit_content_button.setDefaultAction(fit_action)
        self.fit_content_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.fit_content_button.setToolTip("Zoom to content")
        self._canvas_controls.adjustSize()
        self._position_canvas_controls()

    def resizeEvent(self, event):  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._position_canvas_controls()

    def drawForeground(self, painter: QPainter, _rect: QRectF) -> None:  # noqa: N802 - Qt override
        # Screen-fixed X/Y gizmo in the bottom-left corner. World matrix off so it
        # ignores pan/zoom and the Y-flip view transform; +Y drawn upward to match.
        painter.save()
        painter.setWorldMatrixEnabled(False)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        h = self.viewport().height()
        ox, oy, ln = 26.0, h - 26.0, 22.0
        for dx, dy, color, txt, tx, ty in (
            (ln, 0.0, "#c0392b", "X", ox + ln + 4, oy + 4),
            (0.0, -ln, "#27ae60", "Y", ox - 4, oy - ln - 6),
        ):
            painter.setPen(QPen(QColor(color), 2))
            painter.drawLine(QPointF(ox, oy), QPointF(ox + dx, oy + dy))
            painter.drawText(QPointF(tx, ty), txt)
        painter.restore()

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802 - Qt override
        super().scrollContentsBy(dx, dy)
        self._position_canvas_controls()

    def _position_canvas_controls(self) -> None:
        self._canvas_controls.adjustSize()
        viewport_rect = self.viewport().geometry()
        x = max(viewport_rect.left() + 8, viewport_rect.right() - self._canvas_controls.width() - 11)
        self._canvas_controls.move(x, viewport_rect.top() + 12)
        self._canvas_controls.show()
        self._canvas_controls.raise_()
        self._canvas_counts.adjustSize()
        self._canvas_counts.move(viewport_rect.left() + 8, viewport_rect.top() + 12)
        self._canvas_counts.show()
        self._canvas_counts.raise_()

    def set_board(self, width: float, height: float) -> None:
        self.board_width = width
        self.board_height = height
        self.redraw()

    def set_result(self, result: ProcessResult | None) -> None:
        self.result = result
        self.redraw()

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self._cancel_drag()
        self._cancel_dim_pick()
        self._set_selected_dim(None)
        # Dims are hidden while the shared scene shows the simulation preview
        # (result set), so entering the dimension tool after a Simulate would
        # leave them invisible until the first placement clears the result.
        # Drop the preview now, exactly as _prepare_live_items does for a drag.
        if tool == "dimension" and self.result is not None:
            self.result = None
            self.redraw()

    def set_show_vectors(self, show: bool) -> None:
        if self.show_vectors == show:
            return
        self.show_vectors = show
        for item in self._vector_items.values():
            item.setVisible(show)
        for item in self._selection_items:
            item.setVisible(show)
        for item in self._dim_items:
            item.setVisible(show)
        self.viewport().update()
        self._position_canvas_controls()

    def wheelEvent(self, event):  # noqa: N802 - Qt override
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        # Anchor the zoom on the cursor by hand: AnchorUnderMouse works from
        # Qt's remembered mouse position, which can lag the real cursor and
        # makes the view drift towards a corner while wheel-zooming.
        anchor = self.mapToScene(event.position().toPoint())
        self.scale(factor, factor)
        drift = self.mapToScene(event.position().toPoint()) - anchor
        self.translate(drift.x(), drift.y())
        if self.editor.selected_target_ids():
            # Save/restore scrollbars: rebuilding dim items can expand the scene
            # rect and shift the scrollbars, causing the view to drift.
            hval = self.horizontalScrollBar().value()
            vval = self.verticalScrollBar().value()
            self.refresh_selection()
            # refresh_selection rebuilt the box/handles at the committed bounds; if a
            # drag is live, snap them back onto the dragged geometry.
            self._reattach_live_decorations()
            self.horizontalScrollBar().setValue(hval)
            self.verticalScrollBar().setValue(vval)
        self._restore_warning_view_geometry()

    def fit_content(self) -> None:
        x1, y1, x2, y2 = _view_bounds(
            self.editor.visible_content_bounds(),
            self.result,
            self.board_width,
            self.board_height,
        )
        width = max(x2 - x1, 1.0)
        height = max(y2 - y1, 1.0)
        padding = max(width, height) * 0.04
        self.fitInView(
            QRectF(x1 - padding, y1 - padding, width + padding * 2, height + padding * 2),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        if self.editor.selected_target_ids():
            self.refresh_selection()
        self._restore_warning_view_geometry()
        self._position_canvas_controls()
        QTimer.singleShot(0, self._position_canvas_controls)

    def ensure_selection_visible(self) -> None:
        # redraw() keeps the old viewport centre so ordinary edits do not jerk the
        # view about, but a layout can teleport the selection (a DXF drawn far from
        # the origin lands on the board), leaving the camera on empty background.
        bounds = self.editor.selected_bounds()
        if bounds is None:
            return
        x1, y1, x2, y2 = bounds
        rect = QRectF(x1, y1, x2 - x1, y2 - y1)
        if self.mapToScene(self.viewport().rect()).boundingRect().intersects(rect):
            return
        self.centerOn(rect.center())
        self._restore_warning_view_geometry()
        self._position_canvas_controls()

    def keyPressEvent(self, event):  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_Escape:
            if self._dim_pick1 is not None:
                self._cancel_dim_pick()
                event.accept()
                return
            if self.editor.selected_ids or self.editor.selected_spline_ids:
                self.editor.clear_selection()
                self.refresh_selection()
                event.accept()
                return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            clicked_item = self.itemAt(event.position().toPoint())
            if isinstance(clicked_item, WarningBalloonItem):
                self._warning_drag_item = clicked_item
                clicked_item.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
                arrow = self._warning_arrow_items.get(clicked_item.state.detail.key)
                if arrow is not None:
                    arrow.setVisible(False)
                super().mousePressEvent(event)
                return
            point = self.mapToScene(event.position().toPoint())
            # The flip glyph is clickable in any tool (like SolidWorks' flip arrows).
            for item in self._dim_items:
                if item.flip_glyph_contains(point):
                    self.on_dim_flip(item.dim_id)
                    return
            if self.tool == "dimension":
                # Clicking a placed dimension's label selects it (Del-able) and starts
                # dragging it along the axis, SolidWorks-style, rather than a new pick.
                if self._dim_pick1 is None:
                    for item in self._dim_items:
                        if item.label_rect_contains(point):
                            self._set_selected_dim(item.dim_id)
                            self._dim_label_drag_id = item.dim_id
                            self._dim_label_drag_start_cursor = point
                            self._dim_label_drag_start_along = item.label_along
                            return
                    self._set_selected_dim(None)  # clicked empty canvas: deselect
                self._handle_dim_click(point)
                return
            bounds = self.editor.selected_bounds()
            tol = _view_tolerance(self) * 1.5
            scale_corner = _scale_corner_at(point, bounds, tol) if bounds else None
            rotate_zone = (
                bounds is not None
                and scale_corner is None
                and _rotate_zone(point, bounds, tol, tol * 2.5)
            )
            vertex_target = _nearest_selected_vertex(self.editor, (point.x(), point.y()), _view_tolerance(self) * 1.5)
            if scale_corner is not None and bounds is not None:
                self._start_scale_drag(point, bounds, scale_corner)
            elif rotate_zone and bounds is not None:
                self._start_rotate_drag(point, bounds)
            elif vertex_target is not None:
                self._mode = "vertex"
                self._drag_start = point
                self._vertex_target = vertex_target
            else:
                prior_selection = {v.id for v in self.editor.selected_vectors()}
                hit = self.editor.select_at((point.x(), point.y()), _view_tolerance(self), additive=True)
                if hit is not None and hit in prior_selection:
                    self.editor.selected_ids = prior_selection
                    self._drag_start = point
                    self.refresh_selection()
                elif hit is not None:
                    if not bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                        self.editor.selected_ids = {hit}
                    self._drag_start = point
                    self.refresh_selection()
                elif (
                    bounds is not None
                    and not bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                    and bounds[0] <= point.x() <= bounds[2]
                    and bounds[1] <= point.y() <= bounds[3]
                ):
                    # Empty space inside the selection drags it -- folds the old
                    # Move tool into Select (drag inside = move, outside = new box).
                    self._start_move_tool_drag(point, additive=False)
                elif self.tool == "free_lasso":
                    # Empty space with the free-lasso tool traces a lasso, same as
                    # box does for the box tool -- both share the move/select path above.
                    if not bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                        self.editor.clear_selection()
                    self._start_free_lasso(point)
                    self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
                else:
                    if not bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                        self.editor.clear_selection()
                    self._mode = "box"
                    self._drag_start = point
                    self._box_item = QGraphicsRectItem()
                    self._box_item.setPen(_cosmetic_pen("#1f77b4", 1.2, Qt.PenStyle.DashLine))
                    self._box_item.setBrush(QBrush(QColor(31, 119, 180, 30)))
                    self.scene.addItem(self._box_item)
                    self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        elif event.button() == Qt.MouseButton.RightButton and self.tool == "dimension":
            # Right-click cancels an in-progress pick without leaving the tool.
            self._cancel_dim_pick()
            event.accept()
        elif event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def contextMenuEvent(self, event):  # noqa: N802 - Qt override
        point = self.mapToScene(event.pos())
        # Right-clicking a dimension offers flip/delete, in any tool (unless a
        # pick is mid-flight in the dimension tool, where right-click cancels it).
        if self._dim_pick1 is None:
            dim_id = self._dim_at(point)
            if dim_id is not None:
                self._show_dim_menu(dim_id, event.globalPos())
                return
        # While dimensioning, right-click already means "cancel this pick".
        if self.tool == "dimension" or not self.context_actions:
            return
        menu = QMenu(self)
        menu.addActions(self.context_actions)
        menu.exec(event.globalPos())

    def _show_dim_menu(self, dim_id: int, global_pos) -> None:
        item = next((i for i in self._dim_items if i.dim_id == dim_id), None)
        menu = QMenu(self)
        if item is not None and item.flippable:
            menu.addAction("Flip direction", lambda: self.on_dim_flip(dim_id))
        menu.addAction("Delete", lambda: self.on_dim_delete(dim_id))
        menu.exec(global_pos)

    def _dim_at(self, point: QPointF) -> int | None:
        for item in self._dim_items:
            if item.contains_point(point):
                return item.dim_id
        return None

    def _set_selected_dim(self, dim_id: int | None) -> None:
        if self._selected_dim_id == dim_id:
            return
        self._selected_dim_id = dim_id
        for item in self._dim_items:  # repaint in place, no rebuild needed
            want = item.dim_id == dim_id
            if item.selected != want:
                item.selected = want
                item.update()

    def mouseDoubleClickEvent(self, event):  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            point = self.mapToScene(event.position().toPoint())
            for item in self._dim_items:
                if item.label_rect_contains(point):
                    self.on_dim_edit(item.dim_id)
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt override
        if self._warning_drag_item is not None:
            super().mouseMoveEvent(event)
            return
        current = self.mapToScene(event.position().toPoint())
        if self._pan_start is not None:
            delta = event.position() - self._pan_start
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            self._pan_start = event.position()
        elif self.tool == "dimension" and self._dim_label_drag_id is not None:
            self._drag_dim_label(current)
        elif self.tool == "dimension":
            self._handle_dim_move(current)
        elif self._mode == "box" and self._drag_start is not None and self._box_item is not None:
            self._box_item.setRect(QRectF(self._drag_start, current).normalized())
        elif self._mode == "free_lasso" and self._drag_start is not None and self._free_lasso_item is not None:
            if not self._free_lasso_points or _point_distance(self._free_lasso_points[-1], current) >= _view_units_for_pixels(self, 2):
                self._free_lasso_points.append(current)
                self._free_lasso_item.setPath(_free_lasso_path(self._free_lasso_points, closed=False))
        elif self._mode == "move" and self._move_origin is not None:
            dx, dy = _constrain_move_delta(self._move_origin, current, event.modifiers())
            self._move_delta = (dx, dy)
            for item in self._live_items:
                item.setPos(dx, dy)
        elif (
            self._mode == "scale"
            and self._scale_start_bounds is not None
            and self._scale_origin is not None
            and self._scale_corner is not None
        ):
            sx, sy = _scale_factors(
                current,
                self._scale_start_bounds,
                self._scale_corner,
                _preserve_resize_aspect(event.modifiers()),
            )
            transform = _scale_transform(self._scale_origin, sx, sy)
            for item in self._live_geometry:
                item.setTransform(transform)
            # Redraw the box/handles at the resized bounds so the handle boxes keep
            # their pixel size (they'd balloon if scaled with the geometry).
            self._scale_live_bounds = _scaled_bounds(self._scale_start_bounds, self._scale_origin, sx, sy)
            self._redraw_selection_decorations()
        elif self._mode == "rotate" and self._rotate_center is not None:
            angle = _rotation_angle(self._rotate_center, current, self._rotate_start_angle, event.modifiers())
            self._rotate_angle = angle
            transform = _rotate_transform(self._rotate_center, angle)
            # Rotation is isometric, so the box/handles spin with the geometry
            # (unlike scale, which redraws them to keep the handle boxes pixel-sized).
            for item in self._live_items:
                item.setTransform(transform)
        else:
            self._update_hover_cursor(current)
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self._dim_label_drag_id is not None:
            dim_id = self._dim_label_drag_id
            item = next((i for i in self._dim_items if i.dim_id == dim_id), None)
            self._dim_label_drag_id = None
            self._dim_label_drag_start_cursor = None
            if item is not None:
                self.on_dim_label_moved(dim_id, item.label_along)
            return
        if event.button() == Qt.MouseButton.LeftButton and self._warning_drag_item is not None:
            item = self._warning_drag_item
            key = item.state.detail.key
            super().mouseReleaseEvent(event)
            self._warning_drag_item = None
            item.setCursor(Qt.CursorShape.OpenHandCursor)
            self._finish_warning_drag(key)
            self.setViewportUpdateMode(self._normal_viewport_update_mode)
            self.viewport().update()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            end = self.mapToScene(event.position().toPoint())
            additive = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            changed = False
            topology_changed = False
            visuals_current = False
            if self._mode == "move" and self._move_origin is not None:
                if self._live_snapshot is not None:
                    dx, dy = self._move_delta or _constrain_move_delta(
                        self._move_origin,
                        end,
                        event.modifiers(),
                    )
                    changed = self.editor.commit_move_from_snapshot(
                        self._live_snapshot,
                        dx,
                        dy,
                    )
                    visuals_current = changed
                    # Dragging part of a drawing away from the rest separates
                    # endpoints that used to meet, so the fault count changes.
                    topology_changed = changed
            elif self._mode == "scale" and self._scale_start_bounds and self._scale_origin and self._scale_corner:
                sx, sy = _scale_factors(
                    end,
                    self._scale_start_bounds,
                    self._scale_corner,
                    _preserve_resize_aspect(event.modifiers()),
                )
                if self._live_snapshot is not None:
                    changed = self.editor.commit_scale_from_snapshot(
                        self._live_snapshot,
                        self._scale_origin,
                        sx,
                        sy,
                    )
                    visuals_current = changed
                    topology_changed = changed
            elif self._mode == "rotate" and self._rotate_center is not None:
                angle = _rotation_angle(self._rotate_center, end, self._rotate_start_angle, event.modifiers())
                if self._live_snapshot is not None:
                    changed = self.editor.commit_rotate_from_snapshot(
                        self._live_snapshot,
                        self._rotate_center,
                        angle,
                    )
                    visuals_current = changed
                    topology_changed = changed
            elif self._mode == "vertex" and self._vertex_target is not None:
                vector_id, vertex_index = self._vertex_target
                self.editor.edit_vertex(vector_id, vertex_index, (end.x(), end.y()))
                changed = True
                topology_changed = True
            elif self._mode == "box":
                rect = QRectF(self._drag_start, end).normalized()
                if (end - self._drag_start).manhattanLength() < 4:
                    self.editor.select_at((end.x(), end.y()), _view_tolerance(self), additive=additive)
                else:
                    self.editor.select_box(rect.left(), rect.top(), rect.right(), rect.bottom(), additive=additive)
            elif self._mode == "free_lasso":
                if self._free_lasso_points:
                    self._free_lasso_points.append(end)
                if _lasso_screen_span(self, self._free_lasso_points) < 6:
                    self.editor.select_at((end.x(), end.y()), _view_tolerance(self), additive=additive)
                else:
                    points = [(point.x(), point.y()) for point in self._free_lasso_points]
                    self.editor.select_lasso(points, additive=additive)
            if visuals_current:
                self._normalize_live_visuals()
            self._cancel_drag(restore_live=False)
            if changed:
                self.on_changed(topology_changed, visuals_current)
            else:
                self.refresh_selection()
        elif event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = None
            self.viewport().unsetCursor()

    def redraw(self) -> None:
        old_scene_rect = QRectF(self.scene.sceneRect())
        preserved_center = (
            self.mapToScene(self.viewport().rect().center())
            if self.scene.items()
            else None
        )
        self._box_item = None
        self._free_lasso_item = None
        self._free_lasso_points = []
        self._vector_items.clear()
        self._selection_items.clear()
        self._dim_items.clear()
        self._dim_preview_item = None
        self._dim_hover_item = None
        self._dim_pick_items.clear()
        self._live_items.clear()
        self._warning_items.clear()
        self._warning_arrow_items.clear()
        self._warning_highlight_items.clear()
        self.scene.clear()
        self.scene.setBackgroundBrush(QBrush(self.background_color))
        board_fill = self.background_color if self.result else QColor("#c89b6a")
        board = self.scene.addRect(0, 0, self.board_width, self.board_height, QPen(QColor("#7f5539"), 0), QBrush(board_fill))
        board.setZValue(-10)
        if self.result:
            _add_geometry(self.scene, geometry_from_wkt(self.result.remaining_wkt), QColor("#d3a96f"), QColor("#8a5a36"), -5)
            _add_geometry(self.scene, geometry_from_wkt(self.result.removed_wkt), self.background_color, self.background_color, -4)
            # Darker = deeper. depth_cuts is sorted shallowest first, so deeper
            # layers paint last and win where cuts overlap. One depth needs no
            # shading — a single flat cut reads better as plain background.
            cuts = self.result.depth_cuts if len({c[1] for c in self.result.depth_cuts}) > 1 else []
            deepest = max((depth for _, depth, _ in cuts), default=0.0)
            for index, (_, depth, wkt_value) in enumerate(cuts):
                shade = _depth_shade(depth, deepest)
                _add_geometry(self.scene, geometry_from_wkt(wkt_value), shade, shade, -4 + index / (len(cuts) + 1))
            # V-carve hazards ride above the depth bands: where the tool can't cut a
            # clean floor (too wide) or reach the bottom (too narrow for its tip).
            for kind, wkt_value in self.result.vcarve_hazards:
                color = _VCARVE_HAZARD_COLORS.get(kind)
                if color is not None:
                    _add_geometry(self.scene, geometry_from_wkt(wkt_value), color, color, -2.5)
        selected_ids = self.editor.selected_target_ids()
        for vector in self.editor.visible_vectors():
            selected = vector.id in selected_ids
            pen = _selected_vector_pen() if selected else _vector_pen()
            path = _vector_path(vector)
            item = self.scene.addPath(path, pen)
            item.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
            item.setZValue(5 if selected else 1)
            item.setVisible(self.show_vectors)
            self._vector_items[vector.id] = item
        # Render native splines by flattening them for display
        for spline in self.editor.visible_splines():
            selected = spline.id in selected_ids
            pen = _selected_vector_pen() if selected else _vector_pen()
            flattened = spline.flatten(0.5)
            path = _vector_path(flattened)
            item = self.scene.addPath(path, pen)
            # Static curve: cache its rasterization so the rubber-band drag's
            # full-viewport repaints are cheap blits, not re-strokes of every path.
            item.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
            item.setZValue(5 if selected else 1)
            item.setVisible(self.show_vectors)
            self._vector_items[spline.id] = item
        # Items above were penned inline by selected-state; keep the delta tracker
        # (used by refresh_selection) in sync with what was just drawn.
        self._styled_selected_ids = {vid for vid in selected_ids if vid in self._vector_items}
        self._draw_selection_decorations()
        self._rebuild_warning_overlays()
        self._update_scene_rect(preserve_center=False)
        if preserved_center is not None and self.scene.sceneRect() != old_scene_rect:
            self.centerOn(preserved_center)
        self._position_canvas_controls()
        self.on_selection_changed()

    def refresh_selection(self) -> None:
        selected_ids = self.editor.selected_target_ids()
        # Restyle only the items whose selected-state actually flipped. Re-penning
        # every item each click cost ~400ms on a 2000-item scene (setPen re-strokes
        # the path, setZValue reindexes z-order) -- the click/lasso-release delay.
        # The delta is normally one or two items.
        for vector_id in self._styled_selected_ids - selected_ids:
            item = self._vector_items.get(vector_id)
            if item is not None:
                item.setPen(_vector_pen())
                item.setZValue(1)
        for vector_id in selected_ids - self._styled_selected_ids:
            item = self._vector_items.get(vector_id)
            if item is not None:
                item.setPen(_selected_vector_pen())
                item.setZValue(5)
        self._styled_selected_ids = {vid for vid in selected_ids if vid in self._vector_items}
        self._redraw_selection_decorations()
        self.viewport().update()
        self._position_canvas_controls()
        self.on_selection_changed()

    def _redraw_selection_decorations(self) -> None:
        for item in self._selection_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self._selection_items.clear()
        self._draw_selection_decorations()

    def _draw_selection_decorations(self) -> None:
        selected_vectors = self.editor.selected_vectors()
        # Mid-resize the model still holds the pre-scale points, so the vertex dots
        # would sit at stale spots — skip them until the resize commits.
        if self._scale_live_bounds is None and len(selected_vectors) == 1:
            vertex_size = _view_units_for_pixels(self, 7)
            for x, y in selected_vectors[0].points:
                vertex_item = self.scene.addEllipse(
                    x - vertex_size / 2,
                    y - vertex_size / 2,
                    vertex_size,
                    vertex_size,
                    _cosmetic_pen("#e63946", 1.0),
                    QBrush(QColor("#e63946")),
                )
                self._selection_items.append(vertex_item)
        # Bounds box, handles and layout guides must include selected splines, or
        # an all-spline selection shows red curves with no bounding box or guides.
        bounds = self._scale_live_bounds or self.editor.selected_bounds()
        if bounds:
            x1, y1, x2, y2 = bounds
            handle_pen = _cosmetic_pen("#222222", 1.0, Qt.PenStyle.DashLine)
            bounds_item = self.scene.addRect(x1, y1, x2 - x1, y2 - y1, handle_pen)
            self._selection_items.append(bounds_item)
            size = _view_units_for_pixels(self, 10)
            for hx, hy in ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):
                handle = self.scene.addRect(
                    hx - size / 2,
                    hy - size / 2,
                    size,
                    size,
                    _cosmetic_pen("#222222", 1.0),
                    QBrush(QColor("#ffffff")),
                )
                self._selection_items.append(handle)
        for item in self._selection_items:
            item.setVisible(self.show_vectors)
        self._rebuild_dim_items()

    # -- Smart dimension tool ------------------------------------------------

    def _rebuild_dim_items(self) -> None:
        for item in self._dim_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self._dim_items.clear()
        shown_ids: set[int] = set()
        for dim, pat, brd in self.layer_dims():
            p1 = QPointF(*dimensions.feature_point(dim.feat1, pat, brd))
            p2 = QPointF(*dimensions.feature_point(dim.feat2, pat, brd))
            # Label from a live measurement, not dim.value: a corner-handle scale
            # rebuilds the items before the store is remeasured.
            label = self._dim_label(dimensions.measure(dim, pat, brd), dim.driving)
            item = SmartDimItem(
                self, p1, p2, dim.axis, dim.label_offset, label, not dim.driving, dim.id,
                dim.label_along,
                flippable=dim.is_position and dim.driving,
                selected=dim.id == self._selected_dim_id,
            )
            # Hide dims while the simulation preview is on the canvas (result set);
            # they clutter the as-milled view and mean nothing against the cut stock.
            item.setVisible(self.show_vectors and self.result is None)
            self.scene.addItem(item)
            self._dim_items.append(item)
            shown_ids.add(dim.id)
        # A canvas-selected dim that scrolled out of view (layer switched, deleted)
        # must not linger as a phantom Del target.
        if self._selected_dim_id is not None and self._selected_dim_id not in shown_ids:
            self._selected_dim_id = None

    def zoom_to_dim(self, dim_id: int) -> None:
        item = next((i for i in self._dim_items if i.dim_id == dim_id), None)
        if item is None:
            return
        rect = item.boundingRect()
        pad = max(rect.width(), rect.height()) * 0.6
        self.fitInView(rect.adjusted(-pad, -pad, pad, pad), Qt.AspectRatioMode.KeepAspectRatio)
        # Rebuild pixel-frozen decorations (handles, arrows, labels) at the new zoom.
        self.refresh_selection()
        self._restore_warning_view_geometry()
        self._position_canvas_controls()

    def _dim_label(self, value: float, driving: bool) -> str:
        text = _format_layout_value(abs(value), self.layout_units)
        return text if driving else f"({text})"

    def _handle_dim_click(self, point: QPointF) -> None:
        if self._dim_pick2 is not None:
            axis, offset = self._resolve_dim_placement(point)
            feat1 = self._dim_pick1[0]
            feat2 = self._dim_pick2[0]
            self._cancel_dim_pick()
            self.on_dim_placed(feat1, feat2, axis, offset)
            return
        # A double-click on a label edits it; a single click there should not
        # start a new pick underneath the cursor.
        for item in self._dim_items:
            if item.label_rect_contains(point):
                return
        context = self.dim_context()
        if context is None:
            return
        pat, brd = context
        feat = dimensions.nearest_feature(point.x(), point.y(), pat, brd, _view_tolerance(self) * 1.5)
        if feat is None:
            self._cancel_dim_pick()
            return
        anchor = QPointF(*dimensions.feature_point(feat, pat, brd))
        # Picked features keep a green marker until the dimension is placed
        # or the pick is cancelled (Esc), SolidWorks-style.
        self._dim_pick_items.append(self._dim_feature_marker(feat, pat, brd, "#16a34a"))
        if self._dim_pick1 is None:
            self._dim_pick1 = (feat, anchor)
        else:
            self._dim_pick2 = (feat, anchor)
            self._dim_preview_pos = point
            self._refresh_dim_preview()

    def _drag_dim_label(self, current: QPointF) -> None:
        item = next((i for i in self._dim_items if i.dim_id == self._dim_label_drag_id), None)
        if item is None or self._dim_label_drag_start_cursor is None:
            return
        delta = current - self._dim_label_drag_start_cursor
        along = delta.x() if item.axis == "x" else delta.y()
        item.prepareGeometryChange()
        item.label_along = self._dim_label_drag_start_along + along
        item.update()

    def _handle_dim_move(self, current: QPointF) -> None:
        if self._dim_pick2 is not None:
            self._dim_preview_pos = current
            self._refresh_dim_preview()
            return
        context = self.dim_context()
        if context is None:
            self._set_dim_hover(None)
            return
        pat, brd = context
        feat = dimensions.nearest_feature(current.x(), current.y(), pat, brd, _view_tolerance(self) * 1.5)
        if feat is not None and any(pick is not None and pick[0] == feat for pick in (self._dim_pick1, self._dim_pick2)):
            feat = None  # already picked: keep its green marker visible
        self._set_dim_hover(feat, pat, brd)

    def _resolve_dim_placement(self, cursor: QPointF) -> tuple[str, float]:
        p1 = self._dim_pick1[1]
        p2 = self._dim_pick2[1]
        dx = abs(p2.x() - p1.x())
        dy = abs(p2.y() - p1.y())
        if dy <= 1e-9:
            axis = "x"
        elif dx <= 1e-9:
            axis = "y"
        else:
            mid = (p1 + p2) / 2.0
            axis = "x" if abs(cursor.y() - mid.y()) >= abs(cursor.x() - mid.x()) else "y"
        if axis == "x":
            offset = cursor.y() - (p1.y() + p2.y()) / 2.0
        else:
            offset = cursor.x() - (p1.x() + p2.x()) / 2.0
        return axis, offset

    def _refresh_dim_preview(self) -> None:
        if self._dim_preview_item is not None and self._dim_preview_item.scene() is self.scene:
            self.scene.removeItem(self._dim_preview_item)
        self._dim_preview_item = None
        if self._dim_pick1 is None or self._dim_pick2 is None or self._dim_preview_pos is None:
            return
        context = self.dim_context()
        if context is None:
            return
        pat, brd = context
        axis, offset = self._resolve_dim_placement(self._dim_preview_pos)
        feat1 = self._dim_pick1[0]
        feat2 = self._dim_pick2[0]
        value = dimensions.feature_coord(feat2, pat, brd, axis) - dimensions.feature_coord(feat1, pat, brd, axis)
        item = SmartDimItem(
            self,
            self._dim_pick1[1],
            self._dim_pick2[1],
            axis,
            offset,
            self._dim_label(value, True),
            False,
            -1,
        )
        self.scene.addItem(item)
        self._dim_preview_item = item

    def _dim_feature_marker(self, feat: Feature, pat, brd, color: str) -> QGraphicsItem:
        if dimensions.is_edge(feat):
            (x1, y1), (x2, y2) = dimensions.edge_segment(feat, pat, brd)
            marker = self.scene.addLine(x1, y1, x2, y2, _cosmetic_pen(color, 3.0))
        else:
            x, y = dimensions.feature_point(feat, pat, brd)
            r = _view_units_for_pixels(self, 8)
            fill = QColor(color)
            fill.setAlpha(70)
            marker = self.scene.addEllipse(
                x - r / 2,
                y - r / 2,
                r,
                r,
                _cosmetic_pen(color, 1.5),
                QBrush(fill),
            )
        marker.setZValue(23)
        return marker

    def _set_dim_hover(self, feat: Feature | None, pat=None, brd=None) -> None:
        if self._dim_hover_item is not None and self._dim_hover_item.scene() is self.scene:
            self.scene.removeItem(self._dim_hover_item)
        self._dim_hover_item = None
        if feat is None:
            return
        self._dim_hover_item = self._dim_feature_marker(feat, pat, brd, "#7c3aed")

    def _cancel_dim_pick(self) -> None:
        self._dim_pick1 = None
        self._dim_pick2 = None
        self._dim_preview_pos = None
        if self._dim_preview_item is not None and self._dim_preview_item.scene() is self.scene:
            self.scene.removeItem(self._dim_preview_item)
        self._dim_preview_item = None
        for item in self._dim_pick_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self._dim_pick_items.clear()
        self._set_dim_hover(None)

    def _start_move_tool_drag(self, point: QPointF, additive: bool) -> None:
        # Splines have their own selection set; checking only selected_ids made
        # the move tool drop a curve multi-selection and re-select one entity.
        if not self.editor.selected_ids and not self.editor.selected_spline_ids:
            hit = self.editor.select_at((point.x(), point.y()), _view_tolerance(self), additive=additive)
            if hit is None:
                return
            self.refresh_selection()
        self._mode = "move"
        self._move_origin = point
        self._drag_start = point
        self._live_snapshot = self.editor.snapshot()
        self._prepare_live_items()

    def _start_scale_drag(self, point: QPointF, bounds: tuple[float, float, float, float], corner: str) -> None:
        self._mode = "scale"
        self._drag_start = point
        self._scale_start_bounds = bounds
        self._scale_corner = corner
        self._scale_origin = _opposite_corner(bounds, corner)
        self._live_snapshot = self.editor.snapshot()
        self._prepare_live_items()

    def _start_rotate_drag(self, point: QPointF, bounds: tuple[float, float, float, float]) -> None:
        x1, y1, x2, y2 = bounds
        self._mode = "rotate"
        self._drag_start = point
        self._rotate_center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
        self._rotate_start_angle = atan2(point.y() - self._rotate_center[1], point.x() - self._rotate_center[0])
        self._rotate_angle = 0.0
        self._live_snapshot = self.editor.snapshot()
        self._prepare_live_items()

    def _update_hover_cursor(self, point: QPointF) -> None:
        """Show a cross over the rotate ring (just outside a corner handle) so the
        gesture is discoverable. Idempotent: only touches the cursor on entering or
        leaving the ring, so it never fights the pan/handle cursors."""
        want_rotate = False
        bounds = self.editor.selected_bounds()
        if bounds is not None and self.tool != "dimension":
            tol = _view_tolerance(self) * 1.5
            if _scale_corner_at(point, bounds, tol) is None:
                want_rotate = _rotate_zone(point, bounds, tol, tol * 2.5)
        if want_rotate and not self._hover_rotate:
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
            self._hover_rotate = True
        elif not want_rotate and self._hover_rotate:
            self.viewport().unsetCursor()
            self._hover_rotate = False

    def _start_free_lasso(self, point: QPointF) -> None:
        self._mode = "free_lasso"
        self._drag_start = point
        self._free_lasso_points = [point]
        self._free_lasso_item = QGraphicsPathItem(_free_lasso_path(self._free_lasso_points, closed=False))
        self._free_lasso_item.setPen(_cosmetic_pen("#1f77b4", 1.2, Qt.PenStyle.DashLine))
        self._free_lasso_item.setBrush(QBrush(QColor(31, 119, 180, 26)))
        self._free_lasso_item.setZValue(25)
        self.scene.addItem(self._free_lasso_item)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

    def _prepare_live_items(self) -> None:
        if self.result is not None:
            self.result = None
            self.redraw()
        selected_ids = self.editor.selected_target_ids()
        self._live_geometry = [
            item
            for vector_id, item in self._vector_items.items()
            if vector_id in selected_ids
        ]
        self._live_items = list(self._live_geometry)
        self._live_items.extend(self._selection_items)
        if self._live_items:
            self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

    def _reattach_live_decorations(self) -> None:
        """Re-sync the selection box/handles to an in-progress drag.

        A wheel-zoom mid-drag runs refresh_selection to keep the handles pixel-sized,
        but that rebuilds them at the committed model bounds and detaches them from
        _live_items -- so a move/rotate would leave the "shaded line" frozen at the
        pre-drag spot until release. Re-register the fresh decorations and re-apply
        the current drag offset. (Scale needs nothing: its own move handler already
        redraws them at the live bounds each frame.)
        """
        if self._mode not in ("move", "rotate"):
            return
        self._live_items = list(self._live_geometry)
        self._live_items.extend(self._selection_items)
        if self._mode == "move" and self._move_delta is not None:
            dx, dy = self._move_delta
            for item in self._selection_items:
                item.setPos(dx, dy)
        elif self._mode == "rotate" and self._rotate_center is not None:
            transform = _rotate_transform(self._rotate_center, self._rotate_angle)
            for item in self._selection_items:
                item.setTransform(transform)

    def _normalize_live_visuals(self) -> None:
        vectors_by_id = {vector.id: vector for vector in self.editor.vectors}
        # Splines are first-class canvas items too: skipping them left the
        # stale pre-commit path on screen after a handle resize or move.
        splines_by_id = {spline.id: spline for spline in self.editor.splines}
        for entity_id in self.editor.selected_target_ids():
            item = self._vector_items.get(entity_id)
            if item is None:
                continue
            vector = vectors_by_id.get(entity_id)
            if vector is None:
                spline = splines_by_id.get(entity_id)
                if spline is None:
                    continue
                vector = spline.flatten(0.5)  # same rendering as redraw()
            item.setPos(0, 0)
            item.setTransform(QTransform())
            item.setPath(_vector_path(vector))
        for item in self._selection_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self._selection_items.clear()
        self._draw_selection_decorations()

    def _cancel_drag(self, restore_live: bool = True) -> None:
        if self._box_item is not None and self._box_item.scene() is self.scene:
            self.scene.removeItem(self._box_item)
        if self._free_lasso_item is not None and self._free_lasso_item.scene() is self.scene:
            self.scene.removeItem(self._free_lasso_item)
        if restore_live:
            for item in self._live_items:
                item.setPos(0, 0)
                item.setTransform(QTransform())
        self.setViewportUpdateMode(self._normal_viewport_update_mode)
        self._drag_start = None
        self._box_item = None
        self._free_lasso_item = None
        self._free_lasso_points = []
        self._mode = None
        self._pan_start = None
        self._move_origin = None
        self._move_delta = None
        self._scale_origin = None
        self._scale_start_bounds = None
        self._scale_corner = None
        self._scale_live_bounds = None
        self._rotate_center = None
        self._rotate_angle = 0.0
        self._live_items = []
        self._live_geometry = []
        self._live_snapshot = None
        self._vertex_target = None
        if restore_live:
            # Live bounds are cleared above; redraw the box/handles at the model
            # bounds so a tool switch mid-resize doesn't leave them stretched.
            self._redraw_selection_decorations()

    def _update_scene_rect(self, preserve_center: bool = True) -> None:
        preserved_center = self.mapToScene(self.viewport().rect().center()) if preserve_center else None
        bounds = _view_bounds(self.editor.visible_content_bounds(), self.result, self.board_width, self.board_height)
        x1, y1, x2, y2 = bounds
        for state in self._warning_states.values():
            x1 = min(x1, state.position.x())
            y1 = min(y1, state.position.y())
            x2 = max(x2, state.position.x() + state.width)
            y2 = max(y2, state.position.y() + state.height)
        width = max(x2 - x1, 1.0)
        height = max(y2 - y1, 1.0)
        padding = max(width, height) * 0.35 + 100
        desired_rect = QRectF(
            x1 - padding,
            y1 - padding,
            width + padding * 2,
            height + padding * 2,
        )
        current_rect = self.scene.sceneRect()
        content_rect = QRectF(x1, y1, width, height)
        if preserve_center and current_rect.isValid() and not current_rect.isNull():
            # Keep existing pan room on edges that still contain the content.  With the
            # y-up canvas transform, growing unused padding can otherwise shift the view.
            scene_rect = QRectF(current_rect)
            if content_rect.left() < current_rect.left():
                scene_rect.setLeft(desired_rect.left())
            if content_rect.top() < current_rect.top():
                scene_rect.setTop(desired_rect.top())
            if content_rect.right() > current_rect.right():
                scene_rect.setRight(desired_rect.right())
            if content_rect.bottom() > current_rect.bottom():
                scene_rect.setBottom(desired_rect.bottom())
        else:
            scene_rect = desired_rect
        self.scene.setSceneRect(scene_rect)
        # Only recenter when the rect actually grew. Otherwise centerOn round-trips
        # the viewport centre through integer scrollbars and nudges the view a pixel
        # or two every commit -- the little pan seen after a lasso-move release.
        if preserved_center is not None and scene_rect != current_rect:
            self.centerOn(preserved_center)
        self._position_canvas_controls()

    def paste_scene_position(self) -> tuple[float, float]:
        viewport_position = self.viewport().mapFromGlobal(QCursor.pos())
        if not self.viewport().rect().contains(viewport_position):
            viewport_position = self.viewport().rect().center()
        point = self.mapToScene(viewport_position)
        return point.x(), point.y()

    def set_warning_source(self, vectors: list[VectorEntity]) -> None:
        self._warning_source_vectors = [vector.clone() for vector in vectors]
        self._warning_tree = None
        self._warning_tree_vectors = []

    def has_warning_balloon(self, key: str) -> bool:
        return key in self._warning_states

    def warning_balloon_is_visible(self, key: str) -> bool:
        balloon = self._warning_items.get(key)
        if balloon is None:
            return False
        view = self.sizing_view
        viewport_bounds = QRectF(view.viewport().rect()).adjusted(8, 8, -8, -8)
        balloon_bounds = view.viewportTransform().mapRect(balloon.sceneBoundingRect())
        return viewport_bounds.contains(balloon_bounds)

    def reveal_warning_balloon(self, key: str) -> bool:
        balloon = self._warning_items.get(key)
        if balloon is None:
            return False
        if self.warning_balloon_is_visible(key):
            return True
        self.sizing_view.centerOn(balloon.sceneBoundingRect().center())
        self._position_canvas_controls()
        self.sizing_view.viewport().update()
        return self.warning_balloon_is_visible(key)

    def show_warning_balloon(self, detail: ProcessWarning) -> None:
        if detail.key in self._warning_states:
            return
        self._add_warning_state(detail)
        self.redraw()

    def show_warning_balloons(self, details: list[ProcessWarning]) -> None:
        changed = False
        for detail in details:
            if detail.key in self._warning_states:
                continue
            self._add_warning_state(detail)
            changed = True
        if changed:
            self.redraw()

    def _add_warning_state(self, detail: ProcessWarning) -> None:
        context, preview_bounds = self._warning_context(detail.path)
        width, height = self._warning_scene_size()
        position = self._initial_warning_position(detail.path, width, height)
        self._warning_states[detail.key] = WarningOverlayState(
            detail=detail.clone(),
            context_vectors=context,
            preview_bounds=preview_bounds,
            width=width,
            height=height,
            position=position,
        )

    def remove_warning_balloon(self, key: str) -> None:
        if self._warning_states.pop(key, None) is not None:
            self.redraw()

    def clear_warning_balloons(self) -> None:
        if not self._warning_states:
            return
        self._warning_states.clear()
        self.redraw()

    def _warning_scene_size(self) -> tuple[float, float]:
        view = self.sizing_view
        origin = view.mapToScene(0, 0)
        width_point = view.mapToScene(int(WarningBalloonItem.BASE_WIDTH), 0)
        height_point = view.mapToScene(0, int(WarningBalloonItem.BASE_HEIGHT))
        return (
            max(abs(width_point.x() - origin.x()), 1e-9),
            max(abs(height_point.y() - origin.y()), 1e-9),
        )

    def _warning_view_positions(self) -> dict[str, QPointF]:
        transform = self.sizing_view.viewportTransform()
        return {
            key: transform.map(state.position)
            for key, state in self._warning_states.items()
        }

    def _restore_warning_view_geometry(self, _view_positions: dict[str, QPointF] | None = None) -> None:
        if not self._warning_states:
            return
        transform = self.sizing_view.viewportTransform()
        desired_positions = {
            key: transform.map(state.position)
            for key, state in self._warning_states.items()
        }
        resolved_positions = self._spread_warning_view_positions(desired_positions)
        inverse, invertible = transform.inverted()
        if not invertible:
            return
        width, height = self._warning_scene_size()
        self._updating_warning_geometry = True
        try:
            for key, state in self._warning_states.items():
                balloon = self._warning_items.get(key)
                if balloon is not None:
                    balloon.set_scene_size(width, height)
                else:
                    state.width = width
                    state.height = height
                state.position = inverse.map(resolved_positions[key])
            for key, balloon in self._warning_items.items():
                balloon.setPos(self._warning_states[key].position)
        finally:
            self._updating_warning_geometry = False
        for key in self._warning_states:
            self._update_warning_arrow(key)
        warning_bounds = QRectF()
        for balloon in self._warning_items.values():
            warning_bounds = warning_bounds.united(balloon.sceneBoundingRect())
        if not warning_bounds.isNull() and not self.scene.sceneRect().contains(warning_bounds):
            margin = max(width, height) * 0.25
            self.scene.setSceneRect(
                self.scene.sceneRect().united(warning_bounds.adjusted(-margin, -margin, margin, margin))
            )
        self.sizing_view.viewport().update()
        self._position_canvas_controls()

    def _spread_warning_view_positions(self, desired: dict[str, QPointF]) -> dict[str, QPointF]:
        resolved: dict[str, QPointF] = {}
        occupied: list[QRectF] = []
        width = WarningBalloonItem.BASE_WIDTH
        height = WarningBalloonItem.BASE_HEIGHT
        gap = 12.0
        step_x = width + gap
        step_y = height + gap
        for key, origin in desired.items():
            def candidates():
                yield origin
                for ring in range(1, len(desired) + 8):
                    for dx in range(-ring, ring + 1):
                        yield QPointF(origin.x() + dx * step_x, origin.y() - ring * step_y)
                        yield QPointF(origin.x() + dx * step_x, origin.y() + ring * step_y)
                    for dy in range(-ring + 1, ring):
                        yield QPointF(origin.x() - ring * step_x, origin.y() + dy * step_y)
                        yield QPointF(origin.x() + ring * step_x, origin.y() + dy * step_y)

            for candidate in candidates():
                rect = QRectF(candidate.x(), candidate.y(), width, height)
                padded = rect.adjusted(-gap, -gap, gap, gap)
                if any(padded.intersects(other) for other in occupied):
                    continue
                resolved[key] = candidate
                occupied.append(rect.adjusted(-gap, -gap, gap, gap))
                break
        return resolved

    def _warning_context(self, target: VectorEntity) -> tuple[list[VectorEntity], tuple[float, float, float, float]]:
        x1, y1, x2, y2 = target.bounds()
        span = max(x2 - x1, y2 - y1, 1e-6)
        margin = span * 0.9
        preview_bounds = (x1 - margin, y1 - margin, x2 + margin, y2 + margin)
        context_margin = span * 3.0
        context_bounds = (
            x1 - context_margin,
            y1 - context_margin,
            x2 + context_margin,
            y2 + context_margin,
        )
        self._ensure_warning_tree()
        if self._warning_tree is None:
            return [], preview_bounds
        hits = self._warning_tree.query(box(*context_bounds))
        center_x = (x1 + x2) / 2.0
        center_y = (y1 + y2) / 2.0
        candidates: list[tuple[float, VectorEntity]] = []
        for raw_index in hits:
            index = int(raw_index)
            vector = self._warning_tree_vectors[index]
            if vector.id == target.id and vector.points == target.points:
                continue
            bx1, by1, bx2, by2 = vector.bounds()
            distance = ((bx1 + bx2) / 2.0 - center_x) ** 2 + ((by1 + by2) / 2.0 - center_y) ** 2
            candidates.append((distance, vector))
        candidates.sort(key=lambda item: item[0])
        return [vector.clone() for _, vector in candidates[:60]], preview_bounds

    def _ensure_warning_tree(self) -> None:
        if self._warning_tree is not None or self._warning_tree_vectors:
            return
        geometries = []
        vectors = []
        for vector in self._warning_source_vectors:
            if len(vector.points) < 2:
                continue
            points = list(vector.points)
            if vector.closed and points[0] != points[-1]:
                points.append(points[0])
            geometries.append(LineString(points))
            vectors.append(vector)
        self._warning_tree_vectors = vectors
        self._warning_tree = STRtree(geometries) if geometries else None

    def _initial_warning_position(self, path: VectorEntity, width: float, height: float) -> QPointF:
        target = _path_midpoint(path)
        visible = self.sizing_view.mapToScene(self.sizing_view.viewport().rect()).boundingRect()
        gap_x = max(width / 12.0, 1e-9)
        gap_y = max(height / 12.0, 1e-9)
        anchor_x = min(max(target[0], visible.left()), visible.right())
        anchor_y = min(max(target[1], visible.top()), visible.bottom())
        raw_base = QPointF(anchor_x + gap_x, anchor_y - height / 2.0)

        def clamped(position: QPointF) -> QPointF:
            if visible.width() >= width + gap_x * 2:
                x = min(max(position.x(), visible.left() + gap_x), visible.right() - width - gap_x)
            else:
                x = visible.center().x() - width / 2.0
            if visible.height() >= height + gap_y * 2:
                y = min(max(position.y(), visible.top() + gap_y), visible.bottom() - height - gap_y)
            else:
                y = visible.center().y() - height / 2.0
            return QPointF(x, y)

        candidates = [
            clamped(raw_base),
            clamped(QPointF(anchor_x - width - gap_x, anchor_y - height / 2.0)),
            clamped(QPointF(anchor_x - width / 2.0, anchor_y + gap_y)),
            clamped(QPointF(anchor_x - width / 2.0, anchor_y - height - gap_y)),
        ]
        grid_candidates: list[QPointF] = []
        y = visible.top() + gap_y
        while y + height <= visible.bottom() - gap_y + 1e-9:
            x = visible.left() + gap_x
            while x + width <= visible.right() - gap_x + 1e-9:
                grid_candidates.append(QPointF(x, y))
                x += width + gap_x
            y += height + gap_y
        grid_candidates.sort(
            key=lambda point: (point.x() - raw_base.x()) ** 2 + (point.y() - raw_base.y()) ** 2
        )
        candidates.extend(grid_candidates)

        for candidate in candidates:
            if self._can_move_warning("", candidate, width, height):
                return candidate

        base = raw_base
        candidates = [
            base,
            QPointF(anchor_x - width - gap_x, anchor_y - height / 2.0),
            QPointF(anchor_x - width / 2.0, anchor_y + gap_y),
            QPointF(anchor_x - width / 2.0, anchor_y - height - gap_y),
        ]
        step_x = width + gap_x
        step_y = height + gap_y
        for ring in range(1, len(self._warning_states) + 8):
            for dx in range(-ring, ring + 1):
                candidates.append(QPointF(base.x() + dx * step_x, base.y() - ring * step_y))
                candidates.append(QPointF(base.x() + dx * step_x, base.y() + ring * step_y))
            for dy in range(-ring + 1, ring):
                candidates.append(QPointF(base.x() - ring * step_x, base.y() + dy * step_y))
                candidates.append(QPointF(base.x() + ring * step_x, base.y() + dy * step_y))
        for candidate in candidates:
            if self._can_move_warning("", candidate, width, height):
                return candidate
        return candidates[-1]

    def _can_move_warning(self, key: str, position: QPointF, width: float, height: float) -> bool:
        proposed = QRectF(position.x(), position.y(), width, height)
        gap = max(width / 30.0, 1e-9)
        proposed = proposed.adjusted(-gap, -gap, gap, gap)
        for other_key, state in self._warning_states.items():
            if other_key == key:
                continue
            other = QRectF(state.position.x(), state.position.y(), state.width, state.height)
            if proposed.intersects(other.adjusted(-gap, -gap, gap, gap)):
                return False
        return True

    def _rebuild_warning_overlays(self) -> None:
        for key, state in self._warning_states.items():
            highlight = self.scene.addPath(_vector_path(state.detail.path), _cosmetic_pen("#d62828", 2.5))
            highlight.setZValue(20)
            arrow = self.scene.addPath(QPainterPath(), _cosmetic_pen("#b7791f", 1.5))
            arrow.setZValue(30)
            balloon = WarningBalloonItem(self, state)
            self.scene.addItem(balloon)
            balloon.setPos(state.position)
            self._warning_highlight_items[key] = highlight
            self._warning_arrow_items[key] = arrow
            self._warning_items[key] = balloon
            self._update_warning_arrow(key)

    def _warning_item_moved(self, key: str) -> None:
        if key not in self._warning_items:
            return
        if self._updating_warning_geometry:
            return
        if self._warning_drag_item is not None and self._warning_drag_item.state.detail.key == key:
            return
        self._update_warning_arrow(key)
        self._update_scene_rect()

    def _finish_warning_drag(self, key: str) -> None:
        self._update_warning_arrow(key)
        arrow = self._warning_arrow_items.get(key)
        if arrow is not None:
            arrow.setVisible(True)
        balloon = self._warning_items.get(key)
        if balloon is not None and not self.scene.sceneRect().contains(balloon.sceneBoundingRect()):
            margin = max(_view_tolerance(self) * 5.0, 1.0)
            self.scene.setSceneRect(
                self.scene.sceneRect().united(balloon.sceneBoundingRect().adjusted(-margin, -margin, margin, margin))
            )

    def _update_warning_arrow(self, key: str) -> None:
        state = self._warning_states.get(key)
        arrow = self._warning_arrow_items.get(key)
        if state is None or arrow is None:
            return
        target_tuple = _path_midpoint(state.detail.path)
        target = QPointF(*target_tuple)
        rect = QRectF(state.position.x(), state.position.y(), state.width, state.height)
        start = _closest_rect_edge_point(rect, target)
        arrow.setPath(_arrow_path(start, target, max(state.width / 36.0, 1e-9)))


class WorkerSignals(QObject):
    done = Signal(object)
    error = Signal(str)
    progress = Signal(int, str)


# A cyclic-GC pass traverses every GC-tracked object process-wide. When it fires
# on a worker thread (ezdxf's fit allocates thousands of Vec3/Bezier4P, tripping
# the collector often), it calls tp_traverse on the PySide QGraphicsItems the GUI
# thread is concurrently creating/deleting in refresh_selection -- reading a
# half-freed C++ pointer and crashing with an access violation. Suspend automatic
# GC for as long as ANY worker runs; refcounting still frees acyclic garbage on
# each thread, and the next automatic pass reclaims cycles once GC is back on.
# ponytail: counter, not a bool -- recount can overlap Optimize/Send.
_gc_guard_lock = threading.Lock()
_gc_active_workers = 0


def _suspend_gc_for_worker() -> None:
    global _gc_active_workers
    with _gc_guard_lock:
        if _gc_active_workers == 0:
            gc.disable()
        _gc_active_workers += 1


def _resume_gc_for_worker() -> None:
    global _gc_active_workers
    with _gc_guard_lock:
        _gc_active_workers -= 1
        if _gc_active_workers == 0:
            gc.enable()
            # Deliberately no gc.collect() here. This runs on the worker thread,
            # right after run() emitted its queued `done` signal -- so the GUI
            # thread is about to rebuild the scene (scene.clear() deletes the old
            # QGraphicsItems). A collect traverses and frees cyclic PySide wrappers
            # and releases the GIL mid-dealloc, so it overlaps that rebuild: two
            # threads freeing one QGraphicsItem corrupt the scene's BSP index ->
            # access-violation crash (widest window on big imports whose redraw runs
            # long). Re-enabling suffices: automatic GC only fires while no worker
            # runs -- i.e. on the GUI thread -- so GUI items are freed GUI-side only.


class Worker(QRunnable):
    def __init__(self, fn) -> None:
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    def run(self) -> None:
        _suspend_gc_for_worker()
        try:
            self.signals.done.emit(self.fn(self.signals.progress.emit))
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc))
        finally:
            _resume_gc_for_worker()


class SimView(QGraphicsView):
    """Read-only Simulation-tab view sharing the editor's scene.

    The processed board renders into the same QGraphicsScene via set_result, so
    sharing it gives the Simulation tab its own zoom/pan with zero duplicated
    state. Non-interactive: editing stays in the Editor tab.
    """

    def __init__(self, board_view: BoardView, parent=None) -> None:
        super().__init__(board_view.scene, parent)
        self._board_view = board_view
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransform(QTransform(1, 0, 0, -1, 0, 0))  # Y-up, like BoardView
        self.setInteractive(False)
        self._canvas_controls = QWidget(self)
        self._canvas_controls.setObjectName("canvas_controls")
        self._canvas_controls.setStyleSheet(_CANVAS_CONTROLS_QSS)
        controls_layout = QHBoxLayout(self._canvas_controls)
        controls_layout.setContentsMargins(2, 2, 2, 2)
        controls_layout.setSpacing(1)
        self.vector_toggle_button = QToolButton(self._canvas_controls)
        self.fit_content_button = QToolButton(self._canvas_controls)
        for button in (self.vector_toggle_button, self.fit_content_button):
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setAutoRaise(False)
            controls_layout.addWidget(button)
        self._canvas_controls.adjustSize()

    def set_canvas_actions(self, vector_action: QAction, fit_action: QAction) -> None:
        self.vector_toggle_button.setDefaultAction(vector_action)
        self.vector_toggle_button.setToolTip("Show or hide vectors")
        self.fit_content_button.setDefaultAction(fit_action)
        self.fit_content_button.setToolTip("Zoom to content")
        self._canvas_controls.adjustSize()
        self._position_canvas_controls()

    def resizeEvent(self, event):  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._position_canvas_controls()

    def drawForeground(self, painter: QPainter, _rect: QRectF) -> None:  # noqa: N802 - Qt override
        # Screen-fixed X/Y gizmo in the bottom-left corner. World matrix off so it
        # ignores pan/zoom and the Y-flip view transform; +Y drawn upward to match.
        painter.save()
        painter.setWorldMatrixEnabled(False)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        h = self.viewport().height()
        ox, oy, ln = 26.0, h - 26.0, 22.0
        for dx, dy, color, txt, tx, ty in (
            (ln, 0.0, "#c0392b", "X", ox + ln + 4, oy + 4),
            (0.0, -ln, "#27ae60", "Y", ox - 4, oy - ln - 6),
        ):
            painter.setPen(QPen(QColor(color), 2))
            painter.drawLine(QPointF(ox, oy), QPointF(ox + dx, oy + dy))
            painter.drawText(QPointF(tx, ty), txt)
        painter.restore()

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802 - Qt override
        # Panning doesn't change balloon size (only zoom does), and balloons are
        # scene items that scroll with the content -- so, like BoardView, no resize
        # here. Restoring on scroll re-triggers scroll (setSceneRect) -> recursion.
        super().scrollContentsBy(dx, dy)
        self._position_canvas_controls()

    def _position_canvas_controls(self) -> None:
        viewport_rect = self.viewport().geometry()
        x = max(viewport_rect.left() + 8, viewport_rect.right() - self._canvas_controls.width() - 11)
        self._canvas_controls.move(x, viewport_rect.top() + 12)
        self._canvas_controls.show()
        self._canvas_controls.raise_()

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        # Anchor the zoom on the cursor by hand -- same drift fix as
        # BoardView.wheelEvent (AnchorUnderMouse lags the real cursor).
        anchor = self.mapToScene(event.position().toPoint())
        self.scale(factor, factor)
        drift = self.mapToScene(event.position().toPoint()) - anchor
        self.translate(drift.x(), drift.y())
        self._resize_warning_balloons()

    def _resize_warning_balloons(self) -> None:
        # Only when this view owns balloon sizing (Simulation tab active), and not
        # re-entrantly while a restore is already repositioning balloons.
        bv = self._board_view
        if bv.sizing_view is self and not bv._updating_warning_geometry:
            bv._restore_warning_view_geometry()

    def fit_content(self) -> None:
        view = self._board_view
        x1, y1, x2, y2 = _view_bounds(
            view.editor.visible_content_bounds(),
            view.result,
            view.board_width,
            view.board_height,
        )
        width = max(x2 - x1, 1.0)
        height = max(y2 - y1, 1.0)
        padding = max(width, height) * 0.04
        self.fitInView(
            QRectF(x1 - padding, y1 - padding, width + padding * 2, height + padding * 2),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        self._resize_warning_balloons()


# Display label ↔ kind for the Simulation tab's generic tool picker.
TOOL_KIND_LABELS = [
    ("Flat end", ToolKind.FLAT),
    ("Ball nose", ToolKind.BALL),
    ("V-bit", ToolKind.V_BIT),
    ("Tapered", ToolKind.TAPERED),
    ("Laser", ToolKind.LASER),
]
_KIND_LABEL = {kind: label for label, kind in TOOL_KIND_LABELS}

# The Simulation tab's Cut mode selector — each layer picks one independently.
CUT_MODE_LABELS = [
    ("Profile", "profile"),
    ("V-Carve", "vcarve"),
    ("Laser", "laser"),
]
_MODE_LABEL = {value: label for label, value in CUT_MODE_LABELS}


class MainWindow(QMainWindow):
    MAX_BULK_WARNING_BALLOONS = 50

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CurveMill")
        self.resize(1200, 800)
        self.editor = EditorModel()
        self.current_file: Path | None = None
        self.current_files: list[Path] = []
        # Signature of the session as it was last saved/opened. _is_dirty() compares
        # the live session against it to grey the Save button and gate discard prompts.
        # None until the baseline is taken at the end of __init__ (widgets must exist).
        self._saved_signature: str | None = None
        self.current_result: ProcessResult | None = None
        # Exact SolidWorks entity count per layer. Knowing it needs the full Send fit
        # (~0.5s on a big file), so it runs in the background on every geometry change
        # and the panel updates when it lands -- the count stays a touch stale for that
        # moment rather than blocking the edit. busy/pending coalesce rapid edits.
        self._layer_entity_counts: dict[str, int] = {}
        self._entity_recount_busy = False
        self._entity_recount_pending = False
        self._last_verbose_message = ""
        self.vector_clipboard: list[VectorEntity] = []
        self._repair_source_vectors: dict[int, VectorEntity] | None = None
        self._repair_source_splines: dict[int, SplineEntity] = {}
        self._last_repair_tolerance: float | None = None
        self._warning_details: dict[str, ProcessWarning] = {}
        self._last_located_warning_key: str | None = None
        self._open_profile_count = 0
        self._duplicate_count = 0
        self._self_intersection_count = 0
        self._refreshing_layers = False
        self._refreshing_layout = False
        self._layout_aspect_ratio = 1.0
        # Board-relative dimensions, remembered per pattern (the frozenset of the
        # selection's target ids). Selecting a different group hides its dims;
        # reselecting the same group brings them back.
        self._dim_store: dict[frozenset[int], list[Dimension]] = {}
        self._busy = False
        self._sw_target = None  # SWTarget from "Get Board from SolidWorks"
        # IniFormat everywhere (file in AppData, not registry): debuggable, and
        # tests can redirect it wholesale with QSettings.setPath.
        self.settings = QSettings(
            QSettings.Format.IniFormat, QSettings.Scope.UserScope, "CurveMill", "CurveMill"
        )
        # Autosave lives beside the settings ini, so tests that redirect QSettings
        # get an isolated path and never touch a real user's recovery file. Its mere
        # existence at launch means the previous session never exited cleanly (a
        # crash) — closeEvent deletes it on a clean quit. Pairs with v2.5 crash reporting.
        self._autosave_path = Path(self.settings.fileName()).parent / f"autosave{project.SUFFIX}"
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(60_000)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()
        self._chrome_visibility: list[tuple] | None = None  # Editor docks/toolbar, saved off-tab
        self._warnings_visibility: bool | None = None  # Warnings/Log dock, saved off geometry tabs
        self._sim_view_fitted = False
        self.thread_pool = QThreadPool.globalInstance()
        self.view = BoardView(self.editor)
        self.view.on_changed = self._on_editor_changed
        self._build_ui()
        self.view.on_selection_changed = self._on_view_selection_changed
        self.view.dim_context = self._dim_context
        self.view.layer_dims = self._layer_dims
        self.view.on_dim_placed = self._on_dim_placed
        self.view.on_dim_edit = self._edit_dim_value
        self.view.on_dim_label_moved = self._on_dim_label_moved
        self.view.on_dim_flip = self._flip_dim
        self.view.on_dim_delete = self._delete_dim
        self._bind_actions()
        self._refresh()
        # Settings-tab startup defaults; after _bind_actions so the units
        # handler updates spinbox suffixes.
        self.units.setCurrentText(self.default_units_setting.currentText())
        self.repair.setValue(self.default_repair_setting.value())
        # Baseline: a freshly launched, empty session is "clean" -> Save starts greyed.
        self._mark_saved()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QHBoxLayout(root)
        controls = QWidget()
        controls.setFixedWidth(330)
        form = QFormLayout(controls)

        self.open_button = QPushButton("Insert DXF Files")
        self.text_button = QPushButton("Insert Text (T)")
        self.board_width = _double(600, 1, 100000)
        self.board_height = _double(400, 1, 100000)
        self.units = QComboBox()
        self.units.addItems(["dxf", "mm", "in"])
        self.endmill = _double(6, 0.01, 1000)
        self.repair = _double(0.25, 0, 1000)
        self.trace = QComboBox()
        self.trace.addItems([mode.value for mode in TraceMode])
        self.tools = self._load_tools()
        self.tool_combo = QComboBox()
        for label, kind in TOOL_KIND_LABELS:
            self.tool_combo.addItem(label, kind.value)
        self.tool_combo.setCurrentIndex(max(0, self.tool_combo.findData(str(self.settings.value("sim/kind", "flat")))))
        # self.endmill doubles as the kind's Diameter (kerf for lasers); the
        # sweep uses effective_diameter(cut depth) computed in _options.
        self.endmill.setValue(float(self.settings.value("sim/diameter", 6.0)))
        self.tool_taper = _double(float(self.settings.value("sim/taper", 30.0)), 0.1, 89)
        self.tool_tip = _double(float(self.settings.value("sim/tip", 0.0)), 0, 1000)
        self.cut_depth = _double(float(self.settings.value("sim/cut_depth", 3.0)), 0.01, 1000)
        # Cut mode is the top-level choice: it filters the Tool list (V-Carve drops
        # flat mills, Laser shows the laser alone) and, in V-carve, the depth means
        # *max* depth. Laser used to be a tool kind; migrate those users to the mode.
        self.cut_mode = QComboBox()
        for label, value in CUT_MODE_LABELS:
            self.cut_mode.addItem(label, value)
        saved_mode = str(self.settings.value("sim/cut_mode", "profile"))
        if str(self.settings.value("sim/kind", "flat")) == "laser":
            saved_mode = "laser"
        self.cut_mode.setCurrentIndex(max(0, self.cut_mode.findData(saved_mode)))
        self.effective_label = QLabel("")
        # Each layer owns its recipe. Select a layer in the right-hand panel, edit
        # its mode/tool/depth in the toolbar above; while this is checked every
        # layer tracks the current recipe (greyed unless there's >1 layer).
        self.apply_all_check = QCheckBox()  # labelled by its form row, like Hide islands
        self.apply_all_check.setToolTip("Give every layer the selected layer's mode, tool and depth.")
        # Right-side layer panel — display-only, mirroring the Editor's Layers dock.
        # Columns show what each layer will do; the checkbox includes/skips it.
        self.sim_layers = QTreeWidget()
        self.sim_layers.setColumnCount(4)
        self.sim_layers.setHeaderLabels(["Layer", "Mode", "Tool", "Depth"])
        self.sim_layers.setRootIsDecorated(False)
        self.sim_layers.setAlternatingRowColors(True)
        self.sim_layers.setColumnWidth(0, 90)
        self._sim_layers_loading = False  # guards rebuild against edit signals
        self._sim_form_loading = False  # guards form loads against write-back
        self.curve_tolerance = _double(0.2, 0.01, 100)
        self.hide_islands = QCheckBox()
        self.repair_button = QPushButton("Repair Vectors")
        self.repair_button.setToolTip(
            "Remove duplicates, snap open profiles closed, and heal profiles whose\n"
            "outline crosses itself (SolidWorks rejects self-intersecting sketches)."
        )
        self.process_button = QPushButton("Process")
        self.correct_button = QPushButton("Replace with Simulated")
        self.correct_button.setToolTip(
            "Swap the pattern for the tool-corrected (as-milled) outlines from the\n"
            "last simulation. In-editor only -- Export/Send then use the milled shape."
        )
        self.correct_button.setEnabled(False)
        self.optimize_button = QPushButton("Optimize Active Layer")
        self.optimize_button.setToolTip(
            "Fit the active layer's loose segments into one native spline per shape and\n"
            "replace them in place. Other layers are untouched. Nothing is saved -- inspect\n"
            "the new count and any errors, Repair if needed, then Export, Send or Preview."
        )
        self.export_button = QPushButton("Export DXF")
        self.export_button.setToolTip("Export whatever is currently on the canvas as a DXF (R2000, native splines)")
        self.progress_label = QLabel("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")

        # The dock now carries the "Selection Layout" title, so the inner group
        # box is left untitled to avoid showing the heading twice.
        self.selection_layout_group = QGroupBox()
        selection_layout = QVBoxLayout(self.selection_layout_group)
        self.layout_readouts: dict[str, QLabel] = {
            name: QLabel("-")
            for name in ("width", "height", "left", "right", "bottom", "top")
        }
        measurements_group = QGroupBox("Measurements")
        measurements_layout = QGridLayout(measurements_group)
        readouts = QWidget()
        readout_grid = QGridLayout(readouts)
        readout_grid.setContentsMargins(0, 0, 0, 0)
        for index, (label, key) in enumerate(
            (("W", "width"), ("H", "height"), ("L", "left"), ("R", "right"), ("B", "bottom"), ("T", "top"))
        ):
            row, column = divmod(index, 2)
            readout_grid.addWidget(QLabel(label), row, column * 2)
            readout_grid.addWidget(self.layout_readouts[key], row, column * 2 + 1)
        measurements_layout.addWidget(readouts, 0, 0)
        self.layout_width = _double(1, 0.001, 1000000)
        self.layout_height = _double(1, 0.001, 1000000)
        self.layout_aspect_lock = QCheckBox("Lock aspect ratio")
        self.layout_aspect_lock.setChecked(True)
        self.fit_board_width_button = QPushButton("Fit Width")
        self.fit_board_width_button.setToolTip("Fit the selected pattern to the board width")
        self.fit_board_height_button = QPushButton("Fit Height")
        self.fit_board_height_button.setToolTip("Fit the selected pattern to the board height")
        size_group = QGroupBox("Size")
        size_layout = QFormLayout(size_group)
        fit_buttons = QWidget()
        fit_layout = QVBoxLayout(fit_buttons)
        fit_layout.setContentsMargins(0, 0, 0, 0)
        fit_layout.addWidget(self.fit_board_width_button)
        fit_layout.addWidget(self.fit_board_height_button)
        # Smart Dim lives in the Size group so the one aspect-lock checkbox above
        # governs both the manual spinboxes and on-canvas dimensions.
        self.dimension_tool_action = QAction("Smart Dimension (D)", self)
        self.dimension_tool_action.setCheckable(True)
        self.dimension_tool_action.setToolTip(
            "Dimension the selection to the board on the canvas to drive its size and position (D)"
        )
        dimension_button = QToolButton()
        dimension_button.setDefaultAction(self.dimension_tool_action)
        dimension_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        dimension_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        dimension_button.setMinimumHeight(34)
        size_layout.addRow("Width", self.layout_width)
        size_layout.addRow("Height", self.layout_height)
        size_layout.addRow(self.layout_aspect_lock)
        size_layout.addRow(fit_buttons)
        size_layout.addRow(dimension_button)

        alignment_group, self.alignment_buttons = self._make_alignment_grid()
        selection_layout.addWidget(measurements_group)
        selection_layout.addWidget(size_group)
        selection_layout.addWidget(alignment_group)

        form.addRow(self.open_button)
        form.addRow(self.text_button)
        form.addRow("Board width", self.board_width)
        form.addRow("Board height", self.board_height)
        form.addRow("Units", self.units)
        form.addRow("Repair tolerance", self.repair)
        form.addRow("Curve tolerance", self.curve_tolerance)
        form.addRow(self.repair_button)
        form.addRow(self.optimize_button)
        form.addRow(self.export_button)

        self.sw_get_button = QPushButton("Get Board from SolidWorks")
        self.sw_get_button.setToolTip(
            "Read the face (or plane) currently selected in SolidWorks: board size, thickness, and a stored link for Send"
        )
        self.sw_send_button = QPushButton("Send to SolidWorks")
        self.sw_send_button.setToolTip("Draw the visible curves in a sketch on the linked face and apply a Cut/Boss")
        self.sw_send_button.setEnabled(False)
        self.sw_preview_button = QPushButton("Preview in SolidWorks")
        self.sw_preview_button.setToolTip(
            "Place a transparent picture of the pattern on the linked face (takes a few seconds)"
        )
        self.sw_preview_button.setEnabled(False)
        self.sw_target_label = QLabel("Not linked")
        self.sw_target_label.setWordWrap(True)
        sw_group = QGroupBox("SolidWorks")
        sw_layout = QVBoxLayout(sw_group)
        sw_layout.addWidget(self.sw_get_button)
        sw_layout.addWidget(self.sw_send_button)
        sw_layout.addWidget(self.sw_preview_button)
        sw_layout.addWidget(self.sw_target_label)
        form.addRow(sw_group)

        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        controls_scroll.setWidget(controls)
        controls_scroll.setFixedWidth(340)
        layout.addWidget(controls_scroll)
        layout.addWidget(self.view, 1)

        # --- Four-tab shell (master plan §5). Widget attribute names are frozen:
        # tests and handlers reach them on the window regardless of which tab
        # a widget lives in.
        self._editor_tab = root
        self._sim_tab = self._build_simulation_tab()
        self._library_tab = self._build_library_tab()
        self._settings_tab = self._build_settings_tab()
        self.tabs = QTabWidget()
        self.tabs.addTab(self._editor_tab, self.tr("Editor"))
        self.tabs.addTab(self._sim_tab, self.tr("Simulation"))
        self.tabs.addTab(self._library_tab, self.tr("Library"))
        self.tabs.addTab(self._settings_tab, self.tr("Settings"))
        self.setCentralWidget(self.tabs)

        # Progress lives in the status bar so long operations stay visible from
        # every tab.
        self.progress_bar.setFixedWidth(220)
        self.statusBar().addWidget(self.progress_label, 1)
        self.statusBar().addPermanentWidget(self.progress_bar)

        toolbar = QToolBar("Editor")
        self.editor_toolbar = toolbar
        toolbar.setObjectName("editor_toolbar")
        self.addToolBar(toolbar)
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self.select_tool_action = QAction("Box Lasso (L)", self)
        self.select_tool_action.setCheckable(True)
        self.select_tool_action.setChecked(True)
        self.free_lasso_tool_action = QAction("Free Lasso (F)", self)
        self.free_lasso_tool_action.setCheckable(True)
        self.show_vectors_action = QAction("Show Vectors", self)
        self.show_vectors_action.setCheckable(True)
        self.show_vectors_action.setChecked(True)
        self.show_vectors_action.setIcon(_view_vectors_icon())
        self.fit_content_action = QAction("Zoom to Content", self)
        self.fit_content_action.setIcon(_fit_content_icon())
        self.tool_group.addAction(self.select_tool_action)
        self.tool_group.addAction(self.free_lasso_tool_action)
        # Smart Dim stays OUT of the exclusive tool group so clicking it again
        # (or pressing D) toggles it off; _toggle_dimension_tool keeps it and
        # the toolbar tools mutually exclusive by hand.
        toolbar.addAction(self.select_tool_action)
        toolbar.addAction(self.free_lasso_tool_action)
        toolbar.addSeparator()
        self.select_all_action = QAction("Select All", self)
        self.select_all_visible_action = QAction("Select All Visible Layers", self)
        self.cut_action = QAction("Cut", self)
        self.copy_action = QAction("Copy", self)
        self.paste_action = QAction("Paste", self)
        self.delete_action = QAction("Delete (DEL)", self)
        self.group_action = QAction("Group", self)
        self.ungroup_action = QAction("Ungroup", self)
        self.smooth_action = QAction("Smooth Vectors (S)", self)
        self.smooth_corners_action = QAction("Smooth Corners", self)
        self.text_action = QAction("Text (T)", self)
        self.undo_action = QAction("Undo", self)
        self.redo_action = QAction("Redo", self)
        # Undo/redo/clipboard/select-all live in the Edit menu (built below);
        # the toolbar keeps only the geometry-editing verbs.
        for action in [
            self.delete_action,
            self.group_action,
            self.ungroup_action,
            self.smooth_action,
            self.smooth_corners_action,
        ]:
            toolbar.addAction(action)
        self.view.set_canvas_actions(self.show_vectors_action, self.fit_content_action)
        # Sim canvas shares the vector toggle (same scene items) but needs its
        # own fit action -- fit_content_action zooms the Editor view.
        self.sim_fit_action = QAction("Zoom to Content", self)
        self.sim_fit_action.setIcon(_fit_content_icon())
        self.sim_view.set_canvas_actions(self.show_vectors_action, self.sim_fit_action)

        # Layers and Selection Layout are separate docks. Stacked in the same
        # dock area, Qt puts a draggable divider between them so either can be
        # resized, closed, moved, or floated independently.
        # Title left blank: the Layers/Dimensions tabs right below already label
        # the sections, so a dock title would just repeat them.
        self.layers_dock = QDockWidget("", self)
        self.layers_dock.setObjectName("layers_dock")
        layers_section = QWidget()
        layer_layout = QVBoxLayout(layers_section)
        self.layer_list = QTreeWidget()
        self.layer_list.setColumnCount(3)
        self.layer_list.setHeaderLabels(["Layer", "Entities", "Depth"])
        self.layer_list.setToolTip(
            "Entities = the exact number of SolidWorks sketch entities this layer\n"
            "will create. Recomputed automatically after every change."
        )
        self.layer_list.setRootIsDecorated(False)
        self.layer_list.setAlternatingRowColors(True)
        self.layer_list.setColumnWidth(0, 180)
        self.layer_list.setMinimumHeight(220)
        layer_layout.addWidget(self.layer_list, 1)
        layer_buttons = QHBoxLayout()
        self.add_layer_button = QPushButton("Add")
        self.clone_layer_button = QPushButton("Clone")
        self.rename_layer_button = QPushButton("Rename")
        self.delete_layer_button = QPushButton("Delete")
        for button in [
            self.add_layer_button,
            self.clone_layer_button,
            self.rename_layer_button,
            self.delete_layer_button,
        ]:
            layer_buttons.addWidget(button)
        layer_layout.addLayout(layer_buttons)
        dims_panel = QWidget()
        dims_layout = QVBoxLayout(dims_panel)
        self.dim_list = QListWidget()
        self.dim_list.setAlternatingRowColors(True)
        self.dim_list.setWordWrap(True)
        dims_layout.addWidget(self.dim_list, 1)
        dim_buttons = QHBoxLayout()
        self.delete_dim_button = QPushButton("Delete")
        self.delete_dim_button.setEnabled(False)
        dim_buttons.addWidget(self.delete_dim_button)
        dim_buttons.addStretch(1)
        dims_layout.addLayout(dim_buttons)
        self.layers_tabs = QTabWidget()
        self.layers_tabs.addTab(layers_section, "Layers")
        self.layers_tabs.addTab(dims_panel, "Dimensions")
        self.layers_dock.setWidget(self.layers_tabs)
        self.layers_dock.setMinimumHeight(220)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.layers_dock)

        self.selection_dock = QDockWidget("Selection Layout", self)
        self.selection_dock.setObjectName("selection_dock")
        selection_scroll = QScrollArea()
        selection_scroll.setWidgetResizable(True)
        selection_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        selection_scroll.setWidget(self.selection_layout_group)
        self.selection_dock.setWidget(selection_scroll)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.selection_dock)

        self.warnings_dock = QDockWidget("", self)
        self.warnings_dock.setObjectName("warnings_dock")
        warning_panel = QWidget()
        warning_layout = QVBoxLayout(warning_panel)
        self.warning_list = QListWidget()
        self.warning_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.warning_list.setAlternatingRowColors(True)
        self.warning_list.setWordWrap(True)
        self.warning_list.setMinimumHeight(110)
        warning_buttons = QHBoxLayout()
        self.select_all_warnings_button = QPushButton("Select All Warnings")
        self.select_all_warnings_button.setEnabled(False)
        self.locate_warning_button = QPushButton("Locate Next Balloon")
        self.locate_warning_button.setEnabled(False)
        self.clear_balloons_button = QPushButton("Clear Balloons")
        self.clear_balloons_button.setEnabled(False)
        warning_layout.addWidget(self.warning_list, 1)
        warning_buttons.addWidget(self.select_all_warnings_button)
        warning_buttons.addWidget(self.locate_warning_button)
        warning_buttons.addWidget(self.clear_balloons_button)
        warning_layout.addLayout(warning_buttons)

        log_panel = QWidget()
        log_layout = QVBoxLayout(log_panel)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("log_view")
        # Read-only rather than disabled: the user can still select and copy text
        # (Ctrl+C, or the right-click menu) but cannot type into the log.
        self.log_view.setReadOnly(True)
        self.log_view.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setMinimumHeight(110)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.log_view.setPlaceholderText("Actions, warnings and errors are logged here.")
        log_buttons = QHBoxLayout()
        self.copy_log_button = QPushButton("Copy Selected")
        self.copy_log_button.setToolTip("Copy the selected log lines (Ctrl+C), or the whole log if nothing is selected")
        self.clear_log_button = QPushButton("Clear Log")
        self.log_level = QComboBox()
        self.log_level.addItems(["Normal", "Verbose"])
        self.log_level.setToolTip("Verbose also logs every progress step of long operations")
        log_layout.addWidget(self.log_view, 1)
        log_buttons.addWidget(self.copy_log_button)
        log_buttons.addWidget(self.clear_log_button)
        log_buttons.addWidget(QLabel("Detail"))
        log_buttons.addWidget(self.log_level)
        log_buttons.addStretch(1)
        log_layout.addLayout(log_buttons)

        self.warnings_tabs = QTabWidget()
        self.warnings_tabs.addTab(warning_panel, "Warnings")
        self.warnings_tabs.addTab(log_panel, "Log")
        self.warnings_dock.setWidget(self.warnings_tabs)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.warnings_dock)
        # Give the right dock the bottom-right corner so Selection Layout runs the
        # full height and the Warnings & Log block stops at its left edge instead
        # of spanning the whole bottom.
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)

        # A View menu of built-in toggle actions is Qt's standard way to bring a
        # panel back after its close button is used, so closing a dock or the
        # toolbar is never a dead end.
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction("New Project", QKeySequence.StandardKey.New, self.new_project)
        file_menu.addAction("Open Project…", QKeySequence.StandardKey.Open, self.open_project)
        self.save_action = file_menu.addAction("Save", QKeySequence.StandardKey.Save, self.save_project)
        file_menu.addAction("Save As…", QKeySequence.StandardKey.SaveAs, self.save_project_as)
        self.recent_menu = file_menu.addMenu("Recent Projects")
        self._refresh_recent_menu()

        edit_menu = self.menuBar().addMenu("Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.cut_action)
        edit_menu.addAction(self.copy_action)
        edit_menu.addAction(self.paste_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.select_all_action)
        edit_menu.addAction(self.select_all_visible_action)

        view_menu = self.menuBar().addMenu("View")
        for widget, name in (
            (self.layers_dock, "Layers & Dimensions"),
            (self.selection_dock, "Selection Layout"),
            (self.warnings_dock, "Warnings & Log"),
            (self.editor_toolbar, "Toolbar"),
        ):
            action = widget.toggleViewAction()
            action.setText(name)
            view_menu.addAction(action)

    def _build_simulation_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        controls = QWidget()
        controls.setFixedWidth(330)
        form = QFormLayout(controls)
        form.addRow("Cut mode", self.cut_mode)
        form.addRow("Tool", self.tool_combo)
        form.addRow("Diameter", self.endmill)
        form.addRow("Taper angle / side", self.tool_taper)
        form.addRow("Tip diameter", self.tool_tip)
        form.addRow("Cut depth", self.cut_depth)
        form.addRow("Effective width", self.effective_label)
        form.addRow("Trace", self.trace)
        form.addRow("Apply to all layers", self.apply_all_check)
        form.addRow("Hide islands", self.hide_islands)
        form.addRow(self.process_button)
        form.addRow(self.correct_button)
        self._sim_form = form
        self.tool_combo.currentIndexChanged.connect(self._on_tool_params_changed)
        for field in (self.endmill, self.tool_taper, self.tool_tip, self.cut_depth):
            # editingFinished (commit), not valueChanged (per-keystroke): the handler
            # does a full _refresh + 6 QSettings writes, too heavy to run per digit.
            # Mirrors the layout spinboxes below. ponytail: no debounce needed.
            field.editingFinished.connect(self._on_tool_params_changed)
        self.cut_mode.currentIndexChanged.connect(self._on_cut_mode_changed)
        self.apply_all_check.toggled.connect(self._on_apply_all_toggled)
        self.sim_layers.currentItemChanged.connect(self._on_sim_layer_selected)
        self.sim_layers.itemChanged.connect(self._on_sim_layer_check)
        self._on_tool_params_changed()
        layout.addWidget(controls)
        self.sim_view = SimView(self.view)
        layout.addWidget(self.sim_view, 1)
        # Layer panel on the right, same side as the Editor's Layers dock.
        panel = QWidget()
        panel.setFixedWidth(260)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(QLabel("Layers"))
        panel_layout.addWidget(self.sim_layers, 1)
        layout.addWidget(panel)
        return tab

    def _build_library_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        # Side selector instead of nested tabs: the Library already lives inside
        # the main QTabWidget, and tabs-in-tabs read as one confusing strip.
        self.library_sections = QListWidget()
        self.library_sections.addItems([self.tr("Patterns"), self.tr("Tools")])
        self.library_sections.setFixedWidth(150)
        self.library_sections.setCurrentRow(0)
        self.library_pages = QStackedWidget()
        self.library_pages.addWidget(self._build_pattern_library_page())
        self.library_pages.addWidget(self._build_tool_library_page())
        self.library_sections.currentRowChanged.connect(self.library_pages.setCurrentIndex)
        layout.addWidget(self.library_sections)
        layout.addWidget(self.library_pages, 1)
        return tab

    def _build_pattern_library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel(
                self.tr(
                    "Your clipart: save a repaired pattern once, then drop it into any drawing."
                )
            )
        )
        self.pattern_list = QListWidget()
        self.pattern_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.pattern_list.setIconSize(QSize(library.THUMBNAIL_SIZE, library.THUMBNAIL_SIZE))
        self.pattern_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.pattern_list.setMovement(QListWidget.Movement.Static)
        self.pattern_list.setSpacing(8)
        self.pattern_list.itemDoubleClicked.connect(self._insert_library_entry)
        buttons = QHBoxLayout()
        save_button = QPushButton(self.tr("Save selection to Library"))
        open_button = QPushButton(self.tr("Insert into drawing"))
        remove_button = QPushButton(self.tr("Remove selected"))
        folder_button = QPushButton(self.tr("Open folder"))
        save_button.clicked.connect(self._save_to_library)
        open_button.clicked.connect(lambda: self._insert_library_entry(self.pattern_list.currentItem()))
        remove_button.clicked.connect(self._remove_library_entry)
        folder_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(library.library_dir())))
        )
        for button in (save_button, open_button, remove_button, folder_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addWidget(self.pattern_list, 1)
        layout.addLayout(buttons)
        self._refresh_pattern_library()
        return page

    def _refresh_pattern_library(self) -> None:
        self.pattern_list.clear()
        for entry in library.entries():
            item = QListWidgetItem(QIcon(library.thumbnail(entry)), entry.stem)
            item.setData(Qt.ItemDataRole.UserRole, str(entry))
            self.pattern_list.addItem(item)

    def _save_to_library(self) -> None:
        # A pattern is a piece of artwork, so a selection saves just that piece;
        # with nothing selected the whole drawing is the pattern.
        vectors = self.editor.copy_selected() or [v.clone() for v in self.editor.vectors]
        splines = self.editor.copy_selected_splines()
        if not self.editor.selected_target_ids() and not self.editor.selected_spline_ids:
            splines = [s.clone() for s in self.editor.splines]
        if not vectors and not splines:
            self._set_progress(0, "There is nothing to save")
            return
        default = self.current_file.stem if self.current_file else "Pattern"
        name, accepted = QInputDialog.getText(self, "Save to Library", "Pattern name", text=default)
        if not accepted or not name.strip():
            return
        try:
            library.save_pattern(name.strip(), vectors, splines)
        except OSError as error:
            self._on_worker_error("Could not save to library", str(error))
            return
        self._refresh_pattern_library()
        self._finish_progress(f"Saved {name.strip()} to the library")

    def _insert_library_entry(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        entry = Path(item.data(Qt.ItemDataRole.UserRole))
        try:
            vectors, splines = library.load_pattern(entry)
        except (OSError, ValueError, KeyError, TypeError) as error:
            self._on_worker_error("Could not insert pattern", str(error))
            return
        self.tabs.setCurrentWidget(self._editor_tab)
        # Clipart lands on the board, not wherever the mouse happens to be.
        center = (self.board_width.value() / 2.0, self.board_height.value() / 2.0)
        inserted = self.editor.paste_vectors(vectors, center) + self.editor.paste_splines(splines, center)
        if inserted:
            self._invalidate_editor_result(update_open_profiles=True)
        self._finish_progress(f"Inserted {entry.stem} into {self.editor.active_layer}")

    def _remove_library_entry(self) -> None:
        item = self.pattern_list.currentItem()
        if item is None:
            return
        entry = Path(item.data(Qt.ItemDataRole.UserRole))
        if (
            QMessageBox.question(self, "Remove pattern", f"Remove “{entry.stem}” from the library?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        entry.unlink(missing_ok=True)
        entry.with_suffix(".png").unlink(missing_ok=True)
        self._refresh_pattern_library()

    def _build_tool_library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel(self.tr("Save the cutters you own, then load one into the Simulation tab."))
        )
        self.tool_table = QTableWidget(0, 6)
        # Notes is the stretched last column: free text wants the width, and the
        # cutting dimensions stay grouped together to its left.
        self.tool_table.setHorizontalHeaderLabels(
            [
                self.tr("Name"),
                self.tr("Kind"),
                self.tr("Diameter"),
                self.tr("Taper° / side"),
                self.tr("Tip Ø"),
                self.tr("Notes"),
            ]
        )
        self.tool_table.horizontalHeader().setStretchLastSection(True)
        self.tool_table.verticalHeader().setVisible(False)
        self._tool_table_loading = False
        self._populate_tool_table()
        self.tool_table.cellChanged.connect(self._on_tool_table_changed)
        buttons = QHBoxLayout()
        self.use_tool_button = QPushButton(self.tr("Use in Simulation"))
        new_button = QPushButton(self.tr("Add new tool"))
        add_button = QPushButton(self.tr("Save current tool"))
        remove_button = QPushButton(self.tr("Remove selected"))
        self.use_tool_button.clicked.connect(self._use_selected_tool)
        new_button.clicked.connect(self._add_blank_tool)
        add_button.clicked.connect(self._add_tool)
        remove_button.clicked.connect(self._remove_tool)
        for button in (self.use_tool_button, new_button, add_button, remove_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addWidget(self.tool_table, 1)
        layout.addLayout(buttons)
        return page

    def _build_settings_tab(self) -> QWidget:
        tab = QWidget()
        outer = QHBoxLayout(tab)
        column = QWidget()
        column.setFixedWidth(420)
        vbox = QVBoxLayout(column)

        defaults_group = QGroupBox(self.tr("Defaults (applied at startup)"))
        defaults_form = QFormLayout(defaults_group)
        self.default_units_setting = QComboBox()
        self.default_units_setting.addItems(["dxf", "mm", "in"])
        self.default_units_setting.setCurrentText(str(self.settings.value("defaults/units", "dxf")))
        self.default_repair_setting = _double(
            float(self.settings.value("defaults/repair_tolerance", 0.25)), 0, 1000
        )
        defaults_form.addRow(self.tr("Units"), self.default_units_setting)
        defaults_form.addRow(self.tr("Repair tolerance"), self.default_repair_setting)

        optimizer_group = QGroupBox(self.tr("Optimize"))
        optimizer_form = QFormLayout(optimizer_group)
        self.fit_samples_setting = QSpinBox()
        self.fit_samples_setting.setRange(1, 32)
        self.fit_samples_setting.setValue(int(self.settings.value("optimizer/per_segment", 4)))
        self.fit_samples_setting.setToolTip(
            self.tr("Fit-spline samples per curve segment; higher = tighter fit, more points")
        )
        self.corner_degrees_setting = _double(
            float(self.settings.value("optimizer/corner_degrees", 40.0)), 1, 180
        )
        self.corner_degrees_setting.setToolTip(
            self.tr("Bends sharper than this stay corners instead of being rounded into the spline")
        )
        self.simplify_tolerance_setting = _double(
            float(self.settings.value("optimizer/simplify_tol", 0.02)), 0.0, 10.0
        )
        self.simplify_tolerance_setting.setSingleStep(0.01)
        self.simplify_tolerance_setting.setToolTip(
            self.tr(
                "Replace with Simulated thins the as-milled outline to this accuracy.\n"
                "Lower = truer to the cut but more SolidWorks entities; 0 disables thinning."
            )
        )
        optimizer_form.addRow(self.tr("Fit samples per segment"), self.fit_samples_setting)
        optimizer_form.addRow(self.tr("Corner angle (deg)"), self.corner_degrees_setting)
        optimizer_form.addRow(self.tr("Simulated thinning (mm)"), self.simplify_tolerance_setting)

        sw_group = QGroupBox(self.tr("Send to SolidWorks"))
        sw_form = QFormLayout(sw_group)
        self.sw_send_mode_setting = QComboBox()
        # Must match SendToSolidWorksDialog.feature; the dialog preselects this.
        self.sw_send_mode_setting.addItems(["Extruded Cut", "Extruded Boss", "Sketch only"])
        self.sw_send_mode_setting.setCurrentText(
            str(self.settings.value("sw/send_mode", "Extruded Cut"))
        )
        self.sw_cut_depth_setting = _double(
            float(self.settings.value("sw/cut_depth", 10.0)), 0.01, 10000.0
        )
        self.sw_cut_depth_setting.setToolTip(
            self.tr("Blind/Mid-Plane depth when the board thickness is unknown (planes)")
        )
        sw_form.addRow(self.tr("Default feature"), self.sw_send_mode_setting)
        sw_form.addRow(self.tr("Default cut depth (mm)"), self.sw_cut_depth_setting)
        # ponytail: no chunk-threshold knob -- chunked send isn't built yet;
        # add it here when solidworks_bridge grows a chunked path to read it.

        vbox.addWidget(defaults_group)
        vbox.addWidget(optimizer_group)
        vbox.addWidget(sw_group)
        vbox.addStretch(1)
        outer.addWidget(column)
        outer.addStretch(1)

        self.default_units_setting.currentTextChanged.connect(
            lambda value: self.settings.setValue("defaults/units", value)
        )
        self.default_repair_setting.valueChanged.connect(
            lambda value: self.settings.setValue("defaults/repair_tolerance", value)
        )
        self.fit_samples_setting.valueChanged.connect(
            lambda value: self.settings.setValue("optimizer/per_segment", value)
        )
        self.corner_degrees_setting.valueChanged.connect(
            lambda value: self.settings.setValue("optimizer/corner_degrees", value)
        )
        self.simplify_tolerance_setting.valueChanged.connect(
            lambda value: self.settings.setValue("optimizer/simplify_tol", value)
        )
        self.sw_send_mode_setting.currentTextChanged.connect(
            lambda value: self.settings.setValue("sw/send_mode", value)
        )
        self.sw_cut_depth_setting.valueChanged.connect(
            lambda value: self.settings.setValue("sw/cut_depth", value)
        )
        return tab

    def _on_tab_changed(self, index: int) -> None:
        # Layers/Selection docks and the editor toolbar only make sense on the
        # Editor tab; remember the user's own visibility choices across switches.
        on_editor = self.tabs.widget(index) is self._editor_tab
        # Warnings/Log relate to geometry -- hidden on Library/Settings, restored
        # to the user's own choice on Editor/Simulation.
        on_geometry = self.tabs.widget(index) in (self._editor_tab, self._sim_tab)
        if on_geometry:
            if self._warnings_visibility is not None:
                self.warnings_dock.setVisible(self._warnings_visibility)
                self._warnings_visibility = None
        elif self._warnings_visibility is None:
            # not isHidden() = the dock's own show/close flag, independent of whether
            # the top-level window is currently shown (isVisible() would misread it).
            self._warnings_visibility = not self.warnings_dock.isHidden()
            self.warnings_dock.setVisible(False)
        chrome = (self.layers_dock, self.selection_dock, self.editor_toolbar)
        if on_editor:
            if self._chrome_visibility is not None:
                for widget, visible in self._chrome_visibility:
                    widget.setVisible(visible)
                self._chrome_visibility = None
        elif self._chrome_visibility is None:
            self._chrome_visibility = [(widget, widget.isVisible()) for widget in chrome]
            for widget in chrome:
                widget.setVisible(False)
        if self.tabs.widget(index) is self._sim_tab and not self._sim_view_fitted:
            self.sim_view.fit_content()
            self._sim_view_fitted = True
        # Size warning balloons to whichever view is now on screen -- the SimView
        # has its own zoom, so a balloon sized for the editor looks tiny there.
        self.view.sizing_view = self.view if on_editor else self.sim_view
        self.view._restore_warning_view_geometry()

    def _make_alignment_grid(self):
        group = QGroupBox("Align to Board")
        grid = QGridLayout(group)
        grid.setContentsMargins(5, 8, 5, 5)
        grid.setSpacing(1)
        buttons: dict[tuple[str, str], QToolButton] = {}
        for row, vertical in enumerate(("top", "center", "bottom")):
            for column, horizontal in enumerate(("left", "center", "right")):
                label = {
                    ("left", "top"): "TL",
                    ("center", "top"): "T",
                    ("right", "top"): "TR",
                    ("left", "center"): "L",
                    ("center", "center"): "C",
                    ("right", "center"): "R",
                    ("left", "bottom"): "BL",
                    ("center", "bottom"): "B",
                    ("right", "bottom"): "BR",
                }[(horizontal, vertical)]
                button = QToolButton(group)
                button.setText(label)
                button.setFixedSize(36, 25)
                button.setToolTip(f"Align selection {vertical} {horizontal} on the board")
                button.clicked.connect(
                    lambda _checked=False, h=horizontal, v=vertical: self._align_selection(h, v)
                )
                buttons[(horizontal, vertical)] = button
                grid.addWidget(button, row, column)
        return group, buttons

    def _bind_actions(self) -> None:
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.open_button.clicked.connect(self.open_dxf)
        self.repair_button.clicked.connect(self.repair_vectors)
        self.process_button.clicked.connect(self.process)
        self.correct_button.clicked.connect(self.replace_with_corrected)
        self.optimize_button.clicked.connect(self.optimize)
        self.export_button.clicked.connect(self.export_dxf)
        self.sw_get_button.clicked.connect(self._sw_get_board)
        self.sw_send_button.clicked.connect(self._sw_send)
        self.sw_preview_button.clicked.connect(self._sw_preview)
        self.select_tool_action.triggered.connect(lambda: self.view.set_tool("lasso"))
        self.free_lasso_tool_action.triggered.connect(lambda: self.view.set_tool("free_lasso"))
        self.dimension_tool_action.toggled.connect(self._toggle_dimension_tool)
        self.tool_group.triggered.connect(lambda _action: self.dimension_tool_action.setChecked(False))
        self.show_vectors_action.toggled.connect(self._toggle_vectors)
        self.fit_content_action.triggered.connect(self._fit_content)
        self.sim_fit_action.triggered.connect(self.sim_view.fit_content)
        self._bind_canvas_shortcut(self.select_tool_action, QKeySequence("L"))
        self._bind_canvas_shortcut(self.free_lasso_tool_action, QKeySequence("F"))
        self._bind_canvas_shortcut(self.dimension_tool_action, QKeySequence("D"))
        self._bind_canvas_shortcut(self.select_all_action, QKeySequence.StandardKey.SelectAll)
        self.select_all_action.triggered.connect(self._select_all)
        self._bind_canvas_shortcut(self.select_all_visible_action, QKeySequence("Ctrl+Shift+A"))
        self.select_all_visible_action.triggered.connect(self._select_all_visible)
        self._bind_window_shortcut(self.cut_action, QKeySequence.StandardKey.Cut)
        self.cut_action.triggered.connect(self._cut)
        self._bind_window_shortcut(self.copy_action, QKeySequence.StandardKey.Copy)
        self.copy_action.triggered.connect(self._copy)
        self._bind_window_shortcut(self.paste_action, QKeySequence.StandardKey.Paste)
        self.paste_action.triggered.connect(self._paste)
        self._bind_canvas_shortcut(self.delete_action, QKeySequence.StandardKey.Delete)
        self.delete_action.triggered.connect(self._delete)
        self.save_to_library_action = QAction(self.tr("Save Selection to Library"), self)
        self.save_to_library_action.triggered.connect(self._save_to_library)
        self.cut_to_layer_action = QAction(self.tr("Cut to New Layer"), self)
        self.cut_to_layer_action.triggered.connect(self._cut_to_new_layer)
        self.copy_to_layer_action = QAction(self.tr("Copy to New Layer"), self)
        self.copy_to_layer_action.triggered.connect(self._copy_to_new_layer)
        # Rotate/Flip submenus for the right-click menu. A QMenu's menuAction()
        # slots straight into context_actions and renders as a submenu.
        self.rotate_menu = QMenu(self.tr("Rotate"), self)
        for degrees in (45, -45, 90, -90, 135, -135, 180):
            self.rotate_menu.addAction(
                f"{degrees}°", lambda _checked=False, d=degrees: self._rotate_selection(d)
            )
        self.rotate_menu.addSeparator()
        self.rotate_menu.addAction(self.tr("Custom angle…"), self._rotate_selection_custom)
        self.flip_menu = QMenu(self.tr("Flip"), self)
        self.flip_menu.addAction(self.tr("Flip horizontally"), lambda: self._flip_selection(True))
        self.flip_menu.addAction(self.tr("Flip vertically"), lambda: self._flip_selection(False))
        self.view.context_actions = [
            self.cut_action,
            self.copy_action,
            self.paste_action,
            self.delete_action,
            self.rotate_menu.menuAction(),
            self.flip_menu.menuAction(),
            self.cut_to_layer_action,
            self.copy_to_layer_action,
            self.save_to_library_action,
        ]
        self.group_action.triggered.connect(self._group)
        self.ungroup_action.triggered.connect(self._ungroup)
        self._bind_canvas_shortcut(self.smooth_action, QKeySequence("S"))
        self.smooth_action.triggered.connect(self._smooth)
        self.smooth_corners_action.triggered.connect(self._smooth_corners)
        self._bind_canvas_shortcut(self.text_action, QKeySequence("T"))
        self.text_action.triggered.connect(self._insert_text)
        self.text_button.clicked.connect(self._insert_text)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self._undo)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self._redo)
        self.layer_list.currentItemChanged.connect(self._on_active_layer_changed)
        self.layer_list.itemChanged.connect(self._on_layer_item_changed)
        self.add_layer_button.clicked.connect(self._add_layer)
        self.clone_layer_button.clicked.connect(self._clone_layer)
        self.rename_layer_button.clicked.connect(self._rename_layer)
        self.delete_layer_button.clicked.connect(self._delete_layer)
        self.dim_list.itemClicked.connect(self._on_dim_list_clicked)
        self.delete_dim_button.clicked.connect(self._delete_selected_dim)
        self.warning_list.itemClicked.connect(self._on_warning_clicked)
        self.select_all_warnings_button.clicked.connect(self._select_all_warnings)
        self.locate_warning_button.clicked.connect(self._locate_next_warning_balloon)
        self.clear_balloons_button.clicked.connect(self._clear_warning_balloons)
        self.copy_log_button.clicked.connect(self._copy_log)
        self.clear_log_button.clicked.connect(self.log_view.clear)
        self.fit_board_width_button.clicked.connect(lambda: self._fit_selection_to_board("width"))
        self.fit_board_height_button.clicked.connect(lambda: self._fit_selection_to_board("height"))
        self.layout_width.valueChanged.connect(lambda value: self._sync_layout_aspect("width", value))
        self.layout_height.valueChanged.connect(lambda value: self._sync_layout_aspect("height", value))
        # No Apply button anymore: the spinboxes resize the selection directly.
        self.layout_width.editingFinished.connect(lambda: self._apply_size_spinbox("width"))
        self.layout_height.editingFinished.connect(lambda: self._apply_size_spinbox("height"))
        for widget in [self.board_width, self.board_height, self.endmill, self.repair, self.curve_tolerance]:
            widget.valueChanged.connect(self._invalidate_approval)
        self.trace.currentTextChanged.connect(self._invalidate_approval)
        self.hide_islands.stateChanged.connect(self._invalidate_approval)
        self.units.currentTextChanged.connect(self._on_units_changed)
        self._on_units_changed()

    def _bind_canvas_shortcut(self, action: QAction, shortcut) -> None:
        action.setShortcut(shortcut)
        action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.view.addAction(action)

    def _bind_window_shortcut(self, action: QAction, shortcut) -> None:
        action.setShortcut(shortcut)
        action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)

    def _toggle_dimension_tool(self, checked: bool) -> None:
        if checked:
            active = self.tool_group.checkedAction()
            if active is not None:
                active.setChecked(False)
            self.view.set_tool("dimension")
        elif self.tool_group.checkedAction() is None:
            # Toggled off directly (button or D): fall back to the box lasso.
            self.select_tool_action.setChecked(True)
            self.view.set_tool("lasso")

    def _on_view_selection_changed(self) -> None:
        self._sync_action_states(check_dirty=False)  # selection can't dirty the doc
        self._remeasure_active_dims()
        self._refresh_dim_list()
        self._refresh_layout_panel()

    def _align_selection(self, horizontal: str, vertical: str) -> None:
        bounds = self.editor.selected_bounds()
        if bounds is None:
            self._set_progress(0, "Select vectors before aligning")
            return
        pattern = _anchor_point(bounds, horizontal, vertical)
        board = _anchor_point(
            (0.0, 0.0, self.board_width.value(), self.board_height.value()),
            horizontal,
            vertical,
        )
        self._apply_layout_transform(
            bounds[2] - bounds[0],
            bounds[3] - bounds[1],
            (pattern.x(), pattern.y()),
            (board.x(), board.y()),
            "Selection aligned to board",
        )

    # -- Board-relative dimensions ------------------------------------------

    def _dim_key(self) -> frozenset[int] | None:
        ids = self.editor.selected_target_ids()
        return frozenset(ids) if ids else None

    def _dim_context(self) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]] | None:
        bounds = self.editor.selected_bounds()
        if bounds is None:
            return None
        board = (0.0, 0.0, self.board_width.value(), self.board_height.value())
        return bounds, board

    def _active_dims(self) -> list[Dimension]:
        key = self._dim_key()
        return self._dim_store.get(key, []) if key is not None else []

    def _layer_dims(self) -> list[tuple[Dimension, tuple, tuple]]:
        """Dims to draw/list: every stored dim whose pattern lives on the layer
        currently selected in the Layers tab, each paired with its own pattern
        box. Decoupled from the on-canvas selection so dims stay visible while
        you work on the layer, and hidden when you switch to another one.
        """
        active = self.editor.active_layer
        if not self.editor.is_layer_visible(active):
            return []
        board = (0.0, 0.0, self.board_width.value(), self.board_height.value())
        out: list[tuple[Dimension, tuple, tuple]] = []
        for key, dims in self._dim_store.items():
            ids = set(key)
            if self.editor.layer_of_ids(ids) != active:
                continue
            pat = self.editor.bounds_for_ids(ids)
            if pat is None:  # pattern gone (deleted/undone-away): dim lies dormant
                continue
            for dim in dims:
                out.append((dim, pat, board))
        return out

    def _find_dim(self, dim_id: int) -> tuple[frozenset[int], Dimension] | None:
        for key, dims in self._dim_store.items():
            for dim in dims:
                if dim.id == dim_id:
                    return key, dim
        return None

    def _select_dim_pattern(self, key: frozenset[int]) -> None:
        """Make a stored dim's pattern the current selection, so an edit/flip can
        drive it through the existing selection-based layout solver."""
        ids = set(key)
        self.editor.selected_ids = {v.id for v in self.editor.vectors if v.id in ids}
        self.editor.selected_spline_ids = {s.id for s in self.editor.splines if s.id in ids}
        self.view.refresh_selection()

    def _remeasure_active_dims(self) -> None:
        # Dimensions track the live geometry between edits, so their displayed
        # value always reflects reality; editing one is what drives the pattern.
        for dim, pat, brd in self._layer_dims():
            dim.value = dimensions.measure(dim, pat, brd)

    def _refresh_dim_list(self) -> None:
        current = self.dim_list.currentItem()
        current_id = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        self.dim_list.clear()
        dims = self._layer_dims()
        for dim, pat, brd in dims:
            label = self.view._dim_label(dimensions.measure(dim, pat, brd), dim.driving)
            axis = "X" if dim.axis == "x" else "Y"
            item = QListWidgetItem(f"{axis} {label} — {_feature_text(dim.feat1)} → {_feature_text(dim.feat2)}")
            item.setData(Qt.ItemDataRole.UserRole, dim.id)
            self.dim_list.addItem(item)
            if dim.id == current_id:
                self.dim_list.setCurrentItem(item)
        self.delete_dim_button.setEnabled(bool(dims))

    def _on_dim_list_clicked(self, item: QListWidgetItem) -> None:
        self.view.zoom_to_dim(item.data(Qt.ItemDataRole.UserRole))

    def _delete_selected_dim(self) -> None:
        item = self.dim_list.currentItem()
        if item is not None:
            self._delete_dim(item.data(Qt.ItemDataRole.UserRole))

    def _delete_dim(self, dim_id: int) -> None:
        found = self._find_dim(dim_id)
        if found is None:
            return
        key, _ = found
        self._dim_store[key] = [d for d in self._dim_store[key] if d.id != dim_id]
        if self.view._selected_dim_id == dim_id:
            self.view._selected_dim_id = None
        self.view.refresh_selection()

    def _flip_dim(self, dim_id: int) -> None:
        # SolidWorks-style flip: negate a driving location dim so the pattern sits
        # the same distance on the opposite side of the reference.
        found = self._find_dim(dim_id)
        if found is None:
            return
        key, dim = found
        if not (dim.is_position and dim.driving):
            self._set_progress(0, "Only a driving location dimension can be flipped.")
            return
        self._select_dim_pattern(key)
        dim.value = -dim.value
        self._apply_dims_to_geometry()

    def _on_dim_label_moved(self, dim_id: int, along: float) -> None:
        found = self._find_dim(dim_id)
        if found is not None:
            found[1].label_along = along

    def _on_dim_placed(self, feat1: Feature, feat2: Feature, axis: str, offset: float) -> None:
        key = self._dim_key()
        context = self._dim_context()
        if key is None or context is None:
            return
        pat, brd = context
        dim = Dimension(feat1=feat1, feat2=feat2, axis=axis, label_offset=offset)
        dim.value = dimensions.measure(dim, pat, brd)
        dims = self._dim_store.setdefault(key, [])
        if not (dim.is_size or dim.is_position):
            # Board-to-board spans nothing to drive; keep it as a reference only.
            dim.driving = False
        else:
            axis_driving = [d for d in dims if d.driving and d.axis == axis] + [dim]
            if dimensions.is_overconstrained(axis_driving):
                if self._dim_conflict_dialog():
                    dim.driving = False
                else:
                    return
        dims.append(dim)
        self.view.refresh_selection()
        if dim.driving:
            self._edit_dim_value(dim.id)

    def _edit_dim_value(self, dim_id: int) -> None:
        found = self._find_dim(dim_id)
        if found is None:
            return
        key, dim = found
        if not dim.driving:
            QMessageBox.information(
                self,
                "Reference dimension",
                "This dimension is driven (reference only) and can't be edited.",
            )
            return
        self._select_dim_pattern(key)  # so the selection-based solver drives it
        context = self._dim_context()
        if context is None:
            return
        pat, brd = context
        measured = dimensions.measure(dim, pat, brd)
        unit = _effective_units(self.units.currentText())
        new_value, accepted = QInputDialog.getDouble(
            self, "Edit Dimension", f"Value ({unit}):", abs(measured), 0.001, 1e6, 3
        )
        if not accepted:
            return
        dim.value = new_value if measured >= 0 else -new_value
        self._apply_dims_to_geometry()

    def _dim_conflict_dialog(self) -> bool:
        result = QMessageBox.question(
            self,
            "Over-defined layout",
            "This dimension over-defines the selection on that axis.\n"
            "Make it a driven (reference-only) dimension?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        return result == QMessageBox.StandardButton.Yes

    def _aspect_lock_conflict_dialog(self) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Aspect ratio locked")
        box.setText(
            "These dimensions resize width and height by different amounts, "
            "which breaks the locked aspect ratio.\n"
            "Disable lock aspect ratio to apply them?"
        )
        disable = box.addButton("Disable lock aspect ratio", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return box.clickedButton() is disable

    def _mirror_locked_axis(self, dims, bounds, board, axis, scale):
        """Force ``axis`` to ``scale`` for the aspect lock, re-solving its
        translate so a lone position dim keeps its clearance. Returns
        ``[scale, translate, has_size, count]`` or ``None`` when the axis is
        independently pinned (two position dims) to a conflicting scale."""
        x1, y1, x2, y2 = bounds
        cur = (x2 - x1) if axis == "x" else (y2 - y1)
        positions = [d for d in dims if d.driving and d.axis == axis and d.is_position]
        try:
            s, t = dimensions.solve_axis(positions, bounds, board, axis, size_override=cur * scale)
        except OverConstrainedError:
            return None
        return [s, t, False, len(positions)]

    def _apply_dims_to_geometry(self, size_override: tuple[str, float] | None = None) -> None:
        dims = self._active_dims()
        bounds = self.editor.selected_bounds()
        if bounds is None:
            return
        x1, y1, x2, y2 = bounds
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        board = (0.0, 0.0, self.board_width.value(), self.board_height.value())
        solved: dict[str, list] = {}
        for axis in ("x", "y"):
            driving = [d for d in dims if d.driving and d.axis == axis]
            override = size_override[1] if size_override and size_override[0] == axis else None
            try:
                scale, translate = dimensions.solve_axis(driving, bounds, board, axis, size_override=override)
            except OverConstrainedError as error:
                self._set_progress(0, str(error))
                return
            # An axis's scale is pinned by a size dim or by two position dims;
            # a lone position dim only fixes translation, leaving scale free.
            fixed = (
                override is not None
                or any(d.is_size for d in driving)
                or sum(1 for d in driving if d.is_position) >= 2
            )
            solved[axis] = [scale, translate, fixed, len(driving)]
        if self.layout_aspect_lock.isChecked():
            sx, tx, x_fixed, x_count = solved["x"]
            sy, ty, y_fixed, y_count = solved["y"]
            # Whichever axis has its scale pinned drives both. A free axis (no
            # dims, or a lone clearance dim) mirrors the driver's scale while
            # keeping its clearance.
            if x_fixed and not y_fixed:
                mirrored = self._mirror_locked_axis(dims, bounds, board, "y", sx)
                if mirrored is None:
                    if not self._aspect_lock_conflict_dialog():
                        return
                    self.layout_aspect_lock.setChecked(False)
                else:
                    solved["y"] = mirrored
            elif y_fixed and not x_fixed:
                mirrored = self._mirror_locked_axis(dims, bounds, board, "x", sy)
                if mirrored is None:
                    if not self._aspect_lock_conflict_dialog():
                        return
                    self.layout_aspect_lock.setChecked(False)
                else:
                    solved["x"] = mirrored
            elif x_fixed and y_fixed and abs(sx - sy) > 1e-9:
                # Both axes independently pinned to different scales: honoring
                # them would break the locked aspect ratio.
                if not self._aspect_lock_conflict_dialog():
                    return
                self.layout_aspect_lock.setChecked(False)
        sx, tx = solved["x"][0], solved["x"][1]
        sy, ty = solved["y"][0], solved["y"][1]
        self._apply_layout_transform(
            (x2 - x1) * sx,
            (y2 - y1) * sy,
            (cx, cy),
            (cx + tx, cy + ty),
            "Dimensions applied",
        )
        self._remeasure_active_dims()
        self.view.refresh_selection()

    def _apply_size_spinbox(self, axis: str) -> None:
        if self._refreshing_layout:
            return
        bounds = self.editor.selected_bounds()
        if bounds is None:
            return
        x1, y1, x2, y2 = bounds
        current = (x2 - x1) if axis == "width" else (y2 - y1)
        desired = self.layout_width.value() if axis == "width" else self.layout_height.value()
        if current <= 1e-9:
            self._set_progress(0, "Selection has no extent to resize")
            return
        if abs(desired - current) <= 1e-9:
            return
        ax = "x" if axis == "width" else "y"
        dims = self._active_dims()
        axis_driving = [d for d in dims if d.driving and d.axis == ax]
        size_dims = [d for d in axis_driving if d.is_size]
        position_dims = [d for d in axis_driving if d.is_position]
        if size_dims:
            # Manual input drives the existing size dimension in place.
            context = self._dim_context()
            measured = dimensions.measure(size_dims[0], *context) if context else 1.0
            size_dims[0].value = desired if measured >= 0 else -desired
            self._apply_dims_to_geometry()
            return
        if len(position_dims) >= 2:
            # Two position dims already imply the size, so a manual size conflicts.
            if not self._dim_conflict_dialog():
                self._refresh_layout_panel()
                return
            position_dims[0].driving = False
        self._apply_dims_to_geometry(size_override=(ax, desired))

    def _sync_layout_aspect(self, changed_axis: str, value: float) -> None:
        if self._refreshing_layout or not self.layout_aspect_lock.isChecked() or value <= 0:
            return
        ratio = max(self._layout_aspect_ratio, 1e-12)
        self._refreshing_layout = True
        try:
            target = value / ratio if changed_axis == "width" else value * ratio
            other = self.layout_height if changed_axis == "width" else self.layout_width
            other.setValue(target)
        finally:
            self._refreshing_layout = False

    def _refresh_layout_panel(self) -> None:
        if self._refreshing_layout:
            return
        bounds = self.editor.selected_bounds()
        enabled = not self._busy and bounds is not None
        self.selection_layout_group.setEnabled(enabled)
        if bounds is None:
            for label in self.layout_readouts.values():
                label.setText("-")
            return
        x1, y1, x2, y2 = bounds
        width = x2 - x1
        height = y2 - y1
        unit = _effective_units(self.units.currentText())
        values = {
            "width": width,
            "height": height,
            "left": x1,
            "right": self.board_width.value() - x2,
            "bottom": y1,
            "top": self.board_height.value() - y2,
        }
        self._refreshing_layout = True
        try:
            for name, value in values.items():
                self.layout_readouts[name].setText(_format_layout_value(value, unit))
            self.layout_width.setValue(max(width, self.layout_width.minimum()))
            self.layout_height.setValue(max(height, self.layout_height.minimum()))
            self._layout_aspect_ratio = width / height if height > 1e-12 else 1.0
            self.view.layout_units = unit
        finally:
            self._refreshing_layout = False

    def _fit_selection_to_board(self, axis: str) -> None:
        bounds = self.editor.selected_bounds()
        if bounds is None:
            self._set_progress(0, "Select vectors before fitting to the board")
            return
        current_width = bounds[2] - bounds[0]
        current_height = bounds[3] - bounds[1]
        if current_width <= 1e-12 or current_height <= 1e-12:
            self._set_progress(0, "Fit to board requires a selection with non-zero width and height")
            return
        width = self.board_width.value() if axis == "width" else current_width
        height = self.board_height.value() if axis == "height" else current_height
        if self.layout_aspect_lock.isChecked():
            ratio = current_width / current_height
            if axis == "width":
                height = width / ratio
            else:
                width = height * ratio
        # Scale about the selection's centre; Fit only resizes, it does not move.
        pattern = _anchor_point(bounds, "center", "center")
        label = "width" if axis == "width" else "height"
        self._apply_layout_transform(
            width,
            height,
            (pattern.x(), pattern.y()),
            (pattern.x(), pattern.y()),
            f"Selection fitted to board {label}",
        )

    def _apply_layout_transform(
        self,
        width: float,
        height: float,
        pattern_reference: tuple[float, float],
        board_reference: tuple[float, float],
        success_message: str,
    ) -> None:
        try:
            changed = self.editor.apply_selected_layout(
                width,
                height,
                pattern_reference,
                board_reference,
            )
        except ValueError as error:
            self._set_progress(0, str(error))
            return
        if not changed:
            self._set_progress(0, "Layout is already applied")
            return
        # Resizing moves every point, so endpoint coincidence (and with it the
        # fault count) can change; without this the canvas keeps showing the
        # pre-resize count until the next import or repair.
        self._invalidate_editor_result(update_open_profiles=True)
        self._refresh_layout_panel()
        self.view.ensure_selection_visible()
        self._finish_progress(success_message)

    def save_project(self) -> None:
        # Already saved/opened as a project -> overwrite in place. Otherwise (fresh
        # import, or crash-restore which unsets current_file) fall through to Save As.
        if self.current_file and self.current_file.suffix == project.SUFFIX:
            self._write_project(self.current_file)
        else:
            self.save_project_as()

    def new_project(self) -> None:
        """Clear the session back to an empty board, prompting first if unsaved."""
        if not self._confirm_discard("Start a new project?"):
            return
        self._clear_warning_state()
        self.editor.load([], [])  # resets to a single empty "Layer 1", clears undo/redo
        self._dim_store = {}
        self.current_file = None
        self.current_files = []
        self.current_result = None
        self._clear_repair_session()
        self._refresh(update_open_profiles=True)
        self.view.fit_content()
        self._mark_saved()  # empty session is the new clean baseline
        self._finish_progress("New project")

    def _project_signature(self) -> str:
        """A stable string of everything a save would write. Two sessions with the same
        signature are identical on disk, so Save has nothing to do."""
        payload = project.serialize(
            self.editor.vectors,
            self.editor.splines,
            self.editor.layers,
            self.editor.active_layer,
            self._project_settings(),
            self._dim_store,
        )
        return json.dumps(payload, sort_keys=True)

    def _mark_saved(self) -> None:
        self._saved_signature = self._project_signature()
        self._sync_action_states()  # refresh the greyed Save button/action

    def _is_dirty(self) -> bool:
        # None baseline (still constructing) reads as clean so Save starts greyed.
        return self._saved_signature is not None and self._project_signature() != self._saved_signature

    def _confirm_discard(self, question: str) -> bool:
        """Ask before throwing away unsaved changes. Returns True if it is OK to proceed
        (nothing to lose, saved on request, or the user chose to continue anyway);
        False if they cancelled or the save dialog was dismissed."""
        if not self._is_dirty():
            return True
        # A confirmation modal needs an interactive display to answer it. Under the
        # offscreen QPA (headless tests / automation) there is no user, so exec()
        # would block forever -- proceed without prompting instead.
        if QApplication.platformName() == "offscreen":
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Unsaved changes")
        box.setText(question)
        box.setInformativeText("Your changes will be lost if you don't save them.")
        save_btn = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Continue without saving", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(save_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is cancel_btn:
            return False
        if clicked is save_btn:
            self.save_project()
            return not self._is_dirty()  # Save-As can be cancelled at the file dialog
        return True  # continue without saving

    def save_project_as(self) -> None:
        """Always prompt for a location -- keeps the original when saving a copy."""
        default = str(self.current_file.with_suffix(project.SUFFIX)) if self.current_file else ""
        chosen, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", default, f"CurveMill projects (*{project.SUFFIX})"
        )
        if not chosen:
            return
        self._write_project(Path(chosen).with_suffix(project.SUFFIX))

    def _write_project(self, path: Path) -> None:
        try:
            self._snapshot_project(path)
        except OSError as error:
            self._on_worker_error("Could not save project", str(error))
            return
        self.current_file = path  # subsequent Saves overwrite this file directly
        self._remember_recent(path)
        self._mark_saved()  # live state now matches disk -> Save greys out
        self._finish_progress(f"Saved {path.stem}")

    def _snapshot_project(self, path: Path) -> None:
        """Write the full session to path in the .curvemill format (save + autosave)."""
        project.save(
            path,
            self.editor.vectors,
            self.editor.splines,
            self.editor.layers,
            self.editor.active_layer,
            self._project_settings(),
            self._dim_store,
        )

    def _autosave(self) -> None:
        # Nothing to recover from an empty editor — and writing the file anyway would
        # trigger a spurious restore prompt after a clean-but-empty session.
        if not (self.editor.vectors or self.editor.splines):
            return
        try:
            # The settings dir may not exist yet (QSettings creates it lazily on write).
            self._autosave_path.parent.mkdir(parents=True, exist_ok=True)
            self._snapshot_project(self._autosave_path)
        except OSError:
            pass  # autosave must never interrupt the user; the next tick retries

    def offer_crash_report(self, crash_log: Path | None) -> None:
        """If the last run left a crash log, warn and offer to open it."""
        if crash_log is None or not crash_log.exists() or crash_log.stat().st_size == 0:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("CurveMill crashed")
        box.setText("CurveMill closed unexpectedly last session.")
        box.setInformativeText("A crash report was saved. Open it to see what happened.")
        open_button = box.addButton("Open Log", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Dismiss", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_button:
            from PySide6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(crash_log)))

    def offer_crash_restore(self) -> None:
        """If an autosave survived (previous session crashed), offer to reopen it."""
        if not self._autosave_path.exists():
            return
        choice = QMessageBox.question(
            self,
            "Restore last session?",
            "CurveMill closed unexpectedly. Restore your last session?",
        )
        if choice == QMessageBox.StandardButton.Yes:
            # remember=False: the autosave is a temp recovery file, not a real project,
            # so keep it out of Recent and leave current_file unset so Save asks where.
            self.open_project(self._autosave_path, remember=False)
            self.current_file = None
        else:
            self._autosave_path.unlink(missing_ok=True)

    def closeEvent(self, event) -> None:
        if not self._confirm_discard("Exit CurveMill?"):
            event.ignore()
            return
        self._autosave_timer.stop()
        self._autosave_path.unlink(missing_ok=True)  # clean exit: no crash to recover
        super().closeEvent(event)

    def open_project(self, path: Path | None = None, *, remember: bool = True) -> None:
        if path is None:
            chosen, _ = QFileDialog.getOpenFileName(
                self, "Open Project", "", f"CurveMill projects (*{project.SUFFIX})"
            )
            if not chosen:
                return
            path = Path(chosen)
        try:
            vectors, splines, layers, active_layer, settings, dim_store = project.load(path)
        except (OSError, ValueError, KeyError, TypeError) as error:
            self._on_worker_error("Could not open project", str(error))
            return
        self._clear_warning_state()
        self.editor.load(vectors, splines)
        # load() rebuilds layers from the geometry, which drops empty layers and
        # every visibility flag, so restore the saved list over the top.
        self.editor.layers = layers
        self.editor.active_layer = active_layer
        self._dim_store = dim_store
        self._apply_project_settings(settings)
        self.current_files = [path]
        self.current_file = path
        self.current_result = None
        self._clear_repair_session()
        self._refresh(update_open_profiles=True)
        self.view.fit_content()
        if remember:
            self._remember_recent(path)
            self._mark_saved()  # freshly opened == matches disk. A crash-restore
            # (remember=False) deliberately stays dirty so Save is offered.
        self._finish_progress(f"Opened {path.stem}")

    def _project_settings(self) -> dict:
        return {
            "board_width": self.board_width.value(),
            "board_height": self.board_height.value(),
            "units": self.units.currentText(),
            "tool": self._current_tool().to_dict(),
            "cut_depth": self.cut_depth.value(),
            "trace_mode": self.trace.currentText(),
        }

    def _apply_project_settings(self, settings: dict) -> None:
        if not settings:
            return
        self.board_width.setValue(float(settings.get("board_width", self.board_width.value())))
        self.board_height.setValue(float(settings.get("board_height", self.board_height.value())))
        units = settings.get("units")
        if units and self.units.findText(units) >= 0:
            self.units.setCurrentText(units)
        tool = settings.get("tool")
        if tool:
            self._apply_tool(Tool.from_dict(tool))
        self.cut_depth.setValue(float(settings.get("cut_depth", self.cut_depth.value())))
        trace = settings.get("trace_mode")
        if trace and self.trace.findText(trace) >= 0:
            self.trace.setCurrentText(trace)

    def _recent_projects(self) -> list[str]:
        return [p for p in json.loads(str(self.settings.value("recent/projects", "[]")) or "[]") if Path(p).exists()]

    def _remember_recent(self, path: Path) -> None:
        recent = [str(path)] + [p for p in self._recent_projects() if p != str(path)]
        self.settings.setValue("recent/projects", json.dumps(recent[:10]))
        self._refresh_recent_menu()

    def _refresh_recent_menu(self) -> None:
        self.recent_menu.clear()
        recent = self._recent_projects()
        self.recent_menu.setEnabled(bool(recent))
        for entry in recent:
            path = Path(entry)
            self.recent_menu.addAction(path.stem, lambda checked=False, p=path: self.open_project(p))

    def open_dxf(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Insert DXF Files", "", "DXF files (*.dxf)")
        if not paths:
            return
        self._clear_warning_state()
        files = [Path(path) for path in paths]
        units = self.units.currentText()
        import_units = "mm" if units == "dxf" else units
        curve_tolerance = self.curve_tolerance.value()
        self._start_progress("Reading DXF files")
        self._set_busy(True)

        def import_job(progress):
            imported = []
            total = len(files)
            for index, path in enumerate(files):
                def file_progress(value, message, file_index=index, file_name=path.name):
                    overall = int((file_index * 100 + value) / total)
                    progress(overall, f"{file_name}: {message}")

                imported.append((path, import_dxf(path, import_units, curve_tolerance, file_progress)))
            return imported

        worker = Worker(import_job)
        worker.signals.progress.connect(self._set_worker_progress)
        worker.signals.done.connect(self._on_import_done)
        worker.signals.error.connect(lambda message: self._on_worker_error("Could not insert DXF", message))
        self.thread_pool.start(worker)

    def _on_import_done(self, imported) -> None:
        inserted_files = [Path(path) for path, _result in imported]
        had_drawing = bool(self.editor.vectors) or self.editor.layer_names() != ["Layer 1"]
        if had_drawing:
            self.editor.append_layers(
                [(Path(path).stem, result.vectors) for path, result in imported],
                [(Path(path).stem, result.splines) for path, result in imported if result.splines],
            )
        else:
            self.editor.load_layers(
                [(Path(path).stem, result.vectors) for path, result in imported],
                [(Path(path).stem, result.splines) for path, result in imported if result.splines],
            )
        self.current_files.extend(inserted_files)
        self.current_file = self.current_files[0] if self.current_files else None
        warnings = [
            f"{Path(path).name}: {warning}"
            for path, result in imported
            for warning in result.warnings
        ]
        self._set_warnings(warnings, [])
        self.current_result = None
        self._clear_repair_session()
        self._refresh(update_open_profiles=True)
        # Fit to the imported geometry only when it landed on a fresh canvas --
        # open_project/new_project fit too, but inserting into an existing drawing
        # must leave the user's current view where it is. Without this, a DXF whose
        # coordinates sit outside the default board shows only an off-screen slice
        # and reads as "nothing appeared".
        if not had_drawing:
            self.view.fit_content()
        self._set_busy(False)
        self._finish_progress("DXF files inserted")

    def repair_vectors(self) -> None:
        # Duplicates are redundant by definition, so delete them outright before
        # snapping endpoints (their own undo step; often clears multi-vertex too).
        # The scan below runs synchronously on the GUI thread, so paint the
        # progress message first or the bar stays frozen until it finishes.
        self._start_progress("Scanning for duplicates")
        QApplication.processEvents()
        removed = self.editor.remove_duplicates()
        # Sub-tolerance fragments are undercuttable noise that snap would weld
        # into zero-area self-crossing loops and multi-vertex junctions -- delete
        # them before snapping, like duplicates.
        degenerate = self.editor.remove_degenerate(self.repair.value())
        self._repair_removed = removed
        removed_note = ""
        if removed or degenerate:
            notes = []
            if removed:
                noun = "entity" if removed == 1 else "entities"
                notes.append(f"{removed} duplicate {noun}")
            if degenerate:
                noun = "fragment" if degenerate == 1 else "fragments"
                notes.append(f"{degenerate} sub-tolerance {noun}")
            removed_note = "Removed " + " and ".join(notes)
            self._clear_warning_state()
            self.current_result = None
            self.view.set_result(None)
            self._refresh(update_open_profiles=True)
        geometry = self._repair_input_geometry()
        if geometry is None:
            # Nothing open to snap. Self-intersections are still owed a heal -- the
            # zo9yyqx7 case is 0 open profiles yet SolidWorks rejects the sketch.
            # A cancelled tolerance dialog only happens when open profiles exist, so
            # gate on open_profiles == 0 to tell "nothing to do" from "user cancelled".
            if self._open_profile_count == 0:
                self._finish_repair()
            elif removed_note:
                self._set_progress(100, removed_note)
            return
        vectors, splines = geometry
        self._clear_warning_state()
        self.current_result = None
        self.view.set_result(None)
        tolerance = self.repair.value()
        self._last_repair_tolerance = tolerance
        self._start_progress(f"{removed_note}; scanning endpoints" if removed_note else "Scanning endpoints")
        self._set_busy(True)
        worker = Worker(lambda progress: repair_geometry(vectors, splines, tolerance, progress))
        worker.signals.progress.connect(self._set_worker_progress)
        worker.signals.done.connect(self._on_repair_done)
        worker.signals.error.connect(lambda message: self._on_worker_error("Could not repair vectors", message))
        self.thread_pool.start(worker)

    def _repair_input_geometry(self) -> tuple[list[VectorEntity], list[SplineEntity]] | None:
        visible_vectors, visible_splines = self.editor.visible_vectors_and_splines()
        # Open profiles are counted on the flattened geometry (splines included),
        # so the repair gate must consider splines too or Repair would refuse to
        # run on the very open paths Process warns about.
        if count_profile_issues(self.editor.all_visible_vectors()).open_profiles == 0:
            self._set_progress(0, "No open profiles to repair")
            return None
        open_vectors = [vector.clone() for vector in visible_vectors if not vector.closed]
        # Splines are repaired natively by snapping their end control points, so
        # they never get converted to polylines here.
        open_splines = [
            spline.clone()
            for spline in visible_splines
            if not spline.closed and not spline.periodic
        ]
        if not open_vectors and not open_splines:
            self._set_progress(0, "No open profiles to repair")
            return None
        tolerance = self.repair.value()
        tolerance_changed = (
            self._last_repair_tolerance is not None
            and abs(tolerance - self._last_repair_tolerance) > 1e-12
        )
        if self._repair_source_vectors is not None and tolerance_changed:
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Question)
            dialog.setWindowTitle("Repair tolerance changed")
            dialog.setText("Open profiles remain after the previous repair.")
            dialog.setInformativeText(
                "Replace previous repairs from the original vectors, or continue repairing only the profiles that remain open."
            )
            replace_button = dialog.addButton("Replace Previous Repairs", QMessageBox.ButtonRole.AcceptRole)
            remaining_button = dialog.addButton("Repair Remaining Open Profiles", QMessageBox.ButtonRole.ActionRole)
            dialog.addButton(QMessageBox.StandardButton.Cancel)
            dialog.exec()
            if dialog.clickedButton() is replace_button:
                return (
                    [
                        self._repair_source_vectors[vector.id].clone()
                        for vector in visible_vectors
                        if vector.id in self._repair_source_vectors
                    ],
                    [
                        self._repair_source_splines[spline.id].clone()
                        for spline in visible_splines
                        if spline.id in self._repair_source_splines
                    ],
                )
            if dialog.clickedButton() is not remaining_button:
                return None
            return open_vectors, open_splines
        if self._repair_source_vectors is None:
            self._repair_source_vectors = {vector.id: vector.clone() for vector in open_vectors}
            self._repair_source_splines = {spline.id: spline.clone() for spline in open_splines}
        return open_vectors, open_splines

    def _on_repair_done(self, repaired) -> None:
        repaired_vectors, repaired_splines = repaired
        if self.editor.replace_geometry_subset(repaired_vectors, repaired_splines):
            self.current_result = None
            self._refresh(update_open_profiles=True)
        self._set_busy(False)
        self._finish_repair()

    def _heal_self_intersections(self) -> int:
        # Rewrite profiles whose outline crosses itself (split at the crossing into
        # sub-loops) so SolidWorks accepts the sketch. Visible layers only, so hidden
        # geometry is neither chained into the repair nor silently rewritten.
        # Near-linear chaining + only the few crossing profiles rebuilt -> GUI thread.
        visible = self.editor.visible_layer_names()
        vectors = [v for v in self.editor.vectors if v.layer in visible]
        # ponytail: heal must see EXACTLY what the fault counter sees
        # (all_visible_vectors = vectors + every visible spline flattened at 0.5).
        # A crossing formed only when several optimize pieces -- or a spline and a
        # vector -- chain into one profile is invisible to any per-spline check
        # (the previous version only flattened individually-crossing splines, so
        # multi-piece crossers were counted but never healed: the stuck-at-15).
        # So flatten every visible spline into the heal set, then keep native any
        # spline whose flat came back untouched -- heal preserves identity for
        # clean entities, so an untouched flat's id proves its spline is clean.
        # Only crossing profiles lose their native spline form, which they must:
        # their outline is being rewritten into split sub-loops.
        flat_to_spline: dict[int, SplineEntity] = {}
        flats = []
        for s in self.editor.splines:
            if s.layer in visible:
                flat = s.flatten(0.5)
                flat_to_spline[flat.id] = s
                flats.append(flat)
        healed, count = heal_self_intersections(vectors + flats)
        if count:
            self.editor._push_undo()
            untouched_flats = {v.id for v in healed if v.id in flat_to_spline}
            consumed_splines = {
                s.id for fid, s in flat_to_spline.items() if fid not in untouched_flats
            }
            healed_vectors = [v for v in healed if v.id not in flat_to_spline]
            self.editor.vectors = [v for v in self.editor.vectors if v.layer not in visible] + healed_vectors
            self.editor.splines = [s for s in self.editor.splines if s.id not in consumed_splines]
            self.editor.selected_ids.clear()
        return count

    def _finish_repair(self) -> None:
        # Last Repair step, shared by the worker-done path and the no-open-profiles
        # path: heal self-crossing profiles, then report duplicates + heal together
        # (endpoint snapping already reported itself in the worker's progress).
        healed = self._heal_self_intersections()
        # Splitting a barely-bigger-than-tolerance crosser leaves sub-tolerance
        # ring crumbs; purge them now so one Repair click converges instead of
        # leaving junk for the next click to delete.
        if healed:
            self.editor.remove_degenerate(self.repair.value())
        if healed:
            self._clear_warning_state()
            self.current_result = None
            self.view.set_result(None)
            self._refresh(update_open_profiles=True)
        parts = []
        if getattr(self, "_repair_removed", 0):
            n = self._repair_removed
            parts.append(f"removed {n} duplicate{'' if n == 1 else 's'}")
        if healed:
            parts.append(f"healed {healed} self-intersection{'' if healed == 1 else 's'}")
        self._finish_progress("Repair complete" + (f" ({', '.join(parts)})" if parts else ""))

    def process(self) -> None:
        self._clear_warning_state()
        self.current_result = None
        options = self._options()
        self.view.result = None
        self.view.set_board(options.board_width, options.board_height)
        # Native splines can't feed the Shapely-based sim directly, so flatten
        # disposable copies here. The editor keeps its splines as NURBS untouched,
        # so a later Export still writes native curves and keeps element counts low.
        jobs = self._layer_jobs()
        if not jobs:
            self._set_progress(0, "Every layer is set to skip")
            return
        self._last_process_jobs = jobs  # kept so the done handler can log each recipe
        self._start_progress("Preparing CNC simulation")
        self._set_busy(True)
        worker = Worker(lambda progress: process_layers(jobs, progress))
        worker.signals.progress.connect(self._set_worker_progress)
        worker.signals.done.connect(self._on_process_done)
        worker.signals.error.connect(lambda message: self._on_worker_error("Could not process DXF", message))
        self.thread_pool.start(worker)

    def _on_process_done(self, result) -> None:
        self.current_result = result
        self.view.set_warning_source(self.current_result.repaired_vectors)
        self._set_warnings(self.current_result.warnings, self.current_result.warning_details)
        self._set_busy(False)
        self._refresh()
        self._finish_progress("Processing complete")
        self._log_process_recipe(getattr(self, "_last_process_jobs", []))
        self.tabs.setCurrentWidget(self._sim_tab)

    def _log_process_recipe(self, jobs) -> None:
        """Record what each layer was cut with, so the Log says how a result was
        produced, not just that it finished."""
        units = _effective_units(self.units.currentText())
        for job in jobs:
            tool = job.tool
            is_laser = tool.kind is ToolKind.LASER
            mode_label = "Laser" if is_laser else _MODE_LABEL.get(job.mode, job.mode)
            parts = [mode_label, f"{_KIND_LABEL[tool.kind]} ⌀{tool.diameter:g} {units}"]
            if not is_laser:
                parts.append(f"depth {job.depth:g} {units}")
            if job.mode == "profile" and not is_laser:  # trace is ignored in V-carve/laser
                parts.append(f"trace {job.options.trace_mode.value}")
            self._log(f"Layer '{job.name}': " + " · ".join(parts))

    def replace_with_corrected(self) -> None:
        """Swap the canvas for the tool-corrected (as-milled) outlines from the
        last simulation. In-editor only -- Export/Send then use the milled shape.

        Each source layer's milled wall goes back on its own layer (keeping that
        layer's tool/depth/mode), so a multi-layer part stays split -- not merged
        onto one CNC_CORRECTED layer -- and the Simulation form keeps its settings.
        """
        if self.current_result is None:
            self._set_progress(0, "Run Process first")
            return
        vectors = result_corrected_vectors_by_layer(
            self.current_result, tolerance=self.simplify_tolerance_setting.value()
        )
        if not vectors:
            self._set_progress(0, "No simulated geometry to apply")
            return
        self.editor._push_undo()
        self.editor.vectors = [v.clone() for v in vectors]
        self.editor.splines = []
        self.editor.selected_ids.clear()
        self.editor.selected_spline_ids.clear()
        # Keep the existing Layer objects (their tools/depths/visibility intact, so
        # the sim form doesn't snap back to defaults); drop only layers that got no
        # corrected geometry so empties don't linger.
        kept = {v.layer for v in self.editor.vectors}
        self.editor.layers = [l for l in self.editor.layers if l.name in kept] or [Layer("Layer 1")]
        if self.editor.active_layer not in {l.name for l in self.editor.layers}:
            self.editor.active_layer = self.editor.layers[0].name
        self._invalidate_editor_result(update_open_profiles=True)
        self._finish_progress(
            f"Replaced pattern with simulated geometry ({len(vectors)} profiles)"
        )

    def export_dxf(self) -> None:
        """Export whatever is on the canvas -- optimized splines, corrected
        geometry, or the raw import -- as a DXF (R2000, native splines)."""
        vectors, splines = self.editor.visible_vectors_and_splines()
        if not vectors and not splines:
            self._set_progress(0, "Nothing to export")
            return
        default = "export.dxf"
        if self.current_file:
            default = f"{self.current_file.stem}_export.dxf"
        path, _ = QFileDialog.getSaveFileName(self, "Export DXF", default, "DXF files (*.dxf)")
        if not path:
            return
        units = self._options().units
        per_segment = self.fit_samples_setting.value()  # read before the worker thread
        # Control-point splines become fit-point splines (SolidWorks counts those as
        # one element each); splines already fit-point-only pass straight through.
        control = [s for s in splines if s.control_points]
        fit_only = [s for s in splines if s.fit_points and not s.control_points]
        out_splines = to_fit_splines(control, per_segment) + fit_only

        def export_job(progress):
            export_vectors(path, vectors, out_splines, units=units,
                           dxf_format="R2000", progress=progress)
            return path

        self._start_progress("Exporting DXF")
        self._set_busy(True)
        worker = Worker(export_job)
        worker.signals.progress.connect(self._set_worker_progress)
        worker.signals.done.connect(self._on_export_done)
        worker.signals.error.connect(lambda message: self._on_worker_error("Could not export DXF", message))
        self.thread_pool.start(worker)

    def _on_export_done(self, path: str) -> None:
        self._set_busy(False)
        self._finish_progress("Export complete")
        QMessageBox.information(self, "Export complete", f"Exported {path}")

    def optimize(self) -> None:
        """Fit the pattern into native splines and replace it in place -- no save.

        1. Join fragmented bezier splines into one native spline per shape
        2. Fit loose line segments into one native spline per smooth run
        3. Replace the active layer's geometry with the result and refresh the
           error counts, so the user sees the new element count and any
           self-intersection the fit introduced -- then Repair/Export/Send/Preview.

        Both halves exist because DXFs arrive fragmented in two different ways:
        Inkscape exports one SPLINE per bezier segment, while pattern files
        export thousands of tiny LINEs sampling a curve. SolidWorks counts every
        one of them; a native spline is a single element however long it is.

        This is lossless and keeps true centerlines. It replaced a
        render-to-PNG + Potrace round trip, which quantized geometry to pixels
        and, being an outline tracer, returned two contours per stroke.
        """
        vectors, splines = self.editor.active_vectors_and_splines()
        if not vectors and not splines:
            self._set_progress(0, "No vectors to optimize")
            return

        self._clear_warning_state()
        self.current_result = None
        self.view.set_result(None)
        self._start_progress("Optimizing for SolidWorks")
        self._set_busy(True)
        corner_degrees = self.corner_degrees_setting.value()  # read before the worker thread

        def optimize_job(progress):
            progress(5, "Joining spline fragments")
            joined = join_spline_fragments(
                splines,
                corner_degrees=corner_degrees,
                progress=lambda v, m: progress(5 + int(v * 0.35), f"Joining: {m}"),
            )
            progress(40, "Fitting line segments")
            fitted = fit_vector_chains(
                vectors,
                corner_degrees=corner_degrees,
                progress=lambda v, m: progress(40 + int(v * 0.35), f"Fitting: {m}"),
            )
            curves = joined + fitted
            # fit_vector_chains emits control-point *fragments* (one per corner-split,
            # and one per segment where the self-cross fallback fires). curves_from_entities
            # -- which the entity column and Send both run -- re-joins those fragments, so
            # the true SolidWorks element count is the joined count, not len(curves). Report
            # that here or the message contradicts the layer tab (measured: 2500 vs 252).
            after = len(join_spline_fragments(curves, corner_degrees=corner_degrees))
            progress(78, f"Reduced {len(curves)} entities to {after} curves")
            return curves, after

        worker = Worker(optimize_job)
        worker.signals.progress.connect(self._set_worker_progress)
        worker.signals.done.connect(self._on_optimize_done)
        worker.signals.error.connect(lambda message: self._on_worker_error("Optimization failed", message))
        self.thread_pool.start(worker)

    def _on_optimize_done(self, payload) -> None:
        """Swap the active layer's fragments for one native spline per shape.

        In-editor only: no file is written. Refreshing the profile counts here is
        what makes the fit's effect visible -- the new element count and any
        self-intersection it introduced -- so the user can Repair before sending.
        """
        curves, after = payload
        if not curves:
            self._set_busy(False)
            self._finish_progress("Nothing to optimize")
            return

        # Replace the fragments with one native spline per shape, so SolidWorks
        # gets one sketch element per shape instead of one per bezier segment.
        self.editor._push_undo()
        # Clear existing vectors and splines on the active layer
        active = self.editor.active_layer
        self.editor.vectors = [v for v in self.editor.vectors if v.layer != active]
        self.editor.splines = [s for s in self.editor.splines if s.layer != active]
        for spline in curves:
            spline.layer = active
        self.editor.splines.extend(curves)
        self.editor.selected_spline_ids = {s.id for s in curves}
        self.editor.selected_ids.clear()

        self._set_busy(False)
        self._invalidate_editor_result(update_open_profiles=True)  # requests the SW recount
        self._finish_progress(
            f"Optimized {len(curves)} entities to {after} curves"
        )

    # ------------------------------------------------------------------
    # SolidWorks bridge (all COM calls run on this GUI thread -- SW is STA)

    def _sw_bridge(self):
        """Import the COM bridge lazily so the editor runs without SolidWorks."""
        from . import solidworks_bridge
        return solidworks_bridge

    def _sw_error(self, exc: Exception) -> None:
        message = str(exc) or repr(exc)
        self._log(f"SolidWorks: {message}", "ERROR")
        QMessageBox.warning(self, "SolidWorks", message)

    def _sw_set_busy(self, busy: bool) -> None:
        self._set_busy(busy)
        self.sw_get_button.setEnabled(not busy)
        self.sw_send_button.setEnabled(not busy and self._sw_target is not None)
        self.sw_preview_button.setEnabled(not busy and self._sw_target is not None)

    def _sw_get_board(self) -> None:
        try:
            target = self._sw_bridge().get_selection()
        except Exception as exc:
            self._sw_error(exc)
            return
        self._sw_target = target
        if target.board_w_mm:
            factor = 25.4 if _effective_units(self.units.currentText()) == "in" else 1.0
            self.board_width.setValue(target.board_w_mm / factor)
            self.board_height.setValue(target.board_h_mm / factor)
        parts = [target.label]
        if target.board_w_mm:
            parts.append(f"{target.board_w_mm:.1f} x {target.board_h_mm:.1f} mm")
        if target.thickness_mm:
            parts.append(f"{target.thickness_mm:.2f} mm thick")
        text = ", ".join(parts)
        self.sw_target_label.setText(text)
        self.sw_send_button.setEnabled(True)
        self.sw_preview_button.setEnabled(True)
        self._refresh_sim_layers()  # the new thickness re-flags too-deep layers
        self._finish_progress(f"Linked to SolidWorks: {text}")

    def handle_launch_request(self, message: str) -> None:
        # A second launch (e.g. the SolidWorks add-in's "Send to CurveMill" button) was
        # handed to this already-running instance instead of opening a new window.
        self.setWindowState((self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        self.show()
        self.raise_()
        self.activateWindow()
        if message.strip() == "get-selection":
            self._sw_get_board()

    def _sw_unit_scale(self) -> float:
        return 0.0254 if _effective_units(self.units.currentText()) == "in" else 0.001

    def _sw_send_layers(self) -> list[Layer]:
        """Cutting layers that carry geometry, in feature-order (editor order)."""
        counts = self.editor.geometry_count_by_layer()
        return [
            layer for layer in self.editor.layers
            if layer.cut and counts.get(layer.name) and layer.name in self.editor.visible_layer_names()
        ]

    def _sw_send(self) -> None:
        if self._sw_target is None or not self.editor.has_visible_geometry():
            self._set_progress(0, "Nothing to send")
            return
        layers = self._sw_send_layers()
        if len(layers) > 1:
            self._sw_send_per_layer(layers)
        else:
            self._sw_send_single()

    def _sw_send_per_layer(self, layers: list[Layer]) -> None:
        dialog = PerLayerSendDialog(
            self, [(l.name, l.depth) for l in layers], self._sw_target.thickness_mm
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        jobs = dialog.jobs()
        if not jobs:
            self._set_progress(0, "Every layer set to skip")
            return
        self._sw_set_busy(True)
        try:
            swb = self._sw_bridge()
            vs, ss = self.editor.visible_vectors_and_splines()
            scale = self._sw_unit_scale()
            bw, bh = self.board_width.value(), self.board_height.value()
            sent = 0
            span = 90 / len(jobs)
            for index, (name, feature, condition, depth_m) in enumerate(jobs):
                curves = swb.curves_from_entities(
                    [v for v in vs if v.layer == name],
                    [s for s in ss if s.layer == name],
                    bw, bh, scale,
                    corner_degrees=self.corner_degrees_setting.value(),
                )
                if not curves:
                    continue
                base = 5 + int(span * index)
                self._set_progress(base, f"Sending layer '{name}' ({index + 1}/{len(jobs)})...")
                QApplication.processEvents()

                # Pump the event loop mid-draw (like _sw_send_single) so the bar
                # advances per layer instead of freezing at 5%, and the window stays
                # clickable while SolidWorks draws.
                def on_progress(done: int, total: int, base=base, name=name) -> None:
                    self._set_progress(base + int(span * done / max(total, 1)),
                                       f"Drawing '{name}' in SolidWorks: {done}/{total}")
                    QApplication.processEvents()

                summary = swb.send(
                    curves, self._sw_target,
                    feature=feature, end_condition=condition, depth_m=depth_m,
                    progress=on_progress,
                )
                self._log(f"Layer '{name}': {summary}")
                sent += 1
            self._request_entity_recount()
            self._finish_progress(f"SolidWorks: sent {sent} layer(s) — see the log for each feature")
        except Exception as exc:
            self._sw_error(exc)
            self._set_progress(0, "Send to SolidWorks failed")
        finally:
            self._sw_set_busy(False)

    def _sw_send_single(self) -> None:
        dialog = SendToSolidWorksDialog(
            self,
            self._sw_target.thickness_mm,
            default_feature=str(self.settings.value("sw/send_mode", "Extruded Cut")),
            default_depth_mm=float(self.settings.value("sw/cut_depth", 10.0)),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        feature, condition, depth_m, flip = dialog.choices()
        self._sw_set_busy(True)
        try:
            swb = self._sw_bridge()
            vs, ss = self.editor.visible_vectors_and_splines()
            curves = swb.curves_from_entities(
                vs, ss, self.board_width.value(), self.board_height.value(), self._sw_unit_scale(),
                corner_degrees=self.corner_degrees_setting.value(),
            )
            self._set_progress(5, f"Sending {len(curves)} curves to SolidWorks...")
            QApplication.processEvents()

            def on_progress(done: int, total: int) -> None:
                self._set_progress(5 + int(85 * done / max(total, 1)), f"Drawing in SolidWorks: {done}/{total}")
                QApplication.processEvents()

            summary = swb.send(
                curves, self._sw_target,
                feature=feature, end_condition=condition, depth_m=depth_m, flip=flip,
                progress=on_progress,
            )
            self._request_entity_recount()
            self._finish_progress(f"SolidWorks: {summary}")
        except Exception as exc:
            self._sw_error(exc)
            self._set_progress(0, "Send to SolidWorks failed")
        finally:
            self._sw_set_busy(False)

    def _sw_preview(self) -> None:
        if self._sw_target is None or not self.editor.has_visible_geometry():
            self._set_progress(0, "Nothing to preview")
            return
        self._sw_set_busy(True)
        try:
            swb = self._sw_bridge()
            vs, ss = self.editor.visible_vectors_and_splines()
            bw, bh = self.board_width.value(), self.board_height.value()
            # DPI only sets the render's pixel count (~2400 px long side);
            # SolidWorks rescales the picture to the board size regardless.
            dpi = max(10, int(2400 * 25.4 / max(bw, bh)))
            self._set_progress(10, "Rendering preview image...")
            QApplication.processEvents()
            png = render_to_png(
                vs, ss, bw, bh, dpi=dpi,
                line_width_mm=max(bw, bh) / 800.0, transparent=True,
            )
            path = Path(tempfile.gettempdir()) / "curvemill_preview.png"
            path.write_bytes(png)
            self._set_progress(30, "Placing preview in SolidWorks (takes a few seconds)...")
            QApplication.processEvents()
            scale = self._sw_unit_scale()
            summary = swb.insert_preview(str(path), self._sw_target, bw * scale, bh * scale)
            self._finish_progress(f"SolidWorks: {summary}")
        except Exception as exc:
            self._sw_error(exc)
            self._set_progress(0, "Preview failed")
        finally:
            self._sw_set_busy(False)

    def _select_all(self) -> None:
        self.editor.select_all()
        self.view.refresh_selection()
        self._sync_action_states(check_dirty=False)
        self._finish_progress(f"Selected active layer: {self.editor.active_layer}")

    def _select_all_visible(self) -> None:
        self.editor.select_all_visible()
        self.view.refresh_selection()
        self._sync_action_states(check_dirty=False)
        self._finish_progress("All visible-layer vectors selected")

    def _copy(self) -> bool:
        if self._forward_text_clipboard_action("copy"):
            return False
        copied = self.editor.copy_selected()
        if not copied:
            self._set_progress(0, "Nothing selected to copy")
            return False
        self.vector_clipboard = copied
        self._finish_progress(f"Copied {len(copied)} vector(s)")
        self._sync_action_states(check_dirty=False)  # copy fills the clipboard, not the doc
        return True

    def _cut(self) -> None:
        if self._forward_text_clipboard_action("cut"):
            return
        copied = self.editor.copy_selected()
        if not copied:
            self._set_progress(0, "Nothing selected to cut")
            return
        self.vector_clipboard = copied
        if self.editor.delete_selected():
            # Dims are left in the store keyed by the (now absent) ids, so Undo
            # restores them with the geometry; they stay dormant until then.
            self._invalidate_editor_result(update_open_profiles=True)
            self._finish_progress(f"Cut {len(copied)} vector(s)")

    def _paste(self) -> None:
        if self._forward_text_clipboard_action("paste"):
            return
        if not self.vector_clipboard:
            self._set_progress(0, "Clipboard is empty")
            return
        center = self.view.paste_scene_position()
        pasted = self.editor.paste_vectors(self.vector_clipboard, center)
        if pasted:
            self._invalidate_editor_result(update_open_profiles=True)
            self._finish_progress(f"Pasted {len(pasted)} vector(s) into {self.editor.active_layer}")

    def _insert_text(self) -> None:
        dialog = TextToCurvesDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text, font, height_mm = dialog.values()
        vectors = _text_to_vectors(text, font, height_mm, self.editor.active_layer)
        if not vectors:
            self._set_progress(0, "No outlines produced (empty text or a symbol-only font)")
            return
        center = (self.board_width.value() / 2.0, self.board_height.value() / 2.0)
        placed = self.editor.paste_vectors(vectors, center)
        self._invalidate_editor_result(update_open_profiles=True)
        self._finish_progress(f"Inserted '{text}' as {len(placed)} curve(s) into {self.editor.active_layer}")

    def _forward_text_clipboard_action(self, action: str) -> bool:
        focus = QApplication.focusWidget()
        if isinstance(focus, QAbstractSpinBox):
            focus = focus.lineEdit()
        if isinstance(focus, (QLineEdit, QPlainTextEdit, QTextEdit)):
            getattr(focus, action)()
            return True
        return False

    def _delete(self) -> None:
        # Del with a dimension picked on the canvas removes that dimension, not
        # the geometry — matches the right-click Delete on the same dim.
        if self.view._selected_dim_id is not None:
            self._delete_dim(self.view._selected_dim_id)
            self._finish_progress("Dimension deleted")
            return
        if self.editor.delete_selected():
            # Keep the dims in the store (dormant) so Undo brings them back with
            # the geometry; a genuinely deleted pattern just leaves them unused.
            self._invalidate_editor_result(update_open_profiles=True)
            self._finish_progress("Selected vectors deleted")

    def _add_layer(self) -> None:
        name = self.editor.add_layer()
        self._invalidate_editor_result()
        self._finish_progress(f"Added {name}")

    def _clone_layer(self) -> None:
        name = self.editor.clone_layer()
        if name is not None:
            self._invalidate_editor_result(update_open_profiles=True)
            self._finish_progress(f"Cloned layer as {name}")

    def _cut_to_new_layer(self) -> None:
        name = self.editor.selection_to_new_layer(copy=False)
        if name is not None:
            self._invalidate_editor_result(update_open_profiles=True)
            self._finish_progress(f"Cut selection to {name}")

    def _copy_to_new_layer(self) -> None:
        name = self.editor.selection_to_new_layer(copy=True)
        if name is not None:
            self._invalidate_editor_result(update_open_profiles=True)
            self._finish_progress(f"Copied selection to {name}")

    def _rename_layer(self) -> None:
        current = self.layer_list.currentItem()
        if current is None:
            return
        current_name = current.data(0, Qt.ItemDataRole.UserRole)
        name, accepted = QInputDialog.getText(self, "Rename layer", "Layer name", text=current_name)
        if not accepted:
            return
        renamed = self.editor.rename_layer(current_name, name)
        if renamed is None:
            QMessageBox.warning(self, "Invalid layer name", "Layer names must be non-empty and unique.")
            return
        self._invalidate_editor_result()
        self._finish_progress(f"Renamed layer to {renamed}")

    def _delete_layer(self) -> None:
        name = self.editor.active_layer
        if self.editor.delete_layer(name):
            self._invalidate_editor_result(update_open_profiles=True)
            self._finish_progress(f"Deleted layer {name}")

    def _on_active_layer_changed(self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        if self._refreshing_layers or current is None:
            return
        name = current.data(0, Qt.ItemDataRole.UserRole)
        if self.editor.set_active_layer(name):
            self._refresh()
            self._finish_progress(f"Active layer: {name}")

    def _on_layer_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._refreshing_layers or column != 0:
            return
        old_name = item.data(0, Qt.ItemDataRole.UserRole)
        name = item.text(0).strip()
        if name != old_name:
            renamed = self.editor.rename_layer(old_name, name)
            if renamed is None:
                self._refresh_layers()
                QMessageBox.warning(self, "Invalid layer name", "Layer names must be non-empty and unique.")
                return
            old_name = renamed
        visible = item.checkState(0) == Qt.CheckState.Checked
        visibility_changed = self.editor.set_layer_visibility(old_name, visible)
        self._invalidate_editor_result(update_open_profiles=visibility_changed)
        self._finish_progress(f"Layer updated: {old_name}")

    def _group(self) -> None:
        changed = self.editor.group_selected()
        if changed is not None:
            self._invalidate_editor_result()
            self._finish_progress("Vectors grouped")
        else:
            self._refresh()

    def _ungroup(self) -> None:
        changed = self.editor.ungroup_selected()
        if changed:
            self._invalidate_editor_result()
            self._finish_progress("Vectors ungrouped")
        else:
            self._refresh()

    def _smooth(self) -> None:
        self._start_progress("Smoothing vectors")
        if self.editor.smooth_vectors():
            self._invalidate_approval()
            self._finish_progress("Smoothing complete")
        else:
            self._set_progress(0, "Nothing to smooth")

    def _smooth_corners(self) -> None:
        dialog = RoundCornersDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        radius, mode = dialog.values()
        self._start_progress("Rounding corners")
        if self.editor.round_corners(radius, mode):
            self._invalidate_approval()
            self._finish_progress("Corners rounded")
        else:
            self._set_progress(0, "No sharp corners to round")

    def _rotate_selection(self, degrees: float) -> None:
        if self.editor.rotate_selected(radians(degrees)):
            self._invalidate_approval()
            self._finish_progress(f"Rotated {degrees:g}°")
        else:
            self._refresh()

    def _rotate_selection_custom(self) -> None:
        angle, accepted = QInputDialog.getDouble(
            self, "Rotate selection", "Angle (degrees, counter-clockwise):", 0.0, -360.0, 360.0, 2
        )
        if accepted and angle:
            self._rotate_selection(angle)

    def _flip_selection(self, horizontal: bool) -> None:
        if self.editor.flip_selected(horizontal):
            self._invalidate_approval()
            self._finish_progress("Flipped " + ("horizontally" if horizontal else "vertically"))
        else:
            self._refresh()

    def _undo(self) -> None:
        if self.editor.undo():
            self.current_result = None
            self._clear_warning_state()
            self._refresh(update_open_profiles=True)
            self._finish_progress("Undo complete")

    def _redo(self) -> None:
        if self.editor.redo():
            self.current_result = None
            self._clear_warning_state()
            self._refresh(update_open_profiles=True)
            self._finish_progress("Redo complete")

    def _toggle_vectors(self, show: bool) -> None:
        self.view.set_show_vectors(show)
        self._finish_progress("Vectors shown" if show else "Vectors hidden")

    def _fit_content(self) -> None:
        self.view.fit_content()
        self._finish_progress("Canvas fitted to content")

    def _load_tools(self) -> list[Tool]:
        raw = str(self.settings.value("tools/library", "") or "")
        if raw:
            try:
                return [Tool.from_dict(entry) for entry in json.loads(raw)]
            except (ValueError, KeyError, TypeError):
                pass
        # The tool library ships empty — every entry is the user's own.
        return []

    def _save_tools(self) -> None:
        self.settings.setValue("tools/library", json.dumps([tool.to_dict() for tool in self.tools]))

    def _current_tool(self) -> Tool:
        return Tool(
            name=self.tool_combo.currentText(),
            kind=ToolKind(self.tool_combo.currentData() or "flat"),
            diameter=self.endmill.value(),
            taper_angle_deg=self.tool_taper.value(),
            tip_diameter=self.tool_tip.value(),
        )

    def _allowed_tool_kinds(self) -> list[ToolKind]:
        # The tool list follows the selected layer's cut mode: each layer owns its
        # own tool, so only that layer's mode gates the choices.
        mode = self.cut_mode.currentData() or "profile"
        if mode == "laser":
            return [ToolKind.LASER]
        kinds = [ToolKind.FLAT, ToolKind.BALL, ToolKind.V_BIT, ToolKind.TAPERED]
        if mode == "vcarve":  # a flat mill can't vary its width with depth
            return [k for k in kinds if k is not ToolKind.FLAT]
        return kinds

    def _sync_tool_choices(self) -> None:
        """Show only the tools that fit the current cut mode.

        V-Carve drops flat mills; Laser shows the laser alone. The current pick
        survives if it still fits, else the first allowed tool is chosen.
        """
        allowed = self._allowed_tool_kinds()
        current = self.tool_combo.currentData()
        self.tool_combo.blockSignals(True)
        self.tool_combo.clear()
        for kind in allowed:
            self.tool_combo.addItem(_KIND_LABEL[kind], kind.value)
        index = self.tool_combo.findData(current)
        self.tool_combo.setCurrentIndex(index if index >= 0 else 0)
        self.tool_combo.blockSignals(False)

    def _on_cut_mode_changed(self) -> None:
        # Re-filters the tool list, updates the fields, and writes the recipe onto
        # the selected layer (Laser snaps the tool to the laser, V-Carve off flat).
        self._on_tool_params_changed()

    def _on_tool_params_changed(self) -> None:
        self._sync_sim_fields()
        self._write_form_to_selected_layer()

    def _sync_sim_fields(self) -> None:
        """Field visibility, labels and settings for the current tool — no writes."""
        self._sync_tool_choices()  # the cut mode decides the tool list
        tool = self._current_tool()
        kind = tool.kind
        is_laser = kind is ToolKind.LASER
        form = self._sim_form
        # Each kind shows only the fields that shape its cut.
        form.setRowVisible(self.tool_taper, kind in (ToolKind.V_BIT, ToolKind.TAPERED))
        form.setRowVisible(self.tool_tip, kind is ToolKind.TAPERED)
        # A laser cuts one kerf at any depth, so its depth input is meaningless and
        # hidden here — but the layer panel still shows the number per the request.
        form.setRowVisible(self.cut_depth, not is_laser)
        depth_varies = kind in (ToolKind.BALL, ToolKind.V_BIT, ToolKind.TAPERED)
        form.setRowVisible(self.effective_label, depth_varies)
        form.labelForField(self.endmill).setText("Kerf width" if is_laser else "Diameter")
        if is_laser:
            # Inside/outside differ from center by half a sub-mm kerf — a
            # meaningless choice, so lock the trace to center (master plan §5).
            self.trace.setCurrentText(TraceMode.CENTER.value)
        self.trace.setEnabled(not is_laser)
        # V-carve rides the centerline between the walls — no inside/outside/center
        # offset to pick, and vcarve_layer ignores trace_mode. Hide the dead control.
        form.setRowVisible(self.trace, (self.cut_mode.currentData() or "profile") != "vcarve")
        if depth_varies:
            units = _effective_units(self.units.currentText())
            self.effective_label.setText(
                f"{tool.effective_diameter(self.cut_depth.value()):.2f} {units} at {self.cut_depth.value():g} {units} depth"
            )
        self.settings.setValue("sim/kind", kind.value)
        self.settings.setValue("sim/diameter", self.endmill.value())
        self.settings.setValue("sim/taper", self.tool_taper.value())
        self.settings.setValue("sim/tip", self.tool_tip.value())
        self.settings.setValue("sim/cut_depth", self.cut_depth.value())
        self.settings.setValue("sim/cut_mode", self.cut_mode.currentData() or "profile")

    def _selected_sim_layer(self) -> "Layer | None":
        item = self.sim_layers.currentItem()
        if item is None:
            return None
        name = item.data(0, Qt.ItemDataRole.UserRole)
        return next((layer for layer in self.editor.layers if layer.name == name), None)

    def _write_form_to_selected_layer(self) -> None:
        # The left toolbar edits whichever layer is selected on the right.
        if self._sim_form_loading:
            return
        layer = self._selected_sim_layer()
        if layer is None:
            return
        layer.mode = self.cut_mode.currentData() or "profile"
        layer.depth = self.cut_depth.value()
        layer.tool = self._current_tool()
        if self.apply_all_check.isChecked():
            self._broadcast_recipe(layer)  # keep every layer in lockstep while checked
        self._invalidate_approval()  # cut geometry changed; rebuilds the panel too

    def _load_selected_layer_into_form(self) -> None:
        layer = self._selected_sim_layer()
        self._sim_form_loading = True  # setting fields must not write back
        if layer is not None:
            self.cut_mode.setCurrentIndex(max(0, self.cut_mode.findData(layer.mode)))
            # Setting the mode above re-filtered the tool list; now pick its tool.
            tool = layer.tool
            index = self.tool_combo.findData(tool.kind.value)
            if index >= 0:
                self.tool_combo.setCurrentIndex(index)
            self.endmill.setValue(tool.diameter)
            self.tool_taper.setValue(max(tool.taper_angle_deg, self.tool_taper.minimum()))
            self.tool_tip.setValue(tool.tip_diameter)
            self.cut_depth.setValue(layer.depth)
        self._sim_form_loading = False
        self._sync_sim_fields()

    def _on_sim_layer_selected(self, *_args) -> None:
        if self._sim_layers_loading:
            return
        self._load_selected_layer_into_form()

    def _on_sim_layer_check(self, item: "QTreeWidgetItem", _column: int) -> None:
        if self._sim_layers_loading:
            return
        name = item.data(0, Qt.ItemDataRole.UserRole)
        layer = next((l for l in self.editor.layers if l.name == name), None)
        if layer is None:
            return
        new_cut = item.checkState(0) is Qt.CheckState.Checked
        if new_cut == layer.cut:
            return
        layer.cut = new_cut
        self._invalidate_approval()

    def _broadcast_recipe(self, source: "Layer") -> None:
        for other in self.editor.layers:
            if other is source:
                continue
            other.mode = source.mode
            other.depth = source.depth
            other.tool = replace(source.tool)  # an independent copy per layer

    def _on_apply_all_toggled(self, checked: bool) -> None:
        # Checking it copies the selected layer's recipe onto every layer now;
        # _write_form_to_selected_layer keeps them synced while it stays checked.
        if not checked:
            return
        layer = self._selected_sim_layer()
        if layer is None:
            return
        self._broadcast_recipe(layer)
        self._invalidate_approval()

    def _refresh_sim_layers(self) -> None:
        """Rebuild the read-only layer panel; reload the form only on a new pick."""
        prev = self._selected_sim_layer()
        prev_name = prev.name if prev else None
        counts = self.editor.geometry_count_by_layer()
        layers = [layer for layer in self.editor.layers if counts.get(layer.name)]
        thickness = self._sw_target.thickness_mm if self._sw_target else None
        self._sim_layers_loading = True
        self.sim_layers.clear()
        target: QTreeWidgetItem | None = None
        for layer in layers:
            tool_label = f"{_KIND_LABEL[layer.tool.kind]} {layer.tool.diameter:g}"
            item = QTreeWidgetItem(
                [layer.name, _MODE_LABEL.get(layer.mode, layer.mode), tool_label, f"{layer.depth:g}"]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, layer.name)
            item.setFlags((item.flags() | Qt.ItemFlag.ItemIsUserCheckable) & ~Qt.ItemFlag.ItemIsEditable)
            item.setCheckState(0, Qt.CheckState.Checked if layer.cut else Qt.CheckState.Unchecked)
            # A depth past the measured board is flagged in the panel, not at Send.
            # For V-carve the depth is a max, so this is where the bit bottoms out and
            # breaks through — warn to put a sacrificial board under the stock.
            if thickness and layer.cut and layer.depth > thickness:
                item.setForeground(3, QBrush(QColor("#c0392b")))
                if layer.mode == "vcarve":
                    item.setToolTip(3, f"At this max depth the bit cuts through your {thickness:g} mm board — put a sacrificial board underneath so you don't hit the CNC bed")
                else:
                    item.setToolTip(3, f"Deeper than the {thickness:g} mm board — this cuts through")
            self.sim_layers.addTopLevelItem(item)
            if layer.name == prev_name:
                target = item
        if target is None and self.sim_layers.topLevelItemCount():
            target = self.sim_layers.topLevelItem(0)
        if target is not None:
            self.sim_layers.setCurrentItem(target)
        self._sim_layers_loading = False
        self.apply_all_check.setEnabled(len(layers) > 1)
        # The label lives in the form's label column now, so grey it in step.
        apply_all_label = self._sim_form.labelForField(self.apply_all_check)
        if apply_all_label is not None:
            apply_all_label.setEnabled(len(layers) > 1)
        # Reload the form only when the selection changed, so editing the current
        # layer's fields isn't fought by a reload mid-edit.
        new = self._selected_sim_layer()
        if (new.name if new else None) != prev_name:
            self._load_selected_layer_into_form()
        else:
            self._sync_sim_fields()

    def _layer_jobs(self) -> list[LayerJob]:
        """One job per cutting layer, each with its own tool/mode/depth."""
        base = self._options()
        by_layer: dict[str, list[VectorEntity]] = {}
        for vector in self.editor.all_visible_vectors():
            by_layer.setdefault(vector.layer, []).append(vector)
        registered = {layer.name: layer for layer in self.editor.layers}
        jobs: list[LayerJob] = []
        for name, vectors in by_layer.items():
            layer = registered.get(name)
            if layer is not None and not layer.cut:
                continue
            if layer is None:
                # A layer the editor never registered falls back to the form's recipe.
                depth, mode, tool = self.cut_depth.value(), self.cut_mode.currentData() or "profile", self._current_tool()
            else:
                depth, mode, tool = layer.depth, layer.mode, layer.tool
            # Laser runs as a centered kerf sweep; flat mills can't V-carve.
            if mode == "laser" or tool.kind is ToolKind.LASER:
                job_mode, trace = "profile", TraceMode.CENTER
            elif mode == "vcarve" and tool.can_vcarve:
                job_mode, trace = "vcarve", base.trace_mode
            else:
                job_mode, trace = "profile", base.trace_mode
            jobs.append(
                LayerJob(
                    name=name,
                    depth=depth,
                    mode=job_mode,
                    vectors=vectors,
                    options=replace(
                        base,
                        endmill_diameter=tool.effective_diameter(depth),
                        trace_mode=trace,
                        tool_kind=tool.kind.value,
                    ),
                    tool=tool,
                )
            )
        return jobs

    def _populate_tool_table(self) -> None:
        self._tool_table_loading = True
        self.tool_table.setRowCount(len(self.tools))
        for row, tool in enumerate(self.tools):
            self.tool_table.setItem(row, 0, QTableWidgetItem(tool.name))
            kind = QComboBox()
            kind.addItems([k.value for k in ToolKind])
            kind.setCurrentText(tool.kind.value)
            kind.currentTextChanged.connect(self._on_tool_table_changed)
            self.tool_table.setCellWidget(row, 1, kind)
            for column, value in ((2, tool.diameter), (3, tool.taper_angle_deg), (4, tool.tip_diameter)):
                self.tool_table.setItem(row, column, QTableWidgetItem(f"{value:g}"))
            self.tool_table.setItem(row, 5, QTableWidgetItem(tool.notes))
        self._tool_table_loading = False

    def _on_tool_table_changed(self, *_args) -> None:
        if self._tool_table_loading:
            return
        tools: list[Tool] = []
        for row in range(self.tool_table.rowCount()):
            def text(column: int) -> str:
                item = self.tool_table.item(row, column)
                return item.text().strip() if item else ""

            def number(column: int, default: float = 0.0) -> float:
                try:
                    return float(text(column) or default)
                except ValueError:
                    return default

            kind_widget = self.tool_table.cellWidget(row, 1)
            tools.append(
                Tool(
                    name=text(0) or f"Tool {row + 1}",
                    kind=ToolKind(kind_widget.currentText()) if kind_widget else ToolKind.FLAT,
                    diameter=number(2, 6.0),
                    taper_angle_deg=number(3),
                    tip_diameter=number(4),
                    notes=text(5),
                )
            )
        self.tools = tools
        self._save_tools()

    def _add_tool(self) -> None:
        # Saves whatever the Simulation tab is set to right now, so the library
        # fills from real use instead of a blank row the user has to type out.
        tool = self._current_tool()
        tool.name = f"{self.tool_combo.currentText()} {tool.diameter:g}"
        self.tools.append(tool)
        self._save_tools()
        self._populate_tool_table()

    def _add_blank_tool(self) -> None:
        # A fresh default row to fill in by hand, for cutters you haven't set up
        # in the Simulation tab. Select it so the name cell is ready to edit.
        self.tools.append(Tool(name=self.tr("New tool")))
        self._save_tools()
        self._populate_tool_table()
        self.tool_table.setCurrentCell(len(self.tools) - 1, 0)

    def _remove_tool(self) -> None:
        row = self.tool_table.currentRow()
        if row < 0 or row >= len(self.tools):
            return
        del self.tools[row]
        self._save_tools()
        self._populate_tool_table()

    def _use_selected_tool(self) -> None:
        row = self.tool_table.currentRow()
        if row < 0 or row >= len(self.tools):
            return
        self._apply_tool(self.tools[row])
        self.tabs.setCurrentWidget(self._sim_tab)

    def _apply_tool(self, tool: Tool) -> None:
        # A laser tool implies Laser cut mode; picking a mill out of Laser mode
        # falls back to Profile so the tool list actually contains that kind.
        if tool.kind is ToolKind.LASER:
            mode = "laser"
        else:
            mode = self.cut_mode.currentData() or "profile"
            if mode == "laser":
                mode = "profile"
        self.cut_mode.setCurrentIndex(max(0, self.cut_mode.findData(mode)))
        index = self.tool_combo.findData(tool.kind.value)
        if index >= 0:
            self.tool_combo.setCurrentIndex(index)
        self.endmill.setValue(tool.diameter)
        self.tool_taper.setValue(max(tool.taper_angle_deg, self.tool_taper.minimum()))
        self.tool_tip.setValue(tool.tip_diameter)
        self._on_tool_params_changed()

    def _options(self) -> ProcessOptions:
        units = _effective_units(self.units.currentText())
        tool = self._current_tool()
        return ProcessOptions(
            board_width=self.board_width.value(),
            board_height=self.board_height.value(),
            units=units,
            # The sweep is a fixed-width 2D buffer, so feed it the width this
            # tool actually cuts at the chosen depth (flat/laser ignore depth).
            endmill_diameter=tool.effective_diameter(self.cut_depth.value()),
            trace_mode=TraceMode(self.trace.currentText()),
            repair_tolerance=self.repair.value(),
            hide_islands=self.hide_islands.isChecked(),
            curve_tolerance=self.curve_tolerance.value(),
            tool_kind=tool.kind.value,
        )

    def _invalidate_approval(self) -> None:
        self.current_result = None
        self._clear_warning_state()
        self._refresh()

    def _invalidate_editor_result(self, update_open_profiles: bool = False) -> None:
        self.current_result = None
        self._clear_repair_session()
        self._clear_warning_state()
        self._refresh(update_open_profiles=update_open_profiles)  # requests the SW recount

    def _on_editor_changed(self, topology_changed: bool = False, visuals_current: bool = False) -> None:
        self.current_result = None
        self._request_entity_recount()  # geometry changed -> refit the SW count off-thread
        self._clear_repair_session()
        self._clear_warning_state()
        if not visuals_current:
            self._refresh(update_open_profiles=topology_changed)
            self._finish_progress("Edit complete")
            return
        if topology_changed:
            self._update_open_profile_count()
        has_visible_vectors = self.editor.has_visible_geometry()
        self.repair_button.setEnabled(self._repair_enabled())
        self.export_button.setEnabled(has_visible_vectors)
        self.optimize_button.setEnabled(self._optimize_enabled())
        self.correct_button.setEnabled(self.current_result is not None)
        self.view.result = None
        self.view._update_scene_rect()
        self.view.viewport().update()
        self._refresh_layers()
        self._sync_action_states()
        self._refresh_layout_panel()
        self._finish_progress("Edit complete")

    def _refresh(self, update_open_profiles: bool = False) -> None:
        if update_open_profiles:
            self._update_open_profile_count()
        has_visible_vectors = self.editor.has_visible_geometry()
        self.process_button.setEnabled(not self._busy and has_visible_vectors)
        self.repair_button.setEnabled(self._repair_enabled())
        self.export_button.setEnabled(not self._busy and has_visible_vectors)
        self.optimize_button.setEnabled(not self._busy and self._optimize_enabled())
        self.correct_button.setEnabled(not self._busy and self.current_result is not None)
        self.view.board_width = self.board_width.value()
        self.view.board_height = self.board_height.value()
        self.view.result = self.current_result
        self.view.redraw()
        self._refresh_layers()
        self._refresh_sim_layers()
        self._sync_action_states()
        self._refresh_layout_panel()
        # Any geometry/visibility change routes through here (and so does load); refit
        # the SolidWorks count off-thread so the Entities column is always SW-true.
        self._request_entity_recount()

    def _refresh_layers(self) -> None:
        self._refreshing_layers = True
        self.layer_list.blockSignals(True)
        self.layer_list.clear()
        # Count native splines as well as vectors: an all-spline file (common from
        # editors like Inkscape) otherwise shows every layer as empty.
        vector_counts = self.editor.geometry_count_by_layer()
        active_item: QTreeWidgetItem | None = None
        for layer in self.editor.layers:
            # Depth is read-only here; it is edited in the Simulation tab.
            badge = f"{layer.depth:g}" if layer.cut else "skip"
            # Prefer the exact SolidWorks entity count when a fit has produced one;
            # otherwise the raw shape count is the honest best estimate.
            entities = self._layer_entity_counts.get(layer.name)
            count = str(entities) if entities is not None else str(vector_counts.get(layer.name, 0))
            item = QTreeWidgetItem([layer.name, count, badge])
            item.setData(0, Qt.ItemDataRole.UserRole, layer.name)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEditable
            )
            item.setCheckState(0, Qt.CheckState.Checked if layer.visible else Qt.CheckState.Unchecked)
            self.layer_list.addTopLevelItem(item)
            if layer.name == self.editor.active_layer:
                active_item = item
        if active_item is not None:
            self.layer_list.setCurrentItem(active_item)
        self.layer_list.blockSignals(False)
        self._refreshing_layers = False

    def _request_entity_recount(self) -> None:
        """Ask for a fresh SolidWorks entity count. Coalesces bursts: if a fit is
        already running, just flag that another is due when it finishes."""
        self._entity_recount_pending = True
        self._maybe_start_entity_recount()

    def _maybe_start_entity_recount(self) -> None:
        if self._entity_recount_busy or not self._entity_recount_pending:
            return
        self._entity_recount_pending = False
        # Snapshot every input on the GUI thread; the worker only reads them.
        try:
            swb = self._sw_bridge()
            # Count every layer, not just visible ones: a layer's entity count is a
            # property of its geometry, not its visibility. Snapshotting only the
            # visible geometry dropped a hidden layer out of the result, so its row
            # fell back to the raw shape count and the displayed number changed the
            # moment you unchecked it.
            vs, ss = self.editor.vectors, self.editor.splines
            names = [layer.name for layer in self.editor.layers]
            by_layer = {
                name: ([v for v in vs if v.layer == name], [s for s in ss if s.layer == name])
                for name in names
            }
            bw, bh = self.board_width.value(), self.board_height.value()
            scale = self._sw_unit_scale()
            corner = self.corner_degrees_setting.value()
        except Exception as error:
            self._log(f"Entity recount skipped: {error}", "WARN")
            return

        def job(_progress):
            counts: dict[str, int] = {}
            for name, (lv, ls) in by_layer.items():
                if not lv and not ls:
                    continue
                counts[name] = len(swb.curves_from_entities(lv, ls, bw, bh, scale, corner_degrees=corner))
            return counts

        self._entity_recount_busy = True
        worker = Worker(job)
        worker.signals.done.connect(self._on_entity_recount_done)
        worker.signals.error.connect(self._on_entity_recount_error)
        self.thread_pool.start(worker)

    def _on_entity_recount_done(self, counts: dict) -> None:
        self._entity_recount_busy = False
        self._layer_entity_counts = counts
        self._refresh_layers()  # render only -- does not re-trigger a recount
        self._maybe_start_entity_recount()  # a geometry change may have queued while we ran

    def _on_entity_recount_error(self, message: str) -> None:
        self._entity_recount_busy = False
        self._log(f"Entity recount skipped: {message}", "WARN")

    def _sync_action_states(self, check_dirty: bool = True) -> None:
        # check_dirty gates the ONE expensive line here: _is_dirty() re-serialises the
        # whole project to JSON (~30ms on 1500+ entities). Selection, zoom and copy
        # never change what's on disk, so those callers pass check_dirty=False and skip
        # it -- that serialise on every click/wheel-tick was the big-file selection lag.
        # Every real document mutation funnels through _refresh/_on_editor_changed, which
        # call this with the default True, and _confirm_discard recomputes fresh, so the
        # Save button and close-guard stay correct.
        selected = bool(self.editor.selected_target_ids())
        visible_vectors = self.editor.visible_vectors()
        visible_splines = self.editor.visible_splines()
        active_vectors = [
            vector for vector in visible_vectors if vector.layer == self.editor.active_layer
        ]
        active_splines = [
            spline for spline in visible_splines if spline.layer == self.editor.active_layer
        ]
        has_active = bool(active_vectors or active_splines)
        has_visible = bool(visible_vectors or visible_splines)
        enabled = not self._busy
        if check_dirty:
            self.save_action.setEnabled(enabled and self._is_dirty())
        self.select_all_action.setEnabled(enabled and has_active)
        self.select_all_visible_action.setEnabled(enabled and has_visible)
        self.cut_action.setEnabled(enabled and selected)
        self.copy_action.setEnabled(enabled and selected)
        self.paste_action.setEnabled(enabled and bool(self.vector_clipboard))
        self.delete_action.setEnabled(enabled and selected)
        self.rotate_menu.menuAction().setEnabled(enabled and selected)
        self.flip_menu.menuAction().setEnabled(enabled and selected)
        self.group_action.setEnabled(enabled and len(self.editor.selected_target_ids()) >= 2)
        self.ungroup_action.setEnabled(enabled and selected)
        self.smooth_action.setEnabled(enabled and bool(active_vectors or selected))
        self.smooth_corners_action.setEnabled(
            enabled and bool(active_vectors or active_splines or selected)
        )
        for button in [
            self.add_layer_button,
            self.clone_layer_button,
            self.rename_layer_button,
            self.delete_layer_button,
        ]:
            button.setEnabled(enabled)
        self.layer_list.setEnabled(enabled)
        self.selection_layout_group.setEnabled(enabled and selected)
        self.fit_board_width_button.setEnabled(enabled and selected)
        self.fit_board_height_button.setEnabled(enabled and selected)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        has_visible_vectors = self.editor.has_visible_geometry()
        self.open_button.setEnabled(not busy)
        self.process_button.setEnabled(not busy and has_visible_vectors)
        self.repair_button.setEnabled(self._repair_enabled())
        self.export_button.setEnabled(not busy and has_visible_vectors)
        self.correct_button.setEnabled(not busy and self.current_result is not None)
        self.view.setEnabled(not busy)
        for action in [
            self.select_all_action,
            self.select_all_visible_action,
            self.cut_action,
            self.copy_action,
            self.paste_action,
            self.delete_action,
            self.group_action,
            self.ungroup_action,
            self.smooth_action,
            self.smooth_corners_action,
            self.undo_action,
            self.redo_action,
            self.show_vectors_action,
            self.fit_content_action,
        ]:
            action.setEnabled(not busy)
        self.layers_dock.setEnabled(not busy)
        self.selection_dock.setEnabled(not busy)
        # Keep the Warnings & Log dock alive during work so the user can switch
        # tabs and read/copy the log; only the warning list is action-bearing.
        self.warning_list.setEnabled(not busy)
        self._sync_action_states()
        self._refresh_layout_panel()

    def _on_worker_error(self, title: str, message: str) -> None:
        self._set_busy(False)
        self._set_progress(0, f"Failed: {message}")
        self._log(f"{title}: {message}", "ERROR")
        QMessageBox.critical(self, title, message)

    def _log(self, message: str, level: str = "INFO") -> None:
        self.log_view.appendPlainText(f"{datetime.now():%H:%M:%S}  {level:<5}  {message}")

    def _log_copy_text(self) -> str:
        cursor = self.log_view.textCursor()
        if not cursor.hasSelection():
            return self.log_view.toPlainText()
        # Read the selection as a fragment rather than through selectedText(), which
        # returns line breaks as U+2029 and would paste as one run-together line.
        return cursor.selection().toPlainText()

    def _copy_log(self) -> None:
        QApplication.clipboard().setText(self._log_copy_text())

    def _start_progress(self, message: str) -> None:
        self.progress_label.setText(message)
        self.progress_bar.setValue(0)
        self._log(message)

    def _set_progress(self, value: int, message: str) -> None:
        self.progress_bar.setValue(max(0, min(100, int(value))))
        self.progress_label.setText(message)

    def _set_worker_progress(self, value: int, message: str) -> None:
        # Progress ticks fire many times per operation; Normal logs only the
        # start and outcome, Verbose logs each distinct step as it happens.
        self._set_progress(min(int(value), 95), message)
        if self.log_level.currentText() == "Verbose" and message != self._last_verbose_message:
            self._last_verbose_message = message
            self._log(message, "DEBUG")

    def _finish_progress(self, message: str) -> None:
        self._set_progress(100, message)
        self._log(message)

    def _on_units_changed(self) -> None:
        suffix = f" {_effective_units(self.units.currentText())}"
        self.board_width.setSuffix(suffix)
        self.board_height.setSuffix(suffix)
        self.endmill.setSuffix(suffix)
        self.cut_depth.setSuffix(suffix)
        self.repair.setSuffix(suffix)
        self.curve_tolerance.setSuffix(suffix)
        self.layout_width.setSuffix(suffix)
        self.layout_height.setSuffix(suffix)
        self._invalidate_approval()

    def _clear_repair_session(self) -> None:
        self._repair_source_vectors = None
        self._repair_source_splines = {}
        self._last_repair_tolerance = None

    def _update_open_profile_count(self) -> None:
        # Count on the same flattened geometry Process consumes, otherwise an
        # all-spline file reports "0 open profiles" and then Process warns about
        # every open path it finds once the splines are flattened.
        issues = count_profile_issues(self.editor.all_visible_vectors())
        self._open_profile_count = issues.open_profiles
        self._duplicate_count = issues.duplicates
        self._self_intersection_count = issues.self_intersections
        self.view.set_profile_counts(issues)

    def _repair_enabled(self) -> bool:
        # Repair closes open profiles, removes duplicates, and heals self-crossing
        # profiles; multi-vertex stays detection-only (which branch to keep is the
        # user's call).
        return not self._busy and (
            self._open_profile_count > 0
            or self._duplicate_count > 0
            or self._self_intersection_count > 0
        )

    def _optimize_enabled(self) -> bool:
        # Optimize only touches the active layer, so enable it only when that layer
        # is visible and actually holds geometry.
        if not self.editor.active_layer_visible():
            return False
        av, asp = self.editor.active_vectors_and_splines()
        return bool(av or asp)

    def _set_warnings(self, messages: list[str], details: list[ProcessWarning]) -> None:
        self.view.clear_warning_balloons()
        self._last_located_warning_key = None
        self._warning_details = {detail.key: detail.clone() for detail in details}
        # Bind each row to its OWN detail by consuming details in order. Warnings
        # routinely share identical message text ("smaller than the endmill", a
        # self-intersection note), so keying by message text collapsed every
        # same-text row onto one balloon key -- clicking one then checked them all
        # ("selects all warnings under it") while showing a single balloon. details
        # are appended lockstep with messages (_add_path_warning), so they're an
        # in-order subsequence; a two-pointer walk gives every row a unique key.
        pending = iter(details)
        next_detail = next(pending, None)
        self.warning_list.clear()
        for message in messages:
            item = QListWidgetItem(message)
            if next_detail is not None and next_detail.message == message:
                item.setData(Qt.ItemDataRole.UserRole, next_detail.key)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                item.setToolTip("Click to show or hide this path balloon")
                next_detail = next(pending, None)
            else:
                item.setForeground(QColor("#6b7280"))
                item.setToolTip("No path geometry is available for this warning")
            self.warning_list.addItem(item)
            self._log(message, "WARN")
        self._sync_warning_items()

    def _on_warning_clicked(self, item: QListWidgetItem) -> None:
        key = item.data(Qt.ItemDataRole.UserRole)
        detail = self._warning_details.get(key)
        if detail is None:
            return
        if self.view.has_warning_balloon(key):
            self.view.remove_warning_balloon(key)
            self._finish_progress(f"Hidden warning balloon for path {detail.vector_id}")
        else:
            self.view.show_warning_balloon(detail)
            self._finish_progress(f"Showing warning balloon for path {detail.vector_id}")
        self._sync_warning_items()

    def _clear_warning_balloons(self) -> None:
        self.view.clear_warning_balloons()
        self._last_located_warning_key = None
        self._sync_warning_items()
        self._finish_progress("Warning balloons cleared")

    def _locate_next_warning_balloon(self) -> None:
        active_keys = [
            self.warning_list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.warning_list.count())
            if self.view.has_warning_balloon(
                self.warning_list.item(index).data(Qt.ItemDataRole.UserRole)
            )
        ]
        if not active_keys:
            return
        start = 0
        if self._last_located_warning_key in active_keys:
            start = (active_keys.index(self._last_located_warning_key) + 1) % len(active_keys)
        ordered_keys = active_keys[start:] + active_keys[:start]
        key = next(
            (candidate for candidate in ordered_keys if not self.view.warning_balloon_is_visible(candidate)),
            ordered_keys[0],
        )
        self.view.reveal_warning_balloon(key)
        self._last_located_warning_key = key
        detail = self._warning_details[key]
        self._finish_progress(f"Located warning balloon for path {detail.vector_id}")

    def _select_all_warnings(self) -> None:
        details = []
        for index in range(self.warning_list.count()):
            key = self.warning_list.item(index).data(Qt.ItemDataRole.UserRole)
            detail = self._warning_details.get(key)
            if detail is not None and not self.view.has_warning_balloon(key):
                details.append(detail)
        active_count = len(self.view._warning_states)
        available_slots = max(self.MAX_BULK_WARNING_BALLOONS - active_count, 0)
        shown = details[:available_slots]
        self.view.show_warning_balloons(shown)
        self._sync_warning_items()
        skipped = len(details) - len(shown)
        if skipped:
            self._finish_progress(
                f"Showing {len(self.view._warning_states)} balloons; {skipped} omitted to keep the canvas responsive"
            )
        else:
            self._finish_progress(f"Showing {len(self.view._warning_states)} warning balloons")

    def _clear_warning_state(self) -> None:
        self.view.clear_warning_balloons()
        self.view.set_warning_source([])
        self._warning_details.clear()
        self._last_located_warning_key = None
        self.warning_list.clear()
        self.select_all_warnings_button.setEnabled(False)
        self.locate_warning_button.setEnabled(False)
        self.clear_balloons_button.setEnabled(False)

    def _sync_warning_items(self) -> None:
        active = False
        linked = False
        for index in range(self.warning_list.count()):
            item = self.warning_list.item(index)
            key = item.data(Qt.ItemDataRole.UserRole)
            if key is None:
                continue
            linked = True
            checked = self.view.has_warning_balloon(key)
            item.setToolTip(
                "Click to show this balloon, bring it into view when it is offscreen, or hide it when visible"
            )
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            active = active or checked
        if self._last_located_warning_key not in self.view._warning_states:
            self._last_located_warning_key = None
        self.select_all_warnings_button.setEnabled(linked and not self._busy)
        self.locate_warning_button.setEnabled(active and not self._busy)
        self.clear_balloons_button.setEnabled(active and not self._busy)


def _vector_path(vector: VectorEntity) -> QPainterPath:
    path = QPainterPath()
    if not vector.points:
        return path
    path.moveTo(*vector.points[0])
    for point in vector.points[1:]:
        path.lineTo(*point)
    if vector.closed:
        path.closeSubpath()
    return path


def _preview_vector_path(
    vector: VectorEntity,
    source_bounds: tuple[float, float, float, float],
    target_rect: QRectF,
) -> QPainterPath:
    path = QPainterPath()
    if not vector.points:
        return path
    x1, y1, x2, y2 = source_bounds
    source_width = max(x2 - x1, 1e-9)
    source_height = max(y2 - y1, 1e-9)
    scale = min(target_rect.width() / source_width, target_rect.height() / source_height)
    offset_x = target_rect.left() + (target_rect.width() - source_width * scale) / 2.0
    offset_y = target_rect.top() + (target_rect.height() - source_height * scale) / 2.0

    def mapped(point):
        return offset_x + (point[0] - x1) * scale, offset_y + (point[1] - y1) * scale

    path.moveTo(*mapped(vector.points[0]))
    for point in vector.points[1:]:
        path.lineTo(*mapped(point))
    if vector.closed:
        path.closeSubpath()
    return path


def _path_midpoint(vector: VectorEntity) -> tuple[float, float]:
    if not vector.points:
        return 0.0, 0.0
    if len(vector.points) == 1:
        return vector.points[0]
    segments = list(zip(vector.points, vector.points[1:]))
    if vector.closed and len(vector.points) > 2:
        segments.append((vector.points[-1], vector.points[0]))
    lengths = [hypot(b[0] - a[0], b[1] - a[1]) for a, b in segments]
    halfway = sum(lengths) / 2.0
    travelled = 0.0
    for (a, b), length in zip(segments, lengths):
        if length > 0 and travelled + length >= halfway:
            ratio = (halfway - travelled) / length
            return a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio
        travelled += length
    return vector.points[-1]


def _cosmetic_pen(color: str, width: float, style: Qt.PenStyle = Qt.PenStyle.SolidLine) -> QPen:
    pen = QPen(QColor(color), width, style)
    pen.setCosmetic(True)
    return pen


def _vector_pen() -> QPen:
    return _cosmetic_pen("#0b4f6c", 1.0)


def _selected_vector_pen() -> QPen:
    return _cosmetic_pen("#e63946", 2.2)


def _view_vectors_icon() -> QIcon:
    themed = QIcon.fromTheme("view-visible")
    if not themed.isNull():
        return themed
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor("#25313c"), 1.8))
    eye = QPainterPath(QPointF(3, 12))
    eye.cubicTo(7, 6, 17, 6, 21, 12)
    eye.cubicTo(17, 18, 7, 18, 3, 12)
    painter.drawPath(eye)
    painter.setBrush(QColor("#25313c"))
    painter.drawEllipse(QPointF(12, 12), 2.8, 2.8)
    painter.end()
    return QIcon(pixmap)


def _fit_content_icon() -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor("#111827"), 2.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(4, 9, 4, 4)
    painter.drawLine(4, 4, 9, 4)
    painter.drawLine(15, 4, 20, 4)
    painter.drawLine(20, 4, 20, 9)
    painter.drawLine(20, 15, 20, 20)
    painter.drawLine(20, 20, 15, 20)
    painter.drawLine(9, 20, 4, 20)
    painter.drawLine(4, 20, 4, 15)
    painter.end()
    return QIcon(pixmap)


def _closest_rect_edge_point(rect: QRectF, target: QPointF) -> QPointF:
    x = min(max(target.x(), rect.left()), rect.right())
    y = min(max(target.y(), rect.top()), rect.bottom())
    if not rect.contains(target):
        return QPointF(x, y)
    distances = [
        (abs(target.x() - rect.left()), QPointF(rect.left(), target.y())),
        (abs(rect.right() - target.x()), QPointF(rect.right(), target.y())),
        (abs(target.y() - rect.top()), QPointF(target.x(), rect.top())),
        (abs(rect.bottom() - target.y()), QPointF(target.x(), rect.bottom())),
    ]
    return min(distances, key=lambda item: item[0])[1]


def _arrow_path(start: QPointF, target: QPointF, head_size: float) -> QPainterPath:
    path = QPainterPath(start)
    path.lineTo(target)
    angle = atan2(target.y() - start.y(), target.x() - start.x())
    for offset in (2.55, -2.55):
        wing = QPointF(
            target.x() + head_size * cos(angle + offset),
            target.y() + head_size * sin(angle + offset),
        )
        path.moveTo(target)
        path.lineTo(wing)
    return path


# Semi-transparent so the depth shading still reads through the hazard tint.
_VCARVE_HAZARD_COLORS = {
    "flat_bottom": QColor(70, 100, 170, 110),   # wide -> flat floor, needs a clearing pass
    "unreachable": QColor(200, 60, 60, 150),     # narrower than the tip -> can't reach bottom
}


def _depth_shade(depth: float, deepest: float) -> QColor:
    """Cut-floor colour: the surface tone darkened in proportion to depth."""
    fraction = min(max(depth / deepest, 0.0), 1.0) if deepest > 0 else 0.0
    return QColor("#c89b6a").darker(120 + int(180 * fraction))


def _add_geometry(scene: QGraphicsScene, geometry, fill: QColor, stroke: QColor, z: float) -> None:
    if geometry.is_empty:
        return
    for polygon in _polygons(geometry):
        path = QPainterPath()
        exterior = list(polygon.exterior.coords)
        if exterior:
            path.moveTo(exterior[0][0], exterior[0][1])
            for x, y in exterior[1:]:
                path.lineTo(x, y)
            path.closeSubpath()
        for interior in polygon.interiors:
            coords = list(interior.coords)
            if coords:
                path.moveTo(coords[0][0], coords[0][1])
                for x, y in coords[1:]:
                    path.lineTo(x, y)
                path.closeSubpath()
        item = QGraphicsPathItem(path)
        item.setBrush(QBrush(fill))
        item.setPen(QPen(stroke, 0))
        item.setZValue(z)
        # Deliberately uncached: DeviceCoordinateCache renders the WHOLE item at
        # device resolution, and these fills span the board — zoomed in, that's a
        # giant pixmap per depth band, far slower than painting just the exposed
        # viewport. Cheap direct paint relies on vcarve_layer simplifying bands.
        scene.addItem(item)


def _polygons(geometry):
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    if isinstance(geometry, GeometryCollection):
        polygons = []
        for part in geometry.geoms:
            polygons.extend(_polygons(part))
        return polygons
    return []


def _view_bounds(
    content_bounds: tuple[float, float, float, float] | None,
    result: ProcessResult | None,
    board_width: float,
    board_height: float,
) -> tuple[float, float, float, float]:
    bounds = [(0.0, 0.0, board_width, board_height)]
    if content_bounds is not None:
        bounds.append(content_bounds)
    if result is not None:
        for value in (result.remaining_wkt, result.removed_wkt):
            geometry = geometry_from_wkt(value)
            if not geometry.is_empty:
                bounds.append(tuple(float(v) for v in geometry.bounds))
    min_x = min(item[0] for item in bounds)
    min_y = min(item[1] for item in bounds)
    max_x = max(item[2] for item in bounds)
    max_y = max(item[3] for item in bounds)
    return min_x, min_y, max_x, max_y


def _anchor_point(
    bounds: tuple[float, float, float, float],
    horizontal: str,
    vertical: str,
) -> QPointF:
    x1, y1, x2, y2 = bounds
    x = {"left": x1, "center": (x1 + x2) / 2.0, "right": x2}[horizontal]
    y = {"bottom": y1, "center": (y1 + y2) / 2.0, "top": y2}[vertical]
    return QPointF(x, y)


def _format_layout_value(value: float, units: str) -> str:
    return f"{value:.3f} {units}"


def _view_tolerance(view: QGraphicsView) -> float:
    p1 = view.mapToScene(0, 0)
    p2 = view.mapToScene(8, 0)
    return max(abs(p2.x() - p1.x()), 1.0)


def _view_units_for_pixels(view: QGraphicsView, pixels: float) -> float:
    origin = view.mapToScene(0, 0)
    x_point = view.mapToScene(int(max(1, round(pixels))), 0)
    return max(abs(x_point.x() - origin.x()), 1e-9)


def _feature_text(feat: Feature) -> str:
    parts = [p for p in (feat.h, feat.v) if p != "center"] or ["center"]
    return f"{feat.kind} {' '.join(parts)}"


def _free_lasso_path(points: list[QPointF], closed: bool) -> QPainterPath:
    path = QPainterPath()
    if not points:
        return path
    path.moveTo(points[0])
    for point in points[1:]:
        path.lineTo(point)
    if closed and len(points) >= 3:
        path.closeSubpath()
    return path


def _point_distance(a: QPointF, b: QPointF) -> float:
    return ((b.x() - a.x()) ** 2 + (b.y() - a.y()) ** 2) ** 0.5


def _lasso_screen_span(view: QGraphicsView, points: list[QPointF]) -> float:
    if len(points) < 2:
        return 0.0
    mapped = [view.mapFromScene(point) for point in points]
    min_x = min(point.x() for point in mapped)
    max_x = max(point.x() for point in mapped)
    min_y = min(point.y() for point in mapped)
    max_y = max(point.y() for point in mapped)
    return max(max_x - min_x, max_y - min_y)


def _scale_corner_at(point: QPointF, bounds: tuple[float, float, float, float], tolerance: float) -> str | None:
    x1, y1, x2, y2 = bounds
    corners = {
        "nw": (x1, y1),
        "ne": (x2, y1),
        "sw": (x1, y2),
        "se": (x2, y2),
    }
    best_corner: str | None = None
    best_distance = tolerance
    for corner, (x, y) in corners.items():
        distance = ((point.x() - x) ** 2 + (point.y() - y) ** 2) ** 0.5
        if distance <= best_distance:
            best_distance = distance
            best_corner = corner
    return best_corner


def _opposite_corner(bounds: tuple[float, float, float, float], corner: str) -> tuple[float, float]:
    x1, y1, x2, y2 = bounds
    return {
        "nw": (x2, y2),
        "ne": (x1, y2),
        "sw": (x2, y1),
        "se": (x1, y1),
    }[corner]


def _scale_transform(origin: tuple[float, float], sx: float, sy: float) -> QTransform:
    ox, oy = origin
    return QTransform(sx, 0.0, 0.0, sy, ox * (1.0 - sx), oy * (1.0 - sy))


def _rotate_zone(
    point: QPointF,
    bounds: tuple[float, float, float, float],
    scale_tol: float,
    rotate_tol: float,
) -> bool:
    """True when the cursor is in the rotation ring: outside the selection box and
    within rotate_tol of a corner but beyond the scale handle (scale_tol), so the
    scale gesture (on the handle) and rotate gesture (just past it) never overlap."""
    x1, y1, x2, y2 = bounds
    if x1 <= point.x() <= x2 and y1 <= point.y() <= y2:
        return False
    corners = ((x1, y1), (x2, y1), (x1, y2), (x2, y2))
    nearest = min(hypot(point.x() - cx, point.y() - cy) for cx, cy in corners)
    return scale_tol < nearest <= rotate_tol


def _rotation_angle(
    center: tuple[float, float],
    current: QPointF,
    start_angle: float,
    modifiers: Qt.KeyboardModifier,
) -> float:
    """Signed rotation (radians) from the drag's start bearing to the cursor's.
    Shift snaps to 15 deg steps, matching the constrain-with-Shift convention used
    by move/scale."""
    angle = atan2(current.y() - center[1], current.x() - center[0]) - start_angle
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        step = radians(15.0)
        angle = round(angle / step) * step
    return angle


def _rotate_transform(center: tuple[float, float], angle: float) -> QTransform:
    """Rotate by ``angle`` radians about ``center``. Built directly from the matrix
    (like _scale_transform) so the live QTransform preview matches the model-space
    rotation in commit_rotate_from_snapshot exactly -- same sign, same pivot."""
    cx, cy = center
    c, s = cos(angle), sin(angle)
    return QTransform(c, s, -s, c, cx - cx * c + cy * s, cy - cx * s - cy * c)


def _demo_rotate_transform() -> None:
    # 90 deg about the origin sends (1, 0) -> (0, 1) in this row-vector convention.
    t = _rotate_transform((0.0, 0.0), radians(90.0))
    p = t.map(QPointF(1.0, 0.0))
    assert abs(p.x()) < 1e-9 and abs(p.y() - 1.0) < 1e-9


def _scaled_bounds(
    bounds: tuple[float, float, float, float],
    origin: tuple[float, float],
    sx: float,
    sy: float,
) -> tuple[float, float, float, float]:
    """Bounds after _scale_transform(origin, sx, sy), normalized (min/max)."""
    x1, y1, x2, y2 = bounds
    ox, oy = origin
    xs = [ox + (x - ox) * sx for x in (x1, x2)]
    ys = [oy + (y - oy) * sy for y in (y1, y2)]
    return (min(xs), min(ys), max(xs), max(ys))


def _demo_scaled_bounds() -> None:
    # se-corner drag doubling width/height about the nw origin (0,0).
    assert _scaled_bounds((0, 0, 10, 20), (0, 0), 2.0, 2.0) == (0, 0, 20, 40)


def _scale_factors(
    current: QPointF,
    bounds: tuple[float, float, float, float],
    corner: str,
    preserve_aspect: bool,
) -> tuple[float, float]:
    x1, y1, x2, y2 = bounds
    start_corner = {
        "nw": (x1, y1),
        "ne": (x2, y1),
        "sw": (x1, y2),
        "se": (x2, y2),
    }[corner]
    anchor = _opposite_corner(bounds, corner)
    start_dx = start_corner[0] - anchor[0]
    start_dy = start_corner[1] - anchor[1]
    sx = max(0.01, (current.x() - anchor[0]) / start_dx) if abs(start_dx) > 1e-9 else 1.0
    sy = max(0.01, (current.y() - anchor[1]) / start_dy) if abs(start_dy) > 1e-9 else 1.0
    if preserve_aspect:
        horizontal_change = abs(current.x() - start_corner[0]) / max(abs(start_dx), 1e-9)
        vertical_change = abs(current.y() - start_corner[1]) / max(abs(start_dy), 1e-9)
        scale = sx if horizontal_change >= vertical_change else sy
        sx = sy = scale
    return sx, sy


def _preserve_resize_aspect(modifiers: Qt.KeyboardModifier) -> bool:
    return not bool(modifiers & Qt.KeyboardModifier.ShiftModifier)


def _constrain_move_delta(
    origin: QPointF,
    current: QPointF,
    modifiers: Qt.KeyboardModifier,
) -> tuple[float, float]:
    dx = current.x() - origin.x()
    dy = current.y() - origin.y()
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        if abs(dx) >= abs(dy):
            dy = 0.0
        else:
            dx = 0.0
    return dx, dy


def _nearest_selected_vertex(editor: EditorModel, point: tuple[float, float], tolerance: float) -> tuple[int, int] | None:
    best: tuple[int, int] | None = None
    best_distance = tolerance
    px, py = point
    for vector in editor.selected_vectors():
        for index, (x, y) in enumerate(vector.points):
            distance = ((px - x) ** 2 + (py - y) ** 2) ** 0.5
            if distance <= best_distance:
                best_distance = distance
                best = (vector.id, index)
    return best


def _double(value: float, minimum: float, maximum: float) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setDecimals(3)
    widget.setValue(value)
    return widget


class SendToSolidWorksDialog(QDialog):
    """Feature picker for Send to SolidWorks -- mirrors SW's own extrude UI."""

    def __init__(
        self,
        parent,
        thickness_mm: float | None,
        default_feature: str = "Extruded Cut",
        default_depth_mm: float = 10.0,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Send to SolidWorks")
        form = QFormLayout(self)
        self.feature = QComboBox()
        self.feature.addItems(["Extruded Cut", "Extruded Boss", "Sketch only"])
        self.feature.setCurrentText(default_feature)
        self.condition = QComboBox()
        # Keys of solidworks_bridge.END_CONDITIONS; hardcoded so the dialog
        # never imports the COM module. Up To Surface / Offset From Surface
        # wait for the armed-pick widget (plan section 4).
        self.condition.addItems(["Through All", "Blind", "Up To Next", "Mid Plane"])
        self.depth = QDoubleSpinBox()
        self.depth.setRange(0.01, 10000.0)
        self.depth.setDecimals(2)
        self.depth.setSuffix(" mm")
        self.depth.setValue(thickness_mm if thickness_mm else default_depth_mm)
        self.flip = QCheckBox("Flip direction")
        form.addRow("Feature", self.feature)
        form.addRow("End condition", self.condition)
        form.addRow("Depth", self.depth)
        form.addRow(self.flip)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.feature.currentTextChanged.connect(self._sync)
        self.condition.currentTextChanged.connect(self._sync)
        self._sync()

    def _sync(self, _text: str = "") -> None:
        is_sketch = self.feature.currentText() == "Sketch only"
        self.condition.setEnabled(not is_sketch)
        self.depth.setEnabled(
            not is_sketch and self.condition.currentText() in ("Blind", "Mid Plane")
        )
        self.flip.setEnabled(not is_sketch)

    def choices(self) -> tuple[str, str, float, bool]:
        """(feature kind, end condition, depth in meters, flip)."""
        kind = {"Extruded Cut": "cut", "Extruded Boss": "boss", "Sketch only": "sketch"}[
            self.feature.currentText()
        ]
        return kind, self.condition.currentText(), self.depth.value() / 1000.0, self.flip.isChecked()


def _text_to_vectors(text: str, font: QFont, height_mm: float, layer: str) -> list[VectorEntity]:
    """Glyph outlines -> closed vectors, scaled so the text is `height_mm` tall.

    Qt tessellates the path at the font's point size, so we render big (crisp
    curves) then scale to the requested millimetre height. Y is flipped because
    QPainterPath grows downward and the board model grows up.
    """
    render = QFont(font)
    render.setPointSize(128)  # detail only; the scale below sets the real size
    path = QPainterPath()
    path.addText(0.0, 0.0, render, text)
    rect = path.boundingRect()
    if rect.height() <= 0:
        return []
    scale = height_mm / rect.height()
    out: list[VectorEntity] = []
    for poly in path.toSubpathPolygons():
        pts = [(p.x() * scale, -p.y() * scale) for p in poly]
        if len(pts) >= 3:
            out.append(VectorEntity(points=pts, closed=True, layer=layer))
    return out


class TextToCurvesDialog(QDialog):
    """Type text, pick a font + height -> closed curves on the active layer."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setWindowTitle("Text to Curves")
        form = QFormLayout(self)
        self.text = QLineEdit("Text")
        self.font = QFontComboBox()
        self.height = QDoubleSpinBox()
        self.height.setRange(0.5, 10000.0)
        self.height.setDecimals(1)
        self.height.setSuffix(" mm")
        self.height.setValue(25.0)
        form.addRow("Text", self.text)
        form.addRow("Font", self.font)
        form.addRow("Height", self.height)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> tuple[str, QFont, float]:
        font = self.font.currentFont()
        return self.text.text(), font, self.height.value()


class RoundCornersDialog(QDialog):
    """Pick a fillet radius and which corners to round."""

    _MODES = [("All corners", "all"), ("Outside (tips)", "outside"), ("Inside (notches)", "inside")]

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setWindowTitle("Smooth Corners")
        form = QFormLayout(self)
        self.radius = QDoubleSpinBox()
        self.radius.setRange(0.1, 10000.0)
        self.radius.setDecimals(2)
        self.radius.setSuffix(" mm")
        self.radius.setValue(2.0)
        self.mode = QComboBox()
        for label, _ in self._MODES:
            self.mode.addItem(label)
        form.addRow("Radius", self.radius)
        form.addRow("Corners", self.mode)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> tuple[float, str]:
        return self.radius.value(), self._MODES[self.mode.currentIndex()][1]


class PerLayerSendDialog(QDialog):
    """One sketch + feature per cutting layer, prefilled from layer depths.

    Feature order = row order (top-down), which is the order SolidWorks applies
    them. Depth reaching the board thickness prefills Through All.
    """

    _FEATURES = ["Extruded Cut", "Extruded Boss", "Sketch only", "Skip"]
    _KINDS = {"Extruded Cut": "cut", "Extruded Boss": "boss", "Sketch only": "sketch"}

    def __init__(self, parent, layers: list[tuple[str, float]], thickness_mm: float | None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Send to SolidWorks — per layer")
        outer = QVBoxLayout(self)
        outer.addWidget(QLabel("Each layer becomes its own sketch + feature, applied top to bottom."))
        self.table = QTableWidget(len(layers), 4)
        self.table.setHorizontalHeaderLabels(["Layer", "Feature", "End condition", "Depth"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self._rows: list[tuple[str, QComboBox, QComboBox, QDoubleSpinBox]] = []
        for row, (name, depth) in enumerate(layers):
            item = QTableWidgetItem(name)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, item)
            feature = QComboBox()
            feature.addItems(self._FEATURES)
            condition = QComboBox()
            condition.addItems(["Through All", "Blind", "Up To Next", "Mid Plane"])
            through = thickness_mm is not None and depth >= thickness_mm
            condition.setCurrentText("Through All" if through else "Blind")
            spin = QDoubleSpinBox()
            spin.setRange(0.01, 10000.0)
            spin.setDecimals(2)
            spin.setSuffix(" mm")
            spin.setValue(depth)
            self.table.setCellWidget(row, 1, feature)
            self.table.setCellWidget(row, 2, condition)
            self.table.setCellWidget(row, 3, spin)
            self._rows.append((name, feature, condition, spin))
        self.table.resizeColumnsToContents()
        outer.addWidget(self.table)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def jobs(self) -> list[tuple[str, str, str, float]]:
        """(layer name, feature kind, end condition, depth in meters) per non-skipped row."""
        out = []
        for name, feature, condition, spin in self._rows:
            text = feature.currentText()
            if text == "Skip":
                continue
            out.append((name, self._KINDS[text], condition.currentText(), spin.value() / 1000.0))
        return out


def _effective_units(units: str) -> str:
    return "mm" if units == "dxf" else units


_IPC_KEY = "CurveMill-single-instance"  # shared with the SolidWorks add-in's two buttons


def _launch_message(argv: list[str]) -> str:
    # The add-in's "Send to CurveMill" button passes --get-selection; "Open CurveMill"
    # passes nothing. Any other flags are ignored here.
    return "get-selection" if "--get-selection" in argv else "open"


def _hand_off_to_running_instance(message: str) -> bool:
    # If a CurveMill is already listening, give it our command and return True so this
    # process can exit instead of opening a second window. Qt-native, no extra dependency.
    from PySide6.QtNetwork import QLocalSocket

    sock = QLocalSocket()
    sock.connectToServer(_IPC_KEY)
    if not sock.waitForConnected(300):
        return False
    sock.write(message.encode())
    sock.waitForBytesWritten(300)
    sock.disconnectFromServer()
    return True


def _install_ipc_server(window: "MainWindow") -> None:
    from PySide6.QtNetwork import QLocalServer

    QLocalServer.removeServer(_IPC_KEY)  # clear a stale socket a crash may have left
    server = QLocalServer()
    server.listen(_IPC_KEY)

    def _on_connection() -> None:
        conn = server.nextPendingConnection()
        if conn is None:
            return
        conn.waitForReadyRead(300)
        message = bytes(conn.readAll()).decode(errors="ignore")
        conn.disconnectFromServer()
        window.handle_launch_request(message)

    server.newConnection.connect(_on_connection)
    window._ipc_server = server  # keep a reference alive for the app's lifetime


def _diag_dir() -> Path:
    """Directory for crash logs — beside the settings ini so tests redirect it too."""
    settings = QSettings(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, "CurveMill", "CurveMill"
    )
    directory = Path(settings.fileName()).parent
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _enable_crash_log() -> Path | None:
    """Point faulthandler at a log file; return the prior run's crash log if any.

    faulthandler only writes on a fatal signal, so a non-empty crash.log at
    launch means the last run crashed. We move it aside (last-crash.log) before
    truncating, so the file handle held open for this run can't clobber it.
    """
    import faulthandler

    diag = _diag_dir()
    crash_log = diag / "crash.log"
    prior: Path | None = None
    if crash_log.exists() and crash_log.stat().st_size > 0:
        prior = diag / "last-crash.log"
        crash_log.replace(prior)
    # 'w' truncates: this run starts clean; the handle stays open for the app's
    # whole life (main()'s frame lives until app.exec() returns), so no GC.
    global _CRASH_LOG_FILE
    _CRASH_LOG_FILE = open(crash_log, "w")
    faulthandler.enable(_CRASH_LOG_FILE)
    return prior


_CRASH_LOG_FILE = None


def main() -> None:
    # Native Qt crashes (e.g. BSP-index corruption on scene edits) print nothing
    # on their own. faulthandler dumps a C-level stack to the crash log on the
    # fatal signal, so the next launch can surface the traceback.
    prior_crash = _enable_crash_log()
    app = QApplication(sys.argv)
    message = _launch_message(sys.argv[1:])
    if _hand_off_to_running_instance(message):
        return  # a live CurveMill took the command; this launcher exits

    window = MainWindow()
    _install_ipc_server(window)
    window.show()
    # Prompt only from the real entry point, not MainWindow.__init__, so tests that
    # construct windows directly never block on a modal dialog.
    window.offer_crash_report(prior_crash)
    window.offer_crash_restore()
    if message == "get-selection":
        window._sw_get_board()  # cold start via "Send to CurveMill": pull the face now
    sys.exit(app.exec())

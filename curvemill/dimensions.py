"""SolidWorks-style board-relative dimensions for the selection layout tool.

Pure Python (no Qt) so the constraint solver is unit-testable. A dimension ties
a feature of the selection's bounding rectangle to a feature of the board along
one axis; editing its value drives the pattern's size and position through
``EditorModel.apply_selected_layout``.

The transform per axis is ``new = center + (old - center) * s + t`` where
``center`` is the pattern bbox centre on that axis. ``solve_axis`` turns the
driving dimensions on an axis into that ``(s, t)`` pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from typing import Literal

_dim_id_counter = count(1)


def sync_dim_id_counter(dims) -> None:
    """Advance the dim-id counter past every id in ``dims`` (see the twin in
    models: restored dims keep their saved ids, so a new dim placed after a
    project load must not re-mint one, or _find_dim/delete/flip hit the wrong
    dimension)."""
    global _dim_id_counter
    nxt = next(_dim_id_counter)
    highest = max((d.id for d in dims), default=0)
    _dim_id_counter = count(max(nxt, highest + 1))


Bounds = tuple[float, float, float, float]
Axis = Literal["x", "y"]
Kind = Literal["pattern", "board"]

_H = ("left", "center", "right")
_V = ("bottom", "center", "top")

_EPS = 1e-9


class OverConstrainedError(Exception):
    """Raised when an axis has more (or conflicting) dimensions than 2 DOF allow."""


@dataclass(frozen=True, slots=True)
class Feature:
    kind: Kind
    h: str  # one of _H
    v: str  # one of _V


@dataclass(slots=True)
class Dimension:
    feat1: Feature
    feat2: Feature
    axis: Axis = "x"
    driving: bool = True
    value: float = 0.0  # signed: coord(feat2) - coord(feat1) at the target
    label_offset: float = 0.0  # perpendicular scene-unit offset of the dim line
    label_along: float = 0.0   # along-axis offset of the label from the dim midpoint
    id: int = field(default_factory=lambda: next(_dim_id_counter))

    @property
    def is_size(self) -> bool:
        """True when both ends are on the pattern (drives scale)."""
        return self.feat1.kind == "pattern" and self.feat2.kind == "pattern"

    @property
    def is_position(self) -> bool:
        """True when one end is pattern, one board (drives translation)."""
        return self.feat1.kind != self.feat2.kind


def pattern_features() -> list[Feature]:
    return [Feature("pattern", h, v) for v in _V for h in _H]


def board_features() -> list[Feature]:
    return [Feature("board", h, v) for v in _V for h in _H]


def feature_coord(feat: Feature, pat: Bounds, brd: Bounds, axis: Axis) -> float:
    x1, y1, x2, y2 = pat if feat.kind == "pattern" else brd
    if axis == "x":
        return {"left": x1, "center": (x1 + x2) / 2.0, "right": x2}[feat.h]
    return {"bottom": y1, "center": (y1 + y2) / 2.0, "top": y2}[feat.v]


def feature_point(feat: Feature, pat: Bounds, brd: Bounds) -> tuple[float, float]:
    x1, y1, x2, y2 = pat if feat.kind == "pattern" else brd
    x = {"left": x1, "center": (x1 + x2) / 2.0, "right": x2}[feat.h]
    y = {"bottom": y1, "center": (y1 + y2) / 2.0, "top": y2}[feat.v]
    return x, y


def measure(dim: Dimension, pat: Bounds, brd: Bounds) -> float:
    return feature_coord(dim.feat2, pat, brd, dim.axis) - feature_coord(dim.feat1, pat, brd, dim.axis)


def is_edge(feat: Feature) -> bool:
    """Edge features (left/right/top/bottom mid) stand for the whole edge."""
    return (feat.h == "center") != (feat.v == "center")


def edge_segment(feat: Feature, pat: Bounds, brd: Bounds) -> tuple[tuple[float, float], tuple[float, float]]:
    x1, y1, x2, y2 = pat if feat.kind == "pattern" else brd
    if feat.h == "center":
        y = y1 if feat.v == "bottom" else y2
        return (x1, y), (x2, y)
    x = x1 if feat.h == "left" else x2
    return (x, y1), (x, y2)


def nearest_feature(px: float, py: float, pat: Bounds, brd: Bounds, tolerance: float) -> Feature | None:
    feats = pattern_features() + board_features()
    best: Feature | None = None
    best_d = tolerance
    # Point features (corners + centers) win over edges when both are in reach.
    for feat in feats:
        if is_edge(feat):
            continue
        fx, fy = feature_point(feat, pat, brd)
        d = ((fx - px) ** 2 + (fy - py) ** 2) ** 0.5
        if d < best_d:
            best_d, best = d, feat
    if best is not None:
        return best
    # Edges are clickable along their whole length, like SolidWorks.
    for feat in feats:
        if not is_edge(feat):
            continue
        x1, y1, x2, y2 = pat if feat.kind == "pattern" else brd
        fx, fy = feature_point(feat, pat, brd)
        if feat.h == "center":
            d = abs(fy - py) if x1 <= px <= x2 else float("inf")
        else:
            d = abs(fx - px) if y1 <= py <= y2 else float("inf")
        if d < best_d:
            best_d, best = d, feat
    return best


def is_overconstrained(driving: list[Dimension]) -> bool:
    """A per-axis set is over-defined past its 2 DOF (scale + translate)."""
    sizes = sum(1 for d in driving if d.is_size)
    return sizes >= 2 or len(driving) >= 3


def _position_terms(dim: Dimension, pat: Bounds, brd: Bounds, axis: Axis, center: float) -> tuple[float, float]:
    """A position dim as a linear equation ``A*s + t = K`` in the axis transform."""
    p_kind_first = dim.feat1.kind == "pattern"
    pfeat = dim.feat1 if p_kind_first else dim.feat2
    bfeat = dim.feat2 if p_kind_first else dim.feat1
    p = feature_coord(pfeat, pat, brd, axis)
    b = feature_coord(bfeat, pat, brd, axis)
    a = p - center
    # feat1=pattern: b - new_p = value ; feat1=board: new_p - b = value
    k = b - center - dim.value if p_kind_first else b - center + dim.value
    return a, k


def solve_axis(
    driving: list[Dimension],
    pat: Bounds,
    brd: Bounds,
    axis: Axis,
    size_override: float | None = None,
) -> tuple[float, float]:
    """Resolve the driving dimensions on ``axis`` into ``(scale, translate)``.

    ``size_override`` forces the pattern's size on the axis (the manual spinbox
    path when no size dimension exists). Raises ``OverConstrainedError`` when the
    dimensions exceed or contradict the 2 available degrees of freedom.
    """
    x1, y1, x2, y2 = pat
    lo, hi = (x1, x2) if axis == "x" else (y1, y2)
    center = (lo + hi) / 2.0
    cur = hi - lo

    if is_overconstrained(driving):
        raise OverConstrainedError("This axis already has enough dimensions.")

    sizes = [d for d in driving if d.is_size]
    positions = [d for d in driving if d.is_position]

    if size_override is not None and len(positions) >= 2:
        raise OverConstrainedError("This axis already has enough dimensions.")

    s: float | None = None
    if size_override is not None:
        if cur <= _EPS:
            raise OverConstrainedError("Selection has no size to scale on this axis.")
        s = size_override / cur
    elif sizes:
        raw = feature_coord(sizes[0].feat2, pat, brd, axis) - feature_coord(sizes[0].feat1, pat, brd, axis)
        if abs(raw) <= _EPS:
            raise OverConstrainedError("This dimension spans no distance.")
        s = sizes[0].value / raw

    if s is None and len(positions) == 2:
        a1, k1 = _position_terms(positions[0], pat, brd, axis, center)
        a2, k2 = _position_terms(positions[1], pat, brd, axis, center)
        denom = a1 - a2
        if abs(denom) <= _EPS:
            if abs(k1 - k2) <= 1e-6:
                return 1.0, k1 - a1  # redundant: leave scale at 1
            raise OverConstrainedError("These dimensions conflict.")
        s = (k1 - k2) / denom
        return s, k1 - a1 * s

    if s is None:
        s = 1.0
    if positions:
        a, k = _position_terms(positions[0], pat, brd, axis, center)
        return s, k - a * s
    return s, 0.0

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import count

from .models import Layer, Point, SplineEntity, VectorEntity, combined_bounds


@dataclass(slots=True)
class EditorSnapshot:
    vectors: list[VectorEntity]
    splines: list[SplineEntity]
    selected_ids: set[int]
    selected_spline_ids: set[int]
    next_group_id: int
    layers: list[Layer]
    active_layer: str


class EditorModel:
    def __init__(self, vectors: list[VectorEntity] | None = None, splines: list[SplineEntity] | None = None) -> None:
        self.vectors: list[VectorEntity] = [v.clone() for v in (vectors or [])]
        self.splines: list[SplineEntity] = [s.clone() for s in (splines or [])]
        self.selected_ids: set[int] = set()
        self.selected_spline_ids: set[int] = set()
        self._undo: list[EditorSnapshot] = []
        self._redo: list[EditorSnapshot] = []
        layer_names = list(dict.fromkeys(v.layer or "0" for v in self.vectors))
        for s in self.splines:
            if s.layer not in layer_names:
                layer_names.append(s.layer or "0")
        self.layers: list[Layer] = [Layer(name) for name in layer_names] or [Layer("Layer 1")]
        self.active_layer = self.layers[0].name
        self._next_group_id = _next_group_id(self.vectors)
        self._group_counter = count(self._next_group_id)

    def load(self, vectors: list[VectorEntity], splines: list[SplineEntity] | None = None) -> None:
        self.vectors = [v.clone() for v in vectors]
        self.splines = [s.clone() for s in (splines or [])]
        layer_names = list(dict.fromkeys(v.layer or "0" for v in self.vectors))
        for s in self.splines:
            if s.layer not in layer_names:
                layer_names.append(s.layer or "0")
        self.layers = [Layer(name) for name in layer_names] or [Layer("Layer 1")]
        self.active_layer = self.layers[0].name
        self.selected_ids.clear()
        self.selected_spline_ids.clear()
        self._undo.clear()
        self._redo.clear()
        self._next_group_id = _next_group_id(self.vectors)
        self._group_counter = count(self._next_group_id)

    def load_layers(self, layer_vectors: list[tuple[str, list[VectorEntity]]], layer_splines: list[tuple[str, list[SplineEntity]]] | None = None) -> list[str]:
        self.vectors = []
        self.splines = []
        self.layers = []
        assigned_names: list[str] = []
        used_names: set[str] = set()
        for requested_name, vectors in layer_vectors:
            base = requested_name.strip() or "Imported DXF"
            name = base
            index = 2
            while name.casefold() in used_names:
                name = f"{base} {index}"
                index += 1
            used_names.add(name.casefold())
            assigned_names.append(name)
            self.layers.append(Layer(name))
            for vector in vectors:
                clone = vector.clone()
                clone.layer = name
                self.vectors.append(clone)
        # Also load splines if provided
        if layer_splines:
            for requested_name, splines in layer_splines:
                name = requested_name.strip() or "Imported DXF"
                if name not in used_names:
                    used_names.add(name.casefold())
                    assigned_names.append(name)
                    self.layers.append(Layer(name))
                for spline in splines:
                    clone = spline.clone()
                    clone.layer = name
                    self.splines.append(clone)
        if not self.layers:
            self.layers = [Layer("Layer 1")]
        self.active_layer = self.layers[0].name
        self.selected_ids.clear()
        self.selected_spline_ids.clear()
        self._undo.clear()
        self._redo.clear()
        self._next_group_id = _next_group_id(self.vectors)
        self._group_counter = count(self._next_group_id)
        return assigned_names

    def append_layers(self, layer_vectors: list[tuple[str, list[VectorEntity]]], layer_splines: list[tuple[str, list[SplineEntity]]] | None = None) -> list[str]:
        """Append imported DXF files as new, independently named layers."""
        if not layer_vectors and not layer_splines:
            return []
        self._push_undo()
        assigned_names: list[str] = []
        used_names = {name.casefold() for name in self.layer_names()}
        for requested_name, vectors in layer_vectors:
            base = requested_name.strip() or "Imported DXF"
            name = base
            index = 2
            while name.casefold() in used_names:
                name = f"{base} {index}"
                index += 1
            used_names.add(name.casefold())
            assigned_names.append(name)
            self.layers.append(Layer(name))
            for vector in vectors:
                clone = vector.clone()
                clone.layer = name
                self.vectors.append(clone)
        if layer_splines:
            for requested_name, splines in layer_splines:
                base = requested_name.strip() or "Imported DXF"
                name = base
                index = 2
                while name.casefold() in used_names:
                    name = f"{base} {index}"
                    index += 1
                used_names.add(name.casefold())
                assigned_names.append(name)
                self.layers.append(Layer(name))
                for spline in splines:
                    clone = spline.clone()
                    clone.layer = name
                    self.splines.append(clone)
        self.active_layer = assigned_names[0]
        self.selected_ids.clear()
        self.selected_spline_ids.clear()
        self._next_group_id = _next_group_id(self.vectors)
        self._group_counter = count(self._next_group_id)
        return assigned_names

    def append_import_result(self, vectors: list[VectorEntity], splines: list[SplineEntity], layer_name: str | None = None) -> None:
        """Append imported vectors and splines as a new layer."""
        if not vectors and not splines:
            return
        self._push_undo()
        base = (layer_name or "Imported").strip() or "Imported"
        used_names = {name.casefold() for name in self.layer_names()}
        name = base
        index = 2
        while name.casefold() in used_names:
            name = f"{base} {index}"
            index += 1
        self.layers.append(Layer(name))
        for v in vectors:
            clone = v.clone()
            clone.layer = name
            self.vectors.append(clone)
        for s in splines:
            clone = s.clone()
            clone.layer = name
            self.splines.append(clone)
        self.active_layer = name
        self.selected_ids.clear()
        self.selected_spline_ids.clear()

    def snapshot(self) -> EditorSnapshot:
        return EditorSnapshot(
            [v.clone() for v in self.vectors],
            [s.clone() for s in self.splines],
            set(self.selected_ids),
            set(self.selected_spline_ids),
            self._next_group_id,
            [layer.clone() for layer in self.layers],
            self.active_layer,
        )

    def restore(self, snapshot: EditorSnapshot) -> None:
        self.vectors = [v.clone() for v in snapshot.vectors]
        self.splines = [s.clone() for s in snapshot.splines]
        self.selected_ids = set(snapshot.selected_ids)
        self.selected_spline_ids = set(snapshot.selected_spline_ids)
        self._next_group_id = snapshot.next_group_id
        self._group_counter = count(self._next_group_id)
        self.layers = [layer.clone() for layer in snapshot.layers]
        self.active_layer = snapshot.active_layer

    def _push_undo(self) -> None:
        self._undo.append(self.snapshot())
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.snapshot())
        self.restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.snapshot())
        self.restore(self._redo.pop())
        return True

    def layer_names(self) -> list[str]:
        return [layer.name for layer in self.layers]

    def visible_layer_names(self) -> set[str]:
        return {layer.name for layer in self.layers if layer.visible}

    def active_layer_visible(self) -> bool:
        return self.is_layer_visible(self.active_layer)

    def is_layer_visible(self, name: str) -> bool:
        return any(layer.name == name and layer.visible for layer in self.layers)

    def visible_vectors(self) -> list[VectorEntity]:
        visible = self.visible_layer_names()
        return [vector for vector in self.vectors if vector.layer in visible]

    def visible_splines(self) -> list[SplineEntity]:
        visible = self.visible_layer_names()
        return [spline for spline in self.splines if spline.layer in visible]

    def visible_vectors_and_splines(self) -> tuple[list[VectorEntity], list[SplineEntity]]:
        visible = self.visible_layer_names()
        vs = [v for v in self.vectors if v.layer in visible]
        ss = [s for s in self.splines if s.layer in visible]
        return vs, ss

    def active_vectors_and_splines(self) -> tuple[list[VectorEntity], list[SplineEntity]]:
        """Geometry on the active layer only -- Optimize writes back to just this
        layer, so it must read from just this layer too (else other layers' shapes
        get merged onto the active one and duplicated)."""
        vs = [v for v in self.vectors if v.layer == self.active_layer]
        ss = [s for s in self.splines if s.layer == self.active_layer]
        return vs, ss

    def all_visible_vectors(self) -> list[VectorEntity]:
        """Return flattened vectors (includes spline approximations for display/processing)."""
        vs, ss = self.visible_vectors_and_splines()
        result = [v.clone() for v in vs]
        for s in ss:
            result.append(s.flatten(0.5))
        return result

    def visible_content_bounds(self) -> tuple[float, float, float, float] | None:
        """Combined bounds of all visible geometry without flattening splines.

        Used for framing (zoom-to-content) and the scene rect. Both vectors and
        splines expose a cheap ``bounds()``, so an all-spline file frames
        correctly without paying to flatten every curve on each view update.
        """
        vs, ss = self.visible_vectors_and_splines()
        return combined_bounds([*vs, *ss])

    def has_visible_geometry(self) -> bool:
        """True when any visible layer holds a vector or a native spline.

        Splines are first-class geometry, so gating (Process/Repair/Export) must
        not look at ``vectors`` alone: an all-spline file has zero vectors yet is
        perfectly processable once its splines are flattened for the sim.
        """
        visible = self.visible_layer_names()
        return any(v.layer in visible for v in self.vectors) or any(
            s.layer in visible for s in self.splines
        )

    def geometry_count_by_layer(self) -> dict[str, int]:
        """Count entities (vectors + native splines) on each layer for the layer list."""
        counts: dict[str, int] = {}
        for vector in self.vectors:
            counts[vector.layer] = counts.get(vector.layer, 0) + 1
        for spline in self.splines:
            counts[spline.layer] = counts.get(spline.layer, 0) + 1
        return counts

    def set_active_layer(self, name: str) -> bool:
        if name not in self.layer_names() or name == self.active_layer:
            return False
        self.active_layer = name
        self.selected_ids.clear()
        self.selected_spline_ids.clear()
        return True

    def add_layer(self, name: str | None = None) -> str:
        self._push_undo()
        new_name = self.unique_layer_name(name) if name else self._default_layer_name()
        index = self.layer_names().index(self.active_layer) + 1
        self.layers.insert(index, Layer(new_name))
        self.active_layer = new_name
        self.selected_ids.clear()
        self.selected_spline_ids.clear()
        return new_name

    def selection_to_new_layer(self, copy: bool = False) -> str | None:
        """Move (cut) or duplicate (copy) the current selection onto a fresh layer.

        The new layer is auto-named, visible, inserted after the active one, and
        made active so the next action lands there -- backs the right-click
        'Cut/Copy to new layer' actions. Returns None if nothing is selected.
        """
        vectors = self.selected_vectors()
        splines = self.selected_splines()
        if not vectors and not splines:
            return None
        self._push_undo()
        new_name = self._default_layer_name()
        index = self.layer_names().index(self.active_layer) + 1
        self.layers.insert(index, Layer(new_name))
        if copy:
            clones_v = self._clone_vectors_for_layer(vectors, new_name)
            clones_s = self._clone_splines_for_layer(splines, new_name)
            self.vectors.extend(clones_v)
            self.splines.extend(clones_s)
            self.selected_ids = {v.id for v in clones_v}
            self.selected_spline_ids = {s.id for s in clones_s}
        else:
            for vector in vectors:
                vector.layer = new_name
            for spline in splines:
                spline.layer = new_name
            # selection ids stay -- same entities, just reassigned layer
        self.active_layer = new_name
        return new_name

    def rename_layer(self, old_name: str, new_name: str) -> str | None:
        new_name = new_name.strip()
        if not new_name or old_name not in self.layer_names():
            return None
        other_names = {name.casefold() for name in self.layer_names() if name != old_name}
        if new_name.casefold() in other_names:
            return None
        if new_name == old_name:
            return old_name
        self._push_undo()
        for layer in self.layers:
            if layer.name == old_name:
                layer.name = new_name
                break
        for vector in self.vectors:
            if vector.layer == old_name:
                vector.layer = new_name
        for spline in self.splines:
            if spline.layer == old_name:
                spline.layer = new_name
        if self.active_layer == old_name:
            self.active_layer = new_name
        return new_name

    def delete_layer(self, name: str | None = None) -> bool:
        name = name or self.active_layer
        names = self.layer_names()
        if name not in names:
            return False
        self._push_undo()
        index = names.index(name)
        self.vectors = [vector for vector in self.vectors if vector.layer != name]
        self.splines = [spline for spline in self.splines if spline.layer != name]
        self.layers = [layer for layer in self.layers if layer.name != name]
        self.selected_ids.clear()
        self.selected_spline_ids.clear()
        if not self.layers:
            self.layers = [Layer("Layer 1")]
        self.active_layer = self.layers[min(index, len(self.layers) - 1)].name
        return True

    def clone_layer(self, name: str | None = None) -> str | None:
        name = name or self.active_layer
        names = self.layer_names()
        if name not in names:
            return None
        self._push_undo()
        clone_name = self.unique_layer_name(f"{name} copy")
        source_vectors = [vector for vector in self.vectors if vector.layer == name]
        source_splines = [spline for spline in self.splines if spline.layer == name]
        clones_v = self._clone_vectors_for_layer(source_vectors, clone_name)
        clones_s = self._clone_splines_for_layer(source_splines, clone_name)
        index = names.index(name) + 1
        source_layer = self.layers[index - 1]
        self.layers.insert(index, Layer(clone_name, source_layer.visible))
        self.vectors.extend(clones_v)
        self.splines.extend(clones_s)
        self.active_layer = clone_name
        self.selected_ids = {v.id for v in clones_v} if source_layer.visible else set()
        self.selected_spline_ids = {s.id for s in clones_s} if source_layer.visible else set()
        return clone_name

    def set_layer_visibility(self, name: str, visible: bool) -> bool:
        layer = next((item for item in self.layers if item.name == name), None)
        if layer is None or layer.visible == visible:
            return False
        self._push_undo()
        layer.visible = visible
        if not visible:
            hidden_ids = {v.id for v in self.vectors if v.layer == name}
            hidden_spline_ids = {s.id for s in self.splines if s.layer == name}
            self.selected_ids.difference_update(hidden_ids)
            self.selected_spline_ids.difference_update(hidden_spline_ids)
        return True

    def unique_layer_name(self, base: str) -> str:
        base = base.strip() or "Layer"
        existing = {name.casefold() for name in self.layer_names()}
        if base.casefold() not in existing:
            return base
        index = 2
        while f"{base} {index}".casefold() in existing:
            index += 1
        return f"{base} {index}"

    def _default_layer_name(self) -> str:
        existing = {name.casefold() for name in self.layer_names()}
        index = 1
        while f"Layer {index}".casefold() in existing:
            index += 1
        return f"Layer {index}"

    def select_all(self) -> None:
        if not self.active_layer_visible():
            self.selected_ids.clear()
            self.selected_spline_ids.clear()
            return
        self.selected_ids = {v.id for v in self.vectors if v.layer == self.active_layer}
        self.selected_spline_ids = {s.id for s in self.splines if s.layer == self.active_layer}

    def select_all_visible(self) -> None:
        visible = self.visible_layer_names()
        self.selected_ids = {v.id for v in self.vectors if v.layer in visible}
        self.selected_spline_ids = {s.id for s in self.splines if s.layer in visible}

    def clear_selection(self) -> None:
        self.selected_ids.clear()
        self.selected_spline_ids.clear()

    def replace_vectors(self, vectors: list[VectorEntity]) -> bool:
        if _vectors_geometry_equal(vectors, self.vectors):
            return False
        self._push_undo()
        selected_ids = set(self.selected_ids)
        self.vectors = [v.clone() for v in vectors]
        self.selected_ids = {v.id for v in self.vectors if v.id in selected_ids}
        return True

    def replace_vector_subset(self, vectors: list[VectorEntity]) -> bool:
        return self.replace_geometry_subset(vectors, [])

    def replace_geometry_subset(
        self, vectors: list[VectorEntity], splines: list[SplineEntity]
    ) -> bool:
        """Write repaired vectors and natively repaired splines back as one undo step."""
        vector_replacements = {vector.id: vector for vector in vectors}
        spline_replacements = {spline.id: spline for spline in splines}
        changed = any(
            vector.id in vector_replacements
            and not _vector_geometry_equal(vector, vector_replacements[vector.id])
            for vector in self.vectors
        ) or any(
            spline.id in spline_replacements
            and not _spline_geometry_equal(spline, spline_replacements[spline.id])
            for spline in self.splines
        )
        if not changed:
            return False
        self._push_undo()
        self.vectors = [vector_replacements.get(vector.id, vector).clone() for vector in self.vectors]
        self.splines = [spline_replacements.get(spline.id, spline).clone() for spline in self.splines]
        return True

    def select_box(self, min_x: float, min_y: float, max_x: float, max_y: float, additive: bool = False) -> set[int]:
        if not additive:
            self.selected_ids.clear()
            self.selected_spline_ids.clear()
        left, right = sorted((min_x, max_x))
        bottom, top = sorted((min_y, max_y))
        if not self.active_layer_visible():
            return self.selected_ids | self.selected_spline_ids
        for vector in self.vectors:
            if vector.layer != self.active_layer:
                continue
            x1, y1, x2, y2 = vector.bounds()
            if x1 >= left and x2 <= right and y1 >= bottom and y2 <= top:
                self.selected_ids.add(vector.id)
        for spline in self.splines:
            if spline.layer != self.active_layer:
                continue
            x1, y1, x2, y2 = spline.bounds()
            if x1 >= left and x2 <= right and y1 >= bottom and y2 <= top:
                self.selected_spline_ids.add(spline.id)
        # Include the splines too: a box over an all-spline file selected them in
        # state but reported an empty/vectors-only set, so any caller trusting the
        # return saw nothing. Mirrors select_at, which returns either kind.
        return self.selected_ids | self.selected_spline_ids

    def select_lasso(self, polygon: list[Point], additive: bool = False) -> set[int]:
        if not additive:
            self.selected_ids.clear()
            self.selected_spline_ids.clear()
        if len(polygon) < 3 or not self.active_layer_visible():
            return self.selected_ids | self.selected_spline_ids
        left = min(point[0] for point in polygon)
        right = max(point[0] for point in polygon)
        bottom = min(point[1] for point in polygon)
        top = max(point[1] for point in polygon)
        for vector in self.vectors:
            if vector.layer != self.active_layer:
                continue
            x1, y1, x2, y2 = vector.bounds()
            if x2 < left or x1 > right or y2 < bottom or y1 > top:
                continue
            if any(_point_in_polygon(point, polygon) for point in vector.points):
                self.selected_ids.add(vector.id)
        # Native splines are first-class geometry: test their flattened points so
        # the free lasso selects an all-spline file instead of finding nothing.
        for spline in self.splines:
            if spline.layer != self.active_layer:
                continue
            x1, y1, x2, y2 = spline.bounds()
            if x2 < left or x1 > right or y2 < bottom or y1 > top:
                continue
            if any(_point_in_polygon(point, polygon) for point in spline.flatten(0.5).points):
                self.selected_spline_ids.add(spline.id)
        return self.selected_ids | self.selected_spline_ids

    def select_at(self, point: Point, tolerance: float, additive: bool = False) -> int | None:
        if not additive:
            self.selected_ids.clear()
            self.selected_spline_ids.clear()
        best_id: int | None = None
        best_is_spline = False
        best_distance = tolerance
        px, py = point
        if not self.active_layer_visible():
            return None
        for vector in self.vectors:
            if vector.layer != self.active_layer:
                continue
            x1, y1, x2, y2 = vector.bounds()
            if px < x1 - tolerance or px > x2 + tolerance or py < y1 - tolerance or py > y2 + tolerance:
                continue  # cursor can't be within tolerance of any point on this shape
            distance = _distance_to_polyline(point, vector.points, vector.closed)
            if distance <= best_distance:
                best_distance = distance
                best_id = vector.id
        # Also check spline approximations for point selection
        for spline in self.splines:
            if spline.layer != self.active_layer:
                continue
            x1, y1, x2, y2 = spline.bounds()
            if px < x1 - tolerance or px > x2 + tolerance or py < y1 - tolerance or py > y2 + tolerance:
                continue  # skip the flatten entirely for far-away splines
            flattened = spline.flatten(0.5)
            distance = _distance_to_polyline(point, flattened.points, flattened.closed)
            if distance <= best_distance:
                best_distance = distance
                best_id = spline.id
                best_is_spline = True
        if best_id is not None:
            # Splines live in their own selection set; putting a spline id into
            # selected_ids selects nothing (highlight/move/resize never see it).
            (self.selected_spline_ids if best_is_spline else self.selected_ids).add(best_id)
        return best_id

    def selected_vectors(self) -> list[VectorEntity]:
        expanded = self.selected_target_ids()
        return [v for v in self.vectors if v.id in expanded]

    def selected_splines(self) -> list[SplineEntity]:
        return [s for s in self.splines if s.id in self.selected_spline_ids]

    def selected_target_ids(self) -> set[int]:
        visible = self.visible_layer_names()
        expanded = {v.id for v in self.vectors if v.id in self.selected_ids and v.layer in visible}
        selected_groups = {
            v.group_id
            for v in self.vectors
            if v.id in expanded and v.group_id is not None
        }
        for vector in self.vectors:
            if vector.layer in visible and vector.group_id in selected_groups:
                expanded.add(vector.id)
        # Also include selected spline IDs
        expanded |= {s.id for s in self.splines if s.id in self.selected_spline_ids and s.layer in visible}
        return expanded

    def bounds_for_ids(self, ids: set[int]) -> tuple[float, float, float, float] | None:
        """Combined bounds of the vectors/splines with these ids, ignoring selection.

        Lets a stored dimension resolve its own pattern's box (to draw/measure it)
        without that pattern being the current on-canvas selection.
        """
        entities = [v for v in self.vectors if v.id in ids] + [
            s for s in self.splines if s.id in ids
        ]
        return combined_bounds(entities)

    def layer_of_ids(self, ids: set[int]) -> str | None:
        """Layer that owns these ids (a dimensioned pattern lives on one layer)."""
        for vector in self.vectors:
            if vector.id in ids:
                return vector.layer
        for spline in self.splines:
            if spline.id in ids:
                return spline.layer
        return None

    def selected_bounds(self) -> tuple[float, float, float, float] | None:
        # Splines are first-class geometry: an all-spline selection has zero
        # selected vectors, so the layout panel would stay disabled without them.
        # Both VectorEntity and SplineEntity expose bounds(), so combine directly.
        return combined_bounds([*self.selected_vectors(), *self.selected_splines()])

    def delete_selected(self) -> bool:
        targets = self.selected_target_ids()
        spline_targets = set(self.selected_spline_ids)
        if not targets and not spline_targets:
            return False
        self._push_undo()
        self.vectors = [v for v in self.vectors if v.id not in targets]
        self.splines = [s for s in self.splines if s.id not in spline_targets]
        self.selected_ids.clear()
        self.selected_spline_ids.clear()
        return True

    def remove_duplicates(self, tolerance: float = 1e-9) -> int:
        """Delete visible entities that trace the same path as an earlier one.

        Matches the canvas overlay's duplicate count: identification runs on the
        same flattened geometry (vectors first, then splines flattened at 0.5),
        so removal always clears exactly the counted faults. One undo step.
        """
        from .geometry import duplicate_vector_indices

        vs, ss = self.visible_vectors_and_splines()
        flattened = [*vs, *[s.flatten(0.5) for s in ss]]
        duplicates = duplicate_vector_indices(flattened, tolerance)
        if not duplicates:
            return 0
        vector_ids = {vs[i].id for i in duplicates if i < len(vs)}
        spline_ids = {ss[i - len(vs)].id for i in duplicates if i >= len(vs)}
        self._push_undo()
        self.vectors = [v for v in self.vectors if v.id not in vector_ids]
        self.splines = [s for s in self.splines if s.id not in spline_ids]
        self.selected_ids -= vector_ids
        self.selected_spline_ids -= spline_ids
        return len(duplicates)

    def remove_degenerate(self, tolerance: float) -> int:
        """Delete visible junk entities whose whole extent fits inside the tolerance.

        Sub-tolerance fragments (pattern-generator residue, measured 0.006-0.07mm
        on a real file) are noise no tool can cut, and every downstream repair
        fault traced back to them: endpoint snapping welds them into zero-area
        self-crossing loops, and their ends inflate real junctions into
        multi-vertex faults. BUT a tiny entity joined end-to-end to exactly one
        neighbour is legitimate curve sampling (pattern soup is thousands of
        sub-tolerance LINEs) -- deleting those punches holes in every chain. So
        only tiny closed rings and tiny open entities with no valence-2 joint
        (dead ends and >=3-way junction stubs) are junk. Same doctrine as
        remove_duplicates -- deleted outright, one undo step.
        """
        if tolerance <= 0:
            return 0

        def tiny(entity) -> bool:
            min_x, min_y, max_x, max_y = entity.bounds()
            return math.hypot(max_x - min_x, max_y - min_y) <= tolerance

        vs, ss = self.visible_vectors_and_splines()
        flats = {s.id: s.flatten(0.5) for s in ss}
        grid = 1e-9

        def key(p: Point) -> tuple[int, int]:
            return (round(p[0] / grid), round(p[1] / grid))

        from collections import Counter

        uses: Counter = Counter()
        for e in [*vs, *flats.values()]:
            if e.closed or not e.points:
                continue
            uses[key(e.points[0])] += 1
            uses[key(e.points[-1])] += 1

        def junk(entity, flat) -> bool:
            if not tiny(entity):
                return False
            if flat.closed or not flat.points:
                return True
            k0, k1 = key(flat.points[0]), key(flat.points[-1])
            own = 2 if k0 == k1 else 1
            # An end meeting exactly one other end is a bridge inside a real
            # chain; either end being one keeps the entity.
            return (uses[k0] - own) != 1 and (uses[k1] - own) != 1

        vector_ids = {v.id for v in vs if junk(v, v)}
        spline_ids = {s.id for s in ss if junk(s, flats[s.id])}
        if not vector_ids and not spline_ids:
            return 0
        self._push_undo()
        self.vectors = [v for v in self.vectors if v.id not in vector_ids]
        self.splines = [s for s in self.splines if s.id not in spline_ids]
        self.selected_ids -= vector_ids
        self.selected_spline_ids -= spline_ids
        return len(vector_ids) + len(spline_ids)

    def move_selected(self, dx: float, dy: float) -> bool:
        targets = self.selected_target_ids()
        spline_targets = set(self.selected_spline_ids)
        if (not targets and not spline_targets) or (abs(dx) < 1e-12 and abs(dy) < 1e-12):
            return False
        self._push_undo()
        self.vectors = [v.translated(dx, dy) if v.id in targets else v.clone() for v in self.vectors]
        self.splines = [s.translated(dx, dy) if s.id in spline_targets else s.clone() for s in self.splines]
        self.selected_ids = targets
        return True

    def scale_selected(self, origin: Point, sx: float, sy: float | None = None) -> bool:
        sy = sx if sy is None else sy
        targets = self.selected_target_ids()
        spline_targets = set(self.selected_spline_ids)
        if (not targets and not spline_targets) or (abs(sx - 1.0) < 1e-12 and abs(sy - 1.0) < 1e-12):
            return False
        self._push_undo()
        self.vectors = [v.scaled(origin, sx, sy) if v.id in targets else v.clone() for v in self.vectors]
        self.splines = [s.scaled(origin, sx, sy) if s.id in spline_targets else s.clone() for s in self.splines]
        self.selected_ids = targets | spline_targets
        return True

    def _selected_layout_targets(self) -> tuple[set[int], set[int]]:
        """Selected, currently-visible vector and spline ids (groups expanded)."""
        expanded = self.selected_target_ids()
        vector_targets = {v.id for v in self.vectors if v.id in expanded}
        spline_targets = {s.id for s in self.splines if s.id in expanded}
        return vector_targets, spline_targets

    def apply_selected_layout(
        self,
        width: float,
        height: float,
        pattern_reference: Point,
        board_reference: Point,
    ) -> bool:
        """Resize the visible selection to ``width`` x ``height`` and move its
        ``pattern_reference`` point onto ``board_reference``.

        Hidden and unselected entities are left untouched. Raises ``ValueError``
        when the selection has no measurable extent to scale.
        """
        vector_targets, spline_targets = self._selected_layout_targets()
        if not vector_targets and not spline_targets:
            return False
        bounds = combined_bounds(
            [v for v in self.vectors if v.id in vector_targets]
            + [s for s in self.splines if s.id in spline_targets]
        )
        if bounds is None:
            return False
        min_x, min_y, max_x, max_y = bounds
        current_width = max_x - min_x
        current_height = max_y - min_y
        if current_width <= 1e-9 or current_height <= 1e-9:
            raise ValueError("Selection has no width or height to resize.")
        sx = width / current_width
        sy = height / current_height
        px, py = pattern_reference
        dx = board_reference[0] - px
        dy = board_reference[1] - py
        if abs(sx - 1.0) < 1e-12 and abs(sy - 1.0) < 1e-12 and abs(dx) < 1e-12 and abs(dy) < 1e-12:
            return False
        self._push_undo()
        self.vectors = [
            v.scaled(pattern_reference, sx, sy).translated(dx, dy) if v.id in vector_targets else v.clone()
            for v in self.vectors
        ]
        self.splines = [
            s.scaled(pattern_reference, sx, sy).translated(dx, dy) if s.id in spline_targets else s.clone()
            for s in self.splines
        ]
        self.selected_ids = vector_targets | spline_targets
        return True

    def group_selected(self) -> int | None:
        """Assign a shared group id to the visible selection (vectors and
        splines). Returns the new group id, or ``None`` if fewer than two
        entities are selected.
        """
        vector_targets, spline_targets = self._selected_layout_targets()
        if len(vector_targets) + len(spline_targets) < 2:
            return None
        self._push_undo()
        group_id = self._allocate_group_id()
        for vector in self.vectors:
            if vector.id in vector_targets:
                vector.group_id = group_id
        for spline in self.splines:
            if spline.id in spline_targets:
                spline.group_id = group_id
        return group_id

    def ungroup_selected(self) -> bool:
        """Clear the group id from every selected vector and spline. Returns
        ``True`` when at least one entity was actually grouped.
        """
        vector_targets, spline_targets = self._selected_layout_targets()
        grouped = any(v.group_id is not None for v in self.vectors if v.id in vector_targets)
        grouped = grouped or any(s.group_id is not None for s in self.splines if s.id in spline_targets)
        if not grouped:
            return False
        self._push_undo()
        for vector in self.vectors:
            if vector.id in vector_targets:
                vector.group_id = None
        for spline in self.splines:
            if spline.id in spline_targets:
                spline.group_id = None
        return True

    def smooth_vectors(self, iterations: int = 1) -> bool:
        targets = self.selected_target_ids()
        if not targets and self.active_layer_visible():
            targets = {v.id for v in self.vectors if v.layer == self.active_layer}
        if not targets:
            return False
        self._push_undo()
        self.vectors = [_smooth_vector(v, iterations) if v.id in targets else v.clone() for v in self.vectors]
        self.selected_ids = self.selected_ids & {v.id for v in self.vectors}
        return True

    def round_corners(self, radius: float, mode: str = "all") -> bool:
        """Fillet sharp corners of the targeted geometry with an arc of `radius`.

        A corner is a tangent break; after Optimize that break lives at the
        shared endpoint of two separate entities (a fit-point spline can't hold
        one -- see geometry.join_spline_fragments), so raw polylines and
        optimized splines are handled the same way: flatten every target to a
        polyline, weld coincident pieces into chains, and the junction becomes an
        ordinary interior vertex that _round_chain fillets. Chains that touched a
        spline are re-fit to fit-point splines (so the SolidWorks element count
        is preserved); pure-polyline chains stay polylines.

        `mode` is "all" | "outside" (convex tips) | "inside" (reflex notches).
        """
        from .geometry import CORNER_DEGREES, _build_chains, fit_vector_chains

        if radius <= 0:
            return False
        targets = self.selected_target_ids()
        if not targets and self.active_layer_visible():
            targets = {v.id for v in self.vectors if v.layer == self.active_layer}
            targets |= {s.id for s in self.splines if s.layer == self.active_layer}
        target_vectors = [v for v in self.vectors if v.id in targets]
        target_splines = [s for s in self.splines if s.id in targets]
        if not target_vectors and not target_splines:
            return False

        new_polys: list[VectorEntity] = []
        new_splines: list[SplineEntity] = []
        changed = False
        layers = {v.layer for v in target_vectors} | {s.layer for s in target_splines}
        for layer in layers:
            wrappers = [v.clone() for v in target_vectors if v.layer == layer]
            spline_ids: set[int] = set()
            for spline in target_splines:
                if spline.layer != layer:
                    continue
                # is_valid checks control_points, but optimized splines are
                # fit-point-only (empty control net) -- guard on the flattened
                # polyline instead so those aren't silently skipped.
                flat = spline.flatten(_ROUND_FLAT_TOL)
                if len(flat.points) < 2:
                    continue
                flat.closed = spline.closed
                spline_ids.add(flat.id)
                wrappers.append(flat)

            chains = _build_chains(
                [w for w in wrappers if not w.closed], _ROUND_JOIN_TOL
            )
            pieces = [
                (list(w.points), True, w.id in spline_ids)
                for w in wrappers
                if w.closed
            ]
            for pts, members in chains:
                closed = len(pts) > 2 and _distance(pts[0], pts[-1]) <= _ROUND_JOIN_TOL
                if closed:
                    pts = pts[:-1]
                tainted = any(m.id in spline_ids for m in members)
                pieces.append((pts, closed, tainted))

            to_fit: list[VectorEntity] = []
            for pts, closed, tainted in pieces:
                rounded, did = _round_chain(pts, closed, radius, mode, CORNER_DEGREES)
                changed = changed or did
                entity = VectorEntity(points=rounded, closed=closed, layer=layer)
                (to_fit if tainted else new_polys).append(entity)
            if to_fit:
                new_splines.extend(fit_vector_chains(to_fit))

        if not changed:
            return False
        self._push_undo()
        self.vectors = [v.clone() for v in self.vectors if v.id not in targets] + new_polys
        self.splines = [s.clone() for s in self.splines if s.id not in targets] + new_splines
        self.selected_ids &= {v.id for v in self.vectors}
        self.selected_spline_ids &= {s.id for s in self.splines}
        return True

    def preview_move_from_snapshot(self, snapshot: EditorSnapshot, dx: float, dy: float) -> None:
        self.restore(snapshot)
        targets = self.selected_target_ids()
        spline_targets = set(self.selected_spline_ids)
        self.vectors = [v.translated(dx, dy) if v.id in targets else v.clone() for v in self.vectors]
        self.splines = [s.translated(dx, dy) if s.id in spline_targets else s.clone() for s in self.splines]
        self.selected_ids = targets

    def preview_scale_from_snapshot(self, snapshot: EditorSnapshot, origin: Point, sx: float, sy: float) -> None:
        self.restore(snapshot)
        targets = self.selected_target_ids()
        spline_targets = set(self.selected_spline_ids)
        self.vectors = [v.scaled(origin, sx, sy) if v.id in targets else v.clone() for v in self.vectors]
        self.splines = [s.scaled(origin, sx, sy) if s.id in spline_targets else s.clone() for s in self.splines]
        self.selected_ids = targets

    def commit_move_from_snapshot(self, before: EditorSnapshot, dx: float, dy: float) -> bool:
        targets = self.selected_target_ids()
        spline_targets = set(self.selected_spline_ids)
        if (not targets and not spline_targets) or (abs(dx) < 1e-12 and abs(dy) < 1e-12):
            return False
        for vector in self.vectors:
            if vector.id in targets:
                vector.points = [(x + dx, y + dy) for x, y in vector.points]
        for spline in self.splines:
            if spline.id in spline_targets:
                spline.control_points = [(x + dx, y + dy) for x, y in spline.control_points]
                spline.fit_points = [(x + dx, y + dy) for x, y in spline.fit_points]
        self.selected_ids = targets
        self._undo.append(before)
        self._redo.clear()
        return True

    def commit_scale_from_snapshot(
        self,
        before: EditorSnapshot,
        origin: Point,
        sx: float,
        sy: float,
    ) -> bool:
        targets = self.selected_target_ids()
        spline_targets = set(self.selected_spline_ids)
        if (not targets and not spline_targets) or (abs(sx - 1.0) < 1e-12 and abs(sy - 1.0) < 1e-12):
            return False
        ox, oy = origin
        for vector in self.vectors:
            if vector.id in targets:
                vector.points = [
                    (ox + (x - ox) * sx, oy + (y - oy) * sy)
                    for x, y in vector.points
                ]
        for spline in self.splines:
            if spline.id in spline_targets:
                spline.control_points = [
                    (ox + (x - ox) * sx, oy + (y - oy) * sy)
                    for x, y in spline.control_points
                ]
                spline.fit_points = [
                    (ox + (x - ox) * sx, oy + (y - oy) * sy)
                    for x, y in spline.fit_points
                ]
        self.selected_ids = targets
        self._undo.append(before)
        self._redo.clear()
        return True

    def commit_rotate_from_snapshot(
        self,
        before: EditorSnapshot,
        center: Point,
        angle: float,
    ) -> bool:
        """Rotate the selection by ``angle`` radians about ``center``. Mirrors
        commit_scale_from_snapshot -- same targets, same undo bookkeeping -- with a
        rotation matrix in place of the scale."""
        targets = self.selected_target_ids()
        spline_targets = set(self.selected_spline_ids)
        if (not targets and not spline_targets) or abs(angle) < 1e-9:
            return False
        cx, cy = center
        cos_a, sin_a = math.cos(angle), math.sin(angle)

        def rotate(x: float, y: float) -> Point:
            dx, dy = x - cx, y - cy
            return (cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a)

        for vector in self.vectors:
            if vector.id in targets:
                vector.points = [rotate(x, y) for x, y in vector.points]
        for spline in self.splines:
            if spline.id in spline_targets:
                spline.control_points = [rotate(x, y) for x, y in spline.control_points]
                spline.fit_points = [rotate(x, y) for x, y in spline.fit_points]
        self.selected_ids = targets
        self._undo.append(before)
        self._redo.clear()
        return True

    def _selection_center(self) -> Point | None:
        """Centre of the visible selection's bounding box (groups expanded),
        computed over exactly the ids rotate/flip will transform."""
        vector_targets, spline_targets = self._selected_layout_targets()
        if not vector_targets and not spline_targets:
            return None
        bounds = combined_bounds(
            [v for v in self.vectors if v.id in vector_targets]
            + [s for s in self.splines if s.id in spline_targets]
        )
        if bounds is None:
            return None
        min_x, min_y, max_x, max_y = bounds
        return ((min_x + max_x) / 2, (min_y + max_y) / 2)

    def rotate_selected(self, angle: float) -> bool:
        """Rotate the visible selection by ``angle`` radians about its centre.
        Menu twin of the interactive rotate drag -- same commit path, same undo."""
        center = self._selection_center()
        if center is None:
            return False
        return self.commit_rotate_from_snapshot(self.snapshot(), center, angle)

    def flip_selected(self, horizontal: bool) -> bool:
        """Mirror the visible selection about its centre. ``horizontal`` swaps
        left/right (sx=-1); otherwise top/bottom (sy=-1). A mirror is just a
        negative scale, so it reuses the scale commit -- same undo bookkeeping."""
        center = self._selection_center()
        if center is None:
            return False
        sx, sy = (-1.0, 1.0) if horizontal else (1.0, -1.0)
        return self.commit_scale_from_snapshot(self.snapshot(), center, sx, sy)

    def commit_live_edit(self, before: EditorSnapshot) -> bool:
        after = self.snapshot()
        if _snapshots_equal(before, after):
            self.restore(before)
            return False
        self._undo.append(before)
        self._redo.clear()
        return True

    def edit_vertex(self, vector_id: int, vertex_index: int, point: Point) -> bool:
        if not any(v.id == vector_id for v in self.vectors):
            return False
        self._push_undo()
        self.vectors = [
            v.set_vertex(vertex_index, point) if v.id == vector_id else v.clone()
            for v in self.vectors
        ]
        return True

    def copy_selected(self) -> list[VectorEntity]:
        targets = self.selected_target_ids()
        return [vector.clone() for vector in self.vectors if vector.id in targets]

    def copy_selected_splines(self) -> list[SplineEntity]:
        return [spline.clone() for spline in self.splines if spline.id in self.selected_spline_ids]

    def paste_vectors(self, vectors: list[VectorEntity], center: Point) -> list[int]:
        if not vectors:
            return []
        self._push_undo()
        active = next(layer for layer in self.layers if layer.name == self.active_layer)
        active.visible = True
        clones = self._clone_vectors_for_layer(vectors, self.active_layer)
        bounds = combined_bounds(clones)
        if bounds is not None:
            source_center = ((bounds[0] + bounds[2]) / 2.0, (bounds[1] + bounds[3]) / 2.0)
            dx = center[0] - source_center[0]
            dy = center[1] - source_center[1]
            for vector in clones:
                vector.points = [(x + dx, y + dy) for x, y in vector.points]
        self.vectors.extend(clones)
        self.selected_ids = {vector.id for vector in clones}
        return [vector.id for vector in clones]

    def paste_splines(self, splines: list[SplineEntity], center: Point) -> list[int]:
        if not splines:
            return []
        self._push_undo()
        active = next(layer for layer in self.layers if layer.name == self.active_layer)
        active.visible = True
        clones = self._clone_splines_for_layer(splines, self.active_layer)
        if clones:
            all_pts = [p for s in clones for p in s.control_points + s.fit_points]
            if all_pts:
                xs = [p[0] for p in all_pts]
                ys = [p[1] for p in all_pts]
                source_center = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
                dx = center[0] - source_center[0]
                dy = center[1] - source_center[1]
                for spline in clones:
                    spline.control_points = [(x + dx, y + dy) for x, y in spline.control_points]
                    spline.fit_points = [(x + dx, y + dy) for x, y in spline.fit_points]
        self.splines.extend(clones)
        self.selected_spline_ids = {s.id for s in clones}
        return [s.id for s in clones]

    def _clone_vectors_for_layer(self, vectors: list[VectorEntity], layer: str) -> list[VectorEntity]:
        group_map: dict[int, int] = {}
        clones: list[VectorEntity] = []
        for vector in vectors:
            group_id = None
            if vector.group_id is not None:
                if vector.group_id not in group_map:
                    group_map[vector.group_id] = self._allocate_group_id()
                group_id = group_map[vector.group_id]
            clones.append(
                VectorEntity(
                    points=list(vector.points),
                    closed=vector.closed,
                    layer=layer,
                    source_type=vector.source_type,
                    group_id=group_id,
                )
            )
        return clones

    def _clone_splines_for_layer(self, splines: list[SplineEntity], layer: str) -> list[SplineEntity]:
        group_map: dict[int, int] = {}
        clones: list[SplineEntity] = []
        for spline in splines:
            group_id = None
            if spline.group_id is not None:
                if spline.group_id not in group_map:
                    group_map[spline.group_id] = self._allocate_group_id()
                group_id = group_map[spline.group_id]
            clones.append(
                SplineEntity(
                    control_points=list(spline.control_points),
                    fit_points=list(spline.fit_points),
                    degree=spline.degree,
                    knots=list(spline.knots) if spline.knots is not None else None,
                    closed=spline.closed,
                    periodic=spline.periodic,
                    layer=layer,
                    group_id=group_id,
                )
            )
        return clones

    def _allocate_group_id(self) -> int:
        group_id = next(self._group_counter)
        self._next_group_id = group_id + 1
        return group_id


def _snapshots_equal(a: EditorSnapshot, b: EditorSnapshot) -> bool:
    if (
        a.selected_ids != b.selected_ids
        or a.selected_spline_ids != b.selected_spline_ids
        or a.active_layer != b.active_layer
        or a.layers != b.layers
        or len(a.vectors) != len(b.vectors)
        or len(a.splines) != len(b.splines)
    ):
        return False
    for left, right in zip(a.vectors, b.vectors):
        if (
            left.id != right.id
            or left.group_id != right.group_id
            or left.closed != right.closed
            or left.points != right.points
            or left.layer != right.layer
            or left.source_type != right.source_type
        ):
            return False
    for left, right in zip(a.splines, b.splines):
        if (
            left.id != right.id
            or left.group_id != right.group_id
            or left.degree != right.degree
            or left.closed != right.closed
            or left.periodic != right.periodic
            or left.control_points != right.control_points
            or left.fit_points != right.fit_points
            or left.layer != right.layer
        ):
            return False
    return True


def _next_group_id(vectors: list[VectorEntity]) -> int:
    group_ids = [vector.group_id for vector in vectors if vector.group_id is not None]
    return max(group_ids, default=0) + 1


def _vector_geometry_equal(left: VectorEntity, right: VectorEntity) -> bool:
    return (
        left.id == right.id
        and left.points == right.points
        and left.closed == right.closed
        and left.layer == right.layer
        and left.source_type == right.source_type
        and left.group_id == right.group_id
    )


def _spline_geometry_equal(left: SplineEntity, right: SplineEntity) -> bool:
    return (
        left.id == right.id
        and left.control_points == right.control_points
        and left.fit_points == right.fit_points
        and left.closed == right.closed
        and left.periodic == right.periodic
        and left.degree == right.degree
        and left.layer == right.layer
        and left.group_id == right.group_id
    )


def _vectors_geometry_equal(left: list[VectorEntity], right: list[VectorEntity]) -> bool:
    return len(left) == len(right) and all(
        _vector_geometry_equal(a, b) for a, b in zip(left, right)
    )


def _smooth_vector(vector: VectorEntity, iterations: int) -> VectorEntity:
    copy = vector.clone()
    for _ in range(max(1, iterations)):
        copy.points = _chaikin_points(copy.points, copy.closed)
    return copy


def _chaikin_points(points: list[Point], closed: bool) -> list[Point]:
    if len(points) < 3:
        return list(points)
    smoothed: list[Point] = []
    if not closed:
        smoothed.append(points[0])
    count = len(points)
    pair_count = count if closed else count - 1
    for index in range(pair_count):
        p = points[index]
        q = points[(index + 1) % count]
        smoothed.append((0.75 * p[0] + 0.25 * q[0], 0.75 * p[1] + 0.25 * q[1]))
        smoothed.append((0.25 * p[0] + 0.75 * q[0], 0.25 * p[1] + 0.75 * q[1]))
    if not closed:
        smoothed.append(points[-1])
    return smoothed


# Corner rounding. Splines are flattened this fine so the fillet arc lands on
# the real curve, not a coarse chord; chains are welded with the same 0.1um
# tolerance the optimizer's fitting uses.
_ROUND_FLAT_TOL = 0.05
_ROUND_JOIN_TOL = 1e-4
_ARC_STEP_DEG = 12.0


def _unit(x: float, y: float) -> Point | None:
    length = math.hypot(x, y)
    return None if length == 0.0 else (x / length, y / length)


def _winding_sign(points: list[Point]) -> int:
    area = 0.0
    for a, b in zip(points, points[1:] + points[:1]):
        area += a[0] * b[1] - b[0] * a[1]
    return 1 if area >= 0 else -1


def _normalize_angle(angle: float) -> float:
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle <= -math.pi:
        angle += 2 * math.pi
    return angle


def _arc_interior(t1: Point, t2: Point, center: Point) -> list[Point]:
    """Points strictly between t1 and t2 on the minor arc around center."""
    radius = math.hypot(t1[0] - center[0], t1[1] - center[1])
    a1 = math.atan2(t1[1] - center[1], t1[0] - center[0])
    a2 = math.atan2(t2[1] - center[1], t2[0] - center[0])
    delta = _normalize_angle(a2 - a1)  # minor arc: |delta| < pi (defl < 180)
    steps = max(1, math.ceil(abs(delta) / math.radians(_ARC_STEP_DEG)))
    return [
        (center[0] + radius * math.cos(a1 + delta * k / steps),
         center[1] + radius * math.sin(a1 + delta * k / steps))
        for k in range(1, steps)
    ]


def _round_chain(
    points: list[Point], closed: bool, radius: float, mode: str, corner_degrees: float
) -> tuple[list[Point], bool]:
    """Replace each qualifying sharp corner of a chain with a tangent arc.

    Works on any point density: a raw polyline corner and a flattened-spline
    junction are the same case here -- a vertex where the chain turns sharper
    than corner_degrees. `mode` ("all"/"outside"/"inside") only filters closed
    chains, where winding tells a convex tip from a reflex notch; an open chain
    has no interior, so it always rounds every corner.
    ponytail: tangent points are placed along the corner's local tangent, so on
    a curved leg they sit a hair off the true curve -- healed by the re-fit that
    follows for spline chains, and exact for straight polyline legs. Widen
    _ROUND_FLAT_TOL sampling if a sub-0.05mm fillet ever matters.
    """
    pts = list(points)
    if closed and len(pts) > 2 and pts[0] == pts[-1]:
        pts = pts[:-1]  # VectorEntity closed loops don't repeat the seam point
    n = len(pts)
    if n < 3:
        return list(points), False

    def at(i: int) -> Point:
        return pts[i % n]

    span = n if closed else n - 1
    seglen = [_distance(at(i), at(i + 1)) for i in range(span)]
    winding = _winding_sign(pts) if closed else 0

    # Qualifying corners in chain order, each with its half-angle tangent data.
    order: list[int] = []
    corner: dict[int, tuple[float, Point, Point]] = {}
    for i in (range(n) if closed else range(1, n - 1)):
        a, b, c = at(i - 1), at(i), at(i + 1)
        din = _unit(b[0] - a[0], b[1] - a[1])
        dout = _unit(c[0] - b[0], c[1] - b[1])
        if din is None or dout is None:
            continue
        dot = max(-1.0, min(1.0, din[0] * dout[0] + din[1] * dout[1]))
        defl = math.degrees(math.acos(dot))
        if defl <= corner_degrees:
            continue
        if closed and mode != "all":
            cross = din[0] * dout[1] - din[1] * dout[0]
            convex = (cross > 0) == (winding > 0)
            if (mode == "outside") != convex:
                continue
        order.append(i)
        corner[i] = (math.radians(defl), din, dout)
    if not order:
        return list(points), False

    # Distance each corner may eat toward a neighbour: half a shared run (so two
    # corners on one run never overrun each other), a whole free end run.
    def leg_room(k: int, step: int, neighbour_is_corner: bool) -> float:
        room = 0.0
        j = k
        while True:
            nxt = j + step
            if not closed and not (0 <= nxt <= n - 1):
                break
            seg = seglen[min(j, nxt) % span]
            room += seg
            if (nxt % n) in corner:
                break
            j = nxt
        return room * (0.5 if neighbour_is_corner else 1.0)

    blocks: dict[int, tuple[float, list[Point]]] = {}  # filleted corner -> (trim, arc)
    for pos, i in enumerate(order):
        defl, din, dout = corner[i]
        prev_is_corner = closed or pos > 0
        next_is_corner = closed or pos < len(order) - 1
        t = min(
            radius * math.tan(defl / 2),
            leg_room(i, -1, prev_is_corner),
            leg_room(i, +1, next_is_corner),
        )
        if t <= 1e-9:
            continue  # no room; leave this corner sharp
        bisect = _unit(dout[0] - din[0], dout[1] - din[1])
        if bisect is None:  # straight-through (shouldn't pass the corner test)
            continue
        r_eff = t / math.tan(defl / 2)
        b = at(i)
        t1 = (b[0] - t * din[0], b[1] - t * din[1])
        t2 = (b[0] + t * dout[0], b[1] + t * dout[1])
        dist_to_center = r_eff / math.cos(defl / 2)
        center = (b[0] + dist_to_center * bisect[0], b[1] + dist_to_center * bisect[1])
        blocks[i] = (t, [t1] + _arc_interior(t1, t2, center) + [t2])
    if not blocks:
        return list(points), False

    def run_interior(ip: int, iq: int, tp: float, tq: float) -> list[Point]:
        """Kept samples strictly between corners ip and iq (forward), trims removed."""
        samples: list[tuple[int, float]] = []
        acc = 0.0
        j = ip
        while True:
            acc += seglen[j % span]
            nxt = (j + 1) % n
            if nxt == iq:
                break
            samples.append((nxt, acc))
            j = nxt
        return [pts[k] for k, dfwd in samples if dfwd > tp and (acc - dfwd) > tq]

    rounded_order = [i for i in order if i in blocks]
    out: list[Point] = []
    if not closed:
        # Leading free-end run: keep the start point and anything past the trim.
        head, acc = [], 0.0
        first_t = blocks[rounded_order[0]][0]
        for k in range(rounded_order[0] - 1, -1, -1):
            acc += seglen[k]
            if k == 0 or acc > first_t:
                head.append(pts[k])
        out.extend(reversed(head))
    for pos, i in enumerate(rounded_order):
        trim, arc = blocks[i]
        out.extend(arc)
        if closed or pos < len(rounded_order) - 1:
            nxt = rounded_order[(pos + 1) % len(rounded_order)]
            out.extend(run_interior(i, nxt, trim, blocks[nxt][0]))
    if not closed:
        acc, last_t = 0.0, blocks[rounded_order[-1]][0]
        for k in range(rounded_order[-1], n - 1):
            acc += seglen[k]
            if k + 1 == n - 1 or acc > last_t:
                out.append(pts[k + 1])
    return out, True


def _distance_to_polyline(point: Point, points: list[Point], closed: bool) -> float:
    if not points:
        return float("inf")
    if len(points) == 1:
        return _distance(point, points[0])
    segments = list(zip(points, points[1:]))
    if closed and len(points) > 2:
        segments.append((points[-1], points[0]))
    return min(_distance_to_segment(point, a, b) for a, b in segments)


def _distance_to_segment(point: Point, a: Point, b: Point) -> float:
    px, py = point
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return _distance(point, a)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return _distance(point, (ax + t * dx, ay + t * dy))


def _distance(a: Point, b: Point) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return (dx * dx + dy * dy) ** 0.5


def _point_in_polygon(point: Point, polygon: list[Point]) -> bool:
    px, py = point
    inside = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if _distance_to_segment(point, (xi, yi), (xj, yj)) <= 1e-9:
            return True
        crosses = (yi > py) != (yj > py)
        if crosses:
            x_at_y = (xj - xi) * (py - yi) / (yj - yi) + xi
            if px <= x_at_y:
                inside = not inside
        j = i
    return inside
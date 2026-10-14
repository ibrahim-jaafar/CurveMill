"""The .curvemill project file: a paused session, resumed later.

DXF export alone loses layers, board size and tool choice, so a session that
isn't finished in one sitting can't be picked back up. This is a plain JSON
document — the Library tab stores its entries in the same format.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .dimensions import Dimension, Feature, sync_dim_id_counter
from .models import Layer, SplineEntity, VectorEntity, sync_id_counter

FORMAT_VERSION = 1
SUFFIX = ".curvemill"


def _points(raw) -> list[tuple[float, float]]:
    # JSON has no tuples, and downstream geometry compares points for equality.
    return [(float(x), float(y)) for x, y in raw]


def _dump_dims(dim_store) -> list[dict]:
    # dim_store keys are frozensets of entity ids -- not valid JSON keys, so store
    # each group as {ids, dims}. asdict() flattens each Dimension's nested Features.
    return [
        {"ids": sorted(ids), "dims": [asdict(d) for d in dims]}
        for ids, dims in (dim_store or {}).items()
    ]


def _load_dims(raw) -> dict:
    store = {}
    for entry in raw:
        dims = []
        for d in entry["dims"]:
            d = dict(d)
            d["feat1"] = Feature(**d["feat1"])
            d["feat2"] = Feature(**d["feat2"])
            dims.append(Dimension(**d))
        store[frozenset(entry["ids"])] = dims
    return store


def serialize(
    vectors: list[VectorEntity],
    splines: list[SplineEntity],
    layers: list[Layer],
    active_layer: str,
    settings: dict,
    dim_store: dict | None = None,
) -> dict:
    """The full session as a JSON-ready dict. save() writes it; the app also hashes
    it to tell whether the session differs from the last save (Save-button greying)."""
    return {
        "format": FORMAT_VERSION,
        "vectors": [asdict(v) for v in vectors],
        # Drop flatten()'s private memo -- it is not geometry and load() rebuilds
        # SplineEntity(**data), which rejects the init=False cache field.
        "splines": [{k: v for k, v in asdict(s).items() if k != "_flat_cache"} for s in splines],
        "layers": [layer.to_dict() for layer in layers],
        "active_layer": active_layer,
        "settings": settings,
        "dimensions": _dump_dims(dim_store),
    }


def save(
    path: Path,
    vectors: list[VectorEntity],
    splines: list[SplineEntity],
    layers: list[Layer],
    active_layer: str,
    settings: dict,
    dim_store: dict | None = None,
) -> None:
    path = Path(path).with_suffix(SUFFIX)
    payload = serialize(vectors, splines, layers, active_layer, settings, dim_store)
    path.write_text(json.dumps(payload), encoding="utf-8")


def load(path: Path) -> tuple[list[VectorEntity], list[SplineEntity], list[Layer], str, dict, dict]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # ValueError covers JSONDecodeError
        raise ValueError("Couldn't read this file — it isn't a valid CurveMill project.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Couldn't read this file — it isn't a valid CurveMill project.")
    version = payload.get("format")
    if version != FORMAT_VERSION:
        raise ValueError(f"This project was saved by a different version of CurveMill (format {version}).")

    # Past the version gate the shape is trusted, but a hand-edited or truncated
    # file can still be missing keys or hold the wrong types -- turn the raw
    # KeyError/TypeError into a message the open-project dialog can show.
    try:
        vectors = []
        for data in payload["vectors"]:
            data["points"] = _points(data["points"])
            vectors.append(VectorEntity(**data))
        splines = []
        for data in payload["splines"]:
            data["control_points"] = _points(data["control_points"])
            data["fit_points"] = _points(data["fit_points"])
            splines.append(SplineEntity(**data))
        layers = [Layer.from_dict(data) for data in payload["layers"]]
        dim_store = _load_dims(payload.get("dimensions", []))
        active_layer = payload["active_layer"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("This CurveMill project is damaged, so it couldn't be opened.") from exc
    # Restored entities/dims keep their saved ids; push the process-global counters
    # past them so the next paste/draw/dimension can't re-mint a colliding id.
    sync_id_counter(vectors, splines)
    sync_dim_id_counter([d for dims in dim_store.values() for d in dims])
    return vectors, splines, layers, active_layer, payload.get("settings", {}), dim_store

"""COM bridge to a running SolidWorks install (CurveMill Phase B).

Every recipe here was measured in the Phase A spike -- see
docs/solidworks-com-api.md for the full story. The non-negotiables:

- Early binding via makepy wrappers + explicit QueryInterface (``cast``).
  Both ``gencache.EnsureDispatch`` and ``CastTo`` are broken for SolidWorks.
- Bulk sketch insertion needs all SIX flags, restored in ``finally``.
- Any call that opens a PropertyManager (sketch pictures) is async WebView UI:
  pump-messages settle delays around it or SolidWorks hard-crashes.
- The SW API is STA: call this module from the GUI thread only.
- Everything sent over COM is in METERS.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pythoncom
import win32com.client
from win32com.client import VARIANT

from .geometry import fit_vector_chains, join_spline_fragments, to_fit_splines
from .models import SplineEntity, VectorEntity


class BridgeError(RuntimeError):
    """A SolidWorks problem with a user-readable message."""


SW_TYPELIB_GUID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"  # stable across versions
NOTHING = VARIANT(pythoncom.VT_DISPATCH, None)  # VB Nothing for optional params
SW_SEL_FACES = 2
SW_SEL_DATUMPLANES = 4
PREVIEW_SKETCH = "CurveMill Preview"

# swEndCondition_e values for the T1 argument of FeatureCut4/FeatureExtrusion3.
END_CONDITIONS = {
    "Through All": 1,
    "Blind": 0,
    "Up To Next": 2,
    "Mid Plane": 6,
}

# One (kind, points, closed) tuple per curve; points in meters, board-center
# relative. kind "spline" -> fit-point spline, "line" -> polyline segments.
Curve = tuple[str, list[tuple[float, float]], bool]

_swmod_cache = None


def _swmod():
    """The makepy-generated typelib module; generated on first use per SW version."""
    global _swmod_cache
    if _swmod_cache is not None:
        return _swmod_cache
    from win32com.client import gencache

    def try_versions():
        # Typelib minor is 0; major tracks the SW release (2026 = 34).
        for major in range(45, 24, -1):
            try:
                return gencache.GetModuleForTypelib(SW_TYPELIB_GUID, 0, major, 0)
            except Exception:
                continue
        return None

    mod = try_versions()
    if mod is None:
        from win32com.client import makepy
        tlbs = sorted(Path("C:/Program Files/SOLIDWORKS Corp").glob("*/sldworks.tlb"))
        if not tlbs:
            raise BridgeError(
                "SolidWorks type library not found under C:\\Program Files\\SOLIDWORKS Corp -- "
                "is SolidWorks installed?"
            )
        makepy.GenerateFromTypeLibSpec(str(tlbs[-1]))
        mod = try_versions()
    if mod is None:
        raise BridgeError("Could not generate SolidWorks COM wrappers (makepy failed).")
    _swmod_cache = mod
    return mod


def cast(obj, iface: str):
    """Wrap a COM object in the pre-generated typed class for a SW interface."""
    try:
        cls = getattr(_swmod(), iface)
        disp = obj._oleobj_ if hasattr(obj, "_oleobj_") else obj
        try:
            disp = disp.QueryInterface(cls.CLSID, pythoncom.IID_IDispatch)
        except pythoncom.com_error:
            pass  # QI refused; the typed class may still work on the raw dispatch
        return cls(disp)
    except BridgeError:
        raise
    except Exception:
        return obj


def val(x):
    """Members sometimes surface as properties instead of methods; normalize."""
    return x() if callable(x) else x


def settle(seconds: float) -> None:
    """Let SW's async UI (WebView PropertyManagers) finish before the next call."""
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        pythoncom.PumpWaitingMessages()
        time.sleep(0.05)


@dataclass(slots=True)
class SWTarget:
    """A face/plane picked in SolidWorks, storable across the session."""
    kind: str                     # "face" | "plane"
    ref: tuple                    # GetPersistReference3 blob
    label: str                    # e.g. "Face of Boss-Extrude1"
    board_w_mm: float | None      # None for planes (size stays manual)
    board_h_mm: float | None
    thickness_mm: float | None    # body thickness along the face normal
    box: tuple | None             # face AABB in model meters, for centering


def _connect():
    pythoncom.CoInitialize()
    # GetActiveObject binds the already-running instance (it holds the user's
    # selection) but needs a ROT entry at our integrity level, which SolidWorks
    # doesn't always provide. Dispatch binds the running single-instance server
    # directly -- the path the Phase A spike used and verified -- so fall back to it.
    raw = None
    try:
        raw = win32com.client.GetActiveObject("SldWorks.Application")
    except pythoncom.com_error:
        try:
            raw = win32com.client.Dispatch("SldWorks.Application")
        except pythoncom.com_error as exc:
            raise BridgeError(
                "Could not connect to SolidWorks. Either it isn't running, or it and CurveMill "
                "are at different privilege levels -- if you started SolidWorks 'as administrator', "
                "start CurveMill the same way (or neither)."
            ) from exc
    sw = cast(raw, "ISldWorks")
    model = cast(sw.ActiveDoc, "IModelDoc2")
    if model is None or not hasattr(model, "SelectionManager"):
        raise BridgeError("No document is open in SolidWorks.")
    return sw, model


def get_selection() -> SWTarget:
    """Read the current SolidWorks selection into a persistable target."""
    sw, model = _connect()
    selmgr = cast(model.SelectionManager, "ISelectionMgr")
    if selmgr.GetSelectedObjectCount2(-1) < 1:
        raise BridgeError("Nothing is selected in SolidWorks -- click a planar face (or a plane) first.")
    sel_type = selmgr.GetSelectedObjectType3(1, -1)
    obj = selmgr.GetSelectedObject6(1, -1)
    ext = cast(model.Extension, "IModelDocExtension")

    if sel_type == SW_SEL_DATUMPLANES:
        try:
            label = f"Plane '{cast(obj, 'IFeature').Name}'"
        except Exception:
            label = "Plane"
        ref = tuple(val(ext.GetPersistReference3(obj)))
        return SWTarget("plane", ref, label, None, None, None, None)

    if sel_type != SW_SEL_FACES:
        raise BridgeError("The selection is not a face or a plane -- click a planar face of your board.")

    face = cast(obj, "IFace2")
    box = tuple(val(face.GetBox))
    ext_xyz = [box[3] - box[0], box[4] - box[1], box[5] - box[2]]
    # Drop the through-thickness axis (whichever the face normal points along) and
    # keep the other two in X<Y<Z order, so width=X-extent and height=Y-extent match
    # the model instead of always sorting the larger dimension into width.
    try:
        nabs = [abs(c) for c in list(val(face.Normal))[:3]]
        normal_axis = nabs.index(max(nabs))
    except Exception:
        normal_axis = ext_xyz.index(min(ext_xyz))
    in_plane = [ext_xyz[i] for i in range(3) if i != normal_axis]
    w_mm, h_mm = in_plane[0] * 1000.0, in_plane[1] * 1000.0

    thickness_mm = None
    try:
        n = list(val(face.Normal))[:3]
        body = cast(val(face.GetBody), "IBody2")
        bb = list(val(body.GetBodyBox))
        # AABB extent projected on the normal; exact for axis-aligned normals.
        thickness_mm = sum(abs(n[i]) * (bb[i + 3] - bb[i]) for i in range(3)) * 1000.0
    except Exception:
        pass

    try:
        label = f"Face of {cast(val(face.GetFeature), 'IFeature').Name}"
    except Exception:
        label = "Selected face"

    ref = tuple(val(ext.GetPersistReference3(face)))
    return SWTarget("face", ref, label, w_mm, h_mm, thickness_mm, box)


def _resolve(ext, target: SWTarget):
    """Persist-ref -> live entity, or None if the reference dangles."""
    attempts = [
        tuple(target.ref),
        VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_UI1,
                bytes(bytearray(b & 0xFF for b in target.ref))),
    ]
    for candidate in attempts:
        try:
            res = ext.GetObjectByPersistReference3(candidate, 0)
            obj = res[0] if isinstance(res, tuple) else res
            if obj is not None:
                return obj
        except Exception:
            continue
    return None


def _open_sketch_on(model, target: SWTarget):
    """Resolve the target, select it, and enter a sketch on it."""
    ext = cast(model.Extension, "IModelDocExtension")
    ent = _resolve(ext, target)
    if ent is None:
        raise BridgeError(
            "The stored SolidWorks face no longer resolves (the model changed too much) -- "
            "reselect the face in SolidWorks and click 'Get Board' again."
        )
    selmgr = cast(model.SelectionManager, "ISelectionMgr")
    model.ClearSelection2(True)
    sel_data = val(selmgr.CreateSelectData)
    cast(ent, "IEntity").Select4(False, sel_data)
    skm = cast(model.SketchManager, "ISketchManager")
    skm.InsertSketch(True)
    return skm


def _sketch_center(sw, model, box) -> tuple[float, float, bool]:
    """Face-box center in active-sketch coordinates; (0,0,False) if unavailable."""
    if box is None:
        return 0.0, 0.0, True  # plane: sketch origin is the natural anchor
    getters = (
        lambda: val(model.GetActiveSketch2),
        lambda: cast(model.SketchManager, "ISketchManager").ActiveSketch,
    )
    for getter in getters:
        try:
            sketch = cast(getter(), "ISketch")
            xform = val(sketch.ModelToSketchTransform)
            mu = cast(val(sw.GetMathUtility), "IMathUtility")
            cx = [(box[0] + box[3]) / 2, (box[1] + box[4]) / 2, (box[2] + box[5]) / 2]
            pt = mu.CreatePoint(VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, cx))
            arr = list(val(pt.MultiplyTransform(xform).ArrayData))
            return arr[0], arr[1], True
        except Exception:
            continue
    return 0.0, 0.0, False


def _locate_new_sketch(model):
    """The sketch feature send() just inserted, as (feature, name), or (None, None).

    Don't re-find the sketch by name from the tree -- SolidWorks leaves it
    SELECTED when InsertSketch(True) exits, so read the selected feature. That
    names/holds the sketch in whatever document it actually lives in, including
    an in-context component the active (assembly) doc's tree can't see. Fall back
    to scanning this doc's tree for the newest ProfileFeature (the standalone-
    part case); trailing folders -- 'Sensors', 'Annotations', bodies -- sort
    after it, so scan from the end, not just position 0."""
    try:
        selmgr = cast(model.SelectionManager, "ISelectionMgr")
        if selmgr.GetSelectedObjectCount2(-1) >= 1:
            feat = cast(selmgr.GetSelectedObject6(1, -1), "IFeature")
            if feat.GetTypeName2() == "ProfileFeature":
                return feat, feat.Name
    except Exception:
        pass
    for i in range(40):
        try:
            feat = model.FeatureByPositionReverse(i)
        except Exception:
            break
        if feat is None:
            break
        try:
            if feat.GetTypeName2() == "ProfileFeature":
                return feat, feat.Name
        except Exception:
            continue
    return None, None


def _no_sketch_message(model) -> str:
    """Guidance for the rare case where the sketch was drawn but can't be found."""
    try:
        is_assembly = model.GetType() == 2  # swDocASSEMBLY
    except Exception:
        is_assembly = False
    if is_assembly:
        return (
            "Drew the sketch but couldn't find it -- the active document is an ASSEMBLY. "
            "Send builds a sketch and feature on a PART. Open the part in its own window "
            "(right-click the component -> Open Part), pick the face there, Get Board, then Send."
        )
    return (
        "Drew the sketch but no sketch feature appeared in the tree -- the insertion may "
        "have failed. Reselect the face, Get Board, and Send again."
    )


def _select_sketch(model, feat, sketch_name: str) -> None:
    """Select the just-made sketch. Prefer the feature object (works in any
    document, including an in-context component); fall back to by-name."""
    model.ClearSelection2(True)
    try:
        if feat is not None and feat.Select2(False, 0):
            return
    except Exception:
        pass
    ext = cast(model.Extension, "IModelDocExtension")
    for callout in (NOTHING, None):  # the VB-Nothing quirk, with fallback
        try:
            if ext.SelectByID2(sketch_name, "SKETCH", 0, 0, 0, False, 0, callout, 0):
                return
        except Exception:
            continue
    raise BridgeError(f"Could not select sketch '{sketch_name}' in SolidWorks.")


def _fix_all_sketch_entities(model, ext, skm, curves, ox: float, oy: float) -> None:
    """Fix every drawn entity so the big sketch reads Fully Defined.

    Past ~2000 sketch entities SolidWorks turns its sketch solver off and the
    status degenerates to Over Defined / No Solve even with zero relations
    (measured on the real pattern: 0 relations, 0 dimensions, every segment
    under-constrained, sketch-level status OVER). Fixing everything leaves no
    degrees of freedom, so the status becomes Fully Defined and survives
    rebuilds -- the same remedy SolidWorks' own DXF import offers. SelectAll
    and MultiSelect2 never see sketch segments; SketchBoxSelect is the one
    bulk call that works, with a generous margin because a fitted spline
    bulges past its fit-point bbox.
    """
    xs = [p[0] + ox for _kind, pts, _closed in curves for p in pts]
    ys = [p[1] + oy for _kind, pts, _closed in curves for p in pts]
    skm.AutoSolve = False
    try:
        model.ClearSelection2(True)
        ext.SketchBoxSelect(min(xs) - 1.0, min(ys) - 1.0, 0.0,
                            max(xs) + 1.0, max(ys) + 1.0, 0.0)
        model.SketchAddConstraints("sgFIXED")
        model.ClearSelection2(True)
    finally:
        skm.AutoSolve = True


def _delete_preview_sketch(model) -> None:
    """Remove the 'CurveMill Preview' sketch if present (send/refresh replace it)."""
    try:
        ext = cast(model.Extension, "IModelDocExtension")
        # Walk the feature tree by name -- SelectByID2 alone misses renamed/nested sketches.
        feat = cast(val(model.FirstFeature), "IFeature")
        while feat is not None:
            nxt = val(feat.GetNextFeature)
            if val(feat.Name) == PREVIEW_SKETCH:
                model.ClearSelection2(True)
                if feat.Select2(False, 0):
                    ext.DeleteSelection2(0)
                    settle(0.5)
            feat = cast(nxt, "IFeature") if nxt is not None else None
    except Exception:
        pass


def curves_from_entities(
    vectors: list[VectorEntity],
    splines: list[SplineEntity],
    board_w: float,
    board_h: float,
    unit_scale: float,
    corner_degrees: float = 40.0,
) -> list[Curve]:
    """App geometry -> bridge curves: meters, re-centered on the board center.

    Runs the same Optimize-for-SolidWorks pipeline the button does -- join
    fragmented splines, fit loose line runs into corner-aware fit-point splines --
    so a segment-soup DXF collapses to one SW element per shape instead of
    thousands of raw lines. Without this a 7000-segment pattern drew 7000 lines in
    SolidWorks; SW element count == curve count here by construction.
    """
    cx, cy = board_w / 2.0, board_h / 2.0

    def m(p):
        return ((p[0] - cx) * unit_scale, (p[1] - cy) * unit_scale)

    # join_spline_fragments / to_fit_splines evaluate control points, so a spline
    # that is already fit-point-only (a whole shape) is passed straight through;
    # only control-point fragments get joined, and loose lines get fitted.
    frags = [s for s in splines if s.control_points]
    whole = [s for s in splines if s.fit_points and not s.control_points]
    optimized = join_spline_fragments(frags, corner_degrees=corner_degrees) + fit_vector_chains(vectors, corner_degrees=corner_degrees)
    curves: list[Curve] = []
    for s in list(to_fit_splines(optimized)) + whole:
        pts = list(s.fit_points)
        if s.closed and pts and pts[0] != pts[-1]:
            pts.append(pts[0])  # bit-identical seam so the refit closes
        if len(pts) >= 2:
            curves.append(("spline", [m(p) for p in pts], s.closed))
    return curves


def send(
    curves: list[Curve],
    target: SWTarget,
    feature: str = "cut",           # "cut" | "boss" | "sketch"
    end_condition: str = "Through All",
    depth_m: float = 0.01,
    flip: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> str:
    """Draw the curves in a new sketch on the target and apply the chosen feature."""
    if not curves:
        raise BridgeError("Nothing to send -- no visible geometry.")
    sw, model = _connect()
    _delete_preview_sketch(model)  # real geometry replaces the picture preview
    skm = _open_sketch_on(model, target)
    ox, oy, centered = _sketch_center(sw, model, target.box)
    view = cast(model.ActiveView, "IModelView")

    t0 = time.perf_counter()
    try:
        # The six-flag bulk recipe: 4.5 ms/spline vs 224 ms with AddToDB alone.
        skm.AddToDB = True
        skm.DisplayWhenAdded = False
        view.EnableGraphicsUpdate = False
        sw.CommandInProgress = True
        skm.AutoSolve = False
        skm.AutoInference = False
        for i, (kind, pts, closed) in enumerate(curves):
            if kind == "spline":
                flat: list[float] = []
                for x, y in pts:
                    flat += [x + ox, y + oy, 0.0]
                skm.CreateSpline(VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, flat))
            else:
                seq = pts + [pts[0]] if closed else pts
                for a, b in zip(seq, seq[1:]):
                    skm.CreateLine(a[0] + ox, a[1] + oy, 0.0, b[0] + ox, b[1] + oy, 0.0)
            if progress is not None and (i + 1) % 25 == 0:
                progress(i + 1, len(curves))
    finally:
        skm.AutoInference = True
        skm.AutoSolve = True
        sw.CommandInProgress = False
        skm.AddToDB = False
        skm.DisplayWhenAdded = True
        view.EnableGraphicsUpdate = True
    draw_s = time.perf_counter() - t0
    try:
        ext = cast(model.Extension, "IModelDocExtension")
        _fix_all_sketch_entities(model, ext, skm, curves, ox, oy)
    except Exception:
        pass  # best effort -- an unfixed sketch still cuts, it just isn't fully defined
    skm.InsertSketch(True)  # exit the sketch

    sketch_feat, sketch_name = _locate_new_sketch(model)
    if sketch_feat is None:
        raise BridgeError(_no_sketch_message(model))
    origin_note = "" if centered else " (drawn at the sketch origin -- face-centering transform unavailable)"

    if feature == "sketch":
        _select_sketch(model, sketch_feat, sketch_name)
        model.BlankSketch()  # a visible unconsumed sketch is the slow case
        return (f"Sketch '{sketch_name}' inserted and hidden "
                f"({len(curves)} curves in {draw_s:.1f}s){origin_note}")

    _select_sketch(model, sketch_feat, sketch_name)
    t1v = END_CONDITIONS[end_condition]
    feat_mgr = cast(model.FeatureManager, "IFeatureManager")
    t0 = time.perf_counter()
    if feature == "cut":
        result = feat_mgr.FeatureCut4(
            True, flip, False, t1v, 0, depth_m, 0.01,
            False, False, False, False, 0.0, 0.0,
            False, False, False, False,
            False, True, True, True, True, False,
            0, 0.0, False, False)
    else:
        result = feat_mgr.FeatureExtrusion3(
            True, flip, False, t1v, 0, depth_m, 0.01,
            False, False, False, False, 0.0, 0.0,
            False, False, False, False,
            True, True, True, 0, 0.0, False)
    feat_s = time.perf_counter() - t0
    if result is None:
        raise BridgeError(
            "SolidWorks rejected the feature. Common causes: open profiles in the pattern, "
            "or (on a plane) an extrusion that reaches no material -- try 'Flip direction'."
        )
    name = getattr(result, "Name", "feature")
    return (f"'{name}' created in {feat_s:.1f}s "
            f"({len(curves)} curves drawn in {draw_s:.1f}s via '{sketch_name}'){origin_note}")


def insert_preview(png_path: str, target: SWTarget, w_m: float, h_m: float) -> str:
    """Replace the 'CurveMill Preview' sketch picture on the target face.

    Slow by design: the picture PropertyManager is an async WebView; every call
    around it needs a settle-pump delay or SolidWorks access-violates.
    """
    sw, model = _connect()
    _delete_preview_sketch(model)
    skm = _open_sketch_on(model, target)
    ox, oy, _centered = _sketch_center(sw, model, target.box)
    pic = cast(skm.InsertSketchPicture(str(png_path)), "ISketchPicture")
    settle(2.0)
    if pic is None:
        skm.InsertSketch(True)
        raise BridgeError("SolidWorks could not insert the preview picture.")
    pic.SetSize(w_m, h_m, False)
    settle(1.0)
    pic.SetTransparency(1, 0, 0.0, 0.0)  # 1 = use the PNG's alpha channel
    settle(1.0)
    try:
        pic.SetOrigin(ox - w_m / 2.0, oy - h_m / 2.0)
        settle(1.0)
    except Exception:
        pass  # picture stays anchored at the sketch origin
    skm.InsertSketch(True)
    settle(2.0)
    try:
        # Untyped dispatch loses the Name setter -- must cast (Phase A lesson).
        cast(model.FeatureByPositionReverse(0), "IFeature").Name = PREVIEW_SKETCH
    except Exception:
        pass
    return "Preview picture placed in SolidWorks (sketch 'CurveMill Preview')."

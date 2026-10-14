"""Phase A spike: prove the SolidWorks COM bridge end to end. THROWAWAY script.

Run with SolidWorks open, a PART document active, and ONE PLANAR FACE selected:

    uv run --with pywin32 --with pillow python sw_spike_phase_a.py

Later (after editing other features for ~10 min), re-check the persistent ref:

    uv run --with pywin32 python sw_spike_phase_a.py resolve

What it proves (plan section 4, Phase A steps 1-8):
  1. Connect to the running SolidWorks; report version.
  2. Read selection -> IFace2, GetBox -> board size + body thickness along normal.
  3. GetPersistReference3 -> saved to sw_spike_persist.pkl ('resolve' mode re-checks).
  4. InsertSketch + AddToDB/DisplayWhenAdded/EnableGraphicsUpdate bulk fast path.
  5. PROBE: do 540 API-created fit-point splines count as 540 sketch segments (1 each)?
  6. Time the 540 splines, then FeatureCut4 through-all.
  7. pythoncom Nothing quirk handled in SelectByID2.
  8. InsertSketchPicture with a transparent PNG -> eyeball orientation/flip.

The script leaves the cut feature + a preview sketch in the model on purpose --
inspect them, then undo/delete. Everything is in METERS (SW API convention).
"""

import math
import pickle
import sys
import time
from pathlib import Path

import pythoncom
import win32com.client
from win32com.client import VARIANT

HERE = Path(__file__).resolve().parent
PERSIST_FILE = HERE / "sw_spike_persist.pkl"
PNG_FILE = HERE / "sw_spike_preview.png"

SW_SEL_FACES = 2
SW_SEL_DATUMPLANES = 4
SPLINE_COUNT = 540
GRID_COLS, GRID_ROWS = 27, 20

# VB 'Nothing' for optional IDispatch params (the known pywin32 quirk).
NOTHING = VARIANT(pythoncom.VT_DISPATCH, None)

RESULTS: list[tuple[str, str]] = []


def report(step: str, ok: bool, detail: str = "") -> None:
    tag = "PASS" if ok else "FAIL"
    RESULTS.append((step, tag))
    print(f"[{tag}] {step}" + (f" -- {detail}" if detail else ""))


def val(x):
    """Dynamic dispatch sometimes exposes methods as properties; normalize."""
    return x() if callable(x) else x


def settle(seconds: float) -> None:
    """Let SW's UI (async WebView PropertyManager) finish before the next call."""
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        pythoncom.PumpWaitingMessages()
        time.sleep(0.05)


# SW 2026 typelib (sldworks.tlb) = version 34.0; regenerate + adjust for other
# versions. win32com.client.CastTo can't be used: it falls back to the same
# GetTypeInfo path SW doesn't implement, and silently leaves objects dynamic.
SW_TYPELIB = ("{83A33D31-27C5-11CE-BFD4-00400513BB57}", 0, 34, 0)
_swmod = None


def swmod():
    global _swmod
    if _swmod is None:
        from win32com.client import gencache
        _swmod = gencache.GetModuleForTypelib(*SW_TYPELIB)
    return _swmod


def cast(obj, iface: str):
    """Wrap a COM object in the pre-generated typed class for a SW interface."""
    try:
        cls = getattr(swmod(), iface)
        disp = obj._oleobj_ if hasattr(obj, "_oleobj_") else obj
        try:
            disp = disp.QueryInterface(cls.CLSID, pythoncom.IID_IDispatch)
        except pythoncom.com_error:
            pass  # QI refused; try invoking through the object's own dispatch
        return cls(disp)
    except Exception:
        return obj


def connect():
    # SW's IDispatch can't automate makepy (GetTypeInfo -> 'Element not found'),
    # so typed wrappers must be pre-generated once from the typelib:
    #   uv run python -m win32com.client.makepy "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"
    # After that, cast() below early-binds each object to its real interface --
    # dynamic dispatch alone loses members (GetBody, CreateSpline, ...).
    sw = cast(win32com.client.Dispatch("SldWorks.Application"), "ISldWorks")
    sw.Visible = True
    rev = val(sw.RevisionNumber)
    report("1. Connect", True, f"SolidWorks revision {rev}")
    model = cast(sw.ActiveDoc, "IModelDoc2")
    if model is None:
        report("1. Active document", False, "no document open")
        sys.exit(1)
    return sw, model


def get_selected_face(model):
    selmgr = cast(model.SelectionManager, "ISelectionMgr")
    count = selmgr.GetSelectedObjectCount2(-1)
    if count < 1:
        report("2. Selection", False, "nothing selected -- click a planar face first")
        sys.exit(1)
    sel_type = selmgr.GetSelectedObjectType3(1, -1)
    obj = selmgr.GetSelectedObject6(1, -1)
    if sel_type == SW_SEL_DATUMPLANES:
        report("2. Selection", True, "a PLANE is selected (no GetBox; size stays manual)")
        return None, selmgr
    if sel_type != SW_SEL_FACES:
        report("2. Selection", False, f"selected type {sel_type}, expected face ({SW_SEL_FACES})")
        sys.exit(1)
    report("2. Selection", True, "face selected")
    return cast(obj, "IFace2"), selmgr


def probe_face_box(face):
    box = list(val(face.GetBox))
    ext = [box[3] - box[0], box[4] - box[1], box[5] - box[2]]
    try:
        n = list(val(face.Normal))[:3]
    except Exception:
        n = [0.0, 0.0, 1.0]
        print("      (face.Normal failed -- assuming Z; is the face planar?)")
    # In-plane board size: the two largest AABB extents.
    dims = sorted(ext, reverse=True)
    w, h = dims[0], dims[1]
    report("2. GetBox", True, f"board {w * 1000:.1f} x {h * 1000:.1f} mm, normal {tuple(round(c, 3) for c in n)}")
    thickness = None
    try:
        body = cast(val(face.GetBody), "IBody2")
        bb = list(val(body.GetBodyBox))
        # AABB extent projected on the normal; exact for axis-aligned normals.
        thickness = sum(abs(n[i]) * (bb[i + 3] - bb[i]) for i in range(3))
        report("2. Body thickness", True, f"{thickness * 1000:.2f} mm along face normal")
    except Exception as exc:
        report("2. Body thickness", False, repr(exc))
    return w, h, box, thickness


def save_persist_ref(model, face):
    try:
        ext = cast(model.Extension, "IModelDocExtension")
        ref = val(ext.GetPersistReference3(face))
        PERSIST_FILE.write_bytes(pickle.dumps(tuple(ref)))
        report("3. Persist ref", True, f"{len(tuple(ref))} bytes -> {PERSIST_FILE.name}; run 'resolve' mode after editing a while")
    except Exception as exc:
        report("3. Persist ref", False, repr(exc))


def resolve_persist_ref():
    sw = win32com.client.Dispatch("SldWorks.Application")
    model = cast(sw.ActiveDoc, "IModelDoc2")
    ext = cast(model.Extension, "IModelDocExtension")
    ref = pickle.loads(PERSIST_FILE.read_bytes())
    attempts = [
        tuple(ref),
        VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_UI1, bytes(bytearray(b & 0xFF for b in ref))),
    ]
    for candidate in attempts:
        try:
            res = ext.GetObjectByPersistReference3(candidate, 0)
            obj = res[0] if isinstance(res, tuple) else res
            if obj is not None:
                obj = cast(obj, "IFace2")
                box = list(val(obj.GetBox))
                report("3. Persist ref resolves", True, f"GetBox still works, x-extent {(box[3] - box[0]) * 1000:.1f} mm")
                return
        except Exception as exc:
            print(f"      resolve attempt failed: {exc!r}")
    report("3. Persist ref resolves", False, "reference dangling or marshaling mismatch")


def blob_points(cx: float, cy: float, r: float) -> list[float]:
    """One closed wavy blob as a flat [x,y,z,...] fit-point list (first==last)."""
    pts: list[float] = []
    n = 8
    for i in range(n + 1):  # +1 repeats the first point -> closed profile
        a = 2.0 * math.pi * (i % n) / n
        rr = r * (1.0 + 0.15 * math.sin(3.0 * a))
        pts += [cx + rr * math.cos(a), cy + rr * math.sin(a), 0.0]
    return pts


def sketch_center_of(model, sw, box):
    """Face-box center mapped into sketch space; (0,0) if the math plumbing balks."""
    try:
        sketch = cast(cast(model.SketchManager, "ISketchManager").ActiveSketch, "ISketch")
        xform = val(sketch.ModelToSketchTransform)
        mu = cast(val(sw.GetMathUtility), "IMathUtility")
        cx = [(box[0] + box[3]) / 2, (box[1] + box[4]) / 2, (box[2] + box[5]) / 2]
        pt = mu.CreatePoint(VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, cx))
        pt2 = pt.MultiplyTransform(xform)
        arr = list(val(pt2.ArrayData))
        return arr[0], arr[1]
    except Exception as exc:
        print(f"      (ModelToSketchTransform path failed: {exc!r} -- drawing around sketch origin)")
        return 0.0, 0.0


def bulk_splines_and_cut(sw, model, face, selmgr, w, h, box):
    # Re-select the face (reading probes may have disturbed selection).
    sel_data = val(selmgr.CreateSelectData)
    cast(face, "IEntity").Select4(False, sel_data)
    skm = cast(model.SketchManager, "ISketchManager")
    skm.InsertSketch(True)

    view = cast(model.ActiveView, "IModelView")
    skm.AddToDB = True
    skm.DisplayWhenAdded = False
    view.EnableGraphicsUpdate = False
    # Round-4 speedups: first run took 224 ms/spline with AddToDB alone.
    sw.CommandInProgress = True   # stop SW idle processing between API calls
    skm.AutoSolve = False         # no sketch re-solve per entity
    skm.AutoInference = False     # no relation inference per entity
    print(f"      (AddToDB reads back as {skm.AddToDB}, AutoSolve {skm.AutoSolve}, AutoInference {skm.AutoInference})")

    ox, oy = sketch_center_of(model, sw, box)
    span_w, span_h = w * 0.8, h * 0.8
    cell = min(span_w / GRID_COLS, span_h / GRID_ROWS)
    r = cell * 0.35
    made = 0
    t0 = time.perf_counter()
    try:
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                if made >= SPLINE_COUNT:
                    break
                cx = ox + (col - (GRID_COLS - 1) / 2) * cell
                cy = oy + (row - (GRID_ROWS - 1) / 2) * cell
                pts = blob_points(cx, cy, r)
                seg = skm.CreateSpline(VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, pts))
                if seg is not None:
                    made += 1
        elapsed = time.perf_counter() - t0
    finally:
        skm.AutoInference = True
        skm.AutoSolve = True
        sw.CommandInProgress = False
        skm.AddToDB = False
        skm.DisplayWhenAdded = True
        view.EnableGraphicsUpdate = True

    report("4. Bulk CreateSpline", made == SPLINE_COUNT,
           f"{made}/{SPLINE_COUNT} splines in {elapsed:.2f}s ({elapsed / max(made, 1) * 1000:.1f} ms each)")

    # 5. THE PROBE: one API fit-point spline == one sketch segment?
    try:
        segs = val(cast(skm.ActiveSketch, "ISketch").GetSketchSegments)
        n_segs = len(segs) if segs is not None else 0
        report("5. Fit-point count rule", n_segs == made,
               f"{n_segs} sketch segments for {made} splines "
               + ("(rule HOLDS on the API path)" if n_segs == made else "(RULE BROKEN -- investigate!)"))
    except Exception as exc:
        report("5. Fit-point count rule", False, repr(exc))

    skm.InsertSketch(True)  # exit sketch

    # 6. Through-all cut on that sketch.
    try:
        feat = model.FeatureByPositionReverse(0)
        sketch_name = feat.Name
        model.ClearSelection2(True)
        ok = False
        ext = cast(model.Extension, "IModelDocExtension")
        for callout in (NOTHING, None):  # step 7: the Nothing quirk, with fallback
            try:
                ok = ext.SelectByID2(sketch_name, "SKETCH", 0, 0, 0, False, 0, callout, 0)
                break
            except Exception:
                continue
        if not ok:
            raise RuntimeError(f"could not select sketch '{sketch_name}'")
        t0 = time.perf_counter()
        # Args per 2024 API docs: single-ended, no flip, default dir, T1=ThroughAll(1),
        # T2=Blind(0), depths, no draft, no offset/translate, not sheet-metal-normal-cut,
        # feature-scope defaults, T0=FromSketchPlane(0).
        cut = cast(model.FeatureManager, "IFeatureManager").FeatureCut4(
            True, False, False, 1, 0, 0.01, 0.01,
            False, False, False, False, 0.0, 0.0,
            False, False, False, False,
            False, True, True, True, True, False,
            0, 0.0, False, False)
        elapsed = time.perf_counter() - t0
        report("6. FeatureCut4 through-all", cut is not None,
               f"'{getattr(cut, 'Name', '?')}' in {elapsed:.2f}s" if cut is not None else "returned None -- check open profiles / material overlap")
    except Exception as exc:
        report("6. FeatureCut4 through-all", False, repr(exc))


def make_test_png(alpha: bool = True):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        report("8. InsertSketchPicture", False, "Pillow not installed -- rerun with: uv run --with pillow python sw_spike_phase_a.py")
        return False

    img = Image.new("RGBA", (400, 300), (0, 0, 0, 0) if alpha else (255, 255, 255, 255))
    d = ImageDraw.Draw(img)
    # A big letter F (flip-revealing), red square top-left, blue dot bottom-right.
    d.rectangle([60, 40, 100, 260], fill=(30, 30, 30, 255))
    d.rectangle([100, 40, 240, 80], fill=(30, 30, 30, 255))
    d.rectangle([100, 130, 200, 170], fill=(30, 30, 30, 255))
    d.rectangle([10, 10, 50, 50], fill=(220, 40, 40, 255))
    d.ellipse([340, 240, 390, 290], fill=(40, 80, 220, 255))
    if not alpha:
        img = img.convert("RGB")  # drop the alpha channel entirely
    img.save(PNG_FILE)
    return True


def insert_preview_picture(sw, model, face, selmgr, w, h, opts=frozenset()):
    """Bisect flags (append after 'picture'): opaque no-size no-trans small"""
    try:
        if not make_test_png(alpha="opaque" not in opts):
            return
        sel_data = val(selmgr.CreateSelectData)
        cast(face, "IEntity").Select4(False, sel_data)
        skm = cast(model.SketchManager, "ISketchManager")
        skm.InsertSketch(True)
        # Manual insert works; API insert crashes -> race with the async WebView
        # PropertyManager init (SW2026). Give SW settle time between every call.
        pic = cast(skm.InsertSketchPicture(str(PNG_FILE)), "ISketchPicture")
        settle(2.0)
        if pic is None:
            raise RuntimeError("InsertSketchPicture returned None")
        if "no-size" in opts:
            print("      picture inserted; leaving native size...")
        else:
            if "small" in opts:
                w, h = 0.4, 0.3  # 400x300 mm regardless of board
            print(f"      picture inserted; sizing to {w:.2f} x {h:.2f} m...")
            try:
                pic.SetSize(w, h, False)
            except Exception as exc:
                print(f"      (SetSize failed: {exc!r})")
            settle(1.0)
        if "no-trans" in opts:
            print("      skipping transparency...")
        else:
            print("      setting transparency...")
            try:
                pic.SetTransparency(1, 0, 0.0, 0.0)  # 1 = from-file (PNG alpha)
            except Exception as exc:
                print(f"      (SetTransparency failed: {exc!r} -- note whether the background shows white)")
            settle(1.0)
        print("      exiting sketch...")
        skm.InsertSketch(True)
        settle(2.0)
        report("8. InsertSketchPicture", True,
               "EYEBALL IT: 'F' readable (not mirrored)? red square top-left? background transparent?")
    except Exception as exc:
        report("8. InsertSketchPicture", False, repr(exc))


def main():
    pythoncom.CoInitialize()
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    if mode == "resolve":
        if not PERSIST_FILE.exists():
            print("No sw_spike_persist.pkl yet -- run the full spike first.")
            sys.exit(1)
        resolve_persist_ref()
    elif mode == "picture":
        # Step 8 in isolation -- it crashed SW once, so it runs alone now.
        sw, model = connect()
        face, selmgr = get_selected_face(model)
        if face is None:
            sys.exit(0)
        w, h, _box, _thickness = probe_face_box(face)
        insert_preview_picture(sw, model, face, selmgr, w, h, opts=frozenset(sys.argv[2:]))
    else:
        sw, model = connect()
        face, selmgr = get_selected_face(model)
        if face is None:
            print("Plane flow confirmed selectable; re-run with a FACE selected for the rest.")
            sys.exit(0)
        w, h, box, _thickness = probe_face_box(face)
        save_persist_ref(model, face)
        bulk_splines_and_cut(sw, model, face, selmgr, w, h, box)
        print("\nStep 8 (sketch picture) is now separate -- run:  python sw_spike_phase_a.py picture")

    print("\n=== SUMMARY ===")
    for step, tag in RESULTS:
        print(f"  {tag}  {step}")
    print("\nThe cut feature and preview sketch were left in the model on purpose -- inspect, then undo/delete.")


if __name__ == "__main__":
    main()

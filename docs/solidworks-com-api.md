# Automating SolidWorks from Python over COM

Field notes from the Phase A bridge spike (`sw_spike_phase_a.py`), run 2026-07-18/19
against a real install. Everything below was measured or crash-tested, not read from
documentation — SolidWorks documents almost none of it.

**Environment (version matters — re-verify on other installs):**

| Component | Version |
|---|---|
| SOLIDWORKS | 2026 SP2.1 — `ISldWorks.RevisionNumber` = 34.2.1, typelib v34.0 |
| Typelib GUID | `{83A33D31-27C5-11CE-BFD4-00400513BB57}` (sldworks.tlb) |
| Python / pywin32 | 3.14 / pywin32 312 |
| OS | Windows 11 build 26200, dual monitors at mixed DPI (120 / 96) |
| GPU | NVIDIA RTX 3050 Ti (laptop) |

---

## The short version

1. **Early binding is mandatory and the normal pywin32 routes to it are both broken**
   for SolidWorks — run `makepy` on `sldworks.tlb` yourself and wrap objects in the
   generated classes with an explicit `QueryInterface`.
2. **Bulk sketch insertion needs six flags, not two.** The documented pair
   (`AddToDB` + `DisplayWhenAdded`) still costs 224 ms/spline; adding
   `CommandInProgress` + `AutoSolve=False` + `AutoInference=False` +
   `EnableGraphicsUpdate=False` gets **4.5 ms/spline** — a 50× speedup.
3. **`InsertSketchPicture` crashes SolidWorks if you call the next API too soon.**
   The picture PropertyManager is an async WebView; racing it is an access violation.
   Pump-messages settle delays after every picture-related call fix it completely.
4. The fit-point count rule from `solidworks-dxf-import.md` **holds on the sketch-API
   path**: 540 `CreateSpline` fit-point splines = 540 sketch segments.

---

## 1. Early binding: both standard routes fail (one silently)

SolidWorks' `IDispatch` does **not** implement `GetTypeInfo`. Consequences:

- `win32com.client.gencache.EnsureDispatch("SldWorks.Application")` raises
  *"This COM object can not automate the makepy process"*.
- `win32com.client.CastTo(obj, "IFace2")` **fails silently** — it internally relies on
  the same machinery, so you get back a *dynamic* dispatch object that looks alive but
  is missing members. This is the dangerous one.

Symptoms of accidentally-dynamic objects (all observed):

- `IFace2.GetBody` → `com_error: Member not found.`
- `ISketchManager.CreateSpline` resolves as a *property* returning `None` →
  `TypeError: 'NoneType' object is not callable`.
- `IModelDoc2.ModelToSketchTransform` → `Member not found.`
- `ISldWorks.GetMathUtility` fails until `sw` itself is wrapped typed.

### The fix

Generate the wrappers once, directly from the typelib file (per SW version):

```
python -m win32com.client.makepy "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"
```

Output lands in `%TEMP%\gen_py\<pyver>\` (e.g. `gen_py\3.14\`). Then construct typed
wrappers by hand — do not use `CastTo`:

```python
SW_TYPELIB = ("{83A33D31-27C5-11CE-BFD4-00400513BB57}", 0, 34, 0)  # SW 2026

def swmod():
    from win32com.client import gencache
    return gencache.GetModuleForTypelib(*SW_TYPELIB)

def cast(obj, iface: str):
    """Wrap a COM object in the pre-generated typed class for a SW interface."""
    cls = getattr(swmod(), iface)
    disp = obj._oleobj_ if hasattr(obj, "_oleobj_") else obj
    try:
        disp = disp.QueryInterface(cls.CLSID, pythoncom.IID_IDispatch)
    except pythoncom.com_error:
        pass  # some SW objects reject the QI but still work with the typed class
    return cls(disp)
```

A shipped bridge must automate the makepy step at first run, keyed to the detected SW
version (the typelib version changes per release — 2026 is v34.0).

### Related gotchas

- **`Select4` lives on `IEntity`, not `IFace2`** — `cast(face, "IEntity").Select4(...)`.
- Some members surface as **properties instead of methods** depending on wrapper state;
  a tiny `val(x)` normalizer (`return x() if callable(x) else x`) absorbs both.
- VB `Nothing` arguments (e.g. the callout in `SelectByID2`) — pass
  `VARIANT(pythoncom.VT_DISPATCH, None)`, with plain `None` as fallback.
- Spline fit points go in as `VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, flat_xyz_list)`.
- The SW API is **STA**: every call serializes onto SolidWorks' main thread. Keep all
  parallelism in your own process; never call SW from worker threads.

---

## 2. Bulk sketch insertion: the six-flag recipe (50× measured)

Drawing 540 closed 8-fit-point splines into one sketch:

| Flags set | Per spline | Total (540) |
|---|---|---|
| `AddToDB` + `DisplayWhenAdded=False` + `EnableGraphicsUpdate=False` | 224 ms | 121 s |
| + `CommandInProgress` + `AutoSolve=False` + `AutoInference=False` | **4.5 ms** | **2.43 s** |

The commonly documented `AddToDB` fast path is nowhere near enough by itself. All six:

```python
skm.AddToDB = True                 # ISketchManager — skip inference/snapping DB work
skm.DisplayWhenAdded = False       # ISketchManager — no per-entity redraw
view.EnableGraphicsUpdate = False  # IModelView
sw.CommandInProgress = True        # ISldWorks — suppresses per-call idle processing
skm.AutoSolve = False              # ISketchManager — defer constraint solving
skm.AutoInference = False          # ISketchManager
```

**Restore every one of them in a `finally` block** — leaving `CommandInProgress` or
`AutoSolve` stuck ruins the user's session long after your code exits.

Other timings on the same 540-profile sketch:
- `IFeatureManager.FeatureCut4` through-all: **6.0–6.8 s**.
- End-to-end "send & cut" (draw + cut): **≈ 9 s**.

`FeatureCut4` call that worked (27 args; `T1=1` = ThroughAll, `T0=0` = FromSketchPlane):

```python
feat.FeatureCut4(True, False, False, 1, 0, 0.01, 0.01, False, False, False, False,
                 0.0, 0.0, False, False, False, False, False, True, True, True, True,
                 False, 0, 0.0, False, False)
```

Selecting the sketch for the cut: get its name via
`model.FeatureByPositionReverse(0).Name`, then
`ext.SelectByID2(name, "SKETCH", 0, 0, 0, False, 0, callout, 0)`.

---

## 3. Fit-point count rule holds on the API path

The DXF-import rule (see `solidworks-dxf-import.md`: fit-point spline = exactly 1
element) was measured on the *import* path only. Verified 2026-07-18 on the *sketch API*
path: 540 fit-point `CreateSpline` calls → `ISketch.GetSketchSegments` returns exactly
**540**. Element-count parity between the app and SolidWorks carries over to direct
drawing — no DXF round-trip needed.

---

## 4. `InsertSketchPicture`: the crash, the root cause, the fix

**Symptom:** SolidWorks hard-crashed (access violation) 5 runs in a row, at or shortly
after `InsertSketchPicture` + `SetSize`/`SetTransparency`/`InsertSketch(True)`.

**What it wasn't** (each ruled out by a bisect run): picture content (crashed with RGBA
and RGB), image size (crashed at 300 mm and 28 m board scale), the `SetTransparency`
call, the `SetSize` call, `CommandInProgress` wrapping. Manual insertion of the *same
PNG* through the UI worked perfectly — which isolated the difference to **timing**.

**Root cause (from the SW crash log):** `InsertSketchPicture` opens the Sketch Picture
PropertyManager, which since SW 2026 is a **WebView-hosted dialog**
(`srfuiSketchBitmapPropertyDialog_c`) that initializes *asynchronously*. Firing the next
API call milliseconds later — especially exiting the sketch, which tears the sketch down
under the still-initializing dialog — dies with an access violation in `sldJsu` /
`EmbeddedBrowserWebView`. (Machine ran mixed-DPI dual monitors, which may aggravate the
WebView path, but the race is the cause.)

**The fix — human-paced settle delays that pump the message loop** (a plain
`time.sleep` starves the WebView; you must pump):

```python
def settle(seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        pythoncom.PumpWaitingMessages()
        time.sleep(0.05)

pic = skm.InsertSketchPicture(png_path); settle(2.0)
pic.SetSize(w, h, False);               settle(1.0)
pic.SetTransparency(1, 0, 0.0, 0.0);    settle(1.0)  # style 1 = use PNG alpha
model.InsertSketch(True);               settle(2.0)
```

With the delays: zero crashes, and verified behavior —

- **Image ↔ sketch axes are 1:1** — no flip or mirror (an "F" stays readable; a marker
  in the image's top-left lands at the sketch's top-left).
- `SetTransparency(1, ...)` honors **PNG alpha** as true transparency.
- The picture anchors at the **sketch origin**, not the face center — center it with
  `ISketchPicture.SetOrigin` using the face-box center pushed through
  `ModelToSketchTransform`.

**General lesson for any SW automation:** treat every call that opens a
PropertyManager/UI as async. Settle-pump around it, prompt the user to save before heavy
operations, catch dead-COM errors, and offer a reconnect path.

---

## 5. Odds and ends (all measured)

- `IFace2.GetBox` returns the face bounding box in meters (board 2667.1 × 1700.0 mm
  read correctly); body thickness is measurable by ray-walking the owning body's box
  along the face normal (10.00 mm verified).
- `IModelDocExtension.GetPersistReference3` on a face returned a 389-byte blob and
  resolved successfully later in the session (after the cut feature, preview sketch,
  and saves) — persistent references work as a face-storage mechanism. Note: for a
  face whose normal is an axis (e.g. (1,0,0)), `GetBox` legitimately reports zero
  extent along that axis.
- `Dispatch("SldWorks.Application")` binds the registered default install;
  version-suffixed ProgIDs (`SldWorks.Application.NN`) select a specific one.
- Deleting a named sketch (Phase B live testing, cause not fully bisected — two fixes
  landed together and the app may not have been restarted between tests): the robust
  recipe is to **walk the feature tree** (`FirstFeature`/`GetNextFeature`, cast each to
  `IFeature`) and `Select2` the matching feature object, rather than trusting
  `SelectByID2(name, "SKETCH", ...)`, which returned False for the preview sketch on at
  least one run. Also cast to `IFeature` before assigning `.Name =` — a property *setter*
  on a dynamic dispatch object can silently store on the Python wrapper instead of
  reaching SolidWorks (same failure family as §1's missing members).

## Version caveat

Everything here was measured on **one install** (SW 2026 SP2.1). The typelib GUID has
been stable for decades but its *version* changes per release; the WebView
PropertyManager (and therefore the crash + settle-delay requirement) is new-ish UI
architecture that may change again. Re-run `sw_spike_phase_a.py` (or its successor
checks) against any new SolidWorks version before trusting these numbers there.

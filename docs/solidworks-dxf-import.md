# How SolidWorks Counts DXF Sketch Elements

Field notes from a probe campaign run on 2026-07-16 against a real SolidWorks install.
Everything below marked *measured* was confirmed by importing a purpose-built DXF and
reading the count off `Select All` → `Show Selection`. Nothing here is inferred from
documentation — SolidWorks documents none of this.

The context was CurveMill's "Optimize for SolidWorks" feature, but the rules are
generic: they apply to any tool that emits DXF for SolidWorks import.

---

## The short version

**A fit-point SPLINE always imports as exactly one sketch element, no matter how many
segments, corners, or curvature breaks it contains.** A control-point SPLINE gets split at
every joint that is not *bit-exactly* tangent-continuous.

If you control the exporter and you care about element count, write fit-point splines.
That one line is the entire payoff of this investigation.

---

## The problem that started it

A pattern file (`path545.dxf`, exported from Inkscape) contained 3383 SPLINE entities —
540 real shapes, each fragmented into one SPLINE per bezier segment. We joined the
fragments losslessly into 540 multi-segment control-point splines and exported.

- Our app said: **540 entities**.
- SolidWorks said: **2990 elements**.

Same file. The mismatch is not a bug in either tool — it is SolidWorks *splitting entities
on import* according to rules we had to reverse-engineer.

## The rules (measured)

| Behaviour | Verdict | Probes |
|---|---|---|
| Fit-point SPLINE → always 1 element | **Confirmed** | p9 (open) = 1, p21 (closed) = 1, p24 (540 shapes) = 540 |
| Control-point SPLINE splits at tangent (G1) breaks | **Confirmed** | p3 = 2, p14 (3 corners) = 3, p22 (real shape) = 6 |
| Split threshold is effectively *exact* G1 | **Confirmed** | p18/p19 ladders: all 8 rungs split, incl. the 8.5e-7° rung |
| Closed loop counts `max(tangent_breaks, 2)` | **Confirmed** | smooth closed = 2 at 4/6/8 segments; 1 corner = 2; 3 corners = 3 |
| Open chain counts `1 + tangent_breaks` | **Confirmed** | p18 = 9 (8 breaks) |
| Each LINE = 1 element | **Confirmed** | p7 (10 lines) = 10 |
| n-vertex LWPOLYLINE = n−1 elements | **Confirmed** | p8 (10 verts) = 9 |

### Confirmed *irrelevant* — do not waste time here

These were each a plausible hypothesis, and each was killed by a probe:

- **Interior knot multiplicity** — p2 / p4 / p5 all = 1 regardless of multiplicity.
- **Curvature (G2) breaks** — p10 / p12 = 1 even with a 50% curvature jump. Only *tangent*
  continuity matters.
- **The DXF closed flag (group code 70, bit 0)** — p15/p16/p17 with the flag set count the
  same as p6/p11/p13 with it off.
- **The "merge points closer than 0.001" import option** — inert. p18 counted 9 with it
  both on and off.

### The tangent threshold is not a tolerance

The natural assumption is that SolidWorks merges joints within some small angle tolerance.
It does not, in any useful sense. A tangent ladder with breaks descending to **8.5e-7
degrees** split at *every* rung — both with 20mm handles and with 5mm handles, ruling out a
distance-scaled tolerance. The only joints that survive are ones where the tangent matches
to float noise (~1e-8°, e.g. a circle built from trig where the arithmetic happens to
agree).

Practical reading: **you cannot hit exact G1 from a fitted curve.** Don't try. Use fit
points instead.

## Fit points: why they win

A fit-point SPLINE hands SolidWorks a list of points on the curve and no control net.
SolidWorks *refits* its own spline through them, and the result is one element — it shows
in the UI as "Spline" rather than "generic spline", which is the tell that a refit happened.
Corners, curvature breaks, and segment count are all invisible to the count.

The trade: accuracy is now bounded by SolidWorks' interpolation *between* your samples, not
by your own curve. Four samples per bezier segment measured ~0.05mm worst-case proxy error
on a real pattern file, and the user's visual inspection of dozens of shapes was "the shape
of it looks perfect". Sample denser if your tolerance is tighter.

Note the fit-point branch of the DXF does not carry a closed flag — which is fine, because
the flag doesn't affect the count anyway (above). Make the seam bit-identical
(`points[-1] = points[0]`) so the refit closes cleanly.

## Results

| File | Before | After (fit-point export) |
|---|---|---|
| `path545.dxf` (Inkscape original) | 3383 | **540** — one per shape |
| `path545.dxf` via control-point join | 2990 | **540** |
| Dense pattern (`zo9yyqx7.dxf`, 7014 LINEs) | ~7000 | **274** |

Because one entity is now one element by construction, **the app's own count equals
SolidWorks' count with no counting algorithm to maintain**. That was the actual goal, and
it fell out for free.

---

## Methodology lessons (the expensive part)

These cost more time than the SolidWorks rules did. They generalize to any
black-box reverse-engineering.

**Never fit a threshold to an aggregate.** A smooth angle distribution means *some*
tolerance will reproduce any target number. A threshold of 6.6e-5° predicted the observed
2990 *exactly* — and was pure coincidence, proven wrong by a single per-shape probe (p22
predicted 6 under the exact-G1 model, and measured 6). One measured probe beats any curve
fit through aggregate data.

**Probe construction is where the bugs live.** Three separate probes silently tested the
wrong thing:
- Symmetric segments are accidentally C2 — a "curvature break" probe that has none.
- Handles at a junction must differ *from each other*, not just from the neighbours.
- `ezdxf.add_open_spline` leaves the closed flag off, unlike the real file being modelled.

Discipline that fixed it: **re-read every probe back from the saved file and diff its raw
DXF group codes against the real file** before sending it to be tested. What you *intended*
to write is not evidence.

**`acos` has a ~1e-6° noise floor near zero** — `cos` rounds to 1.0 and quantizes the
result. Every angle histogram below that floor was garbage. Use `atan2(|cross|, dot)`,
accurate to ~1e-14°. This invalidated an entire round of analysis before it was caught.

**Falsified hypotheses, kept as a graveyard so nobody resurrects them:** splits-at-knots,
splits-at-curvature-breaks, closed-flag-drives-count, and "one element per SPLINE
regardless of segments".

## Unresolved

The exact-G1 model predicts **3343** elements for `path545_optimized.dxf`; SolidWorks
counted **2990**. About 353 joints are unexplained, even though p22 confirmed the model
holds per-shape. Left open deliberately — the fit-point route bypasses splitting entirely,
so the gap is academic. If it ever matters, start by checking whether some joints in the
real file are coincidentally bit-exact.

Also untested: whether the rules differ across SolidWorks versions or DXF format versions
(everything here is R2000 output into one install), and whether ARC/CIRCLE entities behave
as expected (never probed — assumed 1 each).

**Update 2026-07-18:** the headline rule was re-verified on a *second path* — splines
drawn directly through the sketch API (`ISketchManager.CreateSpline` with fit points,
SOLIDWORKS 2026 SP2.1 / rev 34.2.1): 540 fit-point splines = 540 sketch segments. The
rule is a property of SolidWorks' spline refit, not of the DXF importer. Full COM
automation findings (early binding, bulk-insert performance, `InsertSketchPicture`
crash + fix) live in `solidworks-com-api.md`.

## The probe files

All 24 live in `sw_probes/`, named for what they test (`p18_tangent_ladder.dxf`,
`p24_full_fitpoints.dxf`, …). They are small and self-contained; re-run any of them against
a new SolidWorks version to re-validate a rule in about a minute.

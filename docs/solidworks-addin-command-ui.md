# SolidWorks Add-in Buttons Greyed Out on Startup

Field notes from a debugging campaign run 2026-07-30 against a real SolidWorks install.
Everything below marked *measured* came off the add-in's own diagnostic log
(`%LOCALAPPDATA%\CurveMill\addin.log`) comparing a broken cold-start against a working
manual reload, or off reflecting the interop DLL. SolidWorks documents none of this.

The context is CurveMill's C# add-in (`swaddin/CurveMillAddin.cs`), two ribbon buttons
that launch the app. The rules are generic: they apply to any `ISwAddin` that builds a
CommandManager UI and is set to load at SolidWorks startup.

**Environment (version matters — re-verify on other installs):**

| Component | Value |
|---|---|
| SOLIDWORKS | 2026 (same install as `solidworks-com-api.md`, rev 34.2.1) |
| Add-in | C# `ISwAddin`, .NET Framework 4.8.1, loads at startup (HKCU `AddInsStartup=1`) |
| Compiler | Framework `Csc.exe` v4.0.30319 — C# 5 dialect (no `=>` members, no `$""`, no `?.`) |
| Group id | `0x4375724D` ("CurM"); command user ids 10 / 11 |

---

## The short version

**Greyed add-in buttons on cold start are a broken command→callback binding, not a bad
tab and not a bad command id.** They happen because the add-in loads *during* SolidWorks
startup and registers its callbacks (`SetAddinCallbackInfo2`) and command group before SW
has finished building its own command dispatch — which SW then reshuffles, orphaning the
binding.

**The only fix that works is an in-process add-in reload:** re-run
`SetAddinCallbackInfo2` **and** recreate the whole command group, *after* a
part/assembly is open and its ribbon has settled. Rebuilding just the ribbon tab does
nothing. Do it on `OnIdleNotify` (quiescent), never in a document-load notification
(crashes SW).

If you only remember one line: **a plain tab rebuild is not enough — you must re-bind the
callbacks, and you must do it late.**

---

## The problem that started it

Two ribbon buttons, correct icons, shown **coloured** for a second while SolidWorks was
still starting — then **greyed** the moment SW finished loading, wearing a foreign
tooltip about "stamps and punches." Every cold start, identically. Unchecking and
re-checking the add-in in Tools ▸ Add-Ins fixed it every time; restarting SW brought it
straight back.

## The diagnostic method (this is what cracked it)

Four fixes had already failed by guessing. What finally worked was instrumenting the
add-in to log, on **every** `ConnectToSW`, the things that could differ between the broken
state and the working state, then capturing one log that contained **both** — a cold
start followed by a manual reload in the same session:

- the runtime command ids (`ICommandGroup.get_CommandID`)
- the group's `ToolbarId` and `HasEnabledButton`
- the registry-cached user ids (`GetGroupDataFromRegistry`)

The decisive line was the runtime command ids. **They were identical in both states.**

## The rules (measured)

| Behaviour | Verdict | Evidence |
|---|---|---|
| Runtime command ids are identical cold-start vs after reload | **Confirmed** | log both cycles: `open=41670 send=41671`, `toolbarId=59429` |
| `HasEnabledButton` is `True` in **both** broken and working states | **Confirmed** | log both cycles — broken and working are indistinguishable to the API |
| An always-on button (no enable callback) still greys on cold start | **Confirmed** | the Open button has `""` for its enable method, so greying ⇒ the *callback binding* is dead, not a disabled state |
| `SetAddinCallbackInfo2` + full group recreate, after a part is open, fixes it | **Confirmed** | working run: reload-equivalents at part+3 s and part+8 s → live buttons |
| Rebuilding only the ribbon tab (no callback re-bind) does **not** fix it | **Confirmed** | logged `tab re-asserted` with a part active → still greyed |
| Recreating the group on the **first** idle (before any part opens) does **not** fix it | **Confirmed** | fired ~5 s in, before a part ribbon existed → re-clobbered, still greyed |
| Healing the **part** context does **not** heal the **assembly** context | **Confirmed** | fix ran with a part active, then unhooked; making an assembly from that part → greyed again. SW re-clobbers the binding the *first time each doc-type context is realized*, not just at startup |
| Command-group surgery inside `ActiveModelDocChangeNotify` | **Crashes SW** | access violation on startup — the notify is a non-quiescent state |
| `CreateCommandGroup2` returning `err=1` | **Success, not an error** | `swCreateCommandGroupErrors` via reflection: `1 = ..._Success` |

### The tell

`HasEnabledButton=True` and the same ids `41670/41671` in both the greyed and the working
state means **you cannot detect the fault from the API** — the broken button looks fully
healthy to every property you can read. The only observable difference is on screen. That
one fact drove the whole final design (below).

## Confirmed *irrelevant* — do not waste time here

Each was a plausible theory; each was killed by the log:

- **Command ids colliding with SW's own stamp/punch commands.** The "stamps and punches"
  tooltip made `41670/41671` look like foreign built-ins. Refuted: the working reload uses
  the *same* `41670/41671` and works, so they are legitimately ours. The tooltip is a
  leftover render on an orphaned button, not the command we're actually bound to.
- **Registry command-group cache mismatch** (`GetGroupDataFromRegistry` /
  `IgnorePreviousVersion`). Not causal: cold start logged `have=False`, reload logged
  `have=True userIDs=10,11`, both produced identical ids and the same outcome. We pass
  `IgnorePreviousVersion=true` unconditionally regardless.
- **Wrong or duplicate icons.** No — the icons render correctly in every state; only the
  binding is dead.
- **`CreateCommandGroup2` failing.** No — `err=1` is `Success` (decoded by reflection; an
  earlier log comment calling it "NoError" was wrong).
- **Command-id drift / bumping the user ids** (we moved 0,1 → 10,11 early on). Irrelevant
  to the greying; the ids are stable across load and reload either way.

## What works — the in-process reload

Build the UI in `ConnectToSW` as normal (so the buttons appear early), then arm
`OnIdleNotify`. On idle, wait until a part/assembly is the active doc *and* let its
ribbon settle, then do exactly what a Tools ▸ Add-Ins reload does — **re-bind the
callbacks and recreate the group + tab**:

```csharp
private void ReloadEquivalent()
{
    _sw.SetAddinCallbackInfo2(0, this, _cookie);  // <-- the half every failed attempt omitted
    RemoveCommandUI();                            // remove tabs + RemoveCommandGroup2
    CreateCommandUI();                            // CreateCommandGroup2 + items + tabs
}
```

Timing and firing, from the idle handler:

- **Wait for an active part/assembly.** Before a part exists there is no part ribbon for
  SW to clobber, so a rebuild then is pointless (this is why the "first idle" attempt
  failed).
- **Let it settle, then fire — twice.** The working manual reload landed ~2.3 s after the
  part opened; we fire at part-seen **+3 s** and again **+8 s**. Two shots because, per
  "the tell" above, *we cannot read back whether the first shot took* — the broken and
  fixed states are API-identical — so the second brackets a slower machine. Then unhook.
- **Idle only.** `OnIdleNotify` is quiescent and safe for command-group surgery. The same
  surgery inside `ActiveModelDocChangeNotify` (a doc-load notification) crashed SW with an
  access violation, uncatchable by try/catch.
- **Heal once per doc-type context, and stay armed.** SW re-clobbers the binding the *first
  time each document-type context is realized* — not only at startup. Healing while a **part**
  is active does **not** heal the **assembly** context, so making an assembly from a part greys
  the buttons anew. The handler therefore latches per doc type (`_fixedTypes`), fires its own
  two-shot settle for part and again for assembly, and **never unhooks for the session** —
  earlier versions unhooked after the first type and left every later type broken.

Verified run (part): buttons went live on their own, no manual reload. The per-type latch
(above) then extends that to the assembly context.

> **ceiling:** the latch keys on doc *type*. If a *second* document of an already-healed type
> ever greys (i.e. SW re-clobbers per-document, not per-type), escalate to per-document
> re-arming — track the active-doc identity across idles and reset the settle on change.

## What does not work (kept as a graveyard)

- Rebuilding the **tab** on idle without re-binding callbacks. → still greyed.
- Recreating the **group** on the **first** idle, before a part is open. → re-clobbered.
- Healing once then **unhooking** the idle handler. → the first *other* doc-type context
  (make an assembly from a part) greys again with no healer left to fix it.
- Any surgery in **`ActiveModelDocChangeNotify`**. → crashes SW on startup.
- Trusting `CreateCommandGroup2` / `HasEnabledButton` / the command ids to tell you
  whether the UI is healthy. → they all report healthy while the buttons are dead.

## Methodology lessons

**Measure the difference between broken and working before writing any fix.** Four
attempts failed because they were fired blind. One instrumented log — cold start *and*
manual reload in the same capture — refuted the dominant theory (id collision) in a single
line and pointed straight at the callback binding. The fix wrote itself from the diff:
"what does the reload's `ConnectToSW` do that my idle rebuild didn't?" → `SetAddinCallbackInfo2`.

**If the broken and working states are API-identical, you must fix open-loop.** No
detector, no self-heal, no read-back verification is possible. That is *why* the fix fires
a fixed two shots on a timer instead of "rebuild until the tab looks right" — there is no
"looks right" to test against.

**Never do COM UI surgery in a document notification.** `OnIdleNotify` is the only
quiescent moment. Doing command-group work during `ActiveModelDocChangeNotify` is an
access violation, and access violations are not catchable — the try/catch around it will
not save you. (Same lesson family as the `InsertSketchPicture` WebView race in
`solidworks-com-api.md`: treat SW's UI as asynchronous and only act when it is idle.)

## Version caveat

Measured on one install (SOLIDWORKS 2026). The load-order race is a property of *when* SW
builds its command dispatch during startup, which is exactly the kind of thing that can
change between releases — the `+3 s / +8 s` settle window is a tuned heuristic, not a
guarantee. If buttons grey again on a new SW version or a slower machine, the two settle
constants in `OnIdleReload` are the knobs; bump them. Re-capture a cold-start-plus-reload
log before assuming any of the above still holds.

## Related

- `swaddin/CurveMillAddin.cs` — the add-in; `OnIdleReload` / `ReloadEquivalent` implement this.
- `solidworks-com-api.md` — Python COM automation (early binding, bulk insert, the
  `InsertSketchPicture` crash + settle-delay pattern).
- `solidworks-dxf-import.md` — how SolidWorks counts DXF sketch elements.

"""The worker-thread GC guard: automatic cyclic GC must stay suspended for as
long as ANY background Worker runs, and be restored exactly once the last one
exits. If this balance breaks, GC can fire on a worker thread and traverse the
GUI thread's live QGraphicsItems -> access-violation crash (the recount fit
crash). See Worker in curvemill/app.py."""
import gc

from curvemill.app import _resume_gc_for_worker, _suspend_gc_for_worker


def test_resume_does_not_collect_on_worker_thread(monkeypatch):
    # _resume_gc_for_worker runs in Worker.run's finally, ON the worker thread,
    # just after the queued `done` signal was emitted -- so the GUI thread is
    # rebuilding the scene. A gc.collect() here frees cyclic QGraphicsItem wrappers
    # off the GUI thread and corrupts the scene BSP index (access-violation crash).
    # Re-enabling GC is allowed; collecting is not.
    calls = []
    monkeypatch.setattr(gc, "collect", lambda *a, **k: calls.append(1) or 0)
    try:
        _suspend_gc_for_worker()
        _resume_gc_for_worker()
        assert calls == [], "the last worker must not gc.collect() on its own thread"
    finally:
        if not gc.isenabled():
            gc.enable()


def test_gc_suspended_while_workers_run_and_restored_after():
    assert gc.isenabled()  # sane starting point
    try:
        _suspend_gc_for_worker()
        assert not gc.isenabled(), "first worker must suspend automatic GC"
        _suspend_gc_for_worker()  # overlapping worker (e.g. recount during Send)
        assert not gc.isenabled()
        _resume_gc_for_worker()
        assert not gc.isenabled(), "GC must stay off while a worker is still live"
        _resume_gc_for_worker()
        assert gc.isenabled(), "GC restored only when the last worker exits"
    finally:
        if not gc.isenabled():
            gc.enable()

"""faulthandler crash-log rotation: a non-empty crash.log at launch = last run crashed."""
import faulthandler

from curvemill import app


def test_crash_log_rotates_prior_report(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "_diag_dir", lambda: tmp_path)

    # First run: no prior crash log -> nothing to report.
    assert app._enable_crash_log() is None
    app._CRASH_LOG_FILE.close()  # release the Windows write handle before we simulate a crash

    # Simulate a fatal signal writing a dump into this run's crash.log.
    (tmp_path / "crash.log").write_text("Fatal Python error: Segmentation fault\n")

    # Next launch: detect it, move it aside, and hand back the report path.
    prior = app._enable_crash_log()
    assert prior == tmp_path / "last-crash.log"
    assert "Segmentation fault" in prior.read_text()
    assert (tmp_path / "crash.log").read_text() == ""  # this run's log starts clean

    app._CRASH_LOG_FILE.close()
    faulthandler.disable()

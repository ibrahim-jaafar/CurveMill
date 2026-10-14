"""Shared progress-callback helpers.

dxf_io, geometry, rasterize and autotrace each pump a (percent, message) callback
during long jobs. The two helpers below used to be copy-pasted verbatim into each;
they live here now so there is one copy to fix.
"""

from __future__ import annotations

from typing import Callable

ProgressCallback = Callable[[int, str], None]


def report(progress: ProgressCallback | None, value: int, message: str) -> None:
    if progress is not None:
        progress(max(0, min(100, value)), message)


def report_loop(
    progress: ProgressCallback | None,
    start: int,
    end: int,
    current: int,
    total: int,
    message: str,
) -> None:
    if progress is None or total <= 0:
        return
    step = max(total // 50, 1)
    if current == total or current % step == 0:
        report(progress, start + int((end - start) * current / total), message)

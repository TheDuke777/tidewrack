"""Timings for dev builds: where the map's lag comes from (not in release builds).

`main.py` calls `enable()` for builds without a release tag (a local dev APK, or
`flet run`). Then the map, the Explore screen and Flet itself report how long
things take, summarised every few seconds:

    [perf] patch.Page 41×38.0/91.2 · map.draw 20×3.1/6.0 · map.gesture 41 · …

Each timing is `count×median/max` in milliseconds; plain counts are events. The
line is printed (for `adb logcat`) and kept in `latest` for an on-screen line
under the map, so it can be read without adb.

Flet's own work is measured by wrapping two of its internals: `after_event` (what
runs after every event handler, including the automatic update) and
`patch_control` (diffing a control tree and sending it to Flutter), recorded per
patched control type. Disabled, everything here is a no-op.
"""

from __future__ import annotations

import statistics
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager

REPORT_EVERY = 5.0  # seconds between summaries

ENABLED = False
latest = ""  # the last summary, for the on-screen line

_times: dict[str, list[float]] = defaultdict(list)
_counts: dict[str, int] = defaultdict(int)
_clock: Callable[[], float] = time.monotonic
_last_report = 0.0


def _print_line(line: str) -> None:
    print(line, flush=True)


_print: Callable[[str], None] = _print_line


def enable() -> None:
    global ENABLED, _last_report
    if ENABLED:
        return
    ENABLED = True
    _last_report = _clock()
    _wrap_flet()


@contextmanager
def timed(name: str) -> Iterator[None]:
    if not ENABLED:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        record(name, (time.perf_counter() - start) * 1000)


def record(name: str, ms: float) -> None:
    if ENABLED:
        _times[name].append(ms)
        _maybe_report()


def count(name: str) -> None:
    if ENABLED:
        _counts[name] += 1
        _maybe_report()


def summary() -> str:
    """`name count×median/max` per timing (slowest median first), then counts."""
    timings = sorted(_times.items(), key=lambda kv: -statistics.median(kv[1]))
    parts = [f"{n} {len(v)}×{statistics.median(v):.1f}/{max(v):.1f}" for n, v in timings]
    parts += [f"{n} {c}" for n, c in sorted(_counts.items())]
    return " · ".join(parts)


def _maybe_report() -> None:
    global latest, _last_report
    now = _clock()
    if now - _last_report < REPORT_EVERY or not (_times or _counts):
        return
    latest = summary()
    _print(f"[perf] {latest}")
    _times.clear()
    _counts.clear()
    _last_report = now


def _wrap_flet() -> None:
    """Time Flet's post-event work and its patches (dev builds only)."""
    from flet.messaging.session import Session

    after_event, patch_control = Session.after_event, Session.patch_control

    async def timed_after_event(self, control):
        with timed("flet.after_event"):
            await after_event(self, control)

    def timed_patch_control(self, control, *args, **kwargs):
        with timed(f"patch.{type(control).__name__}"):
            return patch_control(self, control, *args, **kwargs)

    Session.after_event = timed_after_event
    Session.patch_control = timed_patch_control

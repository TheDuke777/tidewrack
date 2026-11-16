"""Dev-build extras, for builds without a release tag (a local dev APK, `flet run`).

`main.py` calls `enable()` there: timings (ui/perf.py) and a "Reveal map" menu
item for testing big maps. Release builds and tests never call it.
"""

from __future__ import annotations

from tidewrack.ui import perf

ENABLED = False


def enable() -> None:
    global ENABLED
    ENABLED = True
    perf.enable()

"""Dev-build timings (ui/perf.py): off by default, summarised every few seconds."""

import pytest

from tidewrack.ui import perf


@pytest.fixture
def enabled(monkeypatch):
    from flet.messaging.session import Session

    now = [0.0]
    printed: list[str] = []
    monkeypatch.setattr(perf, "_clock", lambda: now[0])
    monkeypatch.setattr(perf, "_print", printed.append)
    monkeypatch.setattr(Session, "after_event", Session.after_event)  # restored after
    monkeypatch.setattr(Session, "patch_control", Session.patch_control)
    monkeypatch.setattr(perf, "_times", perf.defaultdict(list))
    monkeypatch.setattr(perf, "_counts", perf.defaultdict(int))
    monkeypatch.setattr(perf, "latest", "")
    monkeypatch.setattr(perf, "ENABLED", False)
    perf.enable()
    yield now, printed


def test_off_by_default_and_then_a_no_op():
    assert perf.ENABLED is False  # tests (and release builds) never call enable()
    with perf.timed("x"):
        pass
    perf.count("y")
    assert perf.summary() == ""


def test_timings_are_summarised_every_few_seconds(enabled):
    now, printed = enabled
    for ms in (2.0, 4.0, 30.0):
        perf.record("map.draw", ms)
    perf.record("patch.Page", 50.0)
    perf.count("map.gesture")
    assert printed == []  # not yet
    now[0] = perf.REPORT_EVERY
    perf.count("map.gesture")
    assert printed == ["[perf] patch.Page 1×50.0/50.0 · map.draw 3×4.0/30.0 · map.gesture 2"]
    assert perf.latest == printed[0].removeprefix("[perf] ")
    assert perf.summary() == ""  # a fresh window


def test_flets_post_event_work_and_patches_are_timed(monkeypatch):
    import asyncio

    from flet.messaging.session import Session

    calls = []

    async def after_event(self, control):
        calls.append(("after_event", control))

    def patch_control(self, control, *args, **kwargs):
        calls.append(("patch", control))
        return "patched"

    # Stand-ins for Flet's originals, installed before enable() wraps them.
    monkeypatch.setattr(Session, "after_event", after_event)
    monkeypatch.setattr(Session, "patch_control", patch_control)
    monkeypatch.setattr(perf, "_times", perf.defaultdict(list))
    monkeypatch.setattr(perf, "_counts", perf.defaultdict(int))
    monkeypatch.setattr(perf, "ENABLED", False)
    perf.enable()

    class Page:
        pass

    page = Page()
    assert Session.patch_control(None, page) == "patched"
    asyncio.run(Session.after_event(None, page))
    assert calls == [("patch", page), ("after_event", page)]
    assert set(perf._times) == {"patch.Page", "flet.after_event"}


def test_the_map_shows_the_latest_timings_in_dev_builds(enabled):
    from tidewrack.ui.map_canvas import MapCanvas

    perf.latest = "map.draw 1×1.0/1.0"
    canvas = MapCanvas(on_command=lambda _: None)
    assert canvas.perf_line in canvas.control.controls and canvas.perf_line.visible
    from tests.ui.test_map_canvas import _map

    canvas.show(_map(), "", key="k")
    assert canvas.perf_line.value == "map.draw 1×1.0/1.0"

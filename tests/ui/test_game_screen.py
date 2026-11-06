import pytest

from tidewrack.ui.screens.game import HIDE_LOG_BELOW, MAX_LOG_SHARE, MIN_LOG_SHARE, LogSplit


def test_tap_hides_and_restores_the_same_size():
    split = LogSplit(visible=True, share=0.3)
    split.toggle()
    assert not split.visible and split.expands() == (1, 0)
    split.toggle()
    assert split.visible and split.share == 0.3 and split.expands() == (70, 30)


def test_dragging_resizes_within_bounds():
    split = LogSplit(visible=True, share=0.4)
    split.start_drag()
    split.drag_to(-0.2)  # up: a bigger log
    assert split.share == pytest.approx(0.6)
    split.drag_to(-0.1)  # back down a little: positions are from the drag's start
    assert split.share == pytest.approx(0.5)
    split.drag_to(-5)
    assert split.share == MAX_LOG_SHARE
    split.start_drag()
    split.drag_to(MAX_LOG_SHARE - 0.08)  # down to just above the hide point
    assert split.visible and split.share == MIN_LOG_SHARE


def test_dragging_to_the_bottom_hides_and_dragging_up_shows_again():
    split = LogSplit(visible=True, share=0.4)
    split.start_drag()
    split.drag_to(0.4 - HIDE_LOG_BELOW / 2)
    assert not split.visible
    split.start_drag()
    split.drag_to(-0.25)
    assert split.visible and split.share == pytest.approx(0.25)


def test_log_lines_mark_the_latest_action_with_weight_and_a_divider():
    import flet as ft

    from tidewrack.ui.screens.game import log_lines

    controls = log_lines(["a", "b", "c", "d"], total=10, fresh_from=8)  # c, d are new
    kinds = [type(c).__name__ for c in controls]
    assert kinds == ["Text", "Text", "Divider", "Text", "Text"]
    texts = [c for c in controls if isinstance(c, ft.Text)]
    assert [t.weight for t in texts] == [None, None, ft.FontWeight.BOLD, ft.FontWeight.BOLD]
    # More new lines than shown: all bold, no divider on top.
    assert [type(c).__name__ for c in log_lines(["a", "b"], total=10, fresh_from=3)] == [
        "Text",
        "Text",
    ]
    # Nothing new (a world just opened): plain.
    assert all(c.weight is None for c in log_lines(["a"], total=5, fresh_from=5))


def test_road_buttons_say_where_a_region_starts_and_who_bars_it():
    from tidewrack.core.engine.game import RoadView
    from tidewrack.ui.screens.game import _road_label

    plain = RoadView("loc_01", "Saltmere", "Town", visited=False)
    assert _road_label(plain) == "Travel to Saltmere · Town  (unexplored)"
    guarded = RoadView(
        "loc_07", "Thornea", "Stilt Village", False, "Reed Warden", "The Sallow Fens"
    )
    assert _road_label(guarded) == (
        "Travel to Thornea · Stilt Village · into The Sallow Fens  (the Reed Warden bars the way)"
    )

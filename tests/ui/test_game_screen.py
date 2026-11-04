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
    split.drag(-0.2)  # up: a bigger log
    assert split.share == pytest.approx(0.6)
    split.drag(-5)
    assert split.share == MAX_LOG_SHARE
    split.start_drag()
    split.drag(MAX_LOG_SHARE - 0.08)  # down to just above the hide point
    assert split.visible and split.share == MIN_LOG_SHARE


def test_dragging_to_the_bottom_hides_and_dragging_up_shows_again():
    split = LogSplit(visible=True, share=0.4)
    split.start_drag()
    split.drag(0.4 - HIDE_LOG_BELOW / 2)
    assert not split.visible
    split.start_drag()
    split.drag(-0.25)
    assert split.visible and split.share == pytest.approx(0.25)

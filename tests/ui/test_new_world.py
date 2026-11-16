"""The New world dialog: difficulty for everyone, a starting region in dev builds."""

import flet as ft

from tidewrack.services.content import load_bundled_content
from tidewrack.ui.screens.new_world import NewWorldDialog

CONTENT = load_bundled_content()


def _radios(group: ft.RadioGroup) -> list[tuple[str, str]]:
    def walk(control):
        yield control
        for attr in ("content", "controls"):
            child = getattr(control, attr, None)
            for c in child if isinstance(child, list) else [child]:
                if isinstance(c, ft.Control):
                    yield from walk(c)

    return [(r.value, r.label) for r in walk(group) if isinstance(r, ft.Radio)]


def _start(dialog: NewWorldDialog) -> None:
    [button] = [a for a in dialog.control.actions if isinstance(a, ft.FilledButton)]
    button.on_click(None)


def test_difficulties_easiest_first_standard_picked():
    started = []
    dialog = NewWorldDialog(CONTENT, "world.standard", lambda *a: started.append(a), lambda: None)
    assert [label for _, label in _radios(dialog.difficulty)] == ["Easy", "Standard", "Hard"]
    assert dialog.region is None  # release builds: no region choice
    _start(dialog)
    assert started == [("difficulty.standard", None)]
    dialog.difficulty.value = "difficulty.hard"
    _start(dialog)
    assert started[-1] == ("difficulty.hard", None)


def test_dev_builds_can_pick_a_region_to_start_in():
    started = []
    dialog = NewWorldDialog(
        CONTENT, "world.standard", lambda *a: started.append(a), lambda: None, regions=True
    )
    assert [label for _, label in _radios(dialog.region)] == [
        "Coast",
        "Fens",
        "Moors",
        "Highlands",
    ]
    _start(dialog)
    assert started == [("difficulty.standard", None)]  # the coast: a normal start
    dialog.region.value = "region.moors"
    _start(dialog)
    assert started[-1] == ("difficulty.standard", "region.moors")

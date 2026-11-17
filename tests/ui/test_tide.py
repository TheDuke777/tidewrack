"""Taking the Drowned Crown, the tide dialog and important log lines (step 8c)."""

import flet as ft

from tidewrack.core.engine.components import Position, Prestige, TideCrown
from tidewrack.core.engine.game import IMPORTANT
from tidewrack.services.content import load_bundled_content
from tidewrack.ui.screens.game import log_lines
from tidewrack.ui.screens.tide import TideDialog

CONTENT = load_bundled_content()


def _session(tmp_path):
    from tidewrack.services.session import GameSession
    from tidewrack.services.storage import FileSaveStore

    return GameSession.generate(
        FileSaveStore(tmp_path / "saves"), CONTENT, "world.standard", "W", 20261103
    )


def _shell(session, tmp_path, rides, toasts=None):
    from tidewrack.services.settings import SettingsStore
    from tidewrack.ui.shell import WorldShell

    return WorldShell(
        session,
        SettingsStore(tmp_path / "s.json"),
        on_back=lambda: None,
        confirm=lambda *_: None,
        notify=(toasts if toasts is not None else []).append,
        on_ascend=lambda: rides.append(True),
    )


def _buttons(screen) -> list[str]:
    return [b.content for b in screen.entrances.controls if isinstance(b, ft.FilledButton)]


def test_the_crown_is_taken_from_its_room(tmp_path):
    session = _session(tmp_path)
    rides: list[bool] = []
    shell = _shell(session, tmp_path, rides)
    screen = shell.explore
    assert "Take the Drowned Crown" not in _buttons(screen)
    game = session.game
    game.world.get(game.player, Prestige).tide_turned = True
    here = game.world.get(game.player, Position)
    game.world.create(TideCrown(), Position(here.location, here.room))
    screen.refresh()
    [take] = [
        b
        for b in screen.entrances.controls
        if getattr(b, "content", None) == "Take the Drowned Crown"
    ]
    take.on_click(None)
    assert rides == [True]


def test_important_log_lines_stand_out():
    plain, marked = log_lines(["You look around.", f"{IMPORTANT}The tide is turning."], 2, 2)
    assert marked.color == ft.Colors.TERTIARY and marked.weight == ft.FontWeight.BOLD
    assert marked.value.startswith("⚑")  # a glyph too, never colour alone
    assert plain.color is None


def test_important_lines_toast_and_dot_while_the_log_is_closed(tmp_path):
    from tidewrack.core.engine.game import Wait

    session = _session(tmp_path)
    toasts: list[str] = []
    shell = _shell(session, tmp_path, [], toasts)
    screen = shell.explore
    screen.split.visible = False
    screen._apply_split()
    session.game._say("Something big.", important=True)
    screen.act(Wait())
    assert toasts[-1] == "Something big."
    assert screen.log_title.badge is not None
    screen._toggle_log()  # open it: the dot goes
    assert screen.log_title.badge is None


def test_the_dialog_needs_a_boon_before_you_ride(tmp_path):
    session = _session(tmp_path)
    ridden: list[str] = []
    dialog = TideDialog(1, session.boon_choices(CONTENT), [], ridden.append, lambda: None)
    ride = dialog.control.actions[-1]
    assert isinstance(ride, ft.FilledButton) and ride.disabled
    dialog.boon.value = "boon.long_table"
    dialog.boon.on_change(None)
    assert not ride.disabled
    ride.on_click(None)
    assert ridden == ["boon.long_table"]

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


def test_dialogs_fit_their_content(tmp_path):
    # A scrolling Flet Column grows to the height it's given, so a dialog whose
    # content is one fills the screen. Dialogs scroll themselves instead.
    from tidewrack.ui.screens.new_world import NewWorldDialog

    session = _session(tmp_path)
    dialogs = [
        TideDialog(1, session.boon_choices(CONTENT), [], lambda _: None, lambda: None).control,
        NewWorldDialog(CONTENT, "world.standard", lambda *_: None, lambda: None).control,
    ]
    for dialog in dialogs:
        assert dialog.scrollable
        assert getattr(dialog.content, "scroll", None) is None


def test_boon_names_stay_short_and_their_effects_wrap(tmp_path):
    session = _session(tmp_path)
    dialog = TideDialog(1, session.boon_choices(CONTENT), [], lambda _: None, lambda: None)
    radios = [c.controls[0] for c in dialog.boon.content.controls]
    assert [r.label for r in radios] == [b.name for b in CONTENT.boon_choices()]


def test_the_toast_comes_after_the_screen_is_refreshed(tmp_path):
    # Showing a toast updates the page and turns off Flet's update at the end of
    # the event, so it must come last, or the fight (warden) or the new place
    # (crossing) only appears after a second tap.
    from tidewrack.core.engine.game import Wait

    session = _session(tmp_path)
    order: list[str] = []
    shell = _shell(session, tmp_path, [], None)
    screen = shell.explore
    screen.notify = lambda text: order.append(f"toast: {text}")
    real = screen._refresh

    def refresh_then_note():
        real()
        order.append("refreshed")

    screen._refresh = refresh_then_note
    screen.split.visible = False
    screen._apply_split()
    session.game._say("A warden bars the way.", important=True)
    screen.act(Wait())
    assert order == ["refreshed", "toast: A warden bars the way."]


def _texts(control) -> list[str]:
    out = []

    def walk(c):
        if isinstance(c, ft.Text) and isinstance(c.value, str):
            out.append(c.value)
        for attr in ("content", "controls", "title"):
            child = getattr(c, attr, None)
            for x in child if isinstance(child, list) else [child]:
                if isinstance(x, ft.Control):
                    walk(x)

    walk(control)
    return out


def test_the_codex_shows_your_tides_and_boons(tmp_path):
    from tidewrack.ui.screens.codex import CodexScreen

    session = _session(tmp_path)
    first = _texts(CodexScreen(session).sections.controls[0])
    assert "The tides" in first and any("first tide" in t for t in first)

    game = session.game
    game.world.get(game.player, Prestige).tide_turned = True
    here = game.world.get(game.player, Position)
    game.world.create(TideCrown(), Position(here.location, here.room))
    session.ascend(CONTENT, "boon.keen_edge")
    texts = _texts(CodexScreen(session).sections.controls[0])
    assert "The tides (tide 1)" in texts
    assert "Foes have 10% more health and hit 1% harder." in texts
    assert "+2 ATK" in texts  # all told
    assert "Tide 1: Keen Edge (+2 ATK)" in texts

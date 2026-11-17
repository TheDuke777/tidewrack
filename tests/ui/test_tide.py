"""The Ride the tide menu item and dialog (step 8c)."""

import flet as ft

from tidewrack.core.engine.components import Prestige
from tidewrack.services.content import load_bundled_content
from tidewrack.ui.screens.tide import TideDialog

CONTENT = load_bundled_content()


def _session(tmp_path):
    from tidewrack.services.session import GameSession
    from tidewrack.services.storage import FileSaveStore

    return GameSession.generate(
        FileSaveStore(tmp_path / "saves"), CONTENT, "world.standard", "W", 20261103
    )


def _shell(session, tmp_path, rides):
    from tidewrack.services.settings import SettingsStore
    from tidewrack.ui.shell import WorldShell

    return WorldShell(
        session,
        SettingsStore(tmp_path / "s.json"),
        on_back=lambda: None,
        confirm=lambda *_: None,
        notify=lambda _: None,
        on_ascend=lambda: rides.append(True),
    )


def test_the_menu_offers_the_tide_only_once_it_has_turned(tmp_path):
    session = _session(tmp_path)
    rides: list[bool] = []
    shell = _shell(session, tmp_path, rides)
    item = shell.explore.ride_tide
    assert not item.visible
    game = session.game
    game.world.get(game.player, Prestige).tide_turned = True
    shell.explore.refresh()
    assert item.visible
    item.on_click(None)
    assert rides == [True]


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

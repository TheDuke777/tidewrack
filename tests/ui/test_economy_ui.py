"""Shops, the inn, selling and abandoning in the UI (step 7a)."""

import flet as ft

from tidewrack.core.engine.components import Health, Position, Shop
from tidewrack.core.engine.game import AcceptQuest
from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()


def _shell(tmp_path, confirm=None):
    from tidewrack.services.session import GameSession
    from tidewrack.services.settings import SettingsStore
    from tidewrack.services.storage import FileSaveStore
    from tidewrack.ui.shell import WorldShell

    # Seed 20261103: the start town has no Smithy room, so its Smithy is at the gate.
    session = GameSession.generate(
        FileSaveStore(tmp_path / "saves"), CONTENT, "world.standard", "W", 20261103
    )
    toasts: list[str] = []
    asked: list[str] = []

    def confirm_now(title, _message, _action, then):
        asked.append(title)
        then()

    shell = WorldShell(
        session,
        SettingsStore(tmp_path / "s.json"),
        on_back=lambda: None,
        confirm=confirm or confirm_now,
        notify=toasts.append,
    )
    return session, shell, toasts, asked


def _walk(control):
    yield control
    for attr in ("content", "controls"):
        child = getattr(control, attr, None)
        for x in child if isinstance(child, list) else [child]:
            if isinstance(x, ft.Control):
                yield from _walk(x)


def _texts(control) -> list[str]:
    return [c.value for c in _walk(control) if isinstance(c, ft.Text) and c.value]


def _buttons(control, starts: str) -> list[ft.Control]:
    return [
        c
        for c in _walk(control)
        if isinstance(c, ft.FilledButton | ft.FilledTonalButton | ft.TextButton | ft.OutlinedButton)
        and isinstance(c.content, str)
        and c.content.startswith(starts)
    ]


def test_shops_show_as_buttons_until_opened(tmp_path):
    session, shell, _, _ = _shell(tmp_path)
    explore = shell.explore
    labels = [b.content for b in _buttons(explore.entrances, "")]
    assert "Smithy · 3 for sale · buys gear" in labels
    assert explore.shops.controls == [] and explore.map.control.visible
    [smithy] = _buttons(explore.entrances, "Smithy")
    smithy.on_click(None)
    assert explore.opened == "Smithy" and not explore.map.control.visible
    assert not explore.entrances.visible and not explore.exits.visible
    assert "Smithy" in _texts(explore.panel_heading)
    [leave] = _buttons(explore.panel_heading, "Leave")
    leave.on_click(None)
    assert explore.opened is None and explore.shops.controls == []
    assert explore.exits.visible and explore.map.control.visible


def test_the_smithy_lists_wares_and_buying_toasts(tmp_path):
    session, shell, toasts, _ = _shell(tmp_path)
    shell.explore.open("Smithy")
    shops = shell.explore.shops
    assert "For sale" in _texts(shops)
    assert any("you have 10 gold" in t for t in _texts(shell.explore.panel_heading))
    buys = _buttons(shops, "Buy · ")
    assert len(buys) == 3
    affordable = [b for b in buys if not b.disabled]
    assert affordable and all("(not enough)" in b.content for b in buys if b.disabled)
    affordable[0].on_click(None)
    assert toasts and toasts[0].endswith("gold.") and "added to your pack" in toasts[0]
    assert len(session.game.inventory().pack) == 1
    assert shell.explore.opened == "Smithy"  # buying keeps the shop open


def test_selling_inside_the_smithy(tmp_path):
    session, shell, toasts, asked = _shell(tmp_path)
    shell.explore.open("Smithy")
    _buttons(shell.explore.shops, "Buy · ")[0].on_click(None)
    gold = session.game.view().gold
    [sell] = _buttons(shell.explore.shops, "Sell · ")
    sell.on_click(None)
    assert asked and asked[0].startswith("Sell the ")
    assert toasts[-1].startswith("Sold the ") and session.game.view().gold > gold
    assert _buttons(shell.explore.shops, "Sell · ") == []


def test_selling_from_the_pack_asks_first_and_pays(tmp_path):
    session, shell, toasts, asked = _shell(tmp_path)
    shell.explore.open("Smithy")
    _buttons(shell.explore.shops, "Buy · ")[0].on_click(None)
    gold = session.game.view().gold
    shell.select(1)
    [sell] = _buttons(shell.inventory.pack, "Sell · ")
    sell.on_click(None)
    assert asked and asked[0].startswith("Sell the ")
    assert session.game.view().gold > gold and session.game.inventory().pack == ()


def test_no_sell_buttons_away_from_a_buyer(tmp_path):
    session, shell, _, _ = _shell(tmp_path)
    shell.explore.open("Smithy")
    _buttons(shell.explore.shops, "Buy · ")[0].on_click(None)
    town = session.game.overworld.location(session.game.overworld.start)
    shell.explore.act(next(iter(_moves(town))))
    shell.select(1)
    assert _buttons(shell.inventory.pack, "Sell") == []


def test_the_inn_rests_you_for_gold(tmp_path):
    session, shell, toasts, _ = _shell(tmp_path)
    game = session.game
    tavern = next(p for _, (s, p) in game.world.query(Shop, Position) if s.inn)
    position = game.world.get(game.player, Position)
    position.location, position.room = tavern.location, tavern.room
    game.world.get(game.player, Health).damage = 5
    shell.explore.refresh()
    [tavern_button] = _buttons(shell.explore.entrances, "Tavern · ")
    assert tavern_button.content == "Tavern · beds 4 gold"
    tavern_button.on_click(None)
    [rest] = _buttons(shell.explore.shops, "Rest the night")
    rest.on_click(None)
    assert game.view().hp == game.view().max_hp and game.view().gold == 6
    shell.explore.refresh()
    [rest] = _buttons(shell.explore.shops, "Rest the night")
    assert rest.disabled  # already rested


def test_abandoning_a_quest_from_the_log(tmp_path):
    session, shell, _, asked = _shell(tmp_path)
    quest = session.game.view().board[0]
    shell.explore.act(AcceptQuest(quest.id))
    shell.select(2)
    [abandon] = _buttons(shell.quests.sections, "Abandon")
    abandon.on_click(None)
    assert asked == [f"Abandon {quest.title}?"]
    assert session.game.quests().active == ()
    assert quest.id in [q.id for q in session.game.view().board]


def _moves(town):
    from tidewrack.core.engine.game import Move

    yield Move(town.room(town.start).exits[0].label)

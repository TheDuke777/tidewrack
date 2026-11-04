from dataclasses import replace

import flet as ft

from tidewrack.core.engine.game import Game
from tidewrack.core.gear.compare import Comparison, StatRow
from tidewrack.core.procgen.gear_gen import generate_kit, make_item
from tidewrack.core.world.overworld import Overworld
from tidewrack.services.content import load_bundled_content
from tidewrack.ui.components.gear_compare_card import gear_compare_card, impact_line, subtitle
from tidewrack.ui.components.stat_delta import delta_label

CONTENT = load_bundled_content()
RECIPE = CONTENT.world("world.standard")
FIRST_DESCENT = CONTENT.dungeon("dungeon.first_descent")


def _game() -> Game:
    world = Overworld(FIRST_DESCENT.id, {FIRST_DESCENT.id: FIRST_DESCENT})
    harpoon = make_item(CONTENT.gear["gear.harpoon"], CONTENT.gearsets)
    return Game(
        1,
        world,
        RECIPE.player,
        generate_kit(RECIPE, CONTENT),
        [(FIRST_DESCENT.id, "wrack_cove", harpoon)],
    )


def _texts(control) -> list[str]:
    """Every Text value in a control tree."""
    found = []

    def walk(c):
        if isinstance(c, ft.Text) and c.value:
            found.append(c.value)
        for attr in ("content", "controls"):
            child = getattr(c, attr, None)
            for x in child if isinstance(child, list) else [child]:
                if isinstance(x, ft.Control):
                    walk(x)

    walk(control)
    return found


def test_deltas_always_carry_a_symbol_and_sign():
    assert delta_label(3) == "▲ +3"
    assert delta_label(-2) == "▼ −2"
    assert delta_label(0) == "＝ 0"


def test_card_shows_verdict_replacement_and_both_deltas():
    harpoon = _game().view().items_here[0]
    texts = _texts(gear_compare_card(harpoon))
    assert "Harpoon" in texts and "◆ Mixed" not in texts and "▲ Better" in texts
    assert subtitle(harpoon) == "Both hands · upgrade +0/3 · replaces Driftwood Club"
    # ATK row: base and total both +5 (7 vs the club's 2); the player goes 4 → 9.
    assert texts.count("▲ +5") == 2 and "4 → 9" in texts
    assert any(t.startswith("Fully upgraded, you'd have ATK 12") for t in texts)
    assert impact_line(harpoon.comparison) == "ATK 4 → 9 · DEF 2 · HP 20"


def test_impact_line_lists_every_stat():
    rows = (StatRow("atk", 1, 1, 4, 5), StatRow("def", -1, -1, 3, 2), StatRow("hp", 0, 0, 20, 20))
    comparison = Comparison("X", "Main hand", False, (), rows, "mixed", (), (), (), (), None)
    assert impact_line(comparison) == "ATK 4 → 5 · DEF 3 → 2 · HP 20"


def _shell(tmp_path, confirm=None):
    from tidewrack.services.session import GameSession
    from tidewrack.services.settings import SettingsStore
    from tidewrack.services.storage import FileSaveStore
    from tidewrack.ui.shell import WorldShell

    session = GameSession.generate(
        FileSaveStore(tmp_path / "saves"), CONTENT, "world.standard", "W", 20261103
    )
    asked = []

    def record(title, message, action, on_confirm):
        asked.append(title)
        if confirm:
            on_confirm()

    shell = WorldShell(
        session,
        SettingsStore(tmp_path / "s.json"),
        on_back=lambda: None,
        confirm=record,
        notify=lambda message: None,
    )
    return session, shell, asked


def test_shell_switches_tabs(tmp_path):
    session, shell, _ = _shell(tmp_path)
    status = shell.explore.status.value
    assert status.startswith("Turn 0 · Rooms 1/") and status.endswith("· Places 1/8")
    assert [d.label for d in shell.navigation_bar.destinations] == [
        "Explore",
        "Inventory",
        "Quests",
        "Codex",
    ]
    assert shell.explore.control.visible and not shell.inventory.control.visible
    shell.select(1)
    # Both tabs stay mounted; only visibility changes (see shell.py).
    tabs = [s.control for s in (shell.explore, shell.inventory, shell.quests, shell.codex)]
    assert shell.body.controls == tabs
    assert shell.inventory.control.visible and not shell.explore.control.visible
    assert shell.current == 1
    texts = _texts(shell.inventory.control)
    assert "HP 20/20   ATK 4   DEF 2" in texts and "Head: empty" in texts
    assert "Your pack is empty." in texts
    shell.select(0)
    assert shell.explore.control.visible and not shell.inventory.control.visible


def _fill_pack(session):
    """Put three finds straight into the player's pack (as if taken)."""
    from tidewrack.core.engine.components import Carried, Position
    from tidewrack.core.gear.item import Item

    game = session.game
    found = [e for e, _ in game.world.query(Item, Position)][:3]
    for entity in found:
        game.world.remove(entity, Position)
        game.world.add(entity, Carried(game.player))
    return [i for i in game.inventory().pack]


def test_dropping_asks_first_and_cancel_keeps_the_item(tmp_path):
    session, shell, asked = _shell(tmp_path, confirm=False)
    pack = _fill_pack(session)
    shell.inventory._drop(pack[0])
    assert asked == [f"Drop the {pack[0].name}?"]
    assert len(session.game.inventory().pack) == 3


def test_bulk_drop_drops_only_selected_and_shown(tmp_path):
    session, shell, asked = _shell(tmp_path, confirm=True)
    pack = _fill_pack(session)
    screen = shell.inventory
    screen.refresh()
    screen._toggle_select(None)
    screen._select_all_shown(None)
    screen._select(pack[0].id, False)
    screen._drop_selected(None)
    assert asked == ["Drop 2 items?"]
    assert [i.id for i in session.game.inventory().pack] == [pack[0].id]
    assert not screen.selecting and screen.selected == set()


def test_pack_filters():
    from tidewrack.ui.screens.inventory import ANY_AFFIX, NO_AFFIX, NO_SET, PackFilter

    def item(slot, affixes=(), gear_set=None):
        view = _game().view().items_here[0]
        return replace(view, slot=slot, affixes=tuple(affixes), gear_set=gear_set)

    keen = item("Main hand", ["Keen"])
    boots = item("Feet", gear_set="Drowned Watch")
    plain = item("Feet")
    pack = [keen, boots, plain]

    def kept(**f):
        return [i for i in pack if PackFilter(**f).keeps(i)]

    assert kept() == pack and not PackFilter().active
    assert kept(slot="Feet") == [boots, plain]
    assert kept(affix=ANY_AFFIX) == [keen] and kept(affix=NO_AFFIX) == [boots, plain]
    assert kept(affix="Keen") == [keen] and kept(affix="Salted") == []
    assert kept(gear_set="Drowned Watch") == [boots]
    assert kept(gear_set=NO_SET, slot="Feet") == [plain]


def test_filter_options_come_from_the_pack():
    from tidewrack.ui.screens.inventory import filter_options

    view = _game().view().items_here[0]
    options = filter_options([replace(view, affixes=("Keen",)), replace(view, slot="Feet")])
    assert [k for k, _ in options["slot"]] == ["all", "Both hands", "Feet"]
    assert [k for k, _ in options["affix"]][-1] == "Keen"


# --- sorting -----------------------------------------------------------------------


def _pack_item(name, slot="Feet", verdict="better", affixes=(), gear_set=None, **total):
    from tidewrack.core.gear.compare import StatRow

    view = _game().view().items_here[0]
    change = total.get("def", 0)  # enough to tell items apart by gain
    rows = (
        StatRow("atk", 0, 0, 4, 4),
        StatRow("def", 0, 0, 2, 2 + change),
        StatRow("hp", 0, 0, 20, 20),
    )
    comparison = replace(view.comparison, verdict=verdict, rows=rows)
    full = {"atk": 0, "def": 0, "hp": 0, **total}
    return replace(
        view,
        id=hash(name) % 10_000,
        name=name,
        slot=slot,
        affixes=tuple(affixes),
        gear_set=gear_set,
        total=full,
        comparison=comparison,
    )


def test_sort_pack_by_each_key_and_direction():
    from tidewrack.ui.screens.inventory import sort_pack

    boots = _pack_item("Boots", verdict="better", hp=0, **{"def": 1})
    helm = _pack_item("Helm", "Head", verdict="mixed", hp=4, **{"def": 1})
    club = _pack_item("Club", "Main hand", verdict="worse", atk=2)
    knife = _pack_item("knife", "Main hand", verdict="same", atk=2)
    pack = [helm, knife, boots, club]

    def names(by, descending=True):
        return [i.name for i in sort_pack(pack, by, descending)]

    assert names("name", descending=False) == ["Boots", "Club", "Helm", "knife"]  # case-blind
    assert names("name") == ["knife", "Helm", "Club", "Boots"]
    assert names("atk") == ["knife", "Club", "Boots", "Helm"]  # ATK tie: better verdict first
    assert names("hp") == ["Helm", "Boots", "knife", "Club"]
    assert names("def") == ["Boots", "Helm", "knife", "Club"]
    assert names("verdict") == ["Boots", "Helm", "knife", "Club"]
    assert names("verdict", descending=False) == ["Club", "knife", "Helm", "Boots"]


def test_sorting_applies_to_the_filtered_pack_and_survives_refreshes(tmp_path):
    session, shell, asked = _shell(tmp_path, confirm=True)
    _fill_pack(session)
    for _ in range(3):  # a few more, so there's something to sort
        _fill_pack(session)
    screen = shell.inventory
    pack = session.game.inventory().pack
    feet = [i for i in pack if i.slot == pack[0].slot]

    screen.filters["slot"].value = pack[0].slot
    screen._filter_changed("slot")
    screen.sort.value = "hp"
    screen._sort_changed()
    shown = [i.id for i in screen._shown]
    expected = [i.id for i in sorted(feet, key=lambda i: (-i.total["hp"],))]
    assert sorted(shown) == sorted(i.id for i in feet)  # filter still applied
    assert [screen_item.total["hp"] for screen_item in screen._shown] == sorted(
        (i.total["hp"] for i in feet), reverse=True
    )
    assert screen.order_button.content == "Best first"

    screen._flip_order()
    assert [i.total["hp"] for i in screen._shown] == sorted(i.total["hp"] for i in feet)
    assert screen.order_button.content == "Worst first"

    screen.refresh()  # e.g. switching tabs
    assert screen.sort.value == "hp" and not screen.descending
    assert len(expected) == len(screen._shown)

    # Selecting "all shown" and dropping touches exactly the filtered, sorted items.
    screen._toggle_select(None)
    screen._select_all_shown(None)
    screen._drop_selected(None)
    left = {i.id for i in session.game.inventory().pack}
    assert left == {i.id for i in pack} - {i.id for i in feet}

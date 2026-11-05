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
    assert "Smithy · 3 for sale · buys gear · crafts" in labels
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
    assert _tabs(shell) == ["Buy (3)", "Sell (0)", "Upgrade (2)", "Craft (4)"]
    assert any(t.endswith(" · 10 gold") for t in _texts(shell.explore.panel_heading))
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
    _buy_first(shell)
    gold = session.game.view().gold
    assert _buttons(shell.explore.shops, "Sell · ") == []  # on the Buy tab
    shell.explore._shop_tab(["sell"])
    assert _buttons(shell.explore.shops, "Buy · ") == [] and _tabs(shell)[1] == "Sell (1)"
    [sell] = _buttons(shell.explore.shops, "Sell · ")
    sell.on_click(None)
    assert asked and asked[0].startswith("Sell the ")
    assert toasts[-1].startswith("Sold the ") and session.game.view().gold > gold
    assert _buttons(shell.explore.shops, "Sell · ") == []


def test_selling_from_the_pack_asks_first_and_pays(tmp_path):
    session, shell, toasts, asked = _shell(tmp_path)
    shell.explore.open("Smithy")
    _buy_first(shell)
    gold = session.game.view().gold
    shell.select(1)
    [sell] = _buttons(shell.inventory.pack, "Sell · ")
    sell.on_click(None)
    assert asked and asked[0].startswith("Sell the ")
    assert session.game.view().gold > gold and session.game.inventory().pack == ()


def test_no_sell_buttons_away_from_a_buyer(tmp_path):
    session, shell, _, _ = _shell(tmp_path)
    shell.explore.open("Smithy")
    _buy_first(shell)
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


def _rich_smithy(tmp_path):
    """A shell open at the start town's Smithy, with gold to buy everything."""
    from tidewrack.core.engine.components import Wallet

    session, shell, toasts, asked = _shell(tmp_path)
    session.game.world.get(session.game.player, Wallet).gold = 500
    shell.explore.open("Smithy")
    while buys := _buttons(shell.explore.shops, "Buy · "):
        buys[0].on_click(None)
    shell.explore._shop_tab(["sell"])
    return session, shell, toasts, asked


def test_bulk_selling_in_the_smithy(tmp_path):
    session, shell, toasts, asked = _rich_smithy(tmp_path)
    packs = shell.explore.sell_list
    pack = session.game.inventory().pack
    assert len(pack) == 3 and packs.heading.value == "Pack (3)"
    packs._toggle_select(None)
    packs._select_all_shown(None)
    [sell] = [
        b for b in packs.selection_bar.controls if getattr(b, "content", None) == "Sell selected"
    ]
    gold = session.game.view().gold
    sell.on_click(None)
    total = sum(i.sell_price for i in pack)
    assert asked[-1] == "Sell 3 items?"
    assert toasts[-1] == f"Sold 3 items for {total} gold."
    assert session.game.view().gold == gold + total and session.game.inventory().pack == ()
    assert not packs.selecting and shell.explore.opened == "Smithy"


def test_the_smithy_and_inventory_share_filters_and_sort(tmp_path):
    session, shell, _, _ = _rich_smithy(tmp_path)
    slot = session.game.inventory().pack[0].slot
    shell.select(1)
    inventory = shell.inventory.pack_list
    inventory.filters["slot"].value = slot
    inventory._filter_changed()
    inventory.sort.value = "price"
    inventory._sort_changed()
    assert inventory.order_button.content == "Highest first"
    shell.select(0)
    smithy = shell.explore.sell_list
    assert smithy.filters["slot"].value == slot and smithy.sort.value == "price"
    assert {i.id for i in smithy.shown} == {i.id for i in inventory.shown}
    prices = [i.sell_price for i in smithy.shown]
    assert prices == sorted(prices, reverse=True)


def _tabs(shell) -> list[str]:
    [tabs] = [c for c in _walk(shell.explore.shops) if isinstance(c, ft.SegmentedButton)]
    return [segment.label for segment in tabs.segments]


def test_reopening_a_shop_starts_on_the_buy_tab(tmp_path):
    session, shell, _, _ = _rich_smithy(tmp_path)
    assert shell.explore.shop_tab == "sell"
    shell.explore.close()
    shell.explore.open("Smithy")
    assert shell.explore.shop_tab == "buy"


def test_the_buy_tab_filters_and_sorts_by_what_things_cost(tmp_path):
    session, shell, _, _ = _shell(tmp_path)
    explore = shell.explore
    explore.open("Smithy")
    buy = explore.buy_list
    wares = {w.item.id: w for w in session.game.view().shops[0].wares}
    assert buy.heading.value == f"For sale ({len(wares)})"
    assert not buy.select_button.visible  # nothing to do with several at once
    buy.sort.value = "price"
    buy._sort_changed()
    prices = [wares[i.id].price for i in buy.shown]
    assert prices == sorted(prices, reverse=True) and buy.order_button.content == "Highest first"
    slot = buy.shown[0].slot
    buy.filters["slot"].value = slot
    buy._filter_changed()
    assert buy.shown and all(i.slot == slot for i in buy.shown)
    # The Buy tab has its own choices: your pack's filters and sort are untouched.
    shell.select(1)
    assert shell.inventory.pack_list.choices.sort_by == "name"
    assert shell.inventory.pack_list.filters["slot"].value == "all"


def _buy_first(shell):
    """Buy the first ware you can afford."""
    [b for b in _buttons(shell.explore.shops, "Buy · ") if not b.disabled][0].on_click(None)


def _at(shell, pred):
    """Put the player in the start town room whose shop matches `pred`, and refresh."""
    game = shell.explore.session.game
    room = next(p for _, (s, p) in game.world.query(Shop, Position) if pred(s))
    position = game.world.get(game.player, Position)
    position.location, position.room = room.location, room.room
    shell.explore.refresh()


def test_the_upgrade_and_craft_tabs_upgrade_worn_gear_and_craft_recipes(tmp_path):
    from tidewrack.core.economy import crafting
    from tidewrack.core.engine.components import MaterialStack, Wallet
    from tidewrack.core.procgen.material_gen import make_material

    session, shell, toasts, _ = _shell(tmp_path)
    game = session.game
    game.world.get(game.player, Wallet).gold = 200
    for material, n in (("material.iron_ore", 6), ("material.timber", 3)):
        crafting.add(game, MaterialStack(make_material(CONTENT.materials[material]), n), "test")
    explore = shell.explore
    explore.open("Smithy")
    explore._shop_tab(["upgrade"])
    ups = explore.upgrade_list
    assert ups.heading.value == "Upgrades (2)"  # the worn club and coat
    # The worn Driftwood Club can go to +1 (1 timber); its card says so.
    [club] = [
        card
        for card in ups.cards.controls
        if any(t.startswith("Your Driftwood Club (worn)") for t in _texts(card))
    ]
    assert "Seasoned Timber 3/1 ✓" in _texts(club)
    [upgrade] = _buttons(club, "Upgrade · ")
    upgrade.on_click(None)
    assert toasts[-1].startswith("It's now a Driftwood Club +1")
    assert explore.shop_tab == "upgrade"  # stays on the tab
    explore._shop_tab(["craft"])
    assert explore.craft_list.heading.value == "Recipes (4)"
    crafts = [b for b in _buttons(explore.shops, "Craft · ") if not b.disabled]
    assert len(crafts) == 1  # the Cutlass: 3 iron ore and 1 timber
    crafts[0].on_click(None)
    assert toasts[-1].endswith("gold fee.") and len(game.inventory().pack) == 1
    assert explore.shop_tab == "craft"


def test_upgrade_and_craft_lists_filter_and_sort(tmp_path):
    session, shell, _, _ = _shell(tmp_path)
    explore = shell.explore
    explore.open("Smithy")
    explore._shop_tab(["craft"])
    recipes = explore.craft_list
    recipes.sort.value = "price"
    recipes._sort_changed()
    fees = [explore._recipes[i.id].fee for i in recipes.shown]
    assert fees == sorted(fees, reverse=True)
    recipes.filters["slot"].value = "Off hand"
    recipes._filter_changed()
    assert {i.name for i in recipes.shown} == {"Buckler", "Storm Lantern"}
    assert recipes.heading.value == "Recipes (2 of 4 shown)"
    explore._shop_tab(["upgrade"])  # the Upgrade tab shares the craft choices
    assert explore.upgrade_list.choices is recipes.choices


def test_short_materials_are_marked_in_words(tmp_path):
    session, shell, _, _ = _shell(tmp_path)
    shell.explore.open("Smithy")
    shell.explore._shop_tab(["craft"])
    texts = _texts(shell.explore.shops)
    assert "Iron Ore 0/3 ✗ short" in texts
    assert all(b.disabled for b in _buttons(shell.explore.shops, "Craft · "))


def test_the_market_sells_and_buys_materials(tmp_path):
    session, shell, toasts, asked = _shell(tmp_path)
    _at(shell, lambda s: s.buys_materials)
    [market] = _buttons(shell.explore.entrances, "Market · ")
    assert market.content == "Market · materials"
    market.on_click(None)
    assert _tabs(shell) == ["Buy (4)", "Sell (0)"]
    [buy] = [b for b in _buttons(shell.explore.shops, "Buy 1 · ") if "3 gold" in b.content][:1]
    buy.on_click(None)
    assert toasts[-1].startswith("Bought 1 ") and session.game.view().gold < 10
    shell.explore._shop_tab(["sell"])
    assert _tabs(shell)[1] == "Sell (1)"
    [sell_all] = _buttons(shell.explore.shops, "Sell all 1 · ")
    sell_all.on_click(None)
    assert asked[-1].startswith("Sell all your ")
    assert session.game.inventory().materials == ()


def test_the_inventory_lists_materials_and_recipes(tmp_path):
    from tidewrack.core.economy import crafting
    from tidewrack.core.engine.components import MaterialStack
    from tidewrack.core.procgen.material_gen import make_material

    session, shell, _, _ = _shell(tmp_path)
    hide = make_material(CONTENT.materials["material.hide"])
    crafting.add(session.game, MaterialStack(hide, 2), "test")
    shell.select(1)
    texts = _texts(shell.inventory.control)
    assert "Hide × 2" in texts
    assert any(t.startswith("Buckler, Cutlass") for t in texts)


def test_inventory_tabs_show_one_part_at_a_time(tmp_path):
    from tidewrack.core.economy import crafting
    from tidewrack.core.engine.components import MaterialStack
    from tidewrack.core.procgen.material_gen import make_material

    session, shell, _, _ = _shell(tmp_path)
    crafting.add(
        session.game, MaterialStack(make_material(CONTENT.materials["material.hide"]), 2), "x"
    )
    shell.select(1)
    inventory = shell.inventory
    labels = [s.label for s in inventory.tabs.segments]
    assert labels == ["Equipped (2)", "Pack (0)", "Satchel (1)"]
    assert inventory.equipped.visible and not inventory.pack_list.control.visible
    assert not inventory.satchel.visible
    inventory.show_tab("satchel")
    assert inventory.satchel.visible and not inventory.equipped.visible
    shell.select(0)
    shell.select(1)  # the tab is kept while the world is open
    assert inventory.tab == "satchel" and inventory.satchel.visible


def test_the_craft_tab_can_hide_recipes_you_lack_materials_for(tmp_path):
    from tidewrack.core.economy import crafting
    from tidewrack.core.engine.components import MaterialStack
    from tidewrack.core.procgen.material_gen import make_material

    session, shell, _, _ = _shell(tmp_path)
    for material, n in (("material.iron_ore", 3), ("material.timber", 1)):
        crafting.add(
            session.game, MaterialStack(make_material(CONTENT.materials[material]), n), "x"
        )
    explore = shell.explore
    explore.open("Smithy")
    explore._shop_tab(["craft"])
    assert explore.craft_list.heading.value == "Recipes (4)"
    [switch] = [c for c in _walk(explore.shops) if isinstance(c, ft.Switch)]
    assert switch.value is False
    explore._craftable_only(True)
    assert explore.craft_list.heading.value == "Recipes (1)"  # the Cutlass: 3 ore, 1 timber
    assert len(_buttons(explore.shops, "Craft · ")) == 1
    explore.close()
    explore.open("Smithy")
    explore._shop_tab(["craft"])
    assert explore.craft_list.heading.value == "Recipes (1)"  # kept while the world is open


def test_shop_cards_start_collapsed_and_open_one_at_a_time(tmp_path):
    session, shell, _, _ = _shell(tmp_path)
    explore = shell.explore
    explore.open("Smithy")
    buy = explore.buy_list
    first, second, *_ = buy.cards.controls
    assert "Base" not in _texts(first)  # no stat table while collapsed
    assert any(isinstance(c, ft.IconButton) and c.tooltip == "Show details" for c in _walk(first))
    assert _buttons(first, "Buy · ")  # the action stays on a collapsed card
    explore.buy_list.folds.toggle(buy.shown[0].id)
    first, second, *_ = buy.cards.controls
    assert "Base" in _texts(first) and "Base" not in _texts(second)


def test_expand_all_is_remembered_across_screens(tmp_path):
    from tidewrack.services.settings import SettingsStore

    session, shell, _, _ = _shell(tmp_path)
    explore = shell.explore
    explore.open("Smithy")
    [expand_all] = _buttons(explore.buy_list.heading_row, "Expand all")
    expand_all.on_click(None)
    assert all("Base" in _texts(card) for card in explore.buy_list.cards.controls)
    assert SettingsStore(tmp_path / "s.json").load().collapsed == {"buy": False}
    # A new screen (another world, or after a restart) starts expanded too.
    _, again, _, _ = _shell(tmp_path)
    again.explore.open("Smithy")
    assert all("Base" in _texts(card) for card in again.explore.buy_list.cards.controls)
    assert _buttons(again.explore.buy_list.heading_row, "Collapse all")


def test_moving_the_log_keeps_the_card_settings(tmp_path):
    from tidewrack.services.settings import SettingsStore

    _, shell, _, _ = _shell(tmp_path)
    shell.explore.open("Smithy")
    _buttons(shell.explore.buy_list.heading_row, "Expand all")[0].on_click(None)
    shell.explore._toggle_log()
    saved = SettingsStore(tmp_path / "s.json").load()
    assert saved.collapsed == {"buy": False} and saved.log_visible is False


def test_equipped_gear_starts_expanded(tmp_path):
    session, shell, _, _ = _shell(tmp_path)
    shell.select(1)
    worn = shell.inventory.equipped.controls[0]
    assert "Gives" in " ".join(_texts(worn))
    assert any(isinstance(c, ft.IconButton) and c.tooltip == "Hide details" for c in _walk(worn))


def test_a_collapsed_card_counts_set_bonuses(tmp_path):
    from tidewrack.core.engine.components import Carried, Equipped
    from tidewrack.core.procgen.gear_gen import make_item

    session, shell, _, _ = _shell(tmp_path)
    game = session.game

    def gear(gear_id):
        return make_item(CONTENT.gear[gear_id], CONTENT.gearsets)

    game.world.create(gear("gear.oilskin_hood"), Carried(game.player), Equipped("head"))
    game.world.create(gear("gear.sealskin_boots"), Carried(game.player))
    shell.select(1)
    shell.inventory.show_tab("pack")
    [boots] = shell.inventory.pack_list.cards.controls
    texts = _texts(boots)
    # The boots' own DEF 1, plus the Drowned Watch's 2-piece bonus of DEF 2.
    assert "▲ +3" in texts
    assert any(t.startswith("Gains set bonus: Drowned Watch") for t in texts)
    assert "Drowned Watch set" in texts  # the set chip, on the line under the name

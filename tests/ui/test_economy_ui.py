"""Shops, the inn, selling and abandoning in the UI (step 7a)."""

import re

import flet as ft

from tidewrack.core.engine.components import Health, Position, Shop
from tidewrack.core.engine.game import AcceptQuest, Wait
from tidewrack.services.content import load_bundled_content
from tidewrack.ui.components.coins import label_of

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
    """Text values, plus the sentence behind each coins()/purse() row."""
    return [
        label_of(c)
        for c in _walk(control)
        if (isinstance(c, ft.Text) and c.value)
        or (isinstance(c, ft.Row) and isinstance(c.data, str))
    ]


def _buttons(control, starts: str) -> list[ft.Control]:
    return [
        c
        for c in _walk(control)
        if isinstance(c, ft.FilledButton | ft.FilledTonalButton | ft.TextButton | ft.OutlinedButton)
        and label_of(label_of(c.content)).startswith(starts)
    ]


def test_shops_show_as_buttons_until_opened(tmp_path):
    session, shell, _, _ = _shell(tmp_path)
    explore = shell.explore
    labels = [label_of(b.content) for b in _buttons(explore.entrances, "")]
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
    assert affordable and all("(not enough)" in label_of(b.content) for b in buys if b.disabled)
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
    assert label_of(tavern_button.content) == "Tavern · beds 4 gold · kitchen"
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
    assert label_of(inventory.order_button.content) == "Highest first"
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
    assert (
        prices == sorted(prices, reverse=True)
        and label_of(buy.order_button.content) == "Highest first"
    )
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
    assert label_of(market.content) == "Market · materials"
    market.on_click(None)
    assert _tabs(shell) == ["Buy (6)", "Sell (0)"]
    [buy] = [
        b for b in _buttons(shell.explore.shops, "Buy 1 · ") if "3 gold" in label_of(b.content)
    ][:1]
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


def test_the_tavern_kitchen_has_a_menu_and_a_cook_tab(tmp_path):
    from tidewrack.core.economy import crafting
    from tidewrack.core.engine.components import MaterialStack
    from tidewrack.core.procgen.material_gen import make_material

    session, shell, toasts, _ = _shell(tmp_path)
    _at(shell, lambda s: s.cooks)
    explore = shell.explore
    explore.open("Tavern")
    texts = _texts(explore.shops)
    assert any(t.startswith("You haven't eaten.") for t in texts)
    assert _tabs(shell) == ["Menu (4)", "Cook (11)"]
    [buy] = [
        b for b in _buttons(explore.shops, "Buy · ") if re.search(r"\b6 gold", label_of(b.content))
    ]
    buy.on_click(None)  # the Kelp Broth
    assert toasts[-1] == "Kelp Broth bought for 6 gold. Eat it any time."
    explore._shop_tab(["cook"])
    assert "Kelp 0/2 ✗ short" in _texts(explore.shops)
    for m, n in (("material.kelp", 2), ("material.salt", 1)):
        crafting.add(session.game, MaterialStack(make_material(CONTENT.materials[m]), n), "x")
    explore.refresh()
    [cook] = [b for b in _buttons(explore.shops, "Cook · ") if not b.disabled]
    cook.on_click(None)
    assert toasts[-1].startswith("Kelp Broth cooked")
    explore._craftable_only(True)
    assert _buttons(explore.shops, "Cook · ") == []  # nothing else to cook now


def test_eating_from_the_satchel_and_the_status_row(tmp_path):
    from tidewrack.core.engine.components import Wallet
    from tidewrack.core.engine.game import BuyMeal

    session, shell, _, asked = _shell(tmp_path)
    session.game.world.get(session.game.player, Wallet).gold = 50
    _at(shell, lambda s: s.cooks)
    session.perform(BuyMeal("meal.kelp_broth"))
    session.perform(BuyMeal("meal.mussel_stew"))
    shell.select(1)
    inventory = shell.inventory
    inventory.show_tab("satchel")
    assert inventory.tabs.segments[2].label == "Satchel (2)"
    [first, _] = [b for b in _walk(inventory.meals) if getattr(b, "content", None) == "Eat"]
    first.on_click(None)  # no meal yet: eats straight away
    assert asked == [] and session.game.view().fed.name == "Kelp Broth"
    assert inventory.fed.value.startswith("Well fed: Kelp Broth")
    [stew] = [b for b in _walk(inventory.meals) if getattr(b, "content", None) == "Eat"]
    stew.on_click(None)  # replacing a meal asks first
    assert asked == ["Eat the Mussel Stew?"]
    assert session.game.view().fed.name == "Mussel Stew"
    shell.select(0)
    assert "· Fed: Mussel Stew (60)" in shell.explore.status.value


def test_satchel_sections_fold_and_stay_folded(tmp_path):
    from tidewrack.core.economy import crafting
    from tidewrack.core.engine.components import MaterialStack
    from tidewrack.core.procgen.material_gen import make_material

    session, shell, _, _ = _shell(tmp_path)
    for m in ("material.kelp", "material.hide"):
        crafting.add(session.game, MaterialStack(make_material(CONTENT.materials[m]), 2), "x")
    shell.select(1)
    inventory = shell.inventory
    inventory.show_tab("satchel")
    tiles = [c for c in inventory.satchel.controls if isinstance(c, ft.ExpansionTile)]
    assert [t.title.value for t in tiles] == [
        "Meals (0)",
        "Ingredients (1)",
        "Materials (1)",
        "Recipes you know (4)",
    ]
    assert all(t.expanded for t in tiles)
    inventory.satchel_open["materials"] = False  # as if folded by a tap
    inventory.refresh()
    tiles = [c for c in inventory.satchel.controls if isinstance(c, ft.ExpansionTile)]
    assert [t.expanded for t in tiles] == [True, True, False, True]


def _dot(shell, index) -> bool:
    return shell.navigation_bar.destinations[index].icon.badge is not None


def _dotted(segment) -> bool:
    icon_dot = isinstance(segment.icon, ft.Icon) and segment.icon.badge is not None
    label_dot = isinstance(segment.label, ft.Text) and segment.label.badge is not None
    return icon_dot or label_dot


def test_unread_dots_on_the_navigation_bar(tmp_path):
    from tidewrack.core.engine.components import Quest

    session, shell, _, _ = _shell(tmp_path)
    game = session.game
    assert not any(_dot(shell, i) for i in range(4))  # nothing new when the world opens
    quest = game.view().board[0]
    shell.explore.act(AcceptQuest(quest.id))
    assert _dot(shell, 2)  # a new quest
    shell.select(2)
    assert not _dot(shell, 2)  # seen
    shell.select(0)
    next(q for _, (q,) in game.world.query(Quest) if q.quest_id == quest.id).state = "ready"
    shell.update_dots()
    assert _dot(shell, 2)
    shell.select(2)
    assert _dot(shell, 2)  # stays until it's turned in


def test_new_gear_dots_the_inventory_and_its_pack_tab(tmp_path):
    session, shell, _, _ = _shell(tmp_path)
    shell.explore.open("Smithy")
    _buy_first(shell)
    assert _dot(shell, 1)
    shell.select(1)
    inventory = shell.inventory
    assert inventory.tab == "equipped" and _dotted(inventory.tabs.segments[1])
    assert _dot(shell, 1)  # still unseen: you're on Equipped
    inventory.show_tab("pack")
    shell.update_dots()
    assert not _dotted(inventory.tabs.segments[1]) and not _dot(shell, 1)


def test_a_meal_running_out_doesnt_dot_the_inventory(tmp_path):
    from tidewrack.core.engine.components import Meal, WellFed

    session, shell, _, _ = _shell(tmp_path)
    game = session.game
    game.world.add(game.player, WellFed(Meal("meal.x", "Broth", "", regen=1, turns=60), 11))
    shell.explore.act(Wait())
    assert not _dot(shell, 1)  # 10 turns left: nothing new to find there


def test_the_smithy_dots_tabs_with_something_you_can_do(tmp_path):
    from tidewrack.core.economy import crafting
    from tidewrack.core.engine.components import MaterialStack, Wallet
    from tidewrack.core.procgen.material_gen import make_material

    session, shell, _, _ = _shell(tmp_path)
    game = session.game
    game.world.get(game.player, Wallet).gold = 100
    crafting.add(game, MaterialStack(make_material(CONTENT.materials["material.timber"]), 1), "x")
    shell.explore.open("Smithy")
    [tabs] = [c for c in _walk(shell.explore.shops) if isinstance(c, ft.SegmentedButton)]
    dotted = [s.value for s in tabs.segments if isinstance(s.label, ft.Control) and _dotted(s)]
    assert dotted == ["upgrade"]  # the worn Driftwood Club takes 1 timber; no recipe yet


def test_a_smithy_dot_clears_once_you_look_and_stays_clear(tmp_path):
    from tidewrack.core.economy import crafting
    from tidewrack.core.engine.components import MaterialStack, Wallet
    from tidewrack.core.procgen.material_gen import make_material

    session, shell, _, _ = _shell(tmp_path)
    game = session.game
    game.world.get(game.player, Wallet).gold = 100
    timber = make_material(CONTENT.materials["material.timber"])
    crafting.add(game, MaterialStack(timber, 1), "x")
    explore = shell.explore

    def dotted():
        [tabs] = [c for c in _walk(explore.shops) if isinstance(c, ft.SegmentedButton)]
        return [s.value for s in tabs.segments if _dotted(s)]

    explore.open("Smithy")
    assert dotted() == ["upgrade"]
    explore._shop_tab(["upgrade"])  # look
    explore._shop_tab(["buy"])
    assert dotted() == []  # seen; it stays clear
    explore.close()
    explore.open("Smithy")
    assert dotted() == []
    for material in ("material.hide", "material.sailcloth"):  # the coat's upgrade: new
        crafting.add(game, MaterialStack(make_material(CONTENT.materials[material]), 1), "x")
    explore.refresh()
    assert dotted() == ["upgrade"]


def test_learning_more_about_a_foe_isnt_a_new_codex_entry(tmp_path):
    from tidewrack.core.engine.components import Codex, FoeEntry

    session, shell, _, _ = _shell(tmp_path)
    codex = session.game.world.get(session.game.player, Codex)
    codex.foes["enemy.cave_rat"] = FoeEntry("enemy.cave_rat", "Cave Rat", "beast", "Rat.", {})
    shell.update_dots()
    assert _dot(shell, 3)  # a new foe
    shell.select(3)
    codex.kills["enemy.cave_rat"] = 3  # stats and drops revealed
    shell.select(0)
    assert not _dot(shell, 3)


def _new_chips(control) -> int:
    return sum(1 for t in _texts(control) if t == "New")


def test_cards_behind_a_cleared_dot_say_new_until_you_leave(tmp_path):
    session, shell, _, _ = _shell(tmp_path)
    shell.explore.open("Smithy")
    _buy_first(shell)
    inventory = shell.inventory
    shell.select(1)
    assert _new_chips(inventory.pack) == 0  # on Equipped, not looking at the pack yet
    inventory.show_tab("pack")
    assert _new_chips(inventory.pack) == 1  # the dot cleared; the bought card says so
    inventory.refresh()
    assert _new_chips(inventory.pack) == 1  # still there while you stay
    shell.select(0)
    shell.select(1)
    assert _new_chips(inventory.pack) == 0  # you left: gone


def test_switching_inner_tabs_clears_the_new_chips(tmp_path):
    session, shell, _, _ = _shell(tmp_path)
    shell.explore.open("Smithy")
    _buy_first(shell)
    shell.select(1)
    inventory = shell.inventory
    inventory.show_tab("pack")
    inventory.show_tab("satchel")
    inventory.show_tab("pack")
    assert _new_chips(inventory.pack) == 0


def _tap(shell, index: int) -> None:
    """Tap a navigation-bar tab the way Flet does: index first, then on_change."""
    bar = shell.navigation_bar
    bar.selected_index = index
    bar.on_change(ft.ControlEvent(name="change", control=bar, data=str(index)))


def test_new_chips_clear_when_you_tap_away_on_the_navigation_bar(tmp_path):
    session, shell, _, _ = _shell(tmp_path)
    shell.explore.open("Smithy")
    _buy_first(shell)
    _tap(shell, 1)
    shell.inventory.show_tab("pack")
    assert _new_chips(shell.inventory.pack) == 1
    _tap(shell, 0)
    _tap(shell, 1)
    assert _new_chips(shell.inventory.pack) == 0


def test_the_log_glides_to_new_lines_but_jumps_when_opened(tmp_path):
    session, shell, _, _ = _shell(tmp_path)
    explore = shell.explore
    assert explore.log.auto_scroll_animation == 0  # opening the world: already at the end
    explore.act(Wait())
    assert explore.log.auto_scroll_animation is None  # a new line: Flet's glide
    explore._toggle_log()
    explore._toggle_log()
    assert explore.log.auto_scroll_animation == 0  # shown again: straight to the end
    explore.refresh()
    assert explore.log.auto_scroll_animation == 0  # nothing new: still no glide
    explore.act(Wait())
    assert explore.log.auto_scroll_animation is None


def test_the_latest_actions_lines_stay_bold_until_the_next_action(tmp_path):
    session, shell, _, _ = _shell(tmp_path)
    explore = shell.explore

    def bold():
        return [
            c.value
            for c in explore.log.controls
            if isinstance(c, ft.Text) and c.weight == ft.FontWeight.BOLD
        ]

    assert bold() == []  # just opened
    explore.act(Wait())
    first = bold()
    assert first and first[-1] == session.game.view().log[-1]
    explore.refresh()  # e.g. switching tabs: still marked
    assert bold() == first


def test_newly_doable_smithy_cards_say_new_until_you_switch_tab(tmp_path):
    from tidewrack.core.economy import crafting
    from tidewrack.core.engine.components import MaterialStack, Wallet
    from tidewrack.core.procgen.material_gen import make_material

    session, shell, _, _ = _shell(tmp_path)
    game = session.game
    game.world.get(game.player, Wallet).gold = 100
    crafting.add(game, MaterialStack(make_material(CONTENT.materials["material.timber"]), 1), "x")
    explore = shell.explore
    explore.open("Smithy")
    explore._shop_tab(["upgrade"])
    assert _new_chips(explore.shops) == 1  # the worn club's upgrade, newly doable
    explore.refresh()
    assert _new_chips(explore.shops) == 1  # still there while you stay
    explore._shop_tab(["buy"])
    explore._shop_tab(["upgrade"])
    assert _new_chips(explore.shops) == 0  # you left the tab: gone


def test_a_new_material_dots_the_codex_and_opens_its_section(tmp_path):
    from tidewrack.core.economy import crafting
    from tidewrack.core.engine.components import MaterialStack
    from tidewrack.core.procgen.material_gen import make_material

    session, shell, _, _ = _shell(tmp_path)
    game = session.game
    pelt = make_material(CONTENT.materials["material.wolf_pelt"])  # not heard of yet
    crafting.add(game, MaterialStack(pelt, 1), "gathered")
    game.bus.flush()
    shell.update_dots()
    assert _dot(shell, 3)
    shell.select(3)
    assert not _dot(shell, 3)
    by_title = {_section(s): s for s in shell.codex.sections.controls}
    materials = by_title["Materials"]
    assert materials.expanded and _new_chips(materials.title) == 1  # it holds the new one
    assert not by_title["Recipes"].expanded  # nothing new there: closed
    texts = _texts(materials)
    assert "Wolf Pelt" in texts and "You have 1" in texts
    assert any(t.startswith("Markets pay ") and t.endswith(" gold each") for t in texts)
    group = next(g for g in materials.controls if _new_chips(g.title))  # its region's
    assert group.expanded and _new_chips(group) == 1  # and the card itself


def _section(tile) -> str:
    return tile.title.controls[0].value.split(" (")[0]

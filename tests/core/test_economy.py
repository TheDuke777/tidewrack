"""The economy: values and prices, shops, the inn, gold (CLAUDE.md §8.6, step 7a)."""

from dataclasses import replace

from tidewrack.core.data.save import GameState
from tidewrack.core.economy.value_model import (
    STANDARD_ECONOMY,
    EconomyRules,
    buy_price,
    sell_price,
    value,
)
from tidewrack.core.engine.components import Enemy, Health, Position, Quest, Shop, Stocked
from tidewrack.core.engine.events import (
    ActionRejected,
    GoldGained,
    GoldSpent,
    ItemBought,
    ItemSold,
    QuestAbandoned,
    Rested,
)
from tidewrack.core.engine.game import (
    AbandonQuest,
    AcceptQuest,
    Attack,
    Buy,
    Equip,
    Game,
    Move,
    Rest,
    Sell,
    TurnInQuest,
    Wait,
)
from tidewrack.core.gear.item import GearSet, Item
from tidewrack.core.procgen.gear_gen import make_item
from tidewrack.core.procgen.shop_gen import generate_shops
from tidewrack.core.procgen.world_gen import generate_world
from tidewrack.core.quests import quests as questing
from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()
WORLD = generate_world(7, CONTENT.world("world.standard"), CONTENT.roomsets)
TOWN = WORLD.location(WORLD.start)
GATE = TOWN.start
CAVES = WORLD.location("loc_02")


def cutlass(**fields) -> Item:
    return Item(
        **{
            "gear_id": "gear.cutlass",
            "name": "Cutlass",
            "slot": "main_hand",
            "base": {"atk": 4},
            **fields,
        }
    )


def smithy(cap=3, wares=()) -> Shop:
    return Shop("shop.smithy", "Smithy", buys_gear=True, cap=cap, wares=list(wares))


def inn() -> Shop:
    return Shop("shop.tavern", "Tavern", inn=True)


def game_with(*shops, gold=50, economy=STANDARD_ECONOMY, **fields) -> Game:
    """A game in the generated town, with `shops` (shop, stock) at the gate."""
    return Game(
        7,
        WORLD,
        {"atk": 4, "def": 2, "hp": 20},
        gold=gold,
        shops=[(TOWN.id, GATE, shop, stock) for shop, stock in shops],
        economy=economy,
        **fields,
    )


def gold(game: Game) -> int:
    return game.view().gold


def rejected(result) -> list[str]:
    return [e.reason for e in result.events if isinstance(e, ActionRejected)]


# --- value and prices --------------------------------------------------------------


def test_value_counts_stats_upgrades_and_sets():
    plain = cutlass()
    assert value(plain) == 20  # 4 ATK × 5
    assert value(cutlass(roll={"atk": 2})) == 30
    upgradable = cutlass(max_upgrade=3, upgrade_step={"atk": 1})
    assert value(upgradable) == round(20 + 0.25 * 3 * 5)
    assert value(replace(upgradable, upgrade=3)) == 35  # 7 ATK, nothing left to upgrade
    in_set = cutlass(gear_set=GearSet("gearset.x", "X"))
    assert value(in_set) == 24
    assert value(Item(gear_id="g", name="Rag", slot="body")) == 1  # never free


def test_selling_always_pays_less_than_buying():
    for price_rules in (STANDARD_ECONOMY, EconomyRules(sell_factor=1.5)):
        for item in (
            cutlass(),
            Item(gear_id="g", name="Rag", slot="body"),
            cutlass(roll={"atk": 9}),
        ):
            assert sell_price(item, price_rules) < buy_price(item, price_rules)
    assert sell_price(cutlass()) == 6  # 30% of 20


# --- shops -------------------------------------------------------------------------


def test_a_shop_shows_its_wares_with_prices_and_comparisons():
    game = game_with((smithy(), [cutlass(), cutlass(roll={"atk": 2})]), gold=25)
    [shop] = game.view().shops
    assert shop.name == "Smithy" and shop.buys_gear and shop.inn_price is None
    assert [(w.price, w.affordable) for w in shop.wares] == [(20, True), (30, False)]
    assert shop.wares[0].item.comparison.verdict == "better"  # vs bare hands
    assert "The Smithy is open for trade." in game.log


def test_buying_takes_gold_and_puts_the_item_in_your_pack():
    game = game_with((smithy(), [cutlass()]), gold=25)
    ware = game.view().shops[0].wares[0].item
    result = game.perform(Buy(ware.id))
    assert not result.took_turn
    assert [type(e) for e in result.events] == [GoldSpent, ItemBought]
    assert gold(game) == 5
    assert [i.name for i in game.inventory().pack] == ["Cutlass"]
    assert game.view().shops[0].wares == ()
    assert "You buy the Cutlass from the Smithy for 20 gold." in game.log


def test_you_cant_buy_what_you_cant_afford_or_isnt_here():
    game = game_with((smithy(), [cutlass(roll={"atk": 2})]), gold=10)
    ware = game.view().shops[0].wares[0].item
    assert rejected(game.perform(Buy(ware.id))) == ["The Cutlass costs 30 gold; you have 10."]
    game.perform(Move(TOWN.room(GATE).exits[0].label))
    assert rejected(game.perform(Buy(ware.id))) == ["That isn't for sale here."]
    assert gold(game) == 10


def test_selling_pays_and_the_shop_can_sell_it_back_for_more():
    game = game_with((smithy(), []), gold=0)
    sword = game.world.create(cutlass(), *_carried(game))
    assert game.inventory().buyer == "Smithy"
    assert game.inventory().pack[0].sell_price == 6
    result = game.perform(Sell(sword))
    assert [type(e) for e in result.events] == [ItemSold, GoldGained]
    assert gold(game) == 6 and game.inventory().pack == ()
    assert [w.price for w in game.view().shops[0].wares] == [20]  # no buy-back profit


def test_you_cant_sell_worn_gear_or_where_nobody_buys():
    game = game_with((inn(), []))
    sword = game.world.create(cutlass(), *_carried(game))
    assert game.inventory().buyer is None
    assert rejected(game.perform(Sell(sword))) == ["Nobody here buys gear. Try a town's smithy."]
    game = game_with((smithy(), []))
    sword = game.world.create(cutlass(), *_carried(game))
    game.perform(Equip(sword))
    assert rejected(game.perform(Sell(sword))) == ["Take the Cutlass off before selling it."]


def test_shops_restock_from_their_wares_up_to_their_cap():
    rules = EconomyRules(restock_every=2)
    game = game_with((smithy(cap=2, wares=[cutlass(roll={"atk": 1})]), []), economy=rules)
    for _ in range(6):
        game.perform(Wait())
    wares = game.view().shops[0].wares
    assert [w.item.name for w in wares] == ["Cutlass", "Cutlass"]  # stopped at the cap
    entities = [e for e, _ in game.world.query(Item, Stocked)]
    assert len(set(entities)) == 2  # separate copies, not one shared object
    a, b = (game.world.get(e, Item) for e in entities)
    assert a == b and a is not b


# --- the inn -----------------------------------------------------------------------


def test_a_night_at_the_inn_costs_gold_and_heals_fully():
    game = game_with((inn(), []), gold=5)
    assert game.view().shops[0].inn_price == 4
    assert rejected(game.perform(Rest())) == ["You're already rested."]
    game.world.get(game.player, Health).damage = 9
    result = game.perform(Rest())
    assert result.took_turn
    assert any(isinstance(e, Rested) and e.price == 4 for e in result.events)
    assert game.view().hp == game.view().max_hp and gold(game) == 1
    game.world.get(game.player, Health).damage = 9
    assert rejected(game.perform(Rest())) == ["A bed costs 4 gold; you have 1."]


def test_there_is_no_inn_away_from_a_tavern():
    game = game_with((smithy(), []))
    game.world.get(game.player, Health).damage = 9
    assert rejected(game.perform(Rest())) == ["There's no inn here. Every town's tavern has beds."]


# --- earning gold ------------------------------------------------------------------


def test_defeated_enemies_hand_over_their_gold():
    room = next(r for r in CAVES.rooms if r not in CAVES.gates)
    wrecker = Enemy("enemy.wrecker", "Wrecker", "person", "A wrecker.", {"hp": 1}, gold=7)
    game = Game(
        7, WORLD, {"atk": 50, "def": 50, "hp": 50}, enemies=[(CAVES.id, room, wrecker)], gold=0
    )
    position = game.world.get(game.player, Position)
    position.location, position.room = CAVES.id, room
    from tidewrack.core.combat import fight
    from tidewrack.core.engine.events import RoomEntered

    fight.encounter(game, RoomEntered(game.player, CAVES.id, room, CAVES.start, False))
    result = game.perform(Attack())
    assert any(isinstance(e, GoldGained) and e.amount == 7 for e in result.events)
    assert gold(game) == 7
    assert "It drops 7 gold." in game.log


def test_quests_pay_gold_with_their_reward():
    reward = cutlass()
    quest = Quest("q.1", "recover", "Find it", "Find it.", reward, board=TOWN.id, gold=15)
    game = game_with(quests=[quest], gold=0)
    game.perform(AcceptQuest("q.1"))
    questing.find(game, "q.1").achieved = True
    questing.find(game, "q.1").state = "ready"
    game.perform(TurnInQuest("q.1"))
    assert gold(game) == 15
    assert "Quest done: Find it. Your reward: the Cutlass and 15 gold." in game.log


# --- abandoning quests -------------------------------------------------------------


def test_abandoning_puts_a_board_quest_back_and_resets_a_cull():
    quest = Quest(
        "q.1", "cull", "Cull", "Cull.", cutlass(), board=TOWN.id, enemy_id="enemy.x", needed=3
    )
    game = game_with(quests=[quest])
    game.perform(AcceptQuest("q.1"))
    questing.find(game, "q.1").progress = 2
    result = game.perform(AbandonQuest("q.1"))
    assert not result.took_turn
    assert any(isinstance(e, QuestAbandoned) for e in result.events)
    assert questing.find(game, "q.1").state == "posted"
    assert questing.find(game, "q.1").progress == 0
    assert [q.id for q in game.view().board] == ["q.1"]
    assert f"You give up on Cull. The notice goes back up at {TOWN.name}." in game.log
    assert rejected(game.perform(AbandonQuest("q.1"))) == [
        "You can only give up a quest you're still working on."
    ]


def test_an_abandoned_found_quest_goes_on_the_last_towns_board():
    quest = Quest(
        "q.1", "explore", "Chart", "Chart.", cutlass(), source="found", state="active", board=None
    )
    game = game_with(quests=[quest])
    game.perform(AbandonQuest("q.1"))
    assert questing.find(game, "q.1").board == TOWN.id
    assert [q.id for q in game.view().board] == ["q.1"]


# --- saving and the map ------------------------------------------------------------


def test_gold_shops_and_stock_survive_saving():
    game = game_with((smithy(wares=[cutlass()]), [cutlass(roll={"atk": 1})]), (inn(), []), gold=33)
    loaded = Game.from_state(GameState.model_validate(game.to_state().model_dump(mode="json")))
    assert loaded.view() == game.view()
    assert loaded.economy == game.economy
    assert loaded.shop_rng.get_state() == game.shop_rng.get_state()


def test_visited_shop_rooms_are_marked_on_the_area_map():
    game = game_with((smithy(), []))
    gate = next(n for n in game.view().map.nodes if n.id == GATE)
    assert gate.shop


# --- balance lint (§8.6 rules 3 and 4) ---------------------------------------------


def test_no_shop_item_sells_for_more_than_it_costs():
    for seed in range(10):
        for placed in generate_shops(seed, WORLD, CONTENT):
            for item in placed.stock + placed.shop.wares:
                assert sell_price(item) < buy_price(item)


def test_quest_rewards_and_best_finds_beat_any_shop_copy():
    """Top-tier gear is never for sale: a shop's best copy of any gear is worth less
    than that gear's best roll (what quest rewards get, before their affix)."""
    for shop in CONTENT.shops.values():
        for gear_id in shop.gear:
            gear = CONTENT.gear[gear_id]
            best_shop = make_item(
                gear,
                CONTENT.gearsets,
                {s: low + (high - low) // 2 for s, (low, high) in gear.rolls.items()},
            )
            best = make_item(
                gear, CONTENT.gearsets, {s: high for s, (_, high) in gear.rolls.items()}
            )
            if gear.rolls:
                assert value(best_shop) < value(best), gear_id


def _carried(game: Game):
    from tidewrack.core.engine.components import Carried

    return (Carried(game.player),)

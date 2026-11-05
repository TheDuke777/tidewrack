"""Materials, markets, crafting, upgrades and the buy-back shelf (CLAUDE.md §8.6, step 7b)."""

import pytest

from tidewrack.core.combat import fight
from tidewrack.core.data.save import GameState
from tidewrack.core.economy import crafting
from tidewrack.core.economy.value_model import (
    STANDARD_ECONOMY,
    EconomyRules,
    craft_fee,
    material_buy_price,
    material_sell_price,
    sell_price,
    upgrade_fee,
)
from tidewrack.core.engine.components import (
    Enemy,
    Material,
    MaterialStack,
    Position,
    Quest,
    Recipe,
    RecipePage,
    Shop,
)
from tidewrack.core.engine.events import (
    ItemCrafted,
    ItemUpgraded,
    MaterialsGained,
    RecipeLearned,
    RoomEntered,
)
from tidewrack.core.engine.game import (
    AcceptQuest,
    Attack,
    Buy,
    BuyMaterials,
    Craft,
    Game,
    Sell,
    SellMaterials,
    TurnInQuest,
    Upgrade,
    Wait,
)
from tidewrack.core.gear.item import Item
from tidewrack.core.procgen.material_gen import known_recipes, make_material
from tidewrack.core.procgen.world_gen import generate_world
from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()
WORLD = generate_world(7, CONTENT.world("world.standard"), CONTENT.roomsets)
TOWN = WORLD.location(WORLD.start)
GATE = TOWN.start
CAVES = WORLD.location("loc_02")
ORE = make_material(CONTENT.materials["material.iron_ore"])
TIMBER = make_material(CONTENT.materials["material.timber"])


def cutlass(**fields) -> Item:
    return Item(
        **{
            "gear_id": "gear.cutlass",
            "name": "Cutlass",
            "slot": "main_hand",
            "base": {"atk": 4},
            "max_upgrade": 3,
            "upgrade_step": {"atk": 1},
            **fields,
        }
    )


def smithy(**fields) -> Shop:
    return Shop(
        "shop.smithy",
        "Smithy",
        buys_gear=True,
        crafts=True,
        upgrades={"gear.cutlass": [MaterialStack(ORE, 2)]},
        **fields,
    )


def market() -> Shop:
    return Shop("shop.market", "Market", materials=[ORE, TIMBER], buys_materials=True)


def game_with(*shops, gold=100, recipes=(), economy=STANDARD_ECONOMY, **fields) -> Game:
    return Game(
        7,
        WORLD,
        {"atk": 4, "def": 2, "hp": 20},
        gold=gold,
        shops=[(TOWN.id, GATE, shop, stock) for shop, stock in shops],
        recipes=recipes,
        economy=economy,
        **fields,
    )


def satchel(game: Game) -> dict[str, int]:
    return {m.id: m.count for m in game.inventory().materials}


def give(game: Game, material: Material, count: int) -> None:
    crafting.add(game, MaterialStack(material, count), "test")


def rejected(result) -> list[str]:
    from tidewrack.core.engine.events import ActionRejected

    return [e.reason for e in result.events if isinstance(e, ActionRejected)]


# --- prices ------------------------------------------------------------------------


def test_material_prices_and_fees_derive_from_value():
    assert material_buy_price(ORE) == 3  # value 2 × 1.5 markup
    assert material_sell_price(ORE) == 1
    for rules in (STANDARD_ECONOMY, EconomyRules(sell_factor=2.0)):
        for value in (1, 2, 6, 40):
            material = Material("m", "M", "", value)
            assert material_sell_price(material, rules) < material_buy_price(material, rules)
    plain = cutlass()
    assert craft_fee(plain) == 12  # value 24 (20 + 0.25 × 3 × 5) × 0.5
    assert [upgrade_fee(cutlass(upgrade=u)) for u in (0, 1, 2)] == [5, 10, 15]


# --- the satchel: gathering, drops, markets ----------------------------------------


def test_walking_into_a_room_gathers_what_lies_there():
    room = next(r for r in CAVES.rooms if r not in CAVES.gates)
    game = Game(7, WORLD, gathering=[(CAVES.id, room, MaterialStack(ORE, 3))])
    game.bus.emit(RoomEntered(game.player, CAVES.id, room, CAVES.start, True))
    events = game.bus.flush()
    assert any(isinstance(e, MaterialsGained) and e.source == "gathered" for e in events)
    assert satchel(game) == {"material.iron_ore": 3}
    assert "You gather 3 Iron Ore." in game.log
    assert not list(game.world.query(MaterialStack, Position))


def test_defeated_enemies_hand_over_their_materials():
    room = next(r for r in CAVES.rooms if r not in CAVES.gates)
    boar = Enemy(
        "enemy.wild_boar",
        "Wild Boar",
        "beast",
        "A boar.",
        {"hp": 1},
        materials=[MaterialStack(make_material(CONTENT.materials["material.hide"]), 2)],
    )
    game = Game(7, WORLD, {"atk": 50, "def": 50, "hp": 50}, enemies=[(CAVES.id, room, boar)])
    position = game.world.get(game.player, Position)
    position.location, position.room = CAVES.id, room
    fight.encounter(game, RoomEntered(game.player, CAVES.id, room, CAVES.start, False))
    game.perform(Attack())
    assert satchel(game) == {"material.hide": 2}
    assert "You take 2 Hide." in game.log


def test_a_market_sells_and_buys_materials():
    game = game_with((market(), []), gold=10)
    [shop] = game.view().shops
    assert [(m.material.name, m.price) for m in shop.materials] == [
        ("Iron Ore", 3),
        ("Seasoned Timber", 3),
    ]
    result = game.perform(BuyMaterials("material.iron_ore", 3))
    assert not result.took_turn and game.view().gold == 1
    assert satchel(game) == {"material.iron_ore": 3}
    assert rejected(game.perform(BuyMaterials("material.timber", 1))) == [
        "1 Seasoned Timber costs 3 gold; you have 1."
    ]
    game.perform(SellMaterials("material.iron_ore", 2))
    assert game.view().gold == 3 and satchel(game) == {"material.iron_ore": 1}
    assert rejected(game.perform(SellMaterials("material.iron_ore", 5))) == [
        "You don't have that many."
    ]
    assert "The Market trades in materials." in game.log


def test_no_material_trading_away_from_a_market():
    game = game_with((smithy(), []))
    give(game, ORE, 2)
    assert rejected(game.perform(SellMaterials("material.iron_ore", 1))) == [
        "Nobody here buys materials. Try a town's market."
    ]
    assert rejected(game.perform(BuyMaterials("material.iron_ore", 1))) == [
        "Nobody here sells that."
    ]


# --- crafting ----------------------------------------------------------------------


def recipe() -> Recipe:
    return Recipe(
        "recipe.cutlass",
        "Cutlass",
        cutlass(roll={"atk": 2}),
        [MaterialStack(ORE, 3), MaterialStack(TIMBER, 1)],
    )


def test_crafting_uses_materials_and_a_fee_and_makes_the_gear():
    game = game_with((smithy(), []), gold=50, recipes=[recipe()])
    [view] = game.view().shops[0].recipes
    assert view.name == "Cutlass" and not view.can_craft
    assert [(c.name, c.need, c.have) for c in view.materials] == [
        ("Iron Ore", 3, 0),
        ("Seasoned Timber", 1, 0),
    ]
    assert rejected(game.perform(Craft("recipe.cutlass"))) == [
        "You need 3 Iron Ore and 1 Seasoned Timber more."
    ]
    give(game, ORE, 4)
    give(game, TIMBER, 1)
    fee = view.fee
    assert game.view().shops[0].recipes[0].can_craft
    result = game.perform(Craft("recipe.cutlass"))
    assert not result.took_turn
    assert any(isinstance(e, ItemCrafted) for e in result.events)
    assert game.view().gold == 50 - fee
    assert satchel(game) == {"material.iron_ore": 1}
    assert [i.name for i in game.inventory().pack] == ["Cutlass"]
    assert game.inventory().pack[0].total["atk"] == 6
    assert f"The smith makes you a Cutlass for {fee} gold." in game.log


def test_crafting_needs_a_smithy_a_known_recipe_and_the_fee():
    assert rejected(
        game_with((market(), []), recipes=[recipe()]).perform(Craft("recipe.cutlass"))
    ) == ["Crafting needs a smithy. Every town has one."]
    assert rejected(game_with((smithy(), [])).perform(Craft("recipe.cutlass"))) == [
        "You don't know how to make that."
    ]
    poor = game_with((smithy(), []), gold=1, recipes=[recipe()])
    give(poor, ORE, 3)
    give(poor, TIMBER, 1)
    fee = craft_fee(recipe().makes)
    assert rejected(poor.perform(Craft("recipe.cutlass"))) == [
        f"The fee is {fee} gold; you have 1."
    ]
    assert satchel(poor) == {"material.iron_ore": 3, "material.timber": 1}  # nothing used


# --- upgrades ----------------------------------------------------------------------


def test_upgrading_takes_more_materials_and_gold_each_level():
    game = game_with((smithy(), [cutlass()]), gold=100)
    game.perform(Buy(game.view().shops[0].wares[0].item.id))
    gold = game.view().gold
    give(game, ORE, 12)
    item = game.inventory().pack[0].id
    for level in (1, 2, 3):
        [up] = game.view().shops[0].upgrades
        assert up.materials[0].need == 2 * level and up.fee == 5 * level
        assert up.upgraded.name == f"Cutlass +{level}"
        result = game.perform(Upgrade(item))
        assert any(isinstance(e, ItemUpgraded) and e.level == level for e in result.events)
    assert game.view().gold == gold - (5 + 10 + 15)
    assert satchel(game) == {}  # 2 + 4 + 6 ore
    assert game.view().shops[0].upgrades == ()  # fully upgraded
    assert rejected(game.perform(Upgrade(item))) == ["The Cutlass +3 is fully upgraded."]
    assert game.inventory().pack[0].total["atk"] == 7


def test_gear_the_smithy_has_no_upgrade_for_cant_be_upgraded():
    game = game_with((smithy(), [Item(gear_id="gear.rag", name="Rag", slot="body")]))
    game.perform(Buy(game.view().shops[0].wares[0].item.id))
    rag = game.inventory().pack[0].id
    assert rejected(game.perform(Upgrade(rag))) == ["The Rag can't be upgraded."]


def test_an_upgrade_never_pays_for_itself_by_selling():
    for level in range(3):
        before, after = cutlass(upgrade=level), cutlass(upgrade=level + 1)
        assert sell_price(after) - sell_price(before) < upgrade_fee(before)


# --- recipes found and taught --------------------------------------------------------


def test_a_recipe_page_is_learned_when_you_walk_in():
    room = next(r for r in CAVES.rooms if r not in CAVES.gates)
    game = Game(7, WORLD, recipe_pages=[(CAVES.id, room, RecipePage(recipe()))])
    game.bus.emit(RoomEntered(game.player, CAVES.id, room, CAVES.start, True))
    events = game.bus.flush()
    assert any(isinstance(e, RecipeLearned) and e.source == "found" for e in events)
    assert game.inventory().recipes == ("Cutlass",)
    assert "You find a recipe: Cutlass. Any smithy can make it." in game.log


def test_a_quest_can_teach_a_recipe_when_turned_in():
    quest = Quest(
        "q.1", "recover", "Find it", "Find it.", cutlass(), board=TOWN.id, recipe=recipe()
    )
    game = Game(7, WORLD, quests=[quest])
    game.perform(AcceptQuest("q.1"))
    next(q for _, (q,) in game.world.query(Quest)).state = "ready"
    assert game.quests().ready[0].recipe == "Cutlass"
    game.perform(TurnInQuest("q.1"))
    assert game.inventory().recipes == ("Cutlass",)


def test_new_worlds_know_the_basic_recipes():
    game = Game(7, WORLD, recipes=known_recipes(CONTENT))
    assert set(game.inventory().recipes) == {"Buckler", "Cutlass", "Miner's Helm", "Storm Lantern"}


# --- the buy-back shelf ------------------------------------------------------------


def test_only_the_newest_sold_gear_stays_on_the_shelf():
    economy = EconomyRules(buyback=2)
    game = game_with((smithy(cap=0), [cutlass() for _ in range(4)]), gold=500, economy=economy)
    bought = []
    for ware in game.view().shops[0].wares:
        game.perform(Buy(ware.item.id))
        bought.append(ware.item.id)
    for item in bought:
        game.perform(Sell(item))
    wares = game.view().shops[0].wares
    assert [w.item.id for w in wares] == bought[-2:]
    assert all(w.sold_by_you for w in wares)
    game.perform(Buy(bought[-1]))
    shop = next(s for _, (s,) in game.world.query(Shop))
    assert shop.buyback == [bought[-2]]


def test_sold_gear_doesnt_stop_restocking():
    economy = EconomyRules(restock_every=1)
    stock = smithy(cap=1, wares=[cutlass()])
    game = game_with((stock, [cutlass()]), economy=economy)
    game.perform(Buy(game.view().shops[0].wares[0].item.id))
    game.perform(Sell(game.inventory().pack[0].id))
    game.perform(Wait())
    wares = game.view().shops[0].wares
    assert len(wares) == 2 and [w.sold_by_you for w in wares] == [True, False]


# --- saving --------------------------------------------------------------------------


def test_materials_recipes_and_shelves_survive_saving():
    game = game_with((smithy(), [cutlass()]), (market(), []), recipes=[recipe()])
    give(game, ORE, 2)
    game.perform(Buy(game.view().shops[0].wares[0].item.id))
    game.perform(Sell(game.inventory().pack[0].id))
    loaded = Game.from_state(GameState.model_validate(game.to_state().model_dump()))
    assert loaded.view() == game.view() and loaded.inventory() == game.inventory()


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_generated_worlds_have_markets_and_smithies_that_craft(seed):
    import tempfile
    from pathlib import Path

    from tidewrack.services.session import GameSession
    from tidewrack.services.storage import FileSaveStore

    session = GameSession.generate(
        FileSaveStore(Path(tempfile.mkdtemp())), CONTENT, "world.standard", "W", seed
    )
    shops = [s for _, (s,) in session.game.world.query(Shop)]
    assert any(s.crafts and s.upgrades for s in shops)
    assert any(s.materials and s.buys_materials for s in shops)
    assert len(session.game.inventory().recipes) == 4


# --- regrowth ----------------------------------------------------------------------


def test_wild_places_regrow_gathering_spots_up_to_their_cap():
    from tidewrack.core.engine.components import GrowEntry, Grower

    grower = Grower(CAVES.id, cap=2, materials=[GrowEntry(ORE, 1.0)], low=2, high=2)
    economy = EconomyRules(regrow_every=1)
    game = Game(7, WORLD, growers=[grower], economy=economy)
    game.perform(Wait())
    spots = [p for _, (_, p) in game.world.query(MaterialStack, Position)]
    assert len(spots) == 1 and spots[0].location == CAVES.id
    assert spots[0].room not in CAVES.gates
    for _ in range(5):
        game.perform(Wait())
    spots = [p for _, (_, p) in game.world.query(MaterialStack, Position)]
    assert len(spots) == 2 and len({p.room for p in spots}) == 2  # the cap, in two rooms
    # Saving keeps the stream, so a loaded game regrows the same way.
    loaded = Game.from_state(GameState.model_validate(game.to_state().model_dump()))
    for g in (game, loaded):
        stack = next(e for e, _ in g.world.query(MaterialStack, Position))
        g.world.destroy(stack)  # as if gathered
        g.perform(Wait())
    rooms = [
        sorted(p.room for _, (_, p) in g.world.query(MaterialStack, Position))
        for g in (game, loaded)
    ]
    assert rooms[0] == rooms[1]


def test_nothing_regrows_in_the_room_youre_standing_in():
    from tidewrack.core.engine.components import GrowEntry, Grower

    rooms = [r for r in CAVES.rooms if r not in CAVES.gates]
    game = Game(
        7,
        WORLD,
        growers=[Grower(CAVES.id, cap=len(rooms), materials=[GrowEntry(ORE, 1.0)])],
        economy=EconomyRules(regrow_every=1),
    )
    position = game.world.get(game.player, Position)
    position.location, position.room = CAVES.id, rooms[0]
    for _ in range(len(rooms) + 3):
        game.perform(Wait())
    spots = {p.room for _, (_, p) in game.world.query(MaterialStack, Position)}
    assert rooms[0] not in spots and len(spots) == len(rooms) - 1


def test_new_worlds_regrow_every_wild_kind_of_place():
    from tidewrack.core.procgen.material_gen import generate_growers

    growers = generate_growers(WORLD, CONTENT)
    kinds = {WORLD.location(g.location).kind for g in growers}
    assert kinds == {loc.kind for loc in WORLD.locations.values()} - {"Town"}
    assert all(g.cap >= 2 and g.materials for g in growers)

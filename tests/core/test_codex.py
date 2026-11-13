"""The codex's item sections: materials, ingredients, recipes, meals (v0.10.2)."""

from tidewrack.core.codex import items
from tidewrack.core.codex.foes import DROPS_AT
from tidewrack.core.combat import fight
from tidewrack.core.data.save import GameState
from tidewrack.core.economy import crafting
from tidewrack.core.engine.components import (
    Carried,
    Codex,
    Enemy,
    Equipped,
    GrowEntry,
    Grower,
    Material,
    MaterialStack,
    Meal,
    MealRecipe,
    Position,
    Quest,
    Recipe,
    RecipePage,
    Shop,
)
from tidewrack.core.engine.events import RoomEntered
from tidewrack.core.engine.game import Attack, Game
from tidewrack.core.gear.item import Item
from tidewrack.core.procgen.material_gen import make_material
from tidewrack.core.procgen.world_gen import generate_world
from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()
WORLD = generate_world(7, CONTENT.world("world.standard"), CONTENT.roomsets, CONTENT.regions)
TOWN = WORLD.location(WORLD.start)
COAST = TOWN.region
CAVES = next(loc for loc in WORLD.locations.values() if loc.region == COAST and not loc.town)
FAR = next(  # a place in the deepest region, which a new player hasn't found
    loc
    for loc in WORLD.locations.values()
    if loc.region == max(WORLD.regions.values(), key=lambda r: r.tier).id and not loc.town
)
ROOM = next(r for r in CAVES.rooms if r not in CAVES.gates)
ORE = make_material(CONTENT.materials["material.iron_ore"])
HIDE = make_material(CONTENT.materials["material.hide"])
KELP = make_material(CONTENT.materials["material.kelp"])
SALT = make_material(CONTENT.materials["material.salt"])
BROTH = Meal("meal.broth", "Kelp Broth", "Warm.", {}, regen=3, turns=5, value=3)


def entries(game: Game) -> dict[str, items.MaterialEntryView]:
    view = game.codex()
    return {e.material.id: e for e in (*view.materials, *view.ingredients)}


def give(game: Game, material: Material, count: int, source: str) -> None:
    crafting.add(game, MaterialStack(material, count), source)
    game.bus.flush()  # outside a command, events wait for a flush


def recipe(material: Material = ORE, count: int = 2) -> Recipe:
    return Recipe(
        "recipe.cutlass",
        "Cutlass",
        Item("gear.cutlass", "Cutlass", "main_hand", base={"atk": 4}),
        [MaterialStack(material, count)],
    )


def boar(**fields) -> Enemy:
    return Enemy(
        "enemy.wild_boar",
        "Wild Boar",
        "beast",
        "A boar.",
        {"hp": 1},
        materials=[MaterialStack(HIDE, 1)],
        **fields,
    )


def fight_in(game: Game, room: str) -> None:
    position = game.world.get(game.player, Position)
    position.location, position.room = CAVES.id, room
    fight.encounter(game, RoomEntered(game.player, CAVES.id, room, CAVES.start, False))
    game.perform(Attack())


# --- discovery ---------------------------------------------------------------------


def test_the_codex_starts_with_what_your_recipes_need():
    game = Game(7, WORLD, recipes=[recipe()])
    assert list(game.world.get(game.player, Codex).materials) == ["material.iron_ore"]
    [ore] = game.codex().materials
    assert ore.material.count == 0 and ore.uses == ("Crafting: Cutlass ×2",)


def test_gathering_looting_and_learning_add_entries():
    game = Game(7, WORLD)
    assert entries(game) == {}
    give(game, KELP, 2, "gathered")
    page = RecipePage(recipe(SALT, 1))
    game.world.create(page, Position(CAVES.id, ROOM))
    game.bus.emit(RoomEntered(game.player, CAVES.id, ROOM, CAVES.start, True))
    game.bus.flush()
    assert set(entries(game)) == {"material.kelp", "material.salt"}
    assert entries(game)["material.kelp"].material.count == 2
    assert [e.material.name for e in game.codex().ingredients] == ["Kelp", "Salt"]


def test_a_market_or_tavern_you_walk_into_is_recorded():
    tavern = Shop(
        "shop.tavern",
        "Tavern",
        cooks=True,
        meals=[MealRecipe(BROTH, [MaterialStack(KELP, 2), MaterialStack(SALT, 1)], sold=True)],
    )
    market = Shop("shop.market", "Market", materials=[ORE], buys_materials=True)
    room = next(r for r in TOWN.rooms if r != TOWN.start)
    game = Game(7, WORLD, shops=[(TOWN.id, room, tavern, []), (TOWN.id, room, market, [])])
    assert entries(game) == {} and game.codex().meals == ()  # not been in yet
    game.bus.emit(RoomEntered(game.player, TOWN.id, room, TOWN.start, True))
    game.bus.flush()
    assert set(entries(game)) == {"material.kelp", "material.salt", "material.iron_ore"}
    [broth] = game.codex().meals
    assert broth.meal.name == "Kelp Broth" and broth.price is not None
    assert [(c.name, c.need, c.have) for c in broth.ingredients] == [
        ("Kelp", 2, 0),
        ("Salt", 1, 0),
    ]
    assert entries(game)["material.kelp"].uses == ("Cooking: Kelp Broth ×2",)
    assert entries(game)["material.iron_ore"].sold_at.startswith("Markets in ")


def test_more_learned_about_an_entry_is_not_a_new_entry():
    game = Game(7, WORLD, {"atk": 50, "def": 50, "hp": 50}, enemies=[(CAVES.id, ROOM, boar())])
    before = items.keys(game)
    fight_in(game, ROOM)
    new = items.keys(game) - before
    assert new == {("foe", "enemy.wild_boar"), ("material", "material.hide")}
    after = items.keys(game)
    give(game, HIDE, 3, "gathered")
    game.world.get(game.player, Codex).kills["enemy.wild_boar"] = DROPS_AT
    assert items.keys(game) == after


# --- where it's found --------------------------------------------------------------


def test_foes_are_named_once_they_dropped_it_for_you_or_you_know_their_drops():
    rooms = [r for r in CAVES.rooms if r not in CAVES.gates][:2]
    wolf = Enemy(
        "enemy.moor_wolf", "Moor Wolf", "beast", "A wolf.", {"hp": 1},
        materials=[MaterialStack(HIDE, 1)],
    )  # fmt: skip
    game = Game(
        7,
        WORLD,
        {"atk": 50, "def": 50, "hp": 50},
        enemies=[(CAVES.id, rooms[0], boar()), (CAVES.id, rooms[1], wolf)],
    )
    give(game, HIDE, 1, "bought")
    assert entries(game)["material.hide"].dropped_by == items.UNKNOWN_FOES
    fight_in(game, rooms[0])
    assert entries(game)["material.hide"].dropped_by == f"Wild Boar; {items.UNKNOWN_FOES}"
    codex = game.world.get(game.player, Codex)
    codex.foes["enemy.moor_wolf"] = codex.foes["enemy.wild_boar"]  # met, but drops unknown
    assert entries(game)["material.hide"].dropped_by == f"Wild Boar; {items.UNKNOWN_FOES}"
    codex.kills["enemy.moor_wolf"] = DROPS_AT  # now its drops are known
    assert "Wild Boar" in entries(game)["material.hide"].dropped_by
    assert items.UNKNOWN_FOES not in entries(game)["material.hide"].dropped_by


def test_places_in_regions_you_havent_found_stay_unnamed():
    grower = Grower(FAR.id, 2, [GrowEntry(KELP)])
    near = Grower(CAVES.id, 2, [GrowEntry(KELP)])
    game = Game(7, WORLD, growers=[near, grower])
    give(game, KELP, 1, "gathered")
    region = WORLD.regions[COAST].name
    assert entries(game)["material.kelp"].gathered == (
        f"{CAVES.kind} ({region}); {items.UNFOUND_PLACES}"
    )
    assert entries(game)["material.kelp"].region == region
    explorer = game._explorer()
    explorer.locations_discovered.add(FAR.id)
    assert WORLD.regions[FAR.region].name in entries(game)["material.kelp"].gathered


def test_something_only_found_far_away_is_listed_further_afield():
    game = Game(7, WORLD, growers=[Grower(FAR.id, 2, [GrowEntry(KELP)])])
    give(game, KELP, 1, "gathered")
    assert entries(game)["material.kelp"].region == items.ELSEWHERE
    assert entries(game)["material.kelp"].gathered == items.UNFOUND_PLACES


def test_uses_include_upgrades_for_gear_you_carry():
    smithy = Shop("shop.smithy", "Smithy", crafts=True, upgrades={"gear.cutlass": [
        MaterialStack(ORE, 2)
    ]})  # fmt: skip
    game = Game(7, WORLD, shops=[(TOWN.id, TOWN.start, smithy, [])])
    sword = Item("gear.cutlass", "Cutlass", "main_hand", base={"atk": 4}, max_upgrade=3)
    game.world.create(sword, Carried(game.player), Equipped("main_hand"))
    give(game, ORE, 1, "bought")
    assert entries(game)["material.iron_ore"].uses == ("Upgrading your Cutlass",)
    sword.upgrade = 3  # fully upgraded: nothing left to use it on
    assert entries(game)["material.iron_ore"].uses == ()


# --- recipes -----------------------------------------------------------------------


def test_recipes_say_how_many_more_are_out_there():
    other = Recipe("recipe.helm", "Helm", Item("gear.helm", "Helm", "head"), [])
    third = Recipe("recipe.boots", "Boots", Item("gear.boots", "Boots", "feet"), [])
    quest = Quest("q.1", "explore", "T", "S", Item("gear.x", "X", "head"), recipe=third)
    game = Game(
        7,
        WORLD,
        recipes=[recipe()],
        quests=[quest],
        recipe_pages=[(CAVES.id, ROOM, RecipePage(other))],
    )
    view = game.codex().recipes
    assert [r.name for r in view.known] == ["Cutlass"]
    assert view.to_find == (
        "2 more recipes to find: 1 written down somewhere in the wild and 1 as a quest reward."
    )
    game.bus.emit(RoomEntered(game.player, CAVES.id, ROOM, CAVES.start, True))
    game.bus.flush()
    assert game.codex().recipes.to_find == "1 more recipe to find: 1 as a quest reward."
    quest.state = "done"
    assert game.codex().recipes.to_find is None


# --- saving ------------------------------------------------------------------------


def test_the_codex_survives_saving():
    game = Game(7, WORLD, {"atk": 50, "def": 50, "hp": 50}, enemies=[(CAVES.id, ROOM, boar())])
    fight_in(game, ROOM)
    state = GameState.model_validate_json(game.to_state().model_dump_json())
    loaded = Game.from_state(state)
    assert entries(loaded)["material.hide"].dropped_by == entries(game)["material.hide"].dropped_by
    assert loaded.world.get(loaded.player, Codex) == game.world.get(game.player, Codex)

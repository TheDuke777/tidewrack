"""Ingredients, the tavern's kitchen, meals and their buffs (CLAUDE.md §8.6, step 7c)."""

from tidewrack.core.data.save import GameState
from tidewrack.core.economy import cooking, crafting
from tidewrack.core.economy.value_model import cook_fee, meal_price
from tidewrack.core.engine.components import (
    Health,
    MaterialStack,
    Meal,
    MealRecipe,
    Shop,
    WellFed,
)
from tidewrack.core.engine.events import ActionRejected, MealEaten, MealWoreOff
from tidewrack.core.engine.game import BuyMeal, Cook, Eat, Game, Wait
from tidewrack.core.procgen.material_gen import make_material, meal_recipes
from tidewrack.core.procgen.world_gen import generate_world
from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()
WORLD = generate_world(7, CONTENT.world("world.standard"), CONTENT.roomsets, CONTENT.regions)
TOWN = WORLD.location(WORLD.start)
KELP = make_material(CONTENT.materials["material.kelp"])
SALT = make_material(CONTENT.materials["material.salt"])
BROTH = Meal("meal.broth", "Kelp Broth", "Warm.", {}, regen=3, turns=5, value=3)
ROAST = Meal("meal.roast", "Boar Roast", "Hearty.", {"atk": 2, "hp": 6}, turns=3, value=4)


def tavern() -> Shop:
    return Shop(
        "shop.tavern",
        "Tavern",
        inn=True,
        cooks=True,
        meals=[
            MealRecipe(BROTH, [MaterialStack(KELP, 2), MaterialStack(SALT, 1)], sold=True),
            MealRecipe(ROAST, [MaterialStack(KELP, 1)]),
        ],
    )


def game_with(gold=50) -> Game:
    return Game(
        7,
        WORLD,
        {"atk": 4, "def": 2, "hp": 20},
        gold=gold,
        shops=[(TOWN.id, TOWN.start, tavern(), [])],
    )


def rejected(result) -> list[str]:
    return [e.reason for e in result.events if isinstance(e, ActionRejected)]


def give(game, material, n):
    crafting.add(game, MaterialStack(material, n), "test")


def test_meal_prices_and_fees_come_from_value():
    assert meal_price(BROTH) == 6 and cook_fee(BROTH) == 2  # value 3: ×2, ×0.5
    recipes = {r.meal.meal_id: r for r in meal_recipes(CONTENT)}
    assert recipes["meal.kelp_broth"].meal.value == 3  # 2 kelp + 1 salt
    assert all(m.ingredient for r in recipes.values() for m in (s.material for s in r.ingredients))


def test_cooking_uses_ingredients_and_a_fee():
    game = game_with(gold=10)
    [broth, roast] = game.view().shops[0].menu
    assert broth.price == 6 and roast.price is None  # only the broth is sold ready-made
    assert not broth.can_cook
    assert rejected(game.perform(Cook("meal.broth"))) == ["You need 2 Kelp and 1 Salt more."]
    give(game, KELP, 2)
    give(game, SALT, 1)
    result = game.perform(Cook("meal.broth"))
    assert not result.took_turn and game.view().gold == 8
    assert crafting.held(game) == {}
    assert [(m.name, m.count) for m in game.inventory().meals] == [("Kelp Broth", 1)]
    assert "The cook makes you a Kelp Broth for 2 gold. It keeps until you eat it." in game.log


def test_buying_a_ready_meal_and_only_where_its_sold():
    game = game_with(gold=10)
    game.perform(BuyMeal("meal.broth"))
    assert game.view().gold == 4 and game.inventory().meals[0].count == 1
    assert rejected(game.perform(BuyMeal("meal.roast"))) == ["Nobody here sells that."]
    assert rejected(game.perform(BuyMeal("meal.broth"))) == [
        "The Kelp Broth costs 6 gold; you have 4."
    ]


def test_eating_gives_a_buff_that_ticks_down_and_wears_off():
    game = game_with()
    give(game, KELP, 1)
    game.perform(Cook("meal.roast"))
    atk, max_hp = game.view().stats["atk"], game.max_hp()
    result = game.perform(Eat("meal.roast"))
    assert any(isinstance(e, MealEaten) and e.replaced is None for e in result.events)
    assert game.inventory().meals == ()
    assert game.view().stats["atk"] == atk + 2 and game.max_hp() == max_hp + 6
    assert game.view().fed.turns_left == 3
    assert any(s.label == "Boar Roast (3 turns)" for s in game.sheet().sources)
    game.world.get(game.player, Health).damage = max_hp + 3  # hurt into the bonus HP
    game.perform(Wait())
    game.perform(Wait())
    result = game.perform(Wait())
    assert any(isinstance(e, MealWoreOff) for e in result.events)
    assert game.view().fed is None and game.view().stats["atk"] == atk
    assert game.hp() >= 1  # losing the max-HP buff never knocks you out
    assert "The Boar Roast has worn off." in game.log


def test_a_new_meal_replaces_the_old_one():
    game = game_with(gold=50)
    game.perform(BuyMeal("meal.broth"))
    give(game, KELP, 1)
    game.perform(Cook("meal.roast"))
    game.perform(Eat("meal.roast"))
    result = game.perform(Eat("meal.broth"))
    [eaten] = [e for e in result.events if isinstance(e, MealEaten)]
    assert eaten.replaced == "Boar Roast"
    assert game.view().fed.name == "Kelp Broth"
    assert game.world.get(game.player, WellFed).turns_left == 5


def test_regen_meals_heal_faster():
    plain, fed = game_with(), game_with()
    fed.perform(BuyMeal("meal.broth"))
    fed.perform(Eat("meal.broth"))
    for game in (plain, fed):
        game.world.get(game.player, Health).damage = 15
        for _ in range(game.rules.regen_every):
            game.perform(Wait())
    healed = [15 - g.world.get(g.player, Health).damage for g in (plain, fed)]
    assert healed[1] == healed[0] + 3


def test_you_cant_cook_away_from_a_tavern_or_eat_what_you_dont_have():
    game = Game(7, WORLD)
    assert rejected(game.perform(Cook("meal.broth"))) == [
        "Cooking needs a tavern's kitchen. Every town has one."
    ]
    assert rejected(game.perform(Eat("meal.broth"))) == ["You don't have that to eat."]


def test_eating_isnt_allowed_mid_fight():
    from tidewrack.core.engine.game import ALLOWED_IN_COMBAT

    assert Eat not in ALLOWED_IN_COMBAT


def test_meals_and_buffs_survive_saving():
    game = game_with()
    game.perform(BuyMeal("meal.broth"))
    game.perform(BuyMeal("meal.broth"))
    game.perform(Eat("meal.broth"))
    loaded = Game.from_state(GameState.model_validate(game.to_state().model_dump()))
    assert loaded.view() == game.view() and loaded.inventory() == game.inventory()
    assert cooking.fed(loaded) is not None


def test_the_meal_lint_catches_a_meal_too_strong_for_its_ingredients():
    from economy_sim import lint_meals

    from tidewrack.core.data.schemas import MealSchema

    assert lint_meals(CONTENT) == []
    greedy = MealSchema(
        id="meal.greedy",
        name="Greedy",
        description="Too good.",
        ingredients={"material.salt": 1},
        stats={"atk": 10},
        sold=True,
    )
    content = replace_meals(CONTENT, {"meal.greedy": greedy})
    assert any("too strong" in p for p in lint_meals(content))


def replace_meals(content, meals):
    from dataclasses import replace

    return replace(content, meals=meals)

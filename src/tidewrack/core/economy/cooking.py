"""Cooking and meals (CLAUDE.md §8.6, step 7c).

Functions over a Game, like core.economy.crafting. Ingredients are materials
marked `ingredient`, held in the same satchel. A tavern that `cooks` makes any of
its meals from ingredients for a small fee, and sells the `sold` ones ready-made
at a markup. Meals go in the player's Meals and can be eaten any time outside a
fight. Eating gives the meal's buff (stats, extra regen) for its `turns`, as a
WellFed component; one meal at a time, so a new one replaces the old. Every
turn the buff ticks down (meal_system), and it wears off at zero.

Cooking, buying and eating are free actions, like trading.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from tidewrack.core.economy import crafting, shops
from tidewrack.core.economy.value_model import cook_fee, meal_price
from tidewrack.core.engine.components import Meal, MealRecipe, Meals, MealStack, Shop, WellFed
from tidewrack.core.engine.events import (
    ActionRejected,
    MealBought,
    MealCooked,
    MealEaten,
    MealWoreOff,
)

if TYPE_CHECKING:
    from tidewrack.core.engine.game import Game


def held(game: Game) -> dict[str, MealStack]:
    return game.world.get(game.player, Meals).held


def fed(game: Game) -> WellFed | None:
    return game.world.try_get(game.player, WellFed)


def buff(game: Game) -> dict[str, int]:
    """The stats the active meal adds (none when not fed)."""
    well_fed = fed(game)
    return dict(well_fed.meal.stats) if well_fed else {}


def extra_regen(game: Game) -> int:
    well_fed = fed(game)
    return well_fed.meal.regen if well_fed else 0


def _add(game: Game, meal: Meal) -> None:
    pantry = held(game)
    if meal.meal_id in pantry:
        pantry[meal.meal_id].count += 1
    else:
        pantry[meal.meal_id] = MealStack(copy.deepcopy(meal), 1)


def kitchen_here(game: Game) -> tuple[int, Shop] | None:
    return next(((e, s) for e, s in shops.shops_here(game) if s.cooks), None)


def _recipe(shop: Shop, meal_id: str) -> MealRecipe | None:
    return next((r for r in shop.meals if r.meal.meal_id == meal_id), None)


# --- commands ----------------------------------------------------------------------


def cook(game: Game, meal_id: str) -> None:
    kitchen = kitchen_here(game)
    recipe = _recipe(kitchen[1], meal_id) if kitchen else None
    if kitchen is None:
        game.bus.emit(ActionRejected("Cooking needs a tavern's kitchen. Every town has one."))
        return
    if recipe is None:
        game.bus.emit(ActionRejected("They don't cook that here."))
        return
    fee = cook_fee(recipe.meal, game.economy)
    if short := crafting.missing(game, recipe.ingredients):
        game.bus.emit(ActionRejected(f"You need {_and(short)} more."))
    elif shops.gold(game) < fee:
        game.bus.emit(ActionRejected(f"The fee is {fee} gold; you have {shops.gold(game)}."))
    else:
        crafting.use(game, recipe.ingredients)
        shops.pay(game, fee, "cooking")
        _add(game, recipe.meal)
        game.bus.emit(MealCooked(meal_id, recipe.meal.name, fee))


def buy_meal(game: Game, meal_id: str) -> None:
    kitchen = kitchen_here(game)
    recipe = _recipe(kitchen[1], meal_id) if kitchen else None
    if kitchen is None or recipe is None or not recipe.sold:
        game.bus.emit(ActionRejected("Nobody here sells that."))
        return
    price = meal_price(recipe.meal, game.economy)
    if shops.gold(game) < price:
        game.bus.emit(
            ActionRejected(
                f"The {recipe.meal.name} costs {price} gold; you have {shops.gold(game)}."
            )
        )
        return
    shops.pay(game, price, "meal")
    _add(game, recipe.meal)
    game.bus.emit(MealBought(meal_id, recipe.meal.name, price, kitchen[1].name))


def eat(game: Game, meal_id: str) -> None:
    pantry = held(game)
    stack = pantry.get(meal_id)
    if stack is None:
        game.bus.emit(ActionRejected("You don't have that to eat."))
        return
    stack.count -= 1
    if stack.count <= 0:
        del pantry[meal_id]
    before = fed(game)
    replaced = before.meal.name if before else None
    if before is not None:
        game.world.remove(game.player, WellFed)
    game.world.add(game.player, WellFed(copy.deepcopy(stack.meal), stack.meal.turns))
    game.bus.emit(MealEaten(meal_id, stack.meal.name, stack.meal.turns, replaced))


# --- systems -----------------------------------------------------------------------


def meal_system(game: Game) -> None:
    """Per turn: the active meal's buff ticks down and wears off at zero."""
    well_fed = fed(game)
    if well_fed is None:
        return
    well_fed.turns_left -= 1
    if well_fed.turns_left <= 0:
        game.world.remove(game.player, WellFed)
        game.clamp_health()  # losing a max-HP buff never knocks you out
        game.bus.emit(MealWoreOff(well_fed.meal.meal_id, well_fed.meal.name))


def _and(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"

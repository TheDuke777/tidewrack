"""Materials and crafting (CLAUDE.md §8.6, step 7b).

Functions over a Game, like core.economy.shops. Materials are counts in the
player's Materials satchel, not items: gathered when you walk into a room where
some lie, taken from enemies you defeat, and bought and sold at a market.
A smithy that crafts upgrades gear (its `upgrades` table says which materials
each level takes) and makes gear from the recipes you know. Recipes are known
from the start, found as pages in rooms, or taught by a quest you turn in.

Fees come from core.economy.value_model under the world's EconomyRules; the
materials come on top. Every action here is free (no turn passes), like buying.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from tidewrack.core.economy import shops
from tidewrack.core.economy.value_model import (
    craft_fee,
    material_buy_price,
    material_sell_price,
    upgrade_fee,
)
from tidewrack.core.engine.components import (
    Carried,
    Materials,
    MaterialStack,
    Position,
    Recipe,
    RecipePage,
    Recipes,
    Shop,
)
from tidewrack.core.engine.events import (
    ActionRejected,
    ItemCrafted,
    ItemUpgraded,
    MaterialsBought,
    MaterialsGained,
    MaterialsSold,
    RecipeLearned,
    RoomEntered,
)
from tidewrack.core.gear.item import Item

if TYPE_CHECKING:
    from tidewrack.core.engine.game import Game


# --- the satchel -------------------------------------------------------------------


def held(game: Game) -> dict[str, MaterialStack]:
    return game.world.get(game.player, Materials).held


def count(game: Game, material_id: str) -> int:
    stack = held(game).get(material_id)
    return stack.count if stack else 0


def add(game: Game, stack: MaterialStack, source: str) -> None:
    if stack.count <= 0:
        return
    satchel = held(game)
    mine = satchel.get(stack.material.material_id)
    if mine is None:
        satchel[stack.material.material_id] = MaterialStack(
            copy.deepcopy(stack.material), stack.count
        )
    else:
        mine.count += stack.count
    game.bus.emit(
        MaterialsGained(stack.material.material_id, stack.material.name, stack.count, source)
    )


def _take(game: Game, material_id: str, amount: int) -> None:
    satchel = held(game)
    satchel[material_id].count -= amount
    if satchel[material_id].count <= 0:
        del satchel[material_id]


def missing(game: Game, needs: list[MaterialStack], times: int = 1) -> list[str]:
    """What's short, e.g. ["2 Iron Ore"] (empty if you have it all)."""
    short = []
    for need in needs:
        lacking = need.count * times - count(game, need.material.material_id)
        if lacking > 0:
            short.append(f"{lacking} {need.material.name}")
    return short


def _use(game: Game, needs: list[MaterialStack], times: int = 1) -> None:
    for need in needs:
        _take(game, need.material.material_id, need.count * times)


# --- recipes -----------------------------------------------------------------------


def known(game: Game) -> dict[str, Recipe]:
    return game.world.get(game.player, Recipes).known


def learn(game: Game, recipe: Recipe, source: str) -> None:
    recipes = known(game)
    if recipe.recipe_id in recipes:
        return
    recipes[recipe.recipe_id] = copy.deepcopy(recipe)
    game.bus.emit(RecipeLearned(recipe.recipe_id, recipe.name, source))


def on_room_entered(game: Game, event: RoomEntered) -> None:
    """Gather materials and learn recipe pages lying here."""
    if event.entity != game.player:
        return
    here = (event.location, event.room)
    for entity, (stack, position) in game.world.query(MaterialStack, Position):
        if (position.location, position.room) == here:
            game.world.destroy(entity)
            add(game, stack, "gathered")
    for entity, (page, position) in game.world.query(RecipePage, Position):
        if (position.location, position.room) == here:
            game.world.destroy(entity)
            learn(game, page.recipe, "found")


# --- at a shop ---------------------------------------------------------------------


def _here(game: Game, want: str) -> tuple[int, Shop] | None:
    return next(((e, s) for e, s in shops.shops_here(game) if getattr(s, want)), None)


def smithy_here(game: Game) -> tuple[int, Shop] | None:
    return _here(game, "crafts")


def market_here(game: Game) -> tuple[int, Shop] | None:
    """A shop here that sells or buys materials."""
    return next(
        ((e, s) for e, s in shops.shops_here(game) if s.materials or s.buys_materials), None
    )


def buy_materials(game: Game, material_id: str, amount: int) -> None:
    market = market_here(game)
    material = next(
        (m for m in (market[1].materials if market else []) if m.material_id == material_id), None
    )
    if market is None or material is None:
        game.bus.emit(ActionRejected("Nobody here sells that."))
        return
    if amount < 1:
        game.bus.emit(ActionRejected("Buy at least one."))
        return
    price = material_buy_price(material, game.economy) * amount
    if shops.gold(game) < price:
        game.bus.emit(
            ActionRejected(
                f"{amount} {material.name} costs {price} gold; you have {shops.gold(game)}."
            )
        )
        return
    shops.pay(game, price, "materials")
    add(game, MaterialStack(material, amount), "bought")
    game.bus.emit(MaterialsBought(material_id, material.name, amount, price, market[1].name))


def sell_materials(game: Game, material_id: str, amount: int) -> None:
    market = market_here(game)
    stack = held(game).get(material_id)
    if market is None or not market[1].buys_materials:
        game.bus.emit(ActionRejected("Nobody here buys materials. Try a town's market."))
    elif stack is None or amount < 1 or stack.count < amount:
        game.bus.emit(ActionRejected("You don't have that many."))
    else:
        price = material_sell_price(stack.material, game.economy) * amount
        name = stack.material.name
        _take(game, material_id, amount)
        game.bus.emit(MaterialsSold(material_id, name, amount, price, market[1].name))
        shops.gain(game, price, "sale")


def craft(game: Game, recipe_id: str) -> None:
    recipe = known(game).get(recipe_id)
    if smithy_here(game) is None:
        game.bus.emit(ActionRejected("Crafting needs a smithy. Every town has one."))
        return
    if recipe is None:
        game.bus.emit(ActionRejected("You don't know how to make that."))
        return
    fee = craft_fee(recipe.makes, game.economy)
    if short := missing(game, recipe.materials):
        game.bus.emit(ActionRejected(f"You need {_and(short)} more."))
    elif shops.gold(game) < fee:
        game.bus.emit(ActionRejected(f"The fee is {fee} gold; you have {shops.gold(game)}."))
    else:
        _use(game, recipe.materials)
        shops.pay(game, fee, "crafting")
        item = copy.deepcopy(recipe.makes)
        entity = game.world.create(item, Carried(game.player))
        game.bus.emit(ItemCrafted(entity, item.gear_id, item.display_name, fee))


def upgrade_needs(game: Game, item: Item, shop: Shop) -> list[MaterialStack] | None:
    """Materials for `item`'s next level at `shop`, or None if it can't be upgraded."""
    per_level = shop.upgrades.get(item.gear_id)
    if per_level is None or item.upgrade >= item.max_upgrade:
        return None
    level = item.upgrade + 1
    return [MaterialStack(s.material, s.count * level) for s in per_level]


def upgrade(game: Game, entity: int) -> None:
    smithy = smithy_here(game)
    item = game.world.try_get(entity, Item)
    carried = game.world.try_get(entity, Carried)
    if smithy is None:
        game.bus.emit(ActionRejected("Upgrades need a smithy. Every town has one."))
        return
    if item is None or carried is None or carried.by != game.player:
        game.bus.emit(ActionRejected("You aren't carrying that."))
        return
    needs = upgrade_needs(game, item, smithy[1])
    if needs is None:
        reason = "is fully upgraded" if item.max_upgrade else "can't be upgraded"
        game.bus.emit(ActionRejected(f"The {item.display_name} {reason}."))
        return
    fee = upgrade_fee(item, game.economy)
    if short := missing(game, needs):
        game.bus.emit(ActionRejected(f"You need {_and(short)} more."))
    elif shops.gold(game) < fee:
        game.bus.emit(ActionRejected(f"The fee is {fee} gold; you have {shops.gold(game)}."))
    else:
        _use(game, needs)
        shops.pay(game, fee, "upgrade")
        item.upgrade += 1
        game.bus.emit(ItemUpgraded(entity, item.gear_id, item.display_name, item.upgrade, fee))


def _and(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"

"""Shops: buying, selling, a night at the inn, and restocking (CLAUDE.md §8.6).

Functions over a Game, like core.combat.fight and core.quests.quests:
Game.perform calls `buy`, `sell` and `rest`, and `restock_system` runs every
turn. Shops are made at world creation (core/procgen/shop_gen.py); each is an
entity with Shop and Position, and its wares for sale are Items with Stocked.

Prices all come from core.economy.value_model under the world's EconomyRules.
Buying and selling are free actions; resting at an inn takes a turn. Gear you
sell goes on that shop's buy-back shelf (at the full price): only the newest
EconomyRules.buyback pieces stay, older ones are gone for good. The shelf doesn't
count towards restocking, which only tops up the shop's own stock.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from tidewrack.core.economy.value_model import buy_price, sell_price
from tidewrack.core.engine.components import (
    Carried,
    Equipped,
    Health,
    Position,
    Shop,
    Stocked,
    Wallet,
)
from tidewrack.core.engine.events import (
    ActionRejected,
    GoldGained,
    GoldSpent,
    ItemBought,
    ItemSold,
    Rested,
)
from tidewrack.core.gear.item import Item

if TYPE_CHECKING:
    from tidewrack.core.engine.game import Game


def gold(game: Game) -> int:
    return game.world.get(game.player, Wallet).gold


def gain(game: Game, amount: int, source: str) -> None:
    if amount > 0:
        game.world.get(game.player, Wallet).gold += amount
        game.bus.emit(GoldGained(amount, source))


def pay(game: Game, amount: int, on: str) -> None:
    game.world.get(game.player, Wallet).gold -= amount
    game.bus.emit(GoldSpent(amount, on))


def shops_here(game: Game) -> list[tuple[int, Shop]]:
    """Shops in the player's room, in the order they were made."""
    here = game.world.get(game.player, Position)
    return [
        (entity, shop)
        for entity, (shop, position) in game.world.query(Shop, Position)
        if (position.location, position.room) == (here.location, here.room)
    ]


def wares(game: Game, shop: int) -> list[tuple[int, Item]]:
    """What a shop has for sale, oldest first."""
    return [(e, item) for e, (item, s) in game.world.query(Item, Stocked) if s.shop == shop]


def buyer_here(game: Game) -> tuple[int, Shop] | None:
    """The shop here that buys gear, if any."""
    return next(((e, s) for e, s in shops_here(game) if s.buys_gear), None)


# --- commands ----------------------------------------------------------------------


def buy(game: Game, entity: int) -> None:
    stocked = game.world.try_get(entity, Stocked)
    here = dict(shops_here(game))
    if stocked is None or stocked.shop not in here:
        game.bus.emit(ActionRejected("That isn't for sale here."))
        return
    item = game.world.get(entity, Item)
    price = buy_price(item, game.economy)
    if gold(game) < price:
        game.bus.emit(
            ActionRejected(f"The {item.display_name} costs {price} gold; you have {gold(game)}.")
        )
        return
    pay(game, price, "gear")
    game.world.remove(entity, Stocked)
    shop = here[stocked.shop]
    if entity in shop.buyback:
        shop.buyback.remove(entity)
    game.world.add(entity, Carried(game.player))
    game.bus.emit(
        ItemBought(entity, item.gear_id, item.display_name, price, here[stocked.shop].name)
    )


def sell(game: Game, entity: int) -> None:
    item = game.world.try_get(entity, Item)
    carried = game.world.try_get(entity, Carried)
    buyer = buyer_here(game)
    if item is None or carried is None or carried.by != game.player:
        game.bus.emit(ActionRejected("You aren't carrying that."))
    elif buyer is None:
        game.bus.emit(ActionRejected("Nobody here buys gear. Try a town's smithy."))
    elif game.world.has(entity, Equipped):
        game.bus.emit(ActionRejected(f"Take the {item.display_name} off before selling it."))
    else:
        shop_entity, shop = buyer
        price = sell_price(item, game.economy)
        game.world.remove(entity, Carried)
        game.world.add(entity, Stocked(shop_entity))
        shop.buyback.append(entity)
        for old in shop.buyback[: -game.economy.buyback or None]:
            game.world.destroy(old)
        del shop.buyback[: -game.economy.buyback or None]
        game.bus.emit(ItemSold(entity, item.gear_id, item.display_name, price, shop.name))
        gain(game, price, "sale")


def rest(game: Game) -> bool:
    """A night at the inn: a full heal for the inn's price. True if it took a turn."""
    location, _ = game.here()
    health = game.world.get(game.player, Health)
    price = game.economy.inn_price
    if not any(shop.inn for _, shop in shops_here(game)):
        game.bus.emit(ActionRejected("There's no inn here. Every town's tavern has beds."))
    elif not health.damage:
        game.bus.emit(ActionRejected("You're already rested."))
    elif gold(game) < price:
        game.bus.emit(ActionRejected(f"A bed costs {price} gold; you have {gold(game)}."))
    else:
        pay(game, price, "rest")
        health.damage = 0
        game.bus.emit(Rested(location.id, price))
        return True
    return False


# --- systems -----------------------------------------------------------------------


def restock_system(game: Game) -> None:
    """Per turn: on every Nth turn, each shop under its cap regains one ware."""
    if game.turn % game.economy.restock_every:
        return
    for entity, (shop,) in game.world.query(Shop):
        if shop.wares and len(wares(game, entity)) - len(shop.buyback) < shop.cap:
            ware = copy.deepcopy(game.shop_rng.choice(shop.wares))
            game.world.create(ware, Stocked(entity))

"""Enchanting (v0.13.0): an Enchanter puts an enchantment in a carried piece's
prefix or suffix slot, replacing whatever affix was there, for materials and a
small fee. Enchantments are affixes with effects (core.gear.effects), so an
enchanted item needs nothing new in a save. Free, like the Smithy's work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tidewrack.core.economy import crafting, shops
from tidewrack.core.engine.components import Carried, EnchantOffer, Shop
from tidewrack.core.engine.events import ActionRejected, ItemEnchanted
from tidewrack.core.gear.item import Affix, Item, slots_taken

if TYPE_CHECKING:
    from tidewrack.core.engine.game import Game

FEE_PER_TIER = 5  # gold: the Enchanter's fee is this × the tier (materials are the cost)
ROMAN = ("I", "II", "III", "IV")


def enchanter_here(game: Game) -> tuple[int, Shop] | None:
    return next(((e, s) for e, s in shops.shops_here(game) if s.enchants), None)


def fee(offer: EnchantOffer) -> int:
    return FEE_PER_TIER * offer.tier


def fits(offer: EnchantOffer, item: Item) -> bool:
    """Whether `offer` can go on `item` (a two-hander counts as a main-hand piece)."""
    return any(slot in offer.slots for slot in slots_taken(item)[:1])


def replaces(offer: EnchantOffer, item: Item) -> str | None:
    """The affix enchanting would remove, if any (the one in the same slot)."""
    return next((a.name for a in item.affixes if a.prefix == offer.prefix), None)


def offer(shop: Shop, enchant_id: str, tier: int) -> EnchantOffer | None:
    return next((o for o in shop.enchants if (o.enchant_id, o.tier) == (enchant_id, tier)), None)


def enchant(game: Game, entity: int, enchant_id: str, tier: int) -> None:
    here = enchanter_here(game)
    item = game.world.try_get(entity, Item)
    carried = game.world.try_get(entity, Carried)
    if here is None:
        game.bus.emit(ActionRejected("Enchanting needs an Enchanter. Every town has one."))
        return
    if item is None or carried is None or carried.by != game.player:
        game.bus.emit(ActionRejected("You aren't carrying that."))
        return
    found = offer(here[1], enchant_id, tier)
    if found is None:
        game.bus.emit(ActionRejected(f"The {here[1].name} can't do that enchantment."))
        return
    if not fits(found, item):
        game.bus.emit(ActionRejected(f"{found.name} can't go on the {item.display_name}."))
        return
    cost = fee(found)
    if short := crafting.missing(game, found.materials):
        game.bus.emit(ActionRejected(f"You need {_and(short)} more."))
        return
    if shops.gold(game) < cost:
        game.bus.emit(ActionRejected(f"The fee is {cost} gold; you have {shops.gold(game)}."))
        return
    crafting.use(game, found.materials)
    shops.pay(game, cost, "enchant")
    lost = replaces(found, item)
    item.affixes = [a for a in item.affixes if a.prefix != found.prefix]
    item.affixes.append(
        Affix(
            id=f"{found.enchant_id}.{found.tier}",
            name=found.name,
            prefix=found.prefix,
            stats=dict(found.stats),
            effects=list(found.effects),
        )
    )
    game.bus.emit(
        ItemEnchanted(entity, item.display_name, found.name, ROMAN[found.tier - 1], lost, cost)
    )


def _and(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"

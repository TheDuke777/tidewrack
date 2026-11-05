"""Every item's one internal value, and the prices derived from it (CLAUDE.md §8.6).

    value = stats (item total, at STAT_VALUES gold a point)
          + a share of what its remaining upgrades would add
          , × SET_FACTOR if it belongs to a gear set
          , at least 1

Buying, selling, crafting fees and upgrade fees all derive from `value` through
the world's EconomyRules, so prices can never drift apart. Materials have a value
of their own (content), priced the same way with a market markup on buying. Selling always gets
less than buying, so buy → sell loops lose gold (tests/core/test_economy.py and
sim/economy_sim.py check this for every item that can be in a shop).

Prices are worked out when shown, never stored on items, so a change here
reprices old worlds too. Treat it like any other balance change.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

from tidewrack.core.engine.components import Material, Meal
from tidewrack.core.gear.item import Item
from tidewrack.core.gear.stat_pipeline import item_total
from tidewrack.core.gear.stats import STAT_VALUES, full

UPGRADE_SHARE = 0.25  # of what the remaining upgrade levels would add
SET_FACTOR = 1.2


@dataclass(frozen=True)
class EconomyRules:
    """The world's prices and shop timing: a snapshot saved with each world, like
    core.combat.rules.Rules, so a later difficulty setting can change them."""

    buy_factor: float = 1.0  # shop price = value × this
    sell_factor: float = 0.3  # what a shop pays = value × this (always below buying)
    inn_price: int = 4  # gold for a night at the inn (a full heal)
    restock_every: int = 40  # turns between each shop regaining one ware
    material_markup: float = 1.5  # a market charges value × buy_factor × this
    craft_fee: float = 0.5  # a smithy's fee to craft = what it makes' value × this
    upgrade_fee: float = 1.0  # per level reached, × the value one level adds
    buyback: int = 6  # gear you sold that a shop keeps on its shelf (newest)
    meal_markup: float = 2.0  # a tavern's ready meal = its value × buy_factor × this
    cook_fee: float = 0.5  # a tavern's fee to cook a meal = its value × this


STANDARD_ECONOMY = EconomyRules()


def stats_value(block: dict[str, int]) -> float:
    return sum(STAT_VALUES[s] * v for s, v in full(block).items())


def value(item: Item) -> int:
    """What an item is worth, in gold."""
    worth = stats_value(item_total(item))
    remaining = max(0, item.max_upgrade - item.upgrade)
    worth += UPGRADE_SHARE * remaining * stats_value(item.upgrade_step)
    if item.gear_set is not None:
        worth *= SET_FACTOR
    return max(1, round(worth))


def buy_price(item: Item, rules: EconomyRules = STANDARD_ECONOMY) -> int:
    return max(1, ceil(value(item) * rules.buy_factor))


def sell_price(item: Item, rules: EconomyRules = STANDARD_ECONOMY) -> int:
    """What a shop pays: always less than its buy price, and at least 1 unless the
    item would only cost 1."""
    return min(max(1, floor(value(item) * rules.sell_factor)), buy_price(item, rules) - 1)


# --- materials and crafting (step 7b) -----------------------------------------------


def material_buy_price(material: Material, rules: EconomyRules = STANDARD_ECONOMY) -> int:
    """What a market charges for one."""
    return max(1, ceil(material.value * rules.buy_factor * rules.material_markup))


def material_sell_price(material: Material, rules: EconomyRules = STANDARD_ECONOMY) -> int:
    """What a market pays for one: always less than it charges."""
    return min(
        max(1, floor(material.value * rules.sell_factor)),
        material_buy_price(material, rules) - 1,
    )


def craft_fee(makes: Item, rules: EconomyRules = STANDARD_ECONOMY) -> int:
    """A smithy's fee for crafting `makes` (the materials come on top)."""
    return max(1, ceil(value(makes) * rules.craft_fee))


def upgrade_fee(item: Item, rules: EconomyRules = STANDARD_ECONOMY) -> int:
    """A smithy's fee to raise `item` one level: more for each level up."""
    level = item.upgrade + 1
    return max(1, ceil(stats_value(item.upgrade_step) * rules.upgrade_fee * level))


# --- meals (step 7c) ----------------------------------------------------------------
# A meal's value is its ingredients' (worked out at world creation). Meals can't be
# sold, so cooking and buying them can't loop into gold.


def meal_price(meal: Meal, rules: EconomyRules = STANDARD_ECONOMY) -> int:
    """What a tavern charges for one ready-made."""
    return max(1, ceil(meal.value * rules.buy_factor * rules.meal_markup))


def cook_fee(meal: Meal, rules: EconomyRules = STANDARD_ECONOMY) -> int:
    """A tavern's fee for cooking it (the ingredients come on top)."""
    return max(1, ceil(meal.value * rules.cook_fee))

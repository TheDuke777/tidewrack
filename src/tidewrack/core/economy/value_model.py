"""Every item's one internal value, and the prices derived from it (CLAUDE.md §8.6).

    value = stats (item total, at STAT_VALUES gold a point)
          + a share of what its remaining upgrades would add
          , × SET_FACTOR if it belongs to a gear set
          , at least 1

Buying, selling (and, from step 7b, crafting) all derive from `value` through
the world's EconomyRules, so prices can never drift apart. Selling always gets
less than buying, so buy → sell loops lose gold (tests/core/test_economy.py and
sim/economy_sim.py check this for every item that can be in a shop).

Prices are worked out when shown, never stored on items, so a change here
reprices old worlds too. Treat it like any other balance change.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

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

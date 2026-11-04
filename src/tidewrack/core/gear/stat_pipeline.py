"""The one stat pipeline every number about gear comes from (CLAUDE.md §8.4).

    base (definition + roll) → upgrades → affixes → [set bonuses] → total

The first three stages belong to a single item; set bonuses depend on what else
is equipped, so they're applied to a whole loadout by `player_stats`. Both the
base and the total comparison in compare.py call these functions, so the two can
never disagree with each other or with the stats the game uses.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace

from tidewrack.core.gear import stats
from tidewrack.core.gear.item import GearSet, Item, SetBonus
from tidewrack.core.gear.stats import StatBlock


def item_base(item: Item) -> StatBlock:
    """The definition's base stats plus this copy's roll."""
    return stats.add(item.base, item.roll)


def item_upgraded(item: Item) -> StatBlock:
    return stats.add(item_base(item), stats.scale(item.upgrade_step, item.upgrade))


def item_total(item: Item) -> StatBlock:
    """Everything the item gives on its own (set bonuses are per loadout)."""
    return stats.total([item_upgraded(item), *(a.stats for a in item.affixes)])


def at_max_upgrade(item: Item) -> Item | None:
    """The item fully upgraded, or None if it can't be upgraded any further."""
    if item.upgrade >= item.max_upgrade:
        return None
    return replace(item, upgrade=item.max_upgrade)


def active_set_bonuses(items: Iterable[Item]) -> list[tuple[GearSet, SetBonus]]:
    """Every set bonus `items` (a loadout) earn, by set in first-seen order."""
    counts: dict[str, int] = {}
    sets: dict[str, GearSet] = {}
    for item in items:
        if item.gear_set is not None:
            counts[item.gear_set.id] = counts.get(item.gear_set.id, 0) + 1
            sets.setdefault(item.gear_set.id, item.gear_set)
    return [
        (gear_set, bonus)
        for set_id, gear_set in sets.items()
        for bonus in gear_set.bonuses
        if counts[set_id] >= bonus.pieces
    ]


@dataclass(frozen=True)
class StatSource:
    label: str  # "Base", an item's name, or "<set> (2 pieces)"
    stats: StatBlock


@dataclass(frozen=True)
class StatSheet:
    total: StatBlock
    sources: tuple[StatSource, ...]  # what adds up to the total, in order


def player_stats(base: Mapping[str, int], equipped: Iterable[Item]) -> StatSheet:
    """The player's stats with `equipped` on: base + item totals + set bonuses."""
    equipped = list(equipped)
    sources = [StatSource("Base", stats.full(base))]
    sources += [StatSource(item.display_name, item_total(item)) for item in equipped]
    sources += [
        StatSource(f"{gear_set.name} ({bonus.pieces} pieces)", stats.full(bonus.stats))
        for gear_set, bonus in active_set_bonuses(equipped)
    ]
    return StatSheet(stats.total(s.stats for s in sources), tuple(sources))

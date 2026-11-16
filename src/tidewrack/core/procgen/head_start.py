"""Dev-build head starts (step 8b): a new world begun in a later region.

For playtesting deep regions without replaying the early game: the player wears
the best gear of the regions before it, at its best roll and fully upgraded,
the way a thorough player would arrive. Only dev builds offer it (ui/dev.py).

A region's gear is what its places' finds, its towns' shops and its enemies'
loot can give, plus what recipes make from that gear (with their affixes).
Nothing here touches an RNG, so a head start never shifts a world's streams.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import NamedTuple

from tidewrack.core.data.loader import Content
from tidewrack.core.economy.value_model import stats_value, value
from tidewrack.core.gear.item import SLOTS, Item
from tidewrack.core.gear.stat_pipeline import player_stats
from tidewrack.core.procgen.gear_gen import make_item
from tidewrack.core.procgen.material_gen import make_recipe

PER_SLOT = 3  # best candidates kept per slot (set pieces are always kept)
GOLD_PER_REGION = 150  # gold for each region skipped, for meals and the inn


def region_gear(content: Content, region_id: str) -> list[str]:
    """Gear ids a region's places, town shops and enemies can give, in content order."""
    region = content.regions[region_id]
    found: set[str] = set()
    for roomset_id in [region.town, *region.roomsets]:
        roomset = content.roomsets[roomset_id]
        found.update(roomset.finds.gear)
        for shop_id in roomset.shops:
            found.update(content.shops[shop_id].gear)
        for enemy_id in roomset.enemies.pool:
            found.update(content.enemies[enemy_id].loot.gear)
    return sorted(found)


def candidates(content: Content, region_ids: Iterable[str]) -> list[Item]:
    """Every piece the regions give, fully upgraded at its best roll, plus each
    recipe's version of it (an affix on top), best first within each slot."""
    gear_ids = sorted({g for r in region_ids for g in region_gear(content, r)})
    items = []
    for gear_id in gear_ids:
        gear = content.gear[gear_id]
        best = {s: hi for s, (_, hi) in gear.rolls.items()}
        items.append(make_item(gear, content.gearsets, best))
    for _, recipe in sorted(content.recipes.items()):
        if recipe.makes in gear_ids and recipe.affix is not None:
            items.append(make_recipe(recipe, content).makes)
    maxed = [replace(i, upgrade=i.max_upgrade) for i in items]
    return sorted(maxed, key=lambda i: (SLOTS.index(i.slot), -value(i), i.display_name))


class Loadout(NamedTuple):
    worn: list[Item]
    spare: list[Item]  # the best other way to fill the hands (2h ⇄ 1h + off hand)


def best_loadout(base: Mapping[str, int], items: Iterable[Item]) -> Loadout:
    """The loadout with the highest total stat value (set bonuses included), and
    the best one with the other kind of weapon, whose new pieces are `spare`."""
    by_slot: dict[str, list[Item]] = {}
    for item in items:
        by_slot.setdefault(item.slot, []).append(item)
    for slot, pieces in by_slot.items():
        # The best few of each slot, the best two-hander, and every set piece.
        ranked = sorted(pieces, key=lambda i: (-value(i), i.display_name))
        kept = ranked[:PER_SLOT]
        kept += [i for i in ranked if i.two_handed][:1]
        kept += [i for i in ranked if i.gear_set is not None]
        by_slot[slot] = _unique(kept)

    def best(two_handed: bool) -> tuple[float, list[Item]] | None:
        mains = [i for i in by_slot.get("main_hand", []) if i.two_handed == two_handed]
        if not mains:
            return None
        choices = [mains]
        for slot in SLOTS[1:]:
            if slot == "off_hand" and two_handed:
                continue
            choices.append(by_slot.get(slot) or [None])
        top: tuple[float, list[Item]] | None = None
        for combo in itertools.product(*choices):
            worn = [i for i in combo if i is not None]
            score = stats_value(player_stats(base, worn).total)
            if top is None or score > top[0]:
                top = (score, worn)
        return top

    options = [b for b in (best(False), best(True)) if b is not None]
    if not options:
        return Loadout([], [])
    options.sort(key=lambda b: -b[0])
    worn = options[0][1]
    spare = [i for i in options[1][1] if not any(i is w for w in worn)] if len(options) > 1 else []
    return Loadout(worn, spare)


def _unique(items: list[Item]) -> list[Item]:
    seen: set[int] = set()
    out = []
    for item in items:
        if id(item) not in seen:
            seen.add(id(item))
            out.append(item)
    return out

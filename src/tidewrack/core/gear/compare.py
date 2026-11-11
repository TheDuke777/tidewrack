"""Compare a piece of gear against what the player has on (CLAUDE.md §8.4).

`compare` is pure and built only from stat_pipeline functions. Per stat it gives
the base Δ (base + roll only), the total Δ (with upgrades and affixes), and the
player's stat before and after equipping, which also counts set bonuses gained
or lost. The verdict comes from that player-level change.

What a candidate replaces is whatever overlaps the slots it takes: a two-hander
replaces both the main and off hand, and an off-hand item replaces an equipped
two-hander. Comparing an item that's already equipped shows no change.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from tidewrack.core.gear import stats
from tidewrack.core.gear.item import SLOT_LABELS, Item, slots_taken
from tidewrack.core.gear.stat_pipeline import (
    active_set_bonuses,
    at_max_upgrade,
    item_base,
    item_total,
    player_stats,
)
from tidewrack.core.gear.stats import STATS, StatBlock

Verdict = Literal["better", "worse", "mixed", "same"]


@dataclass(frozen=True)
class StatRow:
    stat: str
    base_delta: int  # candidate's base + roll vs the replaced items'
    total_delta: int  # candidate's own total vs the replaced items' (no sets)
    before: int  # the player's stat now
    after: int  # the player's stat with the candidate equipped

    @property
    def change(self) -> int:
        return self.after - self.before


@dataclass(frozen=True)
class Comparison:
    name: str
    slot: str  # label, e.g. "Main hand" or "Both hands"
    equipped: bool  # the candidate is already equipped (so nothing changes)
    replaces: tuple[str, ...]  # display names of the items it would take off
    rows: tuple[StatRow, ...]  # one per stat, in STATS order
    verdict: Verdict
    sets_gained: tuple[str, ...]  # e.g. "Drowned Watch (2 pieces): DEF +2"
    sets_lost: tuple[str, ...]
    effects_gained: tuple[str, ...]
    effects_lost: tuple[str, ...]
    at_max: StatBlock | None  # player stats with the candidate fully upgraded
    # Both fully upgraded (the candidate and what it replaces): is it the better
    # piece to put materials into? None when it's equipped (nothing to weigh).
    upgraded_verdict: Verdict | None = None

    @property
    def better_upgraded(self) -> bool:
        """Not better now, but better once both are fully upgraded."""
        return self.verdict != "better" and self.upgraded_verdict == "better"


def compare(
    candidate: Item, equipped: Iterable[Item], player_base: Mapping[str, int]
) -> Comparison:
    equipped = list(equipped)
    is_equipped = any(item is candidate for item in equipped)
    taken = set(slots_taken(candidate))
    replaced = [] if is_equipped else [item for item in equipped if taken & set(slots_taken(item))]
    after_loadout = (
        equipped
        if is_equipped
        else [item for item in equipped if not any(item is r for r in replaced)] + [candidate]
    )

    before = player_stats(player_base, equipped).total
    after = player_stats(player_base, after_loadout).total
    if is_equipped:
        base_delta = total_delta = stats.zero()
    else:
        base_delta = stats.sub(item_base(candidate), stats.total(map(item_base, replaced)))
        total_delta = stats.sub(item_total(candidate), stats.total(map(item_total, replaced)))

    maxed = at_max_upgrade(candidate)
    at_max = None
    if maxed is not None:
        maxed_loadout = [maxed if item is candidate else item for item in after_loadout]
        at_max = player_stats(player_base, maxed_loadout).total

    upgraded_verdict = None
    if not is_equipped:
        rest = [item for item in after_loadout if item is not candidate]
        both_maxed_before = player_stats(player_base, rest + [_maxed(i) for i in replaced]).total
        both_maxed_after = player_stats(player_base, rest + [_maxed(candidate)]).total
        upgraded_verdict = _verdict(stats.sub(both_maxed_after, both_maxed_before))

    bonuses_before, bonuses_after = _set_bonus_labels(equipped), _set_bonus_labels(after_loadout)
    effects_before, effects_after = Counter(_effects(equipped)), Counter(_effects(after_loadout))
    return Comparison(
        name=candidate.display_name,
        slot="Both hands" if candidate.two_handed else SLOT_LABELS[candidate.slot],
        equipped=is_equipped,
        replaces=tuple(item.display_name for item in replaced),
        rows=tuple(StatRow(s, base_delta[s], total_delta[s], before[s], after[s]) for s in STATS),
        verdict=_verdict(stats.sub(after, before)),
        sets_gained=tuple(b for b in bonuses_after if b not in bonuses_before),
        sets_lost=tuple(b for b in bonuses_before if b not in bonuses_after),
        effects_gained=tuple((effects_after - effects_before).elements()),
        effects_lost=tuple((effects_before - effects_after).elements()),
        at_max=at_max,
        upgraded_verdict=upgraded_verdict,
    )


def _maxed(item: Item) -> Item:
    return at_max_upgrade(item) or item


def format_stats(block: Mapping[str, int]) -> str:
    """ "DEF +2, ATK −1": the non-zero stats of a bonus, signed (with a real minus)."""
    return ", ".join(
        f"{stats.STAT_LABELS[s]} {'+' if v > 0 else '−'}{abs(v)}"
        for s, v in stats.full(block).items()
        if v
    )


def _verdict(change: StatBlock) -> Verdict:
    values = change.values()
    if all(v == 0 for v in values):
        return "same"
    if all(v >= 0 for v in values):
        return "better"
    if all(v <= 0 for v in values):
        return "worse"
    return "mixed"


def _set_bonus_labels(loadout: list[Item]) -> list[str]:
    labels = []
    for gear_set, bonus in active_set_bonuses(loadout):
        parts = [p for p in [format_stats(bonus.stats), *bonus.effects] if p]
        labels.append(f"{gear_set.name} ({bonus.pieces} pieces): {'; '.join(parts)}")
    return labels


def _effects(loadout: list[Item]) -> list[str]:
    """Effect text the loadout grants, from items, affixes and set bonuses."""
    found = [e for item in loadout for e in item.effects]
    found += [e for item in loadout for affix in item.affixes for e in affix.effects]
    found += [e for _, bonus in active_set_bonuses(loadout) for e in bonus.effects]
    return found

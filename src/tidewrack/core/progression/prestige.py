"""Prestige (step 8c): the tide turning, boons, and the next world's seed.

When the world's final foe falls the tide turns, and the player may ascend: the
Wrack takes this world and they wake on a new shore (services.session does the
swap), one tide further on (`Prestige.rank`), keeping their codex and boons and
choosing one more boon. A boon gives less each ascent (`BOON_DECAY`), so the
power prestige adds tails off; the difficulty sim counts it (beta 3).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from tidewrack.core.combat.rules import Rules
from tidewrack.core.data.schemas import BoonSchema, TidesSchema
from tidewrack.core.economy.value_model import EconomyRules
from tidewrack.core.engine.components import Boon, Meal, Prestige
from tidewrack.core.gear.stats import STAT_VALUES, STATS
from tidewrack.core.rng import Rng

BOON_DECAY = 0.8  # each ascent's boon is this share of the one before
MIN_PCT = 5  # a percentage boon never gives less than this


def boon_size(base: int, tide: int, floor: int = 1) -> int:
    """A boon amount for the `tide`-th ascent (1 = the first)."""
    return max(floor, round(base * BOON_DECAY ** (tide - 1)))


def boon_stat_sizes(stats: dict[str, int], tide: int) -> dict[str, int]:
    """A boon's stats for the `tide`-th ascent: each shrinks with BOON_DECAY and may
    reach 0 (so a DEF point, the cliffy stat, stops coming after a few tides),
    but the boon keeps at least 1 of its biggest stat."""
    sizes = {s: max(0, round(v * BOON_DECAY ** (tide - 1))) for s, v in stats.items()}
    if stats and not any(sizes.values()):
        biggest = max(stats, key=lambda s: (stats[s] * STAT_VALUES[s], s))
        sizes[biggest] = 1
    return sizes


def make_boon(schema: BoonSchema, tide: int) -> Boon:
    """The boon `schema` gives on reaching tide `tide` (1 = the first ascent)."""
    return Boon(
        boon_id=schema.id,
        name=schema.name,
        description=schema.description,
        tide=tide,
        stats=boon_stat_sizes(dict(schema.stats), tide),
        gold_pct=boon_size(schema.gold_pct, tide, MIN_PCT) if schema.gold_pct else 0,
        meal_turns_pct=(
            boon_size(schema.meal_turns_pct, tide, MIN_PCT) if schema.meal_turns_pct else 0
        ),
        meal_stats_pct=(
            boon_size(schema.meal_stats_pct, tide, MIN_PCT) if schema.meal_stats_pct else 0
        ),
        materials_pct=(
            boon_size(schema.materials_pct, tide, MIN_PCT) if schema.materials_pct else 0
        ),
    )


def boon_text(boon: Boon) -> str:
    """What a boon does, e.g. "+2 ATK", "+20% gold from foes and quests, +4 HP"."""
    parts = []
    if boon.gold_pct:
        parts.append(f"+{boon.gold_pct}% gold from foes and quests")
    if boon.materials_pct:
        parts.append(f"{boon.materials_pct}% chance of an extra material when you loot or gather")
    if boon.meal_stats_pct:
        parts.append(f"meals give {boon.meal_stats_pct}% more")
    if boon.meal_turns_pct:
        parts.append(f"meals last {boon.meal_turns_pct}% longer")
    parts += [f"+{v} {s.upper()}" for s, v in boon.stats.items() if v]
    return ", ".join(parts)


def boon_stats(boons: Iterable[Boon]) -> dict[str, int]:
    total = {s: 0 for s in STATS}
    for boon in boons:
        for stat, value in boon.stats.items():
            total[stat] = total.get(stat, 0) + value
    return {s: v for s, v in total.items() if v}


def gold_pct(prestige: Prestige | None) -> int:
    return sum(b.gold_pct for b in prestige.boons) if prestige else 0


def materials_pct(prestige: Prestige | None) -> int:
    return min(100, sum(b.materials_pct for b in prestige.boons)) if prestige else 0


def meal_stats_pct(prestige: Prestige | None) -> int:
    return sum(b.meal_stats_pct for b in prestige.boons) if prestige else 0


def stronger_meal(meal: Meal, pct: int) -> Meal:
    """A meal's buff with `pct`% more to each stat (rounded, at least +1 where it
    has the stat)."""
    if not pct:
        return meal
    stats = {s: v + max(1, round(v * pct / 100)) if v else 0 for s, v in meal.stats.items()}
    return replace(meal, stats=stats)


def meal_turns_pct(prestige: Prestige | None) -> int:
    return sum(b.meal_turns_pct for b in prestige.boons) if prestige else 0


def with_bonus(amount: int, pct: int) -> int:
    """`amount` plus `pct`% of it, rounded down (never less than the amount)."""
    return amount + amount * pct // 100


def tide_steps(tides: TidesSchema, rank: int) -> int:
    """How many tides of scaling apply on tide `rank` (capped at max_tide)."""
    return max(0, min(rank, tides.max_tide))


def tide_rules(rules: Rules, tides: TidesSchema, rank: int) -> Rules:
    """A preset's rules made harder for tide `rank`: more enemy HP, a little ATK."""
    n = tide_steps(tides, rank)
    return replace(
        rules,
        enemy_hp=rules.enemy_hp * (1 + tides.enemy_hp * n),
        enemy_atk=rules.enemy_atk * (1 + tides.enemy_atk * n),
    )


def tide_economy(economy: EconomyRules, tides: TidesSchema, rank: int) -> EconomyRules:
    """Gold from foes and quests made richer for tide `rank`."""
    n = tide_steps(tides, rank)
    return replace(economy, reward_gold=economy.reward_gold * (1 + tides.reward_gold * n))


def tide_meal(meal: Meal, tides: TidesSchema, rank: int) -> Meal:
    """A meal's buff made stronger for tide `rank` (stats only; its price stays),
    so cooking keeps pace with tougher foes."""
    n = tide_steps(tides, rank)
    if not n or not tides.meal_stats:
        return meal
    stats = {s: v + round(v * tides.meal_stats * n) for s, v in meal.stats.items()}
    return replace(meal, stats=stats)


def next_seed(seed: int, rank: int) -> int:
    """The seed of the world the tide washes you up in after tide `rank`: drawn
    from this world's seed, so a slot's tides are reproducible."""
    return Rng(seed).derive(f"tide.{rank + 1}").next_u64() >> 1

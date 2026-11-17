"""Difficulty sim (step 8b, CLAUDE.md §8.7): fight odds region by region.

Run it for a report (``python sim/difficulty_sim.py [fights]``); CI runs a quick
pass through tests/sim/test_difficulty_sim.py. For every region, from the coast
inward, it fights each foe kind, the hardest bounty and the warden with:

- **arriving** gear: the best loadout from the regions before, at its best roll
  and fully upgraded (core.procgen.head_start, the same as a dev "Start in"
  world); on the coast, the starting kit;
- **geared**: the same, counting this region's gear too;

each unfed and with the best meal cooked from ingredients found so far (for a
warden, which bars the road in, only those of the regions before), under each
difficulty preset. The bot always attacks (no Defend, no Flee), starts at
full health and fights with the real ``damage()``, ``scaled()`` and bounty rule.

Per fight kind it reports the win rate and the share of max HP lost (a defeat
counts as all of it). The target feel (playtests, 2026-11): arriving in a
region, its foes hurt and its warden is a real test with a meal as the edge;
once geared, the region gets comfortable. A full-run bot measuring time to
prestige comes after step 8c.
"""

from __future__ import annotations

import statistics
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import ceil

from tidewrack.core.combat.rules import Rules, damage, scaled
from tidewrack.core.data.loader import Content
from tidewrack.core.data.schemas import EnemySchema, MealSchema
from tidewrack.core.gear.stat_pipeline import StatSource, player_stats
from tidewrack.core.gear.stats import STATS
from tidewrack.core.procgen.gear_gen import generate_kit
from tidewrack.core.procgen.head_start import best_loadout, candidates
from tidewrack.core.rng import Rng

WORLD = "world.standard"
FIGHTS = 2000  # per fight kind in a full report
MAX_ROUNDS = 200  # a fight neither side can finish (never happens: hits are ≥ 1)


@dataclass(frozen=True)
class Foe:
    name: str
    kind: str  # "foe", "bounty", "warden" or "final" (the world's final foe, 8c)
    stats: Mapping[str, int]
    rolls: Mapping[str, tuple[int, int]]
    strength: float = 1.0  # bounties: stats × this after rolling (quest_gen)

    def roll(self, rng: Rng, rules: Rules) -> dict[str, int]:
        stats = dict(self.stats)
        for stat in STATS:
            if stat in self.rolls:
                stats[stat] = stats.get(stat, 0) + rng.randint(*self.rolls[stat])
        if self.strength != 1.0:
            stats = {s: ceil(v * self.strength) for s, v in stats.items()}
        return scaled(stats, rules)

    def mean(self, rules: Rules) -> dict[str, float]:
        stats = {s: float(v) for s, v in self.stats.items()}
        for stat, (low, high) in self.rolls.items():
            stats[stat] = stats.get(stat, 0) + (low + high) / 2
        return scaled({s: round(v * self.strength) for s, v in stats.items()}, rules)


@dataclass(frozen=True)
class Odds:
    win: float  # share of fights won
    hp_lost: float  # mean share of max HP lost (a defeat loses all of it)
    rounds: float  # mean rounds per fight


@dataclass(frozen=True)
class Row:
    region: str
    tier: int
    gear: str  # "arriving" or "geared"
    difficulty: str
    foe: Foe
    you: Mapping[str, int]
    unfed: Odds
    fed: Odds
    meal: str | None  # the meal that did best, if any was available


def regions(content: Content, world: str = WORLD) -> list[str]:
    """The world's region ids, coast first (tiers rise inward)."""
    return [p.region for p in content.world(world).regions]


def _roomsets(content: Content, region_id: str) -> list[str]:
    region = content.regions[region_id]
    return [region.town, *region.roomsets]


def _pool(content: Content, region_id: str) -> list[EnemySchema]:
    ids = {e for rs in _roomsets(content, region_id) for e in content.roomsets[rs].enemies.pool}
    return [content.enemies[e] for e in sorted(ids)]


def foes(content: Content, region_id: str, world: str = WORLD) -> list[Foe]:
    """Each foe kind in the region, its hardest bounty, its warden, and the
    world's final foe if it waits here (the last region)."""
    pool = _pool(content, region_id)
    out = [Foe(e.name, "foe", dict(e.stats), dict(e.rolls)) for e in pool]
    strength = content.quests["quest.bounty"].strength
    hardest = max(pool, key=lambda e: _threat(Foe(e.name, "", e.stats, e.rolls, strength)))
    out.append(Foe(hardest.name, "bounty", dict(hardest.stats), dict(hardest.rolls), strength))
    warden = content.regions[region_id].warden
    if warden is not None:
        e = content.enemies[warden]
        out.append(Foe(e.name, "warden", dict(e.stats), dict(e.rolls)))
    recipe = content.world(world)
    if recipe.final is not None and recipe.regions[-1].region == region_id:
        e = content.enemies[recipe.final.enemy]
        out.append(Foe(e.name, "final", dict(e.stats), dict(e.rolls)))
    return out


def _threat(foe: Foe) -> float:
    m = foe.mean(Rules())
    return m["atk"] * m["hp"]


def material_tiers(content: Content, world: str = WORLD) -> dict[str, int]:
    """Each material's earliest region tier: gathered there, dropped by its foes,
    or sold at its towns' shops."""
    tiers: dict[str, int] = {}
    for region_id in regions(content, world):
        tier = content.regions[region_id].tier
        found: set[str] = set()
        for rs_id in _roomsets(content, region_id):
            roomset = content.roomsets[rs_id]
            found.update(roomset.gathering.materials)
            for shop_id in roomset.shops:
                found.update(content.shops[shop_id].materials)
        for enemy in _pool(content, region_id):
            found.update(d.material for d in enemy.materials)
        for material in found:
            tiers.setdefault(material, tier)
    return tiers


def meal_tier(meal: MealSchema, tiers: Mapping[str, int]) -> int | None:
    """The tier from which every ingredient can be had (None: never)."""
    needed = [tiers.get(m) for m in meal.ingredients]
    return None if None in needed else max(needed)  # type: ignore[type-var]


def meals_by(content: Content, tier: int, world: str = WORLD) -> list[MealSchema]:
    tiers = material_tiers(content, world)
    return [
        m
        for _, m in sorted(content.meals.items())
        if m.stats and (t := meal_tier(m, tiers)) is not None and t <= tier
    ]


def gear_stats(content: Content, region_ids: list[str], world: str = WORLD) -> dict[str, int]:
    """Total stats in the best maxed loadout from these regions (none: the kit)."""
    recipe = content.world(world)
    base = recipe.player
    if not region_ids:
        return dict(player_stats(base, generate_kit(recipe, content)).total)
    worn = best_loadout(base, candidates(content, region_ids)).worn
    return dict(player_stats(base, worn).total)


def fed(you: Mapping[str, int], meal: MealSchema | None) -> dict[str, int]:
    if meal is None:
        return dict(you)
    base = {s: v for s, v in you.items()}
    return dict(player_stats(base, [], [StatSource(meal.name, dict(meal.stats))]).total)


BIG = ("bounty", "warden", "final")  # what bane gear hits harder (core.gear.effects)


def fight(
    rng: Rng,
    you: Mapping[str, int],
    foe: Foe,
    rules: Rules,
    n: int,
    effects: Mapping[str, int] | None = None,
) -> Odds:
    """`n` fights, the bot always attacking; `effects` are the player's gear effects
    that act in a fight (lifesteal, bane, exposed), as core.combat.fight applies
    them."""
    effects = effects or {}
    atk = you["atk"] + (effects.get("bane", 0) if foe.kind in BIG else 0)
    steal, exposed = effects.get("lifesteal", 0), effects.get("exposed", 0)
    wins = lost = rounds = 0
    for _ in range(n):
        enemy = foe.roll(rng, rules)
        hp, enemy_hp = you["hp"], enemy["hp"]
        for _ in range(MAX_ROUNDS):
            rounds += 1
            enemy_hp -= damage(rng, atk, enemy.get("def", 0), False, rules)
            hp = min(you["hp"], hp + steal)
            if enemy_hp <= 0:
                wins += 1
                break
            hp -= damage(rng, enemy.get("atk", 0), you["def"], False, rules) + exposed
            if hp <= 0:
                hp = 0
                break
        lost += you["hp"] - hp
    return Odds(wins / n, lost / n / you["hp"], rounds / n)


def _expected_loss(you: Mapping[str, int], foe: Foe, rules: Rules) -> float:
    """HP lost to a foe of mean stats with mean blows: a cheap way to rank meals."""
    enemy = foe.mean(rules)
    mine = max(1.0, you["atk"] - enemy.get("def", 0) + ceil(you["atk"] / 3) / 2)
    theirs = max(1.0, enemy.get("atk", 0) - you["def"] + ceil(enemy.get("atk", 0) / 3) / 2)
    return (ceil(enemy["hp"] / mine) - 1) * theirs / you["hp"]


def best_meal(
    you: Mapping[str, int], foe: Foe, rules: Rules, meals: Iterable[MealSchema]
) -> MealSchema | None:
    options = list(meals)
    if not options:
        return None
    return min(options, key=lambda m: (_expected_loss(fed(you, m), foe, rules), m.id))


def simulate(content: Content, fights: int = FIGHTS, seed: int = 1) -> list[Row]:
    rng = Rng(seed).derive("difficulty_sim")
    order = regions(content)
    presets = content.difficulty_choices()
    rows = []
    for i, region_id in enumerate(order):
        region = content.regions[region_id]
        # A warden bars the road in, so it's fought with the meals of the
        # regions before; the region's own foes and bounty with its own too.
        meals = {
            "foe": meals_by(content, region.tier),
            "warden": meals_by(content, region.tier - 1),
        }
        for gear, ids in (("arriving", order[:i]), ("geared", order[: i + 1])):
            you = gear_stats(content, ids)
            for preset in presets:
                rules = preset.to_rules()
                for foe in foes(content, region_id):
                    meal = best_meal(you, foe, rules, meals.get(foe.kind, meals["foe"]))
                    unfed = fight(rng, you, foe, rules, fights)
                    full = fight(rng, fed(you, meal), foe, rules, fights) if meal else unfed
                    rows.append(
                        Row(
                            region.name,
                            region.tier,
                            gear,
                            preset.name,
                            foe,
                            you,
                            unfed,
                            full,
                            meal.name if meal else None,
                        )
                    )
    return rows


@dataclass(frozen=True)
class MealEdge:
    region: str
    own: str  # the region's best own meal (all its ingredients first found here)
    own_lost: float
    earlier: str | None  # the best meal from the regions before
    earlier_lost: float


def meal_edges(content: Content, fights: int = FIGHTS, seed: int = 1) -> list[MealEdge]:
    """Per region on Standard, geared there: the share of HP lost to its hardest
    bounty (and the final foe, if it waits there) plus the next region's warden
    (the fights a meal is for), fed with the best meal that only became cookable
    here versus the best from before. Each region's own meals should win (8b:
    meals sized against their region's foes)."""
    rng = Rng(seed).derive("meal_edges")
    rules = Rules()  # Standard
    tiers = material_tiers(content)
    order = regions(content)
    out = []
    for i, region_id in enumerate(order):
        region = content.regions[region_id]
        you = gear_stats(content, order[: i + 1])
        hard = [f for f in foes(content, region_id) if f.kind in ("bounty", "final")]
        if i + 1 < len(order):
            hard += [f for f in foes(content, order[i + 1]) if f.kind == "warden"]
        lost: dict[str, float] = {}
        for meal in meals_by(content, region.tier):
            fed_you = fed(you, meal)
            lost[meal.id] = sum(fight(rng, fed_you, foe, rules, fights).hp_lost for foe in hard)
        own = [m for m in lost if meal_tier(content.meals[m], tiers) == region.tier]
        earlier = [m for m in lost if m not in own]
        best_own = min(own, key=lambda m: (lost[m], m))
        best_earlier = min(earlier, key=lambda m: (lost[m], m)) if earlier else None
        out.append(
            MealEdge(
                region.name,
                content.meals[best_own].name,
                lost[best_own],
                content.meals[best_earlier].name if best_earlier else None,
                lost[best_earlier] if best_earlier else 0.0,
            )
        )
    return out


def summary(rows: list[Row], region: str, gear: str, difficulty: str) -> dict[str, Odds]:
    """Per kind for one region/gear/difficulty: the hardest foe (most HP lost),
    the median foe, the bounty and the warden, unfed."""
    picked = [r for r in rows if (r.region, r.gear, r.difficulty) == (region, gear, difficulty)]
    plain = sorted((r.unfed for r in picked if r.foe.kind == "foe"), key=lambda o: o.hp_lost)
    out = {"worst foe": plain[-1], "median foe": plain[len(plain) // 2]}
    for r in picked:
        if r.foe.kind in ("bounty", "warden", "final"):
            out[r.foe.kind] = r.unfed
            out[f"{r.foe.kind} fed"] = r.fed
    return out


def _pct(x: float) -> str:
    return f"{x:4.0%}"


def report(rows: list[Row]) -> str:
    lines = []
    for region in dict.fromkeys(r.region for r in rows):
        for gear in ("arriving", "geared"):
            first = next(r for r in rows if (r.region, r.gear) == (region, gear))
            you = first.you
            lines.append(
                f"\n{region} (tier {first.tier}), {gear}: ATK {you['atk']} DEF {you['def']}"
                f" HP {you['hp']}"
            )
            lines.append(
                f"  {'':9} {'median foe':>11} {'worst foe':>11} {'bounty':>11} {'fed':>11}"
                f" {'warden':>11} {'fed':>11}   (win/HP lost)"
            )
            for difficulty in dict.fromkeys(r.difficulty for r in rows):
                s = summary(rows, region, gear, difficulty)
                cells = [
                    f"{_pct(o.win)}/{_pct(o.hp_lost)}" if o else f"{'—':>11}"
                    for o in (
                        s["median foe"],
                        s["worst foe"],
                        s.get("bounty"),
                        s.get("bounty fed"),
                        s.get("warden"),
                        s.get("warden fed"),
                    )
                ]
                lines.append(f"  {difficulty:9} " + " ".join(f"{c:>11}" for c in cells))
            picked = [
                r for r in rows if (r.region, r.gear, r.difficulty) == (region, gear, "Standard")
            ]
            per_foe = ", ".join(
                f"{r.foe.name} {_pct(r.unfed.hp_lost).strip()}"
                for r in sorted(picked, key=lambda r: -r.unfed.hp_lost)
                if r.foe.kind == "foe"
            )
            for r in picked:
                if r.foe.kind == "final":
                    lines.append(
                        f"  {r.foe.name} (final): unfed {_pct(r.unfed.win).strip()} won,"
                        f" {_pct(r.unfed.hp_lost).strip()} HP lost; fed ({r.meal})"
                        f" {_pct(r.fed.win).strip()} won, {_pct(r.fed.hp_lost).strip()} lost"
                    )
            meals = sorted({r.meal for r in picked if r.meal})
            lines.append(f"  Standard per foe (HP lost): {per_foe}")
            lines.append(f"  meals used: {', '.join(meals) or 'none available'}")
    return "\n".join(lines)


def main(argv: list[str]) -> None:
    from tidewrack.services.content import load_bundled_content

    fights = int(argv[1]) if len(argv) > 1 else FIGHTS
    rows = simulate(load_bundled_content(), fights)
    print(report(rows))
    rounds = statistics.median(r.unfed.rounds for r in rows)
    print(f"\n{fights} fights per row; median rounds per fight {rounds:.1f}")
    print("\nMeals, geared, Standard (HP lost to the bounty + the next warden):")
    for e in meal_edges(load_bundled_content(), fights):
        before = f"{e.earlier} {e.earlier_lost:.0%}" if e.earlier else "none"
        print(f"  {e.region:18} own: {e.own} {e.own_lost:.0%}   best before: {before}")
    print(tide_report(tide_curve(load_bundled_content(), max(fights // 4, 100))))
    print(set_report(set_odds(load_bundled_content(), fights)))


if __name__ == "__main__":
    main(sys.argv)


# --- tides (8c beta 3) ---------------------------------------------------------------

# Boon picks a player might make on each ascent, cycled (boon ids).
BOON_PLANS = {
    "mixed": ["boon.keen_edge", "boon.sea_hardened", "boon.deep_lungs"],
    "all DEF": ["boon.sea_hardened"],
    "all ATK": ["boon.keen_edge"],
    "gold + meals": ["boon.wreckers_luck", "boon.long_table"],
    "all meals": ["boon.long_table"],
}
TIDES = range(0, 11)


@dataclass(frozen=True)
class TideRow:
    tide: int
    plan: str
    difficulty: str
    you: Mapping[str, int]  # geared in the last region, boons included, unfed
    king: Odds  # the final foe, fed with the best meal (scaled for the tide)
    bounty: Odds  # the last region's hardest bounty, fed
    warden: Odds  # its warden on arrival (gear from the regions before), fed


def boons_for(content: Content, plan: list[str], tide: int) -> tuple[dict[str, int], int]:
    """What the boons a plan has picked by `tide` (one per ascent so far) add in a
    fight: (stats, % stronger meals)."""
    from tidewrack.core.progression.prestige import boon_stats, make_boon

    picks = [make_boon(content.boons[plan[(t - 1) % len(plan)]], t) for t in range(1, tide + 1)]
    return boon_stats(picks), sum(b.meal_stats_pct for b in picks)


def tide_curve(
    content: Content, fights: int = FIGHTS, seed: int = 1, tides: Iterable[int] = TIDES
) -> list[TideRow]:
    """The last region's hardest fights on each tide, per boon plan and preset."""
    from tidewrack.core.progression.prestige import tide_rules

    rng = Rng(seed).derive("tide_curve")
    order = regions(content)
    recipe = content.world(WORLD)
    last = order[-1]
    region = content.regions[last]
    fights_here = {f.kind: f for f in foes(content, last)}
    geared, arriving = gear_stats(content, order), gear_stats(content, order[:-1])
    rows = []
    for tide in tides:
        for plan_name, plan in BOON_PLANS.items():
            boons, meal_pct = boons_for(content, plan, tide)
            own = _tide_meals(content, region.tier, tide, meal_pct)
            before = _tide_meals(content, region.tier - 1, tide, meal_pct)
            you = {s: v + boons.get(s, 0) for s, v in geared.items()}
            came = {s: v + boons.get(s, 0) for s, v in arriving.items()}
            for preset in content.difficulty_choices():
                rules = tide_rules(preset.to_rules(), recipe.tides, tide)
                rows.append(
                    TideRow(
                        tide,
                        plan_name,
                        preset.name,
                        you,
                        _fed_fight(rng, you, fights_here["final"], rules, own, fights),
                        _fed_fight(rng, you, fights_here["bounty"], rules, own, fights),
                        _fed_fight(rng, came, fights_here["warden"], rules, before, fights),
                    )
                )
    return rows


def _tide_meals(content: Content, tier: int, tide: int, boon_pct: int = 0) -> list[MealSchema]:
    """The meals cookable by `tier`, their stats scaled for `tide` (as a world on
    that tide's taverns snapshot them) and by boons that make meals stronger."""
    from tidewrack.core.procgen.material_gen import make_meal
    from tidewrack.core.progression.prestige import stronger_meal, tide_meal

    tides = content.world(WORLD).tides
    out = []
    for schema in meals_by(content, tier):
        meal = stronger_meal(tide_meal(make_meal(schema, content), tides, tide), boon_pct)
        out.append(schema.model_copy(update={"stats": dict(meal.stats)}))
    return out


def _fed_fight(
    rng: Rng, you: Mapping[str, int], foe: Foe, rules: Rules, meals, fights: int
) -> Odds:
    meal = best_meal(you, foe, rules, meals)
    return fight(rng, fed(you, meal), foe, rules, fights)


def tide_report(rows: list[TideRow]) -> str:
    lines = ["\nTides: the last region's hardest fights, fed (win/HP lost)"]
    for difficulty in dict.fromkeys(r.difficulty for r in rows):
        lines.append(f"  {difficulty}")
        for plan in BOON_PLANS:
            cells = [
                f"t{r.tide}:{_pct(r.king.win).strip()}/{_pct(r.king.hp_lost).strip()}"
                for r in rows
                if (r.plan, r.difficulty) == (plan, difficulty)
            ]
            lines.append(f"    king, {plan:8} " + " ".join(cells))
    return "\n".join(lines)


# --- playstyle sets (v0.13.0) --------------------------------------------------------


@dataclass(frozen=True)
class SetRow:
    region: str
    gear_set: str
    foe: str
    plain: Odds  # the best plain loadout (sets only for their stats), fed
    with_set: Odds  # the same with the region's playstyle set's pieces swapped in, fed
    effects: Mapping[str, int]


def playstyle_sets(content: Content, region_id: str) -> list[str]:
    """Gear sets whose pieces come from this region and whose bonuses have effects."""
    from tidewrack.core.procgen.head_start import region_gear

    here = set(region_gear(content, region_id))
    return sorted(
        gs.id
        for gs in content.gearsets.values()
        if any(b.effects for b in gs.bonuses)
        and any(g.set == gs.id and g.id in here for g in content.gear.values())
    )


def set_odds(content: Content, fights: int = FIGHTS, seed: int = 1) -> list[SetRow]:
    """Each region's hardest bounty (and the king in the last region), geared and
    fed, with the best plain loadout versus that loadout wearing a playstyle set:
    how much a set changes the fights that matter (Standard)."""
    from tidewrack.core.gear.item import slots_taken
    from tidewrack.core.gear.stat_pipeline import player_stats
    from tidewrack.core.procgen.head_start import best_loadout, candidates

    rng = Rng(seed).derive("set_odds")
    rules = Rules()
    order = regions(content)
    base = content.world(WORLD).player
    rows = []
    for i, region_id in enumerate(order):
        pool = candidates(content, order[: i + 1])
        worn = best_loadout(base, pool).worn
        plain_sheet = player_stats(base, worn)
        meals = meals_by(content, content.regions[region_id].tier)
        targets = [f for f in foes(content, region_id) if f.kind in ("bounty", "final")]
        for set_id in playstyle_sets(content, region_id):
            pieces = {}
            for item in pool:
                if item.gear_set and item.gear_set.id == set_id:
                    pieces.setdefault(item.slot, item)
            swapped = [w for w in worn if not set(slots_taken(w)) & set(pieces)] + list(
                pieces.values()
            )
            sheet = player_stats(base, swapped)
            for foe in targets:
                plain_you, set_you = dict(plain_sheet.total), dict(sheet.total)
                rows.append(
                    SetRow(
                        content.regions[region_id].name,
                        content.gearsets[set_id].name,
                        f"{foe.name} ({foe.kind})",
                        _fed_fight(rng, plain_you, foe, rules, meals, fights),
                        _fed_effect_fight(rng, set_you, foe, rules, meals, fights, sheet.effects),
                        sheet.effects,
                    )
                )
    return rows


def _fed_effect_fight(rng, you, foe, rules, meals, fights, effects) -> Odds:
    meal = best_meal(you, foe, rules, meals)
    return fight(rng, fed(you, meal), foe, rules, fights, effects)


def set_report(rows: list[SetRow]) -> str:
    lines = ["\nPlaystyle sets, geared, fed, Standard (win/HP lost): plain -> with the set"]
    for r in rows:
        lines.append(
            f"  {r.region:10} {r.gear_set:15} vs {r.foe:28}"
            f" {_pct(r.plain.win).strip()}/{_pct(r.plain.hp_lost).strip()}"
            f" -> {_pct(r.with_set.win).strip()}/{_pct(r.with_set.hp_lost).strip()}"
            f"   {dict(r.effects)}"
        )
    return "\n".join(lines)

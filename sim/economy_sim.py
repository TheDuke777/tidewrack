"""Economy sim and lint: generate many worlds and check the §8.6 balance rules.

Run it for a report (``python sim/economy_sim.py [seeds]``); CI runs a quick pass
through tests/sim/test_economy_sim.py. Per world it totals:

- **income**: starting gold, gold every enemy carries (placed, wandering and
  bounties), quest gold, and what selling every find, drop and quest reward
  would fetch;
- **for sale**: what buying the whole first stock of every shop would cost;
- **problems**: any buy → sell loop that makes money, and any shop item worth
  as much as the same gear's best roll (top-tier gear must never be for sale).

Returning wanderers and restocks add more of both over time; they're not
counted here (the step-8 difficulty sim plays worlds turn by turn).
"""

from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass, field

from tidewrack.core.data.loader import Content
from tidewrack.core.economy.value_model import buy_price, sell_price, value
from tidewrack.core.procgen.enemy_gen import generate_enemies
from tidewrack.core.procgen.gear_gen import generate_finds, make_item
from tidewrack.core.procgen.quest_gen import generate_quests
from tidewrack.core.procgen.shop_gen import generate_shops
from tidewrack.core.procgen.world_gen import generate_world


@dataclass
class WorldReport:
    seed: int
    start_gold: int
    enemy_gold: int
    quest_gold: int
    sales: int  # selling every find, drop and quest reward
    stock_cost: int  # buying every shop's first stock
    cheapest_ware: int | None
    problems: list[str] = field(default_factory=list)

    @property
    def income(self) -> int:
        return self.start_gold + self.enemy_gold + self.quest_gold + self.sales


def simulate(seed: int, content: Content, recipe_id: str = "world.standard") -> WorldReport:
    recipe = content.world(recipe_id)
    world = generate_world(seed, recipe, content.roomsets)
    placed, spawners = generate_enemies(seed, world, content)
    plan = generate_quests(seed, world, content, recipe, placed, spawners)
    finds = generate_finds(seed, world, content)
    shops = generate_shops(seed, world, content)

    enemies = [p.enemy for p in placed] + [e for s in spawners for e in s.queue]
    enemies += [b.enemy for b in plan.bounties]
    sellable = [f.item for f in finds] + [i for e in enemies for i in e.loot]
    sellable += [q.reward for q in plan.quests]
    stock = [i for s in shops for i in s.stock]
    report = WorldReport(
        seed=seed,
        start_gold=recipe.gold,
        enemy_gold=sum(e.gold for e in enemies),
        quest_gold=sum(q.gold for q in plan.quests),
        sales=sum(sell_price(i) for i in sellable),
        stock_cost=sum(buy_price(i) for i in stock),
        cheapest_ware=min((buy_price(i) for i in stock), default=None),
    )
    for item in stock + [w for s in shops for w in s.shop.wares]:
        if sell_price(item) >= buy_price(item):
            report.problems.append(f"seed {seed}: {item.display_name} sells for its price")
        gear = content.gear[item.gear_id]
        best = make_item(gear, content.gearsets, {s: h for s, (_, h) in gear.rolls.items()})
        if gear.rolls and value(item) >= value(best):
            report.problems.append(f"seed {seed}: a shop sells a top-roll {item.display_name}")
    return report


def lint_content(content: Content) -> list[str]:
    """Content-level checks that don't need a world."""
    problems = []
    for shop in content.shops.values():
        for gear_id in shop.gear:
            gear = content.gear[gear_id]
            half = {s: lo + (hi - lo) // 2 for s, (lo, hi) in gear.rolls.items()}
            top = {s: hi for s, (_, hi) in gear.rolls.items()}
            shop_best = make_item(gear, content.gearsets, half)
            if gear.rolls and value(shop_best) >= value(make_item(gear, content.gearsets, top)):
                problems.append(f"{shop.id}: {gear_id}'s shop copies can match its best roll")
    return problems


def main(seeds: int = 50) -> int:
    from tidewrack.services.content import load_bundled_content

    content = load_bundled_content()
    reports = [simulate(seed, content) for seed in range(seeds)]
    problems = lint_content(content) + [p for r in reports for p in r.problems]

    def line(label: str, values: list[int]) -> str:
        values = sorted(values)
        p10 = values[len(values) // 10]
        return (
            f"{label:<28} median {statistics.median(values):>6.0f}   "
            f"p10 {p10:>5}   max {values[-1]:>5}"
        )

    print(f"Economy sim: {seeds} standard worlds")
    print(line("enemy gold", [r.enemy_gold for r in reports]))
    print(line("quest gold", [r.quest_gold for r in reports]))
    print(line("selling everything", [r.sales for r in reports]))
    print(line("total income", [r.income for r in reports]))
    print(line("buying every first stock", [r.stock_cost for r in reports]))
    cheapest = [r.cheapest_ware for r in reports if r.cheapest_ware is not None]
    print(line("cheapest ware", cheapest))
    print(f"{len(problems)} problem(s)")
    for problem in problems:
        print("  " + problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 50))

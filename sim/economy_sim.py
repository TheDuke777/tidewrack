"""Economy sim and lint: generate many worlds and check the §8.6 balance rules.

Run it for a report (``python sim/economy_sim.py [seeds]``); CI runs a quick pass
through tests/sim/test_economy_sim.py. Per world it totals:

- **income**: starting gold, gold every enemy carries (placed, wandering and
  bounties), quest gold, and what selling every find, drop and quest reward
  would fetch, plus every material (dropped or gathered) sold at a market;
- **for sale**: what buying the whole first stock of every shop would cost;
- **crafting**: the fees for upgrading the starting kit all the way and for
  crafting each known recipe once (the gold sink step 7b adds);
- **problems**: any buy → sell loop that makes money, and any shop item worth
  as much as the same gear's best roll (top-tier gear must never be for sale).

The content lint also checks crafting: buying a gear the smithy sells costs more
than the fee for crafting it from gathered materials (rule 2, the convenience
tax), and no craft or upgrade can be sold for more than its fee plus what its
materials would have sold for. Meals (step 7c): a ready-made meal costs more than
cooking it (rule 2), and no meal's buff is worth more than MEAL_POWER_PER_VALUE
times its ingredients, so pricier meals can be stronger but never runaway.

Returning wanderers and restocks add more of both over time; they're not
counted here (the step-8 difficulty sim plays worlds turn by turn).
"""

from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass, field

from tidewrack.core.data.loader import Content
from tidewrack.core.economy.value_model import (
    buy_price,
    cook_fee,
    craft_fee,
    material_sell_price,
    meal_price,
    sell_price,
    stats_value,
    upgrade_fee,
    value,
)
from tidewrack.core.gear.stat_pipeline import at_max_upgrade
from tidewrack.core.procgen.enemy_gen import generate_enemies
from tidewrack.core.procgen.gear_gen import generate_finds, generate_kit, make_item
from tidewrack.core.procgen.material_gen import (
    generate_gathering,
    known_recipes,
    make_material,
    make_meal,
    make_recipe,
)
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
    materials: int = 0  # selling every dropped and gathered material
    crafting: int = 0  # fees: the kit fully upgraded, each known recipe once
    problems: list[str] = field(default_factory=list)

    @property
    def income(self) -> int:
        return self.start_gold + self.enemy_gold + self.quest_gold + self.sales + self.materials


def simulate(seed: int, content: Content, recipe_id: str = "world.standard") -> WorldReport:
    recipe = content.world(recipe_id)
    world = generate_world(seed, recipe, content.roomsets, content.regions)
    placed, spawners = generate_enemies(seed, world, content)
    plan = generate_quests(seed, world, content, recipe, placed, spawners)
    finds = generate_finds(seed, world, content)
    shops = generate_shops(seed, world, content)

    enemies = [p.enemy for p in placed] + [e for s in spawners for e in s.queue]
    enemies += [b.enemy for b in plan.bounties]
    sellable = [f.item for f in finds] + [i for e in enemies for i in e.loot]
    sellable += [q.reward for q in plan.quests]
    stock = [i for s in shops for i in s.stock]
    stacks = [m for e in enemies for m in e.materials]
    stacks += [g.stack for g in generate_gathering(seed, world, content)]
    fees = sum(craft_fee(r.makes) for r in known_recipes(content))
    for item in generate_kit(recipe, content):
        while item.upgrade < item.max_upgrade:
            fees += upgrade_fee(item)
            item.upgrade += 1
    report = WorldReport(
        seed=seed,
        start_gold=recipe.gold,
        enemy_gold=sum(e.gold for e in enemies),
        quest_gold=sum(q.gold for q in plan.quests),
        sales=sum(sell_price(i) for i in sellable),
        stock_cost=sum(buy_price(i) for i in stock),
        cheapest_ware=min((buy_price(i) for i in stock), default=None),
        materials=sum(material_sell_price(s.material) * s.count for s in stacks),
        crafting=fees,
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
    sold = {g for shop in content.shops.values() for g in shop.gear}
    for schema in content.recipes.values():
        made = make_recipe(schema, content)
        fee = craft_fee(made.makes)
        materials = sum(material_sell_price(m.material) * m.count for m in made.materials)
        if sell_price(made.makes) >= fee + materials:
            problems.append(f"{schema.id}: crafting it then selling it makes money")
        if schema.makes in sold and not schema.affix:
            cheapest = shop_copy_low(content, schema.makes)
            if buy_price(cheapest) <= fee:
                problems.append(f"{schema.id}: buying it costs no more than crafting it (rule 2)")
    for gear in content.gear.values():
        if not gear.max_upgrade:
            continue
        item = make_item(gear, content.gearsets)
        per_level = sum(
            material_sell_price(make_material(content.materials[m])) * n
            for m, n in gear.upgrade_materials.items()
        )
        while item.upgrade < item.max_upgrade:
            better = at_max_upgrade(item)
            assert better is not None
            better.upgrade = item.upgrade + 1
            gain = sell_price(better) - sell_price(item)
            if gain >= upgrade_fee(item) + per_level * better.upgrade:
                problems.append(f"{gear.id}: upgrading it to +{better.upgrade} pays for itself")
            item = better
    return problems + lint_meals(content)


MEAL_POWER_PER_VALUE = 4.0
REGEN_POWER = 3.0  # a point of extra regen, in stat value


def meal_power(meal) -> float:
    """A meal's buff in stat value, for 60 turns: stats, plus extra regen."""
    return (stats_value(meal.stats) + REGEN_POWER * meal.regen) * meal.turns / 60


def lint_meals(content: Content) -> list[str]:
    problems = []
    for schema in content.meals.values():
        meal = make_meal(schema, content)
        if schema.sold and meal_price(meal) <= cook_fee(meal):
            problems.append(f"{schema.id}: buying it costs no more than cooking it (rule 2)")
        if meal_power(meal) > MEAL_POWER_PER_VALUE * meal.value:
            problems.append(
                f"{schema.id}: its buff ({meal_power(meal):.0f}) is too strong for its "
                f"ingredients (value {meal.value}; at most {MEAL_POWER_PER_VALUE:g}×)"
            )
    return problems


def shop_copy_low(content: Content, gear_id: str):
    """The cheapest copy a shop could sell (lowest rolls, no affix)."""
    gear = content.gear[gear_id]
    return make_item(gear, content.gearsets, {s: lo for s, (lo, _) in gear.rolls.items()})


def main(seeds: int = 50) -> int:
    from tidewrack.services.content import load_bundled_content

    content = load_bundled_content()
    reports = [simulate(seed, content) for seed in range(seeds)]
    problems = lint_content(content) + [p for r in reports for p in r.problems]

    def line(label: str, values: list[int]) -> str:
        values = sorted(values)
        p10 = values[len(values) // 10]
        return (
            f"{label:<29} median {statistics.median(values):>6.0f}   "
            f"p10 {p10:>5}   max {values[-1]:>5}"
        )

    print(f"Economy sim: {seeds} standard worlds")
    print(line("enemy gold", [r.enemy_gold for r in reports]))
    print(line("quest gold", [r.quest_gold for r in reports]))
    print(line("selling everything", [r.sales for r in reports]))
    print(line("selling every material", [r.materials for r in reports]))
    print(line("total income", [r.income for r in reports]))
    print(line("buying every first stock", [r.stock_cost for r in reports]))
    cheapest = [r.cheapest_ware for r in reports if r.cheapest_ware is not None]
    print(line("cheapest ware", cheapest))
    print(line("crafting fees (kit, recipes)", [r.crafting for r in reports]))
    print(f"{len(problems)} problem(s)")
    for problem in problems:
        print("  " + problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 50))

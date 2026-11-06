"""Seeded materials and recipes (step 7b): what lies about to gather, what enemies
drop, and which recipes a world teaches where.

Snapshots, like everything else made at world creation (CLAUDE.md §9): a Material
copies its definition, a Recipe holds the Item it makes. Gathering comes from the
seed's "gathering" substream (one sub-substream per location) and found recipes
from its "recipes" substream, so worlds, finds, enemies, quests and shops never
shift. Enemy drops are rolled with the enemy itself (core/procgen/enemy_gen.py).

Found recipes (content `known: false`) each turn up once per world: as a quest's
extra reward (at the world recipe's `quests.recipe_chance`), else as a page in a
room outside towns. Known recipes are taught to every new player.

Any change to this module's output for a given seed must bump
core.versions.GENERATOR_VERSION (tests/core/test_procgen.py pins golden hashes).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict
from typing import NamedTuple

from tidewrack.core.data.loader import Content
from tidewrack.core.data.schemas import (
    MaterialDropSchema,
    MaterialSchema,
    MealSchema,
    RecipeSchema,
    WorldRecipeSchema,
)
from tidewrack.core.engine.components import (
    GrowEntry,
    Grower,
    Material,
    MaterialDrop,
    MaterialStack,
    Meal,
    MealRecipe,
    Quest,
    Recipe,
    RecipePage,
)
from tidewrack.core.procgen.gear_gen import make_item
from tidewrack.core.rng import Rng
from tidewrack.core.world.overworld import Overworld


def make_material(schema: MaterialSchema) -> Material:
    return Material(schema.id, schema.name, schema.description, schema.value, schema.ingredient)


def make_meal(schema: MealSchema, content: Content) -> Meal:
    """A meal snapshot; its value is what its ingredients are worth."""
    worth = sum(content.materials[m].value * n for m, n in schema.ingredients.items())
    return Meal(
        schema.id,
        schema.name,
        schema.description,
        dict(schema.stats),
        schema.regen,
        schema.turns,
        worth,
    )


def meal_recipes(content: Content) -> list[MealRecipe]:
    """Every meal, as a tavern that cooks knows it."""
    return [
        MealRecipe(make_meal(m, content), stacks(m.ingredients, content), m.sold)
        for _, m in sorted(content.meals.items())
    ]


def stacks(counts: dict[str, int], content: Content) -> list[MaterialStack]:
    """Material id -> count, as snapshots in content order."""
    return [MaterialStack(make_material(content.materials[m]), n) for m, n in counts.items()]


def roll_drops(
    rng: Rng, drops: Iterable[MaterialDropSchema], content: Content
) -> list[MaterialStack]:
    """What one enemy drops: each of its kind's drops rolled in turn."""
    rolled = []
    for drop in drops:
        if rng.chance(drop.chance):
            count = rng.randint(*drop.count)
            rolled.append(MaterialStack(make_material(content.materials[drop.material]), count))
    return rolled


def drop_table(drops: Iterable[MaterialDropSchema], content: Content) -> list[MaterialDrop]:
    """A kind's drops as snapshots, for enemies that come back later."""
    return [
        MaterialDrop(make_material(content.materials[d.material]), d.chance, *d.count)
        for d in drops
    ]


def roll_template_drops(rng: Rng, drops: Iterable[MaterialDrop]) -> list[MaterialStack]:
    """roll_drops, for a returning enemy (from its template's snapshot)."""
    rolled = []
    for drop in drops:
        if rng.chance(drop.chance):
            rolled.append(MaterialStack(drop.material, rng.randint(drop.low, drop.high)))
    return rolled


# --- gathering ---------------------------------------------------------------------


class Gathered(NamedTuple):
    """Materials lying in a room; Game takes these as (location, room, stack)."""

    location: str
    room: str
    stack: MaterialStack


def generate_gathering(seed: int, world: Overworld, content: Content) -> list[Gathered]:
    rng = Rng(seed).derive("gathering")
    roomsets = {r.name: r for _, r in sorted(content.roomsets.items())}
    placed = []
    for location in world.locations.values():
        roomset = roomsets.get(location.kind)
        if roomset is None or not roomset.gathering.chance:
            continue
        table = roomset.gathering
        location_rng = rng.derive(f"gathering.{location.id}")
        choices = list(table.materials)
        weights = [table.materials[m] for m in choices]
        for room in location.rooms.values():
            if room.id in location.gates or not location_rng.chance(table.chance):
                continue
            material = content.materials[location_rng.weighted_choice(choices, weights)]
            count = location_rng.randint(*table.count)
            placed.append(
                Gathered(location.id, room.id, MaterialStack(make_material(material), count))
            )
    return placed


def generate_growers(world: Overworld, content: Content) -> list[Grower]:
    """Each wild location's regrowth: its roomset's gathering table, and a cap of
    about as many spots as it started with (at least 2). No randomness here; what
    regrows is rolled during play, on the game's saved gathering stream."""
    roomsets = {r.name: r for _, r in sorted(content.roomsets.items())}
    growers = []
    for location in world.locations.values():
        roomset = roomsets.get(location.kind)
        if roomset is None or not roomset.gathering.chance:
            continue
        table = roomset.gathering
        rooms = sum(1 for r in location.rooms if r not in location.gates)
        growers.append(
            Grower(
                location=location.id,
                cap=max(2, round(rooms * table.chance)),
                materials=[
                    GrowEntry(make_material(content.materials[m]), w)
                    for m, w in table.materials.items()
                ],
                low=table.count[0],
                high=table.count[1],
            )
        )
    return growers


def gathering_hash(placed: Iterable[Gathered]) -> str:
    """Stable fingerprint of a world's gathering, for golden-seed tests (§9)."""
    blob = json.dumps(
        [{"location": g.location, "room": g.room, "stack": asdict(g.stack)} for g in placed],
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


# --- recipes -----------------------------------------------------------------------


def make_recipe(schema: RecipeSchema, content: Content) -> Recipe:
    """A recipe snapshot. Crafted gear has its best roll (quest rewards add an
    affix on top, so they're still a cut above), plus the recipe's own affix."""
    gear = content.gear[schema.makes]
    affixes = [content.affixes[schema.affix]] if schema.affix else []
    item = make_item(gear, content.gearsets, {s: hi for s, (_, hi) in gear.rolls.items()}, affixes)
    return Recipe(schema.id, item.display_name, item, stacks(schema.materials, content))


def known_recipes(content: Content) -> list[Recipe]:
    """What every new player knows, in content order."""
    return [make_recipe(r, content) for _, r in sorted(content.recipes.items()) if r.known]


class Page(NamedTuple):
    """A recipe page in a room; Game takes these as (location, room, page)."""

    location: str
    room: str
    page: RecipePage


class RecipePlan(NamedTuple):
    rewards: dict[str, Recipe]  # quest id -> the recipe it also teaches
    pages: list[Page]


def generate_recipes(
    seed: int,
    world: Overworld,
    content: Content,
    recipe: WorldRecipeSchema,
    quests: Iterable[Quest] = (),
) -> RecipePlan:
    """Place each found recipe once: on a quest (some), else as a page in the wild."""
    rng = Rng(seed).derive("recipes")
    open_quests = [q.quest_id for q in quests]
    wild = [
        loc
        for loc in world.locations.values()
        if not loc.town and any(r not in loc.gates for r in loc.rooms)
    ]
    plan = RecipePlan({}, [])
    for _, schema in sorted(content.recipes.items()):
        if schema.known:
            continue
        made = make_recipe(schema, content)
        if open_quests and rng.chance(recipe.quests.recipe_chance):
            quest_id = open_quests.pop(rng.randint(0, len(open_quests) - 1))
            plan.rewards[quest_id] = made
        elif wild:
            location = rng.choice(wild)
            room = rng.choice([r for r in location.rooms if r not in location.gates])
            plan.pages.append(Page(location.id, room, RecipePage(made)))
    return plan


def recipes_hash(known: Iterable[Recipe], plan: RecipePlan) -> str:
    """Stable fingerprint of a world's recipes, for golden-seed tests (§9)."""
    blob = json.dumps(
        {
            "known": [asdict(r) for r in known],
            "rewards": {q: asdict(r) for q, r in plan.rewards.items()},
            "pages": [
                {"location": p.location, "room": p.room, "recipe": asdict(p.page.recipe)}
                for p in plan.pages
            ],
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()

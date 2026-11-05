"""Seeded enemies: those placed in rooms, and each location's wanderers.

Everything is decided at world creation (CLAUDE.md §9), on the seed's "enemies"
substream with one sub-substream per location, so world layout and gear finds
never shift. Each enemy is a self-contained snapshot, loot included (rolled
now), and a location's wandering enemies are rolled up front into its Spawner
queue. As with finds, a location's roomset is the one whose name is its kind;
towns and hand-authored dungeons have no enemies table and stay peaceful.

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
from tidewrack.core.data.schemas import EnemySchema
from tidewrack.core.engine.components import Enemy, EnemyTemplate, Spawner
from tidewrack.core.gear.stats import STATS
from tidewrack.core.procgen.gear_gen import roll_item
from tidewrack.core.rng import Rng
from tidewrack.core.world.overworld import Overworld

LOOT_AFFIX_CHANCE = 0.3
RETURN_LOOT_PIECES = 3  # pre-rolled loot pieces per template, for returning enemies


class PlacedEnemy(NamedTuple):
    """An enemy in a room; Game takes these as (location, room, enemy)."""

    location: str
    room: str
    enemy: Enemy


def make_enemy(rng: Rng, schema: EnemySchema, content: Content) -> Enemy:
    stats = dict(schema.stats)
    for stat in STATS:
        if stat in schema.rolls:
            stats[stat] = stats.get(stat, 0) + rng.randint(*schema.rolls[stat])
    loot = []
    if schema.loot.chance and rng.chance(schema.loot.chance):
        choices = list(schema.loot.gear)
        gear_id = rng.weighted_choice(choices, [schema.loot.gear[g] for g in choices])
        loot.append(roll_item(rng, content.gear[gear_id], content, LOOT_AFFIX_CHANCE))
    gold = rng.randint(*schema.gold) if schema.gold[1] else 0  # beasts don't use a draw
    return Enemy(
        enemy_id=schema.id,
        name=schema.name,
        category=schema.category,
        description=schema.description,
        stats=stats,
        drops=sorted({content.gear[g].name for g in schema.loot.gear}),
        loot=loot,
        gold=gold,
    )


def generate_enemies(
    seed: int, world: Overworld, content: Content
) -> tuple[list[PlacedEnemy], list[Spawner]]:
    rng = Rng(seed).derive("enemies")
    roomsets = {r.name: r for _, r in sorted(content.roomsets.items())}
    placed, spawners = [], []
    for location in world.locations.values():
        roomset = roomsets.get(location.kind)
        if roomset is None or not roomset.enemies.pool:
            continue
        table = roomset.enemies
        location_rng = rng.derive(f"enemies.{location.id}")
        choices = list(table.pool)
        weights = [table.pool[e] for e in choices]

        for room in location.rooms.values():
            if room.id not in location.gates and location_rng.chance(table.placed_chance):
                enemy = _pick(location_rng, choices, weights, content)
                placed.append(PlacedEnemy(location.id, room.id, enemy))
        if table.wandering_chance:
            queue = [_pick(location_rng, choices, weights, content) for _ in range(table.wanderers)]
            # What can come back later (step 6c), on its own substream so the
            # placed enemies and the first queue never shift.
            returns_rng = rng.derive(f"returns.{location.id}")
            templates = [
                make_template(returns_rng, content.enemies[e], table.pool[e], content)
                for e in sorted(table.pool)
            ]
            spawners.append(
                Spawner(location.id, table.wandering_chance, queue, table.wanderers, templates)
            )
    return placed, spawners


def make_template(rng: Rng, schema: EnemySchema, weight: float, content: Content) -> EnemyTemplate:
    """A snapshot of an enemy kind, with a few loot pieces rolled now."""
    loot = []
    if schema.loot.chance and schema.loot.gear:
        choices = sorted(schema.loot.gear)
        weights = [schema.loot.gear[g] for g in choices]
        for _ in range(RETURN_LOOT_PIECES):
            gear = content.gear[rng.weighted_choice(choices, weights)]
            loot.append(roll_item(rng, gear, content, LOOT_AFFIX_CHANCE))
    return EnemyTemplate(
        enemy_id=schema.id,
        name=schema.name,
        category=schema.category,
        description=schema.description,
        stats=dict(schema.stats),
        rolls={s: list(r) for s, r in schema.rolls.items()},
        drops=sorted({content.gear[g].name for g in schema.loot.gear}),
        loot_chance=schema.loot.chance,
        loot=loot,
        weight=weight,
        gold=list(schema.gold),
    )


def _pick(rng: Rng, choices: list[str], weights: list[float], content: Content) -> Enemy:
    return make_enemy(rng, content.enemies[rng.weighted_choice(choices, weights)], content)


def enemies_hash(placed: Iterable[PlacedEnemy], spawners: Iterable[Spawner]) -> str:
    """Stable fingerprint of a world's enemies, for golden-seed tests (§9)."""
    blob = json.dumps(
        {
            "placed": [
                {"location": p.location, "room": p.room, "enemy": asdict(p.enemy)} for p in placed
            ],
            "spawners": [asdict(s) for s in spawners],
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()

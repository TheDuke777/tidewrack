"""Seeded gear: the starting kit and the finds lying about a new world.

Finds are placed when the world is made (CLAUDE.md §9), from the seed's "gear"
substream with one sub-substream per location. That keeps them independent of
world layout and naming: world_hash doesn't change, and editing one location's
finds never moves another's. A location's finds come from the roomset whose
name is its kind (the loader keeps roomset names unique); hand-authored
locations (kind "Dungeon") have none.

Any change to this module's output for a given seed must bump
core.versions.GENERATOR_VERSION (tests/core/test_procgen.py pins golden hashes).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from typing import NamedTuple

from tidewrack.core.data.loader import Content
from tidewrack.core.data.schemas import AffixSchema, GearSchema, GearSetSchema, WorldRecipeSchema
from tidewrack.core.gear.item import Affix, GearSet, Item, SetBonus
from tidewrack.core.gear.stats import STATS
from tidewrack.core.rng import Rng
from tidewrack.core.world.overworld import Overworld


class Find(NamedTuple):
    """An item lying in a room; Game takes these as (location, room, item)."""

    location: str
    room: str
    item: Item


def make_item(
    gear: GearSchema,
    gearsets: Mapping[str, GearSetSchema],
    roll: Mapping[str, int] | None = None,
    affixes: Iterable[AffixSchema] = (),
) -> Item:
    """Resolve a gear definition into a self-contained Item."""
    gear_set = None
    if gear.set is not None:
        schema = gearsets[gear.set]
        gear_set = GearSet(
            id=schema.id,
            name=schema.name,
            bonuses=[
                SetBonus(b.pieces, dict(b.stats), list(b.effects))
                for b in sorted(schema.bonuses, key=lambda b: b.pieces)
            ],
            color=schema.color,
        )
    return Item(
        gear_id=gear.id,
        name=gear.name,
        slot=gear.slot,
        two_handed=gear.two_handed,
        base=dict(gear.base),
        roll={s: v for s, v in (roll or {}).items() if v},
        max_upgrade=gear.max_upgrade,
        upgrade_step=dict(gear.upgrade_step),
        affixes=[
            Affix(a.id, a.name, a.position == "prefix", dict(a.stats), list(a.effects))
            for a in affixes
        ],
        effects=list(gear.effects),
        gear_set=gear_set,
    )


def roll_item(rng: Rng, gear: GearSchema, content: Content, affix_chance: float) -> Item:
    """A found copy of `gear`: each roll drawn in its range, maybe one affix."""
    roll = {s: rng.randint(*gear.rolls[s]) for s in STATS if s in gear.rolls}
    affixes = []
    if rng.chance(affix_chance):
        eligible = [a for _, a in sorted(content.affixes.items()) if gear.slot in a.slots]
        if eligible:
            affixes.append(rng.weighted_choice(eligible, [a.weight for a in eligible]))
    return make_item(gear, content.gearsets, roll, affixes)


def generate_kit(recipe: WorldRecipeSchema, content: Content) -> list[Item]:
    """The starting kit: plain copies (lowest rolls, no affixes), equipped at start."""
    return [
        make_item(
            content.gear[g],
            content.gearsets,
            {s: low for s, (low, _) in content.gear[g].rolls.items()},
        )
        for g in recipe.kit
    ]


def generate_finds(seed: int, world: Overworld, content: Content) -> list[Find]:
    rng = Rng(seed).derive("gear")
    roomsets = {r.name: r for _, r in sorted(content.roomsets.items())}
    finds = []
    for location in world.locations.values():
        roomset = roomsets.get(location.kind)
        if roomset is None or not roomset.finds.chance:
            continue
        location_rng = rng.derive(f"finds.{location.id}")
        choices = list(roomset.finds.gear)
        weights = [roomset.finds.gear[g] for g in choices]
        for room in location.rooms.values():
            if room.id in location.gates or not location_rng.chance(roomset.finds.chance):
                continue
            gear = content.gear[location_rng.weighted_choice(choices, weights)]
            item = roll_item(location_rng, gear, content, roomset.finds.affix_chance)
            finds.append(Find(location.id, room.id, item))
    return finds


def finds_hash(finds: Iterable[Find]) -> str:
    """Stable fingerprint of a world's finds, for golden-seed tests (§9)."""
    blob = json.dumps(
        [{"location": f.location, "room": f.room, "item": asdict(f.item)} for f in finds],
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()

"""Seeded world generator: an overworld of locations, each fully generated.

The overworld uses the same grid layout as rooms do (grid.py), with locations as
nodes and roads as edges. The start location is the recipe's `start` kind (a
town); the rest are drawn by weight from its roomsets. Every location's rooms are
generated up front from its own substream and the whole world is snapshotted into
the save, so updates to the generator or content never change an existing world
(CLAUDE.md §9).

Any change to this module's output for a given seed must bump
core.versions.GENERATOR_VERSION (tests/core/test_procgen.py pins golden hashes).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import replace

from tidewrack.core.data.schemas import OverworldSchema, RoomsetSchema, WorldRecipeSchema
from tidewrack.core.procgen.grid import Shape, grow_layout, roman
from tidewrack.core.procgen.location_gen import generate_location
from tidewrack.core.rng import Rng
from tidewrack.core.world.overworld import Overworld

OVERWORLD_SHAPE = Shape(spread=2.0, loops=0.3, corridors=0.35)


def generate_world(
    seed: int, recipe: WorldRecipeSchema, roomsets: Mapping[str, RoomsetSchema]
) -> Overworld:
    """The world for a new game. Uses the "worldgen" substream of the seed, so it's
    independent of the in-game streams Game derives from the same seed."""
    rng = Rng(seed).derive("worldgen")
    layout_rng, kinds_rng, names_rng = (
        rng.derive("layout"),
        rng.derive("kinds"),
        rng.derive("names"),
    )

    layout = grow_layout(layout_rng, recipe.locations, OVERWORLD_SHAPE)
    ids = {cell: f"loc_{i:02d}" for i, cell in enumerate(layout.cells)}
    choices = list(recipe.roomsets)
    weights = [recipe.roomsets[c] for c in choices]

    used_names: set[str] = set()
    locations = {}
    for i, cell in enumerate(layout.cells):
        roomset = roomsets[recipe.start if i == 0 else kinds_rng.weighted_choice(choices, weights)]
        location_id = ids[cell]
        location_rng = rng.derive(f"location.{location_id}")
        location = generate_location(
            location_rng,
            roomset,
            location_rng.randint(*roomset.size),
            location_id,
            name=_unique_name(names_rng, roomset, used_names),
        )
        locations[location_id] = replace(
            location,
            pos=layout.place(layout_rng, cell),
            roads=tuple(ids[to] for to, _ in layout.directions(cell)),
        )

    world = Overworld(start=ids[layout.cells[0]], locations=locations)
    if problems := world.problems():  # the algorithm guarantees validity
        raise AssertionError(f"generator produced an invalid world: {problems}")
    return world


def world_hash(world: Overworld) -> str:
    """Stable fingerprint of a generated world, for golden-seed tests (§9)."""
    blob = OverworldSchema.from_overworld(world).model_dump_json()
    return hashlib.sha256(blob.encode()).hexdigest()


def _unique_name(rng: Rng, roomset: RoomsetSchema, used: set[str]) -> str:
    fresh = [n for n in roomset.location_names if n not in used]
    if fresh:
        name = rng.choice(fresh)
    else:
        base, n = rng.choice(roomset.location_names), 2
        while (name := f"{base} {roman(n)}") in used:
            n += 1
    used.add(name)
    return name

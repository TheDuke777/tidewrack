"""Seeded world generator: an overworld of locations, each fully generated.

The overworld uses the same grid layout as rooms do (grid.py), with locations as
nodes and roads as edges, grown region by region (coast first) so each region is
a cluster joined to the one before by a single road. Each region's first place
is its town (the coast's is where the game starts); the rest are drawn by weight
from its roomsets. Every location's rooms are
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

from tidewrack.core.data.schemas import (
    OverworldSchema,
    RegionSchema,
    RoomsetSchema,
    WorldRecipeSchema,
)
from tidewrack.core.procgen.grid import Shape, grow_regions, roman
from tidewrack.core.procgen.location_gen import generate_location
from tidewrack.core.rng import Rng
from tidewrack.core.world.overworld import Overworld, Region

OVERWORLD_SHAPE = Shape(spread=2.0, loops=0.3, corridors=0.35)


def generate_world(
    seed: int,
    recipe: WorldRecipeSchema,
    roomsets: Mapping[str, RoomsetSchema],
    regions: Mapping[str, RegionSchema],
) -> Overworld:
    """The world for a new game. Uses the "worldgen" substream of the seed, so it's
    independent of the in-game streams Game derives from the same seed."""
    rng = Rng(seed).derive("worldgen")
    layout_rng, kinds_rng, names_rng = (
        rng.derive("layout"),
        rng.derive("kinds"),
        rng.derive("names"),
    )

    plans = [(regions[p.region], p.locations) for p in recipe.regions]
    layout = grow_regions(layout_rng, [n for _, n in plans], OVERWORLD_SHAPE)
    ids = {cell: f"loc_{i:02d}" for i, cell in enumerate(layout.cells)}

    used_names: set[str] = set()
    world_regions = {}
    locations = {}
    for (region, _), cells in zip(plans, layout.regions, strict=True):
        world_regions[region.id] = Region(
            region.id, names_rng.choice(region.names), region.name, region.tier
        )
        choices = list(region.roomsets)
        weights = [region.roomsets[c] for c in choices]
        for i, cell in enumerate(cells):
            roomset = roomsets[
                region.town if i == 0 else kinds_rng.weighted_choice(choices, weights)
            ]
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
                region=region.id,
                town=roomset.town,
            )

    world = Overworld(start=ids[layout.cells[0]], locations=locations, regions=world_regions)
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

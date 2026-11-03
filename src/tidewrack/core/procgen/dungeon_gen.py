"""Seeded dungeon generator: a point-crawl map built from a roomset.

Layout: rooms occupy cells of a square grid. Starting from an entrance on the
south edge, the dungeon grows one room at a time into a free orthogonal neighbour
of an existing room (a random spanning tree, so everything is reachable), then a
few extra edges between adjacent rooms add loops. Orthogonal edges never cross,
which keeps the map readable; positions are jittered within their cells so it
doesn't look like graph paper. Exits are labelled by compass direction.

Layout and naming draw from separate RNG substreams, so changing how rooms are
named never changes a world's shape. Any change to this module's output for a
given seed must bump core.versions.GENERATOR_VERSION (tests/core/test_procgen.py
pins a golden hash).
"""

from __future__ import annotations

import hashlib
import math

from tidewrack.core.data.schemas import ArchetypeSchema, DungeonSchema, RoomsetSchema
from tidewrack.core.rng import Rng
from tidewrack.core.world.dungeon import DungeonMap, Exit, Node

Cell = tuple[int, int]  # (col, row); row 0 is the north edge

# Compass order is also the order exits are listed in.
DIRECTIONS: dict[Cell, str] = {(0, -1): "north", (1, 0): "east", (0, 1): "south", (-1, 0): "west"}
SPREAD = 1.8  # grid cells per room: higher = more room to wander, sparser maps
LOOP_CHANCE = 0.25  # chance each extra adjacent pair gets joined
EXTEND_NEWEST = 0.5  # chance to grow from the newest room (longer corridors)
JITTER = 0.22  # max offset of a room from its cell centre, in cells
MAX_FEATURES = 2


def generate_dungeon(
    rng: Rng, roomset: RoomsetSchema, size: int, dungeon_id: str = "dungeon.generated"
) -> DungeonMap:
    if size < 2:
        raise ValueError("a dungeon needs at least two rooms")
    layout_rng, names_rng = rng.derive("layout"), rng.derive("names")

    side = math.ceil(math.sqrt(size * SPREAD))
    cells, edges = _grow(layout_rng, side, size)
    edges |= _loops(layout_rng, cells, edges)
    ids = {cell: f"room_{i:02d}" for i, cell in enumerate(cells)}

    used_names: set[str] = set()
    nodes = {}
    for i, cell in enumerate(cells):
        archetype = roomset.entrance if i == 0 else _pick_archetype(names_rng, roomset)
        name = _unique_name(names_rng, roomset, archetype, used_names, entrance=i == 0)
        x, y = cell
        nodes[ids[cell]] = Node(
            id=ids[cell],
            name=name,
            description=names_rng.choice(archetype.descriptions),
            exits=tuple(
                Exit(f"Go {direction}", ids[(x + dx, y + dy)])
                for (dx, dy), direction in DIRECTIONS.items()
                if frozenset((cell, (x + dx, y + dy))) in edges
            ),
            features=_pick_features(names_rng, archetype),
            ambient=tuple(archetype.ambient),
            pos=(
                _place(layout_rng, x, side),
                _place(layout_rng, y, side),
            ),
        )

    dungeon = DungeonMap(
        id=dungeon_id,
        name=names_rng.choice(roomset.dungeon_names),
        start=ids[cells[0]],
        nodes=nodes,
    )
    if problems := dungeon.problems():  # the algorithm guarantees validity
        raise AssertionError(f"generator produced an invalid dungeon: {problems}")
    return dungeon


def generate_world(seed: int, roomset: RoomsetSchema, size: int) -> DungeonMap:
    """The dungeon for a new world. Uses the "worldgen" substream of the world seed,
    so it's independent of the in-game streams Game derives from the same seed."""
    return generate_dungeon(Rng(seed).derive("worldgen"), roomset, size)


def world_hash(dungeon: DungeonMap) -> str:
    """Stable fingerprint of a generated world, for golden-seed tests (§9)."""
    blob = DungeonSchema.from_map(dungeon).model_dump_json()
    return hashlib.sha256(blob.encode()).hexdigest()


# --- layout ------------------------------------------------------------------------


def _neighbours(cell: Cell, side: int) -> list[Cell]:
    x, y = cell
    return [(x + dx, y + dy) for dx, dy in DIRECTIONS if 0 <= x + dx < side and 0 <= y + dy < side]


def _grow(rng: Rng, side: int, size: int) -> tuple[list[Cell], set[frozenset[Cell]]]:
    start = (rng.below(side), side - 1)  # enter from the south edge
    cells, taken = [start], {start}
    edges: set[frozenset[Cell]] = set()
    while len(cells) < size:
        frontier = [c for c in cells if any(n not in taken for n in _neighbours(c, side))]
        parent = frontier[-1] if rng.chance(EXTEND_NEWEST) else rng.choice(frontier)
        child = rng.choice([n for n in _neighbours(parent, side) if n not in taken])
        cells.append(child)
        taken.add(child)
        edges.add(frozenset((parent, child)))
    return cells, edges


def _loops(rng: Rng, cells: list[Cell], edges: set[frozenset[Cell]]) -> set[frozenset[Cell]]:
    taken = set(cells)
    extra = set()
    for x, y in cells:
        for other in ((x + 1, y), (x, y + 1)):  # each adjacent pair considered once
            pair = frozenset(((x, y), other))
            if other in taken and pair not in edges and rng.chance(LOOP_CHANCE):
                extra.add(pair)
    return extra


def _place(rng: Rng, index: int, side: int) -> float:
    offset = (rng.random() * 2 - 1) * JITTER
    return round((index + 0.5 + offset) / side, 4)


# --- naming and dressing -----------------------------------------------------------


def _pick_archetype(rng: Rng, roomset: RoomsetSchema) -> ArchetypeSchema:
    return rng.weighted_choice(roomset.rooms, [a.weight for a in roomset.rooms])


def _unique_name(
    rng: Rng, roomset: RoomsetSchema, archetype: ArchetypeSchema, used: set[str], entrance: bool
) -> str:
    if entrance:
        name = f"The {archetype.noun}"
    else:
        for _ in range(10):
            name = f"{rng.choice(roomset.adjectives)} {archetype.noun}"
            if name not in used:
                break
        base, n = name, 2
        while name in used:
            name, n = f"{base} {_roman(n)}", n + 1
    used.add(name)
    return name


def _pick_features(rng: Rng, archetype: ArchetypeSchema) -> tuple[str, ...]:
    pool = list(archetype.features)
    rng.shuffle(pool)
    return tuple(pool[: rng.randint(0, min(MAX_FEATURES, len(pool)))])


def _roman(n: int) -> str:
    numerals = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for value, letters in numerals:
        while n >= value:
            out, n = out + letters, n - value
    return out

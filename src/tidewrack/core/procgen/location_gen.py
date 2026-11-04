"""Seeded location generator: one location's rooms, built from a roomset.

Rooms are laid out on a grid (see grid.py) shaped by the roomset's layout: towns
compact and loopy, mines long and branching, and so on. Exits are labelled by
compass direction; the entrance room is the location's gate.

Layout and naming draw from separate RNG substreams, so changing how rooms are
named never changes a location's shape. Any change to this module's output for a
given seed must bump core.versions.GENERATOR_VERSION (tests/core/test_procgen.py
pins golden hashes).
"""

from __future__ import annotations

from tidewrack.core.data.schemas import ArchetypeSchema, RoomsetSchema
from tidewrack.core.procgen.grid import Shape, grow_layout, roman
from tidewrack.core.rng import Rng
from tidewrack.core.world.location import Exit, Location, Room

MAX_FEATURES = 2


def generate_location(
    rng: Rng,
    roomset: RoomsetSchema,
    size: int,
    location_id: str = "location",
    name: str | None = None,
) -> Location:
    """A location of `size` rooms. Without `name`, one is picked from the roomset."""
    if size < 2:
        raise ValueError("a location needs at least two rooms")
    layout_rng, names_rng = rng.derive("layout"), rng.derive("names")

    shape = Shape(roomset.layout.spread, roomset.layout.loops, roomset.layout.corridors)
    layout = grow_layout(layout_rng, size, shape)
    ids = {cell: f"room_{i:02d}" for i, cell in enumerate(layout.cells)}

    used_names: set[str] = set()
    rooms = {}
    for i, cell in enumerate(layout.cells):
        archetype = roomset.entrance if i == 0 else _pick_archetype(names_rng, roomset)
        room_name = _unique_name(names_rng, roomset, archetype, used_names, entrance=i == 0)
        rooms[ids[cell]] = Room(
            id=ids[cell],
            name=room_name,
            description=names_rng.choice(archetype.descriptions),
            exits=tuple(Exit(f"Go {d}", ids[to]) for to, d in layout.directions(cell)),
            features=_pick_features(names_rng, archetype),
            ambient=tuple(archetype.ambient),
            pos=layout.place(layout_rng, cell),
        )

    start = ids[layout.cells[0]]
    location = Location(
        id=location_id,
        name=name or names_rng.choice(roomset.location_names),
        kind=roomset.name,
        start=start,
        rooms=rooms,
        gates=(start,),
    )
    if problems := location.problems():  # the algorithm guarantees validity
        raise AssertionError(f"generator produced an invalid location: {problems}")
    return location


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
            name, n = f"{base} {roman(n)}", n + 1
    used.add(name)
    return name


def _pick_features(rng: Rng, archetype: ArchetypeSchema) -> tuple[str, ...]:
    pool = list(archetype.features)
    rng.shuffle(pool)
    return tuple(pool[: rng.randint(0, min(MAX_FEATURES, len(pool)))])

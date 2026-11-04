"""Grid layout shared by the location and overworld generators.

Nodes occupy cells of a square grid. Starting from a cell on the south edge, the
graph grows one node at a time into a free orthogonal neighbour of an existing
node (a random spanning tree, so everything is reachable), then a few extra edges
between adjacent nodes add loops. Orthogonal edges never cross, which keeps maps
readable; positions are jittered within their cells so they don't look like
graph paper.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from tidewrack.core.rng import Rng

Cell = tuple[int, int]  # (col, row); row 0 is the north edge
Edge = frozenset[Cell]

# Compass order is also the order exits are listed in.
DIRECTIONS: dict[Cell, str] = {(0, -1): "north", (1, 0): "east", (0, 1): "south", (-1, 0): "west"}
JITTER = 0.22  # max offset of a node from its cell centre, in cells


@dataclass(frozen=True)
class Shape:
    spread: float  # grid cells per node: higher = sparser maps
    loops: float  # chance each extra adjacent pair gets joined
    corridors: float  # chance to grow from the newest node (longer chains)


@dataclass(frozen=True)
class GridLayout:
    side: int
    cells: list[Cell]  # in growth order; cells[0] is the start
    edges: set[Edge]

    def joined(self, a: Cell, b: Cell) -> bool:
        return frozenset((a, b)) in self.edges

    def directions(self, cell: Cell) -> list[tuple[Cell, str]]:
        """Neighbours joined to `cell`, in compass order."""
        x, y = cell
        return [
            ((x + dx, y + dy), name)
            for (dx, dy), name in DIRECTIONS.items()
            if self.joined(cell, (x + dx, y + dy))
        ]

    def place(self, rng: Rng, cell: Cell) -> tuple[float, float]:
        return (_place(rng, cell[0], self.side), _place(rng, cell[1], self.side))


def grow_layout(rng: Rng, size: int, shape: Shape) -> GridLayout:
    side = math.ceil(math.sqrt(size * shape.spread))
    cells, edges = _grow(rng, side, size, shape.corridors)
    edges |= _loops(rng, cells, edges, shape.loops)
    return GridLayout(side, cells, edges)


def _neighbours(cell: Cell, side: int) -> list[Cell]:
    x, y = cell
    return [(x + dx, y + dy) for dx, dy in DIRECTIONS if 0 <= x + dx < side and 0 <= y + dy < side]


def _grow(rng: Rng, side: int, size: int, corridors: float) -> tuple[list[Cell], set[Edge]]:
    start = (rng.below(side), side - 1)  # enter from the south edge
    cells, taken = [start], {start}
    edges: set[Edge] = set()
    while len(cells) < size:
        frontier = [c for c in cells if any(n not in taken for n in _neighbours(c, side))]
        parent = frontier[-1] if rng.chance(corridors) else rng.choice(frontier)
        child = rng.choice([n for n in _neighbours(parent, side) if n not in taken])
        cells.append(child)
        taken.add(child)
        edges.add(frozenset((parent, child)))
    return cells, edges


def _loops(rng: Rng, cells: list[Cell], edges: set[Edge], chance: float) -> set[Edge]:
    taken = set(cells)
    extra = set()
    for x, y in cells:
        for other in ((x + 1, y), (x, y + 1)):  # each adjacent pair considered once
            pair = frozenset(((x, y), other))
            if other in taken and pair not in edges and rng.chance(chance):
                extra.add(pair)
    return extra


def _place(rng: Rng, index: int, side: int) -> float:
    offset = (rng.random() * 2 - 1) * JITTER
    return round((index + 0.5 + offset) / side, 4)


def roman(n: int) -> str:
    numerals = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for value, letters in numerals:
        while n >= value:
            out, n = out + letters, n - value
    return out

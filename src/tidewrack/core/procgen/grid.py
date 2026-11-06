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


@dataclass(frozen=True)
class RegionLayout(GridLayout):
    regions: list[list[Cell]]  # each region's cells, in growth order (its entry first)


MAX_ATTEMPTS = 12  # layouts tried on one grid size before trying a bigger grid


def grow_regions(rng: Rng, sizes: list[int], shape: Shape) -> RegionLayout:
    """Regions grown one after another on one grid, so each is a cluster: the
    first from the south edge, each later one from a free cell beside the deepest
    part of the one before (northward when it can), joined to it by one road.
    Loops only join cells of the same region, so that road is the only way in.

    A region can box itself in before it's full; then the whole layout is tried
    again on a fresh substream, and after a few tries on a bigger grid."""
    side = math.ceil(math.sqrt(sum(sizes) * shape.spread))
    attempt = 0
    while True:
        layout = _try_regions(rng.derive(f"attempt.{attempt}"), side, sizes, shape)
        if layout is not None:
            return layout
        attempt += 1
        if attempt % MAX_ATTEMPTS == 0:
            side += 1


def _try_regions(rng: Rng, side: int, sizes: list[int], shape: Shape) -> RegionLayout | None:
    taken: set[Cell] = set()
    edges: set[Edge] = set()
    regions: list[list[Cell]] = []
    for size in sizes:
        if not regions:
            entry, parent = (rng.below(side), side - 1), None
        else:
            depth = _depths(regions[0][0], edges)
            previous = regions[-1]
            open_cells = [c for c in previous if any(n not in taken for n in _neighbours(c, side))]
            if not open_cells:
                return None
            deepest = max(depth[c] for c in open_cells)
            parent = rng.choice([c for c in open_cells if depth[c] == deepest])
            free = [n for n in _neighbours(parent, side) if n not in taken]
            north = min(n[1] for n in free)
            entry = rng.choice([n for n in free if n[1] == north])
        cells = [entry]
        taken.add(entry)
        if parent is not None:
            edges.add(frozenset((parent, entry)))
        while len(cells) < size:
            frontier = [c for c in cells if any(n not in taken for n in _neighbours(c, side))]
            if not frontier:
                return None
            grow_from = frontier[-1] if rng.chance(shape.corridors) else rng.choice(frontier)
            child = rng.choice([n for n in _neighbours(grow_from, side) if n not in taken])
            cells.append(child)
            taken.add(child)
            edges.add(frozenset((grow_from, child)))
        regions.append(cells)
    for cells in regions:
        edges |= _loops(rng, cells, edges, shape.loops)
    return RegionLayout(side, [c for cells in regions for c in cells], edges, regions)


def _depths(start: Cell, edges: set[Edge]) -> dict[Cell, int]:
    """Road steps from `start` to every cell joined to it."""
    links: dict[Cell, list[Cell]] = {}
    for edge in edges:
        a, b = tuple(edge)
        links.setdefault(a, []).append(b)
        links.setdefault(b, []).append(a)
    depth, todo = {start: 0}, [start]
    while todo:
        cell = todo.pop(0)
        for nxt in sorted(links.get(cell, ())):
            if nxt not in depth:
                depth[nxt] = depth[cell] + 1
                todo.append(nxt)
    return depth


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

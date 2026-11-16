"""Where regions meet on the world map, as dotted borders along the overworld grid.

The overworld is laid out on a square grid (procgen/grid.py): each place sits in
its own cell, jittered at most JITTER from the cell's centre. Worlds don't save
the grid's size, so `grid_side` recovers it from the saved positions.

`region_borders` works only from the places it's given (the ones the player
knows), so a border never gives away land they haven't found: each known place's
cell and the cells around it are claimed by the nearest known place's region, and
a border runs wherever two regions' claimed cells meet.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from tidewrack.core.procgen.grid import JITTER

Segment = tuple[float, float, float, float]  # x1, y1, x2, y2 in 0..1 map coordinates
Place = tuple[float, float, int]  # x, y (0..1) and its region's order (ties go to the lower)


def grid_side(positions: Sequence[tuple[float, float]]) -> int | None:
    """The overworld grid's side: the smallest one every position fits, as
    (cell + 0.5 ± JITTER) / side. None if none does (not a grid layout)."""
    if not positions:
        return None
    tolerance = JITTER + 0.001  # positions are saved rounded to 4 decimals
    limit = 10 * len(positions) + 10
    for side in range(max(1, math.isqrt(len(positions))), limit):
        if all(
            abs(v * side - 0.5 - round(v * side - 0.5)) <= tolerance
            for pos in positions
            for v in pos
        ):
            return side
    return None


def region_borders(places: Sequence[Place], side: int) -> tuple[Segment, ...]:
    """Straight runs along cell edges where two regions' ground meets (none
    unless the places span at least two regions)."""
    if len({region for _, _, region in places}) < 2:
        return ()

    def cell(x: float, y: float) -> tuple[int, int]:
        return (min(side - 1, int(x * side)), min(side - 1, int(y * side)))

    def owner(c: tuple[int, int]) -> int:
        cx, cy = c[0] + 0.5, c[1] + 0.5
        nearest = min(
            places, key=lambda p: ((p[0] * side - cx) ** 2 + (p[1] * side - cy) ** 2, p[2])
        )
        return nearest[2]

    ground: dict[tuple[int, int], int] = {}
    for kx, ky in sorted({cell(x, y) for x, y, _ in places}):
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                c = (kx + dx, ky + dy)
                if 0 <= c[0] < side and 0 <= c[1] < side and c not in ground:
                    ground[c] = owner(c)

    # Unit edges by their start corner: vertical ones run down, horizontal ones right.
    vertical, horizontal = set(), set()
    for (x, y), region in ground.items():
        if ground.get((x + 1, y), region) != region:
            vertical.add((x + 1, y))
        if ground.get((x, y + 1), region) != region:
            horizontal.add((x, y + 1))

    segments: list[Segment] = []
    for edges, down in ((vertical, True), (horizontal, False)):
        step = (0, 1) if down else (1, 0)
        for start in sorted(edges):
            if (start[0] - step[0], start[1] - step[1]) in edges:
                continue  # inside a run; its start adds it
            end = start
            while (end[0] + step[0], end[1] + step[1]) in edges:
                end = (end[0] + step[0], end[1] + step[1])
            x2, y2 = end[0] + step[0], end[1] + step[1]
            segments.append((start[0] / side, start[1] / side, x2 / side, y2 / side))
    return tuple(segments)

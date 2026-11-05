"""The stats gear and the player have (CLAUDE.md §8.4).

A stat block is a plain ``{stat id: int}`` dict. Missing stats count as 0, and
every helper returns a full block with every stat, in STATS order, so blocks
compare and display consistently. A new stat is one entry here (plus content).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

STATS = ("atk", "def", "hp")
STAT_LABELS = {"atk": "ATK", "def": "DEF", "hp": "HP"}
STAT_NAMES = {"atk": "Attack", "def": "Defence", "hp": "Health"}
# Gold each point of a stat is worth (core/economy/value_model.py). A point of
# DEF takes about as much off every blow as a point of ATK adds; HP is cheaper.
STAT_VALUES = {"atk": 5.0, "def": 5.0, "hp": 1.5}

StatBlock = dict[str, int]

# The player's starting stats when a world recipe doesn't set its own, and for
# saves made before stats existed (schema v3; see services/storage/migrations.py).
DEFAULT_PLAYER_BASE: Mapping[str, int] = {"atk": 2, "def": 1, "hp": 20}


def zero() -> StatBlock:
    return dict.fromkeys(STATS, 0)


def full(block: Mapping[str, int]) -> StatBlock:
    """`block` with every stat present (missing ones as 0)."""
    unknown = set(block) - set(STATS)
    if unknown:
        raise ValueError(f"unknown stats: {', '.join(sorted(unknown))}")
    return {s: block.get(s, 0) for s in STATS}


def add(*blocks: Mapping[str, int]) -> StatBlock:
    return total(blocks)


def total(blocks: Iterable[Mapping[str, int]]) -> StatBlock:
    result = zero()
    for block in blocks:
        for stat, value in full(block).items():
            result[stat] += value
    return result


def sub(a: Mapping[str, int], b: Mapping[str, int]) -> StatBlock:
    a, b = full(a), full(b)
    return {s: a[s] - b[s] for s in STATS}


def scale(block: Mapping[str, int], factor: int) -> StatBlock:
    return {s: v * factor for s, v in full(block).items()}

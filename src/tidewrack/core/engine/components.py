"""ECS components. Plain data only; behaviour lives in systems and handlers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Player:
    """Tag: the entity the person controls."""


@dataclass
class Name:
    text: str


@dataclass
class Position:
    node: str  # dungeon node id


@dataclass
class Explorer:
    """What an entity knows of the map (drives fog of war)."""

    visited: set[str] = field(default_factory=set)
    discovered: set[str] = field(default_factory=set)  # includes visited


@dataclass
class Scenery:
    """A non-interactive feature described when looking around a node."""

    text: str


# Every component type, by name, for saving and loading. Names are part of the save
# format: renaming one needs a save migration.
COMPONENTS: dict[str, type] = {c.__name__: c for c in (Player, Name, Position, Explorer, Scenery)}

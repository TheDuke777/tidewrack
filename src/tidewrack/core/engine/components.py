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
    location: str  # location id
    room: str  # room id within that location


@dataclass
class Explorer:
    """What an entity knows of the world (drives fog of war on both maps).

    "Discovered" means known but maybe not visited (seen as an exit or a road);
    it always includes everything visited. Rooms are keyed by location id.
    """

    locations_visited: set[str] = field(default_factory=set)
    locations_discovered: set[str] = field(default_factory=set)
    rooms_visited: dict[str, set[str]] = field(default_factory=dict)
    rooms_discovered: dict[str, set[str]] = field(default_factory=dict)


@dataclass
class Scenery:
    """A non-interactive feature described when looking around a node."""

    text: str


# Every component type, by name, for saving and loading. Names are part of the save
# format: renaming one needs a save migration.
COMPONENTS: dict[str, type] = {c.__name__: c for c in (Player, Name, Position, Explorer, Scenery)}

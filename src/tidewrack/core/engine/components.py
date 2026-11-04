"""ECS components. Plain data only; behaviour lives in systems and handlers."""

from __future__ import annotations

from dataclasses import dataclass, field

from tidewrack.core.gear.item import Item


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


@dataclass
class Stats:
    """An entity's own stats before gear (the "Base" line of its stat sheet)."""

    base: dict[str, int]


@dataclass
class Carried:
    """An item in someone's pack (equipped items are carried too)."""

    by: int  # the carrying entity


@dataclass
class Equipped:
    """A carried item that's worn or held. A two-hander's slot is main_hand but it
    also fills the off hand (see core.gear.item.slots_taken)."""

    slot: str


@dataclass
class Health:
    """Damage taken. Max HP comes from the stat sheet, so HP gear counts at once."""

    damage: int = 0


@dataclass
class Enemy:
    """Someone or something hostile: a snapshot, so saves never need content."""

    enemy_id: str
    name: str
    category: str  # "beast", "person", "spirit", …
    description: str
    stats: dict[str, int]  # before the world's Rules scale them
    drops: list[str] = field(default_factory=list)  # names of what its kind can drop
    loot: list[Item] = field(default_factory=list)  # what this one will drop


@dataclass
class Fighting:
    """On the player during a fight."""

    enemy: int
    retreat_room: str  # where a successful Flee takes you
    enemy_damage: int = 0  # damage dealt to the enemy so far
    enemy_stats: dict[str, int] = field(default_factory=dict)  # scaled by Rules at the start


@dataclass
class Respawn:
    """Where the player wakes after a defeat: the last town visited."""

    location: str


@dataclass
class Spawner:
    """A location's wandering enemies, rolled at world creation, used front first."""

    location: str
    chance: float  # per room entered (not gates, not towns)
    queue: list[Enemy] = field(default_factory=list)


@dataclass
class FoeEntry:
    """What the codex records about an enemy kind when first met."""

    enemy_id: str
    name: str
    category: str
    description: str
    stats: dict[str, int]
    drops: list[str] = field(default_factory=list)


@dataclass
class Codex:
    """What the player has discovered (Foes for now; more sections later)."""

    foes: dict[str, FoeEntry] = field(default_factory=dict)  # in order of meeting
    kills: dict[str, int] = field(default_factory=dict)


# Every component type, by name, for saving and loading. Names are part of the save
# format: renaming one needs a save migration.
COMPONENTS: dict[str, type] = {
    c.__name__: c
    for c in (
        Player,
        Name,
        Position,
        Explorer,
        Scenery,
        Stats,
        Item,
        Carried,
        Equipped,
        Health,
        Enemy,
        Fighting,
        Respawn,
        Spawner,
        Codex,
    )
}

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
class EnemyTemplate:
    """A kind of enemy a location can produce again later (step 6c): a snapshot of
    its definition, so returning enemies never need the content files."""

    enemy_id: str
    name: str
    category: str
    description: str
    stats: dict[str, int]
    rolls: dict[str, list[int]] = field(default_factory=dict)  # stat -> [min, max] bonus
    drops: list[str] = field(default_factory=list)  # names of what its kind can drop
    loot_chance: float = 0.0  # its kind's own chance (Rules.return_loot_factor scales it)
    loot: list[Item] = field(default_factory=list)  # pre-rolled pieces it may drop
    weight: float = 1.0  # how often it's picked


@dataclass
class Spawner:
    """A location's wandering enemies, rolled at world creation, used front first.
    The queue slowly refills up to `cap` from `templates` (core.combat.returns)."""

    location: str
    chance: float  # per room entered (not gates, not towns)
    queue: list[Enemy] = field(default_factory=list)
    cap: int = 0  # the queue never refills past this
    templates: list[EnemyTemplate] = field(default_factory=list)


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


@dataclass
class Bounty:
    """On an enemy a bounty quest is after. The enemy is a tougher, named one of
    its kind; `kind_name` and `kind_stats` are its ordinary kind's, for the codex."""

    quest_id: str
    kind_name: str
    kind_stats: dict[str, int]


@dataclass
class Quest:
    """A quest, on an entity of its own: a snapshot, reward included.

    States: board quests go posted → active → ready → done; found quests start
    hidden (their Clue is still lying somewhere) and go active when found.
    """

    quest_id: str
    kind: str  # "bounty", "cull", "explore" or "recover"
    title: str
    summary: str
    reward: Item
    state: str = "posted"  # posted, hidden, active, ready, done
    source: str = "board"  # "board" or "found"
    board: str | None = None  # the town whose notice board posts it
    found_in: str | None = None  # where its clue was found
    location: str | None = None  # where it sends you (cull: where they're common)
    enemy_id: str | None = None  # cull: the kind to defeat
    target: str | None = None  # bounty enemy, culled kind (plural) or recovered item
    needed: int = 1  # cull: how many
    progress: int = 0  # cull: defeated since accepting
    achieved: bool = False  # bounty beaten or item recovered (counts before accepting)


@dataclass
class QuestItem:
    """Something a Recover quest wants, lying in a room until you walk in."""

    quest_id: str
    name: str
    description: str


@dataclass
class Clue:
    """A found quest's start (a torn notice, a letter), lying in a room."""

    quest_id: str
    text: str


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
        Bounty,
        Quest,
        QuestItem,
        Clue,
    )
}

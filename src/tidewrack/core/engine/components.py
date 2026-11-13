"""ECS components. Plain data only; behaviour lives in systems and handlers."""

from __future__ import annotations

from dataclasses import dataclass, field

from tidewrack.core.gear.item import Item


@dataclass
class Material:
    """A kind of crafting material (step 7b): a snapshot, so saves never need content."""

    material_id: str
    name: str
    description: str = ""
    value: int = 1  # gold, before the world's EconomyRules
    ingredient: bool = False  # food for cooking (step 7c) rather than for crafting


@dataclass
class MaterialStack:
    """Some of one material. As a component with a Position it lies in a room and
    is gathered when you walk in; it's also how enemies, recipes and the player's
    Materials hold amounts."""

    material: Material
    count: int = 1


@dataclass
class MaterialDrop:
    """What a returning enemy kind may drop, rolled when it comes back."""

    material: Material
    chance: float
    low: int = 1
    high: int = 1


@dataclass
class GrowEntry:
    """One thing a wild place regrows, and how often it's picked."""

    material: Material
    weight: float = 1.0


@dataclass
class Grower:
    """A wild location's gathering spots grow back (core.economy.crafting): every
    EconomyRules.regrow_every turns, if fewer than `cap` spots lie about, one
    regrows in an empty room, from `materials`, with `low`–`high` of it."""

    location: str
    cap: int
    materials: list[GrowEntry] = field(default_factory=list)
    low: int = 1
    high: int = 2


@dataclass
class Recipe:
    """How to craft one piece of gear at a smithy: a snapshot, output included."""

    recipe_id: str
    name: str  # what it makes, e.g. "Keen Cutlass"
    makes: Item  # copied for each craft
    materials: list[MaterialStack] = field(default_factory=list)


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
    gold: int = 0  # what it carries (rolled at creation), yours if you win
    materials: list[MaterialStack] = field(default_factory=list)  # yours if you win


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
    gold: list[int] = field(default_factory=lambda: [0, 0])  # [min, max] it carries
    materials: list[MaterialDrop] = field(default_factory=list)


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
class MaterialEntry:
    """What the codex records about a material or ingredient you've heard of: got
    some, saw it for sale, or know a recipe or meal that needs it."""

    material: Material
    looted_from: list[str] = field(default_factory=list)  # enemy ids that dropped it for you


@dataclass
class Codex:
    """What the player has discovered: foes met, materials heard of, meals seen.
    (Known recipes live in Recipes.)"""

    foes: dict[str, FoeEntry] = field(default_factory=dict)  # in order of meeting
    kills: dict[str, int] = field(default_factory=dict)
    materials: dict[str, MaterialEntry] = field(default_factory=dict)  # in order heard of
    meals: dict[str, MealRecipe] = field(default_factory=dict)  # in order seen on a menu


@dataclass
class Bounty:
    """On an enemy a bounty quest is after. The enemy is a tougher, named one of
    its kind; `kind_name` and `kind_stats` are its ordinary kind's, for the codex."""

    quest_id: str
    kind_name: str
    kind_stats: dict[str, int]


@dataclass
class Warden:
    """On the enemy guarding a border (step 8a): it stands at the gate of the last
    place before a deeper region and bars the road `road` into it. It never
    attacks first; taking that road challenges it, and beating it opens the way."""

    region: str  # the region it guards (its id)
    road: str  # the location just over the border
    crossing: str  # what it bars, e.g. "the causeway"


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
    gold: int = 0  # paid on turning in, with the reward item
    recipe: Recipe | None = None  # also taught on turning in


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


@dataclass
class Wallet:
    """The player's gold: the one currency (CLAUDE.md §1)."""

    gold: int = 0


@dataclass
class Meal:
    """Something cooked (step 7c): a snapshot of its buff, so saves never need content."""

    meal_id: str
    name: str
    description: str
    stats: dict[str, int] = field(default_factory=dict)  # added while you're fed
    regen: int = 0  # extra HP each time you regenerate out of a fight
    turns: int = 60  # how long the buff lasts
    value: int = 1  # gold, before the world's EconomyRules


@dataclass
class MealStack:
    meal: Meal
    count: int = 1


@dataclass
class MealRecipe:
    """How a tavern cooks a meal, and whether it sells it ready-made."""

    meal: Meal
    ingredients: list[MaterialStack] = field(default_factory=list)
    sold: bool = False


@dataclass
class Meals:
    """Cooked meals the player carries, by meal id."""

    held: dict[str, MealStack] = field(default_factory=dict)


@dataclass
class WellFed:
    """On the player while a meal's buff lasts. Only one at a time."""

    meal: Meal
    turns_left: int


@dataclass
class Materials:
    """The player's satchel of crafting materials, by material id."""

    held: dict[str, MaterialStack] = field(default_factory=dict)


@dataclass
class Recipes:
    """The recipes the player knows, in the order learned."""

    known: dict[str, Recipe] = field(default_factory=dict)


@dataclass
class RecipePage:
    """A recipe lying in a room, learned when you walk in."""

    recipe: Recipe


@dataclass
class Shop:
    """A shop in a town room (with a Position). Its wares for sale are Items with
    Stocked; it restocks slowly from `wares`, pre-rolled at world creation, up to
    `cap` (core.economy.shops). An inn sells a night's rest instead. Gear you sell
    goes on a buy-back shelf (`buyback`, oldest first) that only keeps the last
    few. A market sells `materials` (never runs out); a smithy that `crafts`
    upgrades gear for the materials in `upgrades` and makes gear from recipes."""

    shop_id: str  # its content definition, e.g. "shop.smithy"
    name: str  # "Smithy"
    buys_gear: bool = False  # you can sell gear here
    inn: bool = False  # you can pay to rest here
    cap: int = 0  # restocking stops at this many wares
    wares: list[Item] = field(default_factory=list)  # what restocking picks from
    buyback: list[int] = field(default_factory=list)  # entities of gear you sold here
    materials: list[Material] = field(default_factory=list)  # for sale
    buys_materials: bool = False
    crafts: bool = False
    upgrades: dict[str, list[MaterialStack]] = field(default_factory=dict)  # gear id ->
    # materials for one upgrade level (times the level being reached)
    cooks: bool = False  # a tavern that cooks `meals` (and sells the `sold` ones)
    meals: list[MealRecipe] = field(default_factory=list)


@dataclass
class Stocked:
    """An item for sale in a shop (an entity with Shop)."""

    shop: int


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
        Wallet,
        Shop,
        Stocked,
        MaterialStack,
        Materials,
        Recipes,
        RecipePage,
        Meals,
        WellFed,
        Grower,
        Warden,
    )
}

"""The game session: world state, the turn loop, and a view model for the UI.

The UI only ever calls :meth:`Game.perform` with a command and reads
:meth:`Game.view`; it never touches the ECS world directly (CLAUDE.md §4).

Turn loop, delivered in phases so each sees the previous one's consequences:
1. the command is validated and applied; its events (and whatever subscribers
   emit in response, e.g. RoomDiscovered) are delivered;
2. if it took a turn: the counter advances and each per-turn system runs in
   order, and their events are delivered;
3. ``TurnEnded`` is delivered last.
Subscribers (exploration, narration, later achievements/codex) therefore see
every event in a deterministic order.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from functools import cached_property
from typing import Literal

from tidewrack.core.codex import items as codex_items
from tidewrack.core.codex.foes import FoesView, foes_view
from tidewrack.core.combat import fight, returns
from tidewrack.core.combat.rules import STANDARD, Rules
from tidewrack.core.data.save import (
    EconomyState,
    EntityState,
    GameState,
    RngState,
    RulesState,
    decode_component,
    encode_component,
)
from tidewrack.core.data.schemas import OverworldSchema
from tidewrack.core.economy import cooking, crafting, enchanting, shops
from tidewrack.core.economy.value_model import (
    STANDARD_ECONOMY,
    EconomyRules,
    buy_price,
    cook_fee,
    craft_fee,
    material_buy_price,
    material_sell_price,
    meal_price,
    sell_price,
    upgrade_fee,
    value,
)
from tidewrack.core.engine.components import (
    Bounty,
    Carried,
    Clue,
    Codex,
    Enemy,
    Equipped,
    Explorer,
    Fighting,
    FinalFoe,
    Grower,
    Health,
    Materials,
    MaterialStack,
    Meal,
    MealRecipe,
    Meals,
    Name,
    Player,
    Position,
    Prestige,
    Quest,
    QuestItem,
    Recipe,
    RecipePage,
    Recipes,
    Respawn,
    Scenery,
    Shop,
    Spawner,
    Stats,
    Stocked,
    TideCrown,
    Wallet,
    Warden,
)
from tidewrack.core.engine.ecs import World
from tidewrack.core.engine.events import (
    ActionRejected,
    AmbientNoticed,
    Attacked,
    CombatStarted,
    EnemyKilled,
    Event,
    EventBus,
    Fled,
    FleeFailed,
    GameStarted,
    ItemBought,
    ItemCrafted,
    ItemDropped,
    ItemEnchanted,
    ItemEquipped,
    ItemSold,
    ItemTaken,
    ItemUnequipped,
    ItemUpgraded,
    LocationDiscovered,
    LocationEntered,
    LookedAround,
    MaterialsBought,
    MaterialsGained,
    MaterialsSold,
    MealBought,
    MealCooked,
    MealEaten,
    MealWoreOff,
    Milestone,
    PlayerDefeated,
    QuestAbandoned,
    QuestAccepted,
    QuestCompleted,
    QuestFound,
    QuestItemFound,
    QuestProgress,
    QuestReady,
    RecipeLearned,
    RegionOpened,
    Respawned,
    Rested,
    RoomDiscovered,
    RoomEntered,
    TideCarried,
    TideTurned,
    TurnEnded,
    Waited,
    WayBarred,
)
from tidewrack.core.gear import effects as gear_effects
from tidewrack.core.gear import stats
from tidewrack.core.gear.compare import Comparison, compare, set_summary
from tidewrack.core.gear.item import SLOT_LABELS, SLOTS, Item, slots_taken
from tidewrack.core.gear.stat_pipeline import (
    StatSheet,
    StatSource,
    item_base,
    item_total,
    player_stats,
)
from tidewrack.core.gear.stats import DEFAULT_PLAYER_BASE, StatBlock
from tidewrack.core.progression.prestige import TidesView, boon_stats, boon_text, tides_view
from tidewrack.core.quests import quests as questing
from tidewrack.core.rng import Rng
from tidewrack.core.world.borders import grid_side, region_borders
from tidewrack.core.world.location import Location, Room
from tidewrack.core.world.overworld import Overworld

AMBIENT_CHANCE = 0.35  # per turn, when the current room has ambient lines
LOG_LIMIT = 200


# --- commands ----------------------------------------------------------------------


@dataclass(frozen=True)
class Move:
    """Take an exit to another room of this location."""

    exit_label: str


@dataclass(frozen=True)
class Travel:
    """Take the road to a neighbouring location (only from a gate room)."""

    location: str


@dataclass(frozen=True)
class Look:
    """Free action: describe the scenery here."""


@dataclass(frozen=True)
class Wait:
    """Spend a turn doing nothing."""


@dataclass(frozen=True)
class Take:
    """Pick up an item lying here."""

    item: int  # entity id, from an ItemView


@dataclass(frozen=True)
class Drop:
    """Put down a carried item (taking it off first if it's equipped)."""

    item: int


@dataclass(frozen=True)
class Equip:
    """Wear or wield a carried item, taking off whatever is in its slots."""

    item: int


@dataclass(frozen=True)
class Unequip:
    """Take off an equipped item; it stays in the pack."""

    item: int


@dataclass(frozen=True)
class Attack:
    """Strike the enemy you're fighting; it strikes back if it's still standing."""


@dataclass(frozen=True)
class Defend:
    """Brace: the enemy's next blow does less damage."""


@dataclass(frozen=True)
class Flee:
    """Try to escape back the way you came; if it fails, the enemy gets a free blow."""


@dataclass(frozen=True)
class AcceptQuest:
    """Take a notice from the board you're at (free)."""

    quest: str  # quest id, from a QuestView


@dataclass(frozen=True)
class TurnInQuest:
    """Hand in a finished quest at any town's board for its reward (free)."""

    quest: str


@dataclass(frozen=True)
class AbandonQuest:
    """Give up an active quest; its notice goes back on a board (free)."""

    quest: str


@dataclass(frozen=True)
class Buy:
    """Buy an item from a shop here (free)."""

    item: int  # entity id, from a WareView's item


@dataclass(frozen=True)
class Sell:
    """Sell a carried, unequipped item to a shop here that buys gear (free)."""

    item: int


@dataclass(frozen=True)
class Rest:
    """Pay for a night at an inn here: back to full health."""


@dataclass(frozen=True)
class BuyMaterials:
    """Buy materials from a market here (free)."""

    material: str  # material id, from a MaterialView
    count: int = 1


@dataclass(frozen=True)
class SellMaterials:
    """Sell materials from your satchel to a market here (free)."""

    material: str
    count: int = 1


@dataclass(frozen=True)
class Craft:
    """Make gear from a recipe you know, at a smithy here (free)."""

    recipe: str  # recipe id, from a RecipeView


@dataclass(frozen=True)
class Enchant:
    """Put an enchantment (tier `tier`) on a carried item, at an Enchanter here (free)."""

    item: int
    enchant_id: str
    tier: int


@dataclass(frozen=True)
class Upgrade:
    """Raise a carried item one upgrade level, at a smithy here (free)."""

    item: int


@dataclass(frozen=True)
class Cook:
    """Cook a meal from ingredients at a tavern here (free)."""

    meal: str  # meal id, from a MealView


@dataclass(frozen=True)
class BuyMeal:
    """Buy a ready-made meal at a tavern here (free)."""

    meal: str


@dataclass(frozen=True)
class Eat:
    """Eat a meal you carry: its buff replaces any meal's you have (free)."""

    meal: str


Command = (
    Move
    | Travel
    | Look
    | Wait
    | Take
    | Drop
    | Equip
    | Unequip
    | Attack
    | Defend
    | Flee
    | AcceptQuest
    | TurnInQuest
    | AbandonQuest
    | Buy
    | Sell
    | Rest
    | BuyMaterials
    | SellMaterials
    | Craft
    | Upgrade
    | Enchant
    | Cook
    | BuyMeal
    | Eat
)
COMBAT_COMMANDS = (Attack, Defend, Flee)
ALLOWED_IN_COMBAT = (Look, *COMBAT_COMMANDS)


# --- results and view model --------------------------------------------------------


@dataclass(frozen=True)
class TurnResult:
    took_turn: bool
    events: tuple[Event, ...]


@dataclass(frozen=True)
class ExitView:
    label: str
    destination: str | None  # room name once visited; None while unexplored


@dataclass(frozen=True)
class RoadView:
    location: str  # id, for Travel(location)
    name: str
    kind: str
    visited: bool
    guard: str | None = None  # the warden barring it (taking the road challenges it)
    region: str | None = None  # the region it leads into, when that's another one


@dataclass(frozen=True)
class MapNode:
    id: str
    x: float
    y: float
    state: Literal["current", "visited", "seen"]  # "seen": known but not yet visited
    name: str | None  # None while the player doesn't know it
    command: Command | None  # set when one step away: perform it to go there
    gate: bool = False  # a room roads leave from (area maps)
    kind: str | None = None  # a location's kind, e.g. "Town" (world maps)
    items: bool = False  # a visited room with items left lying in it (area maps)
    quest: bool = False  # where an active quest sends you (a seen bounty, a target place)
    charted: bool = False  # every room visited (world maps)
    shop: bool = False  # a visited room with a shop or inn in it (area maps)
    blocked: str | None = None  # why you can't go there from here yet (tap to be told)
    guarded: bool = False  # a warden bars the road there (world maps)
    crown: bool = False  # the final foe or its crown is there, and you've been (8c)


@dataclass(frozen=True)
class RegionMark:
    """A region's name on the world map, centred on the places known in it."""

    name: str
    x: float
    y: float


@dataclass(frozen=True)
class MapView:
    """A fog-of-war map: only nodes the player knows, only paths they've seen."""

    nodes: tuple[MapNode, ...]
    edges: tuple[tuple[str, str], ...]
    size: int  # nodes in the whole map, known or not (for scaling)
    regions: tuple[RegionMark, ...] = ()  # world maps with more than one region
    # Dotted lines where known regions meet (world maps): (x1, y1, x2, y2), 0..1.
    borders: tuple[tuple[float, float, float, float], ...] = ()
    # The part of 0..1 to fit to the map: a place's maps use the box around all its
    # rooms (known or not, so the layout never shifts as you explore; v0.11.2).
    bounds: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)  # x0, y0, x1, y1


@dataclass(frozen=True)
class ItemView:
    id: int  # entity id, for Take/Drop/Equip/Unequip
    name: str  # with affixes and upgrade level
    slot: str  # "Main hand", "Both hands", …
    equipped: bool
    base: StatBlock  # base + roll
    total: StatBlock  # with upgrades and affixes
    upgrade: str | None  # "+1/3" when upgradable
    affixes: tuple[str, ...]
    gear_set: str | None
    gear_set_id: str | None
    gear_set_color: str | None  # one of core.gear.item.SET_COLORS, if the set has one
    effects: tuple[str, ...]  # what the item's own effects do, as players read it
    comparison: Comparison  # against what the player has on now
    set_bonuses: tuple[str, ...] = ()  # every bonus its set has (compare.set_summary)
    value: int = 0  # core.economy.value_model.value
    sell_price: int = 0  # what a shop that buys gear pays for it


@dataclass(frozen=True)
class SlotView:
    slot: str  # slot id
    label: str
    item: ItemView | None
    filled_by: str | None  # when a two-hander in another slot fills this one


@dataclass(frozen=True)
class InventoryView:
    slots: tuple[SlotView, ...]  # every slot, in SLOTS order
    pack: tuple[ItemView, ...]  # carried but not equipped
    sheet: StatSheet
    gold: int = 0
    buyer: str | None = None  # the shop here that buys gear (sell from the pack)
    materials: tuple[MaterialView, ...] = ()  # your satchel, by name
    recipes: tuple[str, ...] = ()  # names of the recipes you know
    meals: tuple[MealView, ...] = ()  # cooked meals you carry
    fed: FedView | None = None


@dataclass(frozen=True)
class MaterialView:
    id: str  # material id, for BuyMaterials / SellMaterials
    name: str
    description: str
    count: int  # how many you have
    sell_price: int  # what a market pays for one
    ingredient: bool = False  # for cooking rather than crafting


@dataclass(frozen=True)
class CostView:
    """One material a craft or upgrade needs."""

    name: str
    need: int
    have: int

    @property
    def enough(self) -> bool:
        return self.have >= self.need


@dataclass(frozen=True)
class RecipeView:
    id: str  # for Craft
    name: str
    item: ItemView  # what it makes, compared with what you have on
    materials: tuple[CostView, ...]
    fee: int
    can_craft: bool  # enough materials and gold


@dataclass(frozen=True)
class UpgradeView:
    item: ItemView  # as it is; its id is what Upgrade takes
    upgraded: ItemView  # one level up
    materials: tuple[CostView, ...]
    fee: int
    can_upgrade: bool


@dataclass(frozen=True)
class MealView:
    id: str  # meal id, for Cook / BuyMeal / Eat
    name: str
    description: str
    buff: str  # "ATK +2, faster healing (+2 HP)"
    turns: int
    count: int  # how many you carry


@dataclass(frozen=True)
class MenuView:
    """A meal at a tavern: what cooking it takes, and its price if it's sold."""

    meal: MealView
    ingredients: tuple[CostView, ...]
    fee: int
    can_cook: bool
    price: int | None  # ready-made, if the tavern sells it
    affordable: bool = False


@dataclass(frozen=True)
class FedView:
    """The meal whose buff you have now."""

    name: str
    buff: str
    turns_left: int


@dataclass(frozen=True)
class MaterialWareView:
    material: MaterialView
    price: int  # for one
    affordable: bool  # at least one


@dataclass(frozen=True)
class WareView:
    item: ItemView  # its id is what Buy takes
    price: int
    affordable: bool
    sold_by_you: bool = False  # on the buy-back shelf


@dataclass(frozen=True)
class EnchantOptionView:
    """One enchantment an Enchanter could put on one of your pieces (v0.13.0)."""

    enchant_id: str
    tier: int
    name: str  # "Baneful II"
    does: str  # its effects (and any stats), as players read them
    description: str
    costs: tuple[CostView, ...]
    fee: int
    replaces: str | None  # the affix it would take the place of
    can_afford: bool


@dataclass(frozen=True)
class EnchantableView:
    item: ItemView
    options: tuple[EnchantOptionView, ...]  # best tier first, by enchantment


@dataclass(frozen=True)
class ShopView:
    name: str  # "Smithy"
    wares: tuple[WareView, ...]
    buys_gear: bool
    inn_price: int | None  # set at an inn
    materials: tuple[MaterialWareView, ...] = ()  # a market's (never runs out)
    buys_materials: bool = False
    crafts: bool = False
    recipes: tuple[RecipeView, ...] = ()  # every recipe you know, at a smithy
    upgrades: tuple[UpgradeView, ...] = ()  # your gear it can upgrade
    cooks: bool = False
    menu: tuple[MenuView, ...] = ()  # a tavern's meals
    enchants: bool = False  # an Enchanter (v0.13.0)
    enchantable: tuple[EnchantableView, ...] = ()  # your gear it can enchant, worn first


@dataclass(frozen=True)
class CombatView:
    enemy: int
    name: str
    category: str
    description: str
    hp: int
    max_hp: int
    stats: StatBlock  # the enemy's, as this world's rules scale them


@dataclass(frozen=True)
class QuestView:
    id: str  # for AcceptQuest / TurnInQuest
    kind: str  # "Bounty", "Cull", "Explore", "Recover"
    title: str
    summary: str
    source: str  # "Posted at Saltmere" / "Found in the Kelp Caves"
    progress: str  # "2/4 Shore Crabs defeated", …
    state: str  # posted, active, ready, done
    reward: ItemView
    gold: int = 0  # paid with the reward
    recipe: str | None = None  # also taught: what the recipe makes


@dataclass(frozen=True)
class QuestLogView:
    ready: tuple[QuestView, ...]
    active: tuple[QuestView, ...]
    done: tuple[QuestView, ...]


@dataclass(frozen=True)
class GameView:
    location: str  # the location's name
    kind: str  # "Town", "Sea Caves", …
    room: str
    description: str
    exits: tuple[ExitView, ...]
    at_gate: bool  # roads can be taken from here
    gates: tuple[str, ...]  # names of this location's gate rooms
    roads: tuple[RoadView, ...]  # this location's neighbours (usable when at_gate)
    log: tuple[str, ...]
    turn: int
    seed: int
    rooms_visited: int
    total_rooms: int
    locations_visited: int
    total_locations: int
    map: MapView | None  # rooms of this location; None if it has no map positions
    world_map: MapView | None  # locations; None if the world has no map positions
    items_here: tuple[ItemView, ...]  # lying in this room
    stats: StatBlock  # the player's total, gear included
    hp: int
    max_hp: int
    combat: CombatView | None  # set while fighting
    in_town: bool
    board: tuple[QuestView, ...] | None = None  # at a notice board: posted + ready quests
    gold: int = 0
    shops: tuple[ShopView, ...] = ()  # shops in this room
    fed: FedView | None = None
    log_total: int = 0  # lines ever written while open (log keeps the last LOG_LIMIT)
    region: str | None = None  # the region you're in, e.g. "The Sallow Fens"
    tide: int = 0  # prestige rank: tides lived through (8c)
    can_ascend: bool = False  # the tide has turned and you're not fighting


IMPORTANT = "⚑ "  # starts a log line the player mustn't miss (8c; the UI highlights it)


# --- the game ----------------------------------------------------------------------


class Game:
    # Set only while a view is being built (_building_views); never saved.
    _compare_with: tuple[list[Item], dict[str, int]] | None = None

    def __init__(
        self,
        seed: int,
        world: Overworld,
        player_base: Mapping[str, int] = DEFAULT_PLAYER_BASE,
        kit: Iterable[Item] = (),
        finds: Iterable[tuple[str, str, Item]] = (),
        enemies: Iterable[tuple[str, str, Enemy]] = (),
        spawners: Iterable[Spawner] = (),
        rules: Rules = STANDARD,
        quests: Iterable[Quest] = (),
        bounties: Iterable[tuple[str, str, Enemy, Bounty]] = (),
        quest_things: Iterable[tuple[str, str, QuestItem | Clue]] = (),
        gold: int = 0,
        shops: Iterable[tuple[str, str, Shop, Iterable[Item]]] = (),
        economy: EconomyRules = STANDARD_ECONOMY,
        gathering: Iterable[tuple[str, str, MaterialStack]] = (),
        recipes: Iterable[Recipe] = (),
        recipe_pages: Iterable[tuple[str, str, RecipePage]] = (),
        growers: Iterable[Grower] = (),
        wardens: Iterable[tuple[str, str, Enemy, Warden]] = (),
        finals: Iterable[tuple[str, str, Enemy, FinalFoe]] = (),
    ) -> None:
        """Start a new run in `world`, wearing `kit`, with `finds` and `enemies`
        (location id, room id, thing) where they were placed at world creation,
        each location's wandering enemies in `spawners`, under `rules`; plus the
        world's `quests`, their `bounties` and their items and clues; `gold` to
        start with; its `shops` (location, room, shop, stock) under `economy`;
        materials to `gathering`, the `recipes` known from the start, and found
        `recipe_pages` (location, room, thing), and the `wardens` at the gates
        of the roads into deeper regions (location, room, enemy, warden), and the
        world's final foe in `finals` (location, room, enemy, final; 8c)."""
        self._setup(seed, world)
        self.rules = rules
        self.economy = economy
        start = world.location(world.start)
        self.player = self.world.create(
            Player(),
            Name("You"),
            Position(start.id, start.start),
            Explorer(),
            Stats(stats.full(player_base)),
            Health(),
            Codex(),
            Respawn(start.id),
            Wallet(gold),
            Materials(),
            Recipes({r.recipe_id: r for r in recipes}),
            Meals(),
            Prestige(),
        )
        for location in world.locations.values():
            for room in location.rooms.values():
                for text in room.features:
                    self.world.create(Scenery(text), Position(location.id, room.id))
        for item in kit:
            if any(set(slots_taken(item)) & set(slots_taken(i)) for i in self._equipped()):
                raise ValueError(f"kit has two items for the {item.slot} slot")
            self.world.create(item, Carried(self.player), Equipped(item.slot))
        for location_id, room_id, item in finds:
            if room_id not in world.location(location_id).rooms:
                raise ValueError(f"find placed in unknown room {location_id}/{room_id}")
            self.world.create(item, Position(location_id, room_id))
        for location_id, room_id, enemy in enemies:
            location = world.location(location_id)
            if room_id not in location.rooms or room_id in location.gates:
                raise ValueError(f"enemy placed in a gate or unknown room {location_id}/{room_id}")
            self.world.create(enemy, Position(location_id, room_id))
        for spawner in spawners:
            world.location(spawner.location)  # must exist
            self.world.create(spawner)
        for quest in quests:
            self.world.create(quest)
        for location_id, room_id, enemy, bounty in bounties:
            location = world.location(location_id)
            if room_id not in location.rooms or room_id in location.gates:
                raise ValueError(f"bounty placed in a gate or unknown room {location_id}/{room_id}")
            self.world.create(enemy, bounty, Position(location_id, room_id))
        for location_id, room_id, thing in quest_things:
            if room_id not in world.location(location_id).rooms:
                raise ValueError(f"quest item placed in unknown room {location_id}/{room_id}")
            self.world.create(thing, Position(location_id, room_id))
        for location_id, room_id, shop, stock in shops:
            if room_id not in world.location(location_id).rooms:
                raise ValueError(f"shop placed in unknown room {location_id}/{room_id}")
            shop_entity = self.world.create(shop, Position(location_id, room_id))
            for item in stock:
                self.world.create(item, Stocked(shop_entity))
        for grower in growers:
            world.location(grower.location)  # must exist
            self.world.create(grower)
        for location_id, room_id, enemy, warden in wardens:
            location = world.location(location_id)
            if room_id not in location.gates or warden.road not in location.roads:
                raise ValueError(f"warden not at a gate on its road: {location_id}/{room_id}")
            self.world.create(enemy, warden, Position(location_id, room_id))
        for location_id, room_id, enemy, final, *_ in finals:
            location = world.location(location_id)
            if room_id not in location.rooms or room_id in location.gates:
                raise ValueError(f"final foe in a gate or unknown room {location_id}/{room_id}")
            if any(
                (p.location, p.room) == (location_id, room_id)
                for _, (_, p) in self.world.query(Enemy, Position)
            ):
                raise ValueError(f"final foe shares a room: {location_id}/{room_id}")
            self.world.create(enemy, final, Position(location_id, room_id))
        for location_id, room_id, thing in [*gathering, *recipe_pages]:
            location = world.location(location_id)
            if room_id not in location.rooms or room_id in location.gates:
                raise ValueError(
                    f"material or recipe in a gate or unknown room {location_id}/{room_id}"
                )
            self.world.create(thing, Position(location_id, room_id))

        self.bus.emit(GameStarted(seed))
        self.bus.emit(LocationEntered(self.player, start.id, None, first_visit=True))
        self.bus.emit(RoomEntered(self.player, start.id, start.start, None, first_visit=True))
        self.bus.flush()

    def _setup(
        self, seed: int, overworld: Overworld, snapshot: OverworldSchema | None = None
    ) -> None:
        """Runtime wiring shared by new and loaded games."""
        self.seed = seed
        self.overworld = overworld
        # The world never changes during play, so it's snapshotted for saving once.
        self._snapshot = snapshot or OverworldSchema.from_overworld(overworld)
        self.rng = Rng(seed)
        self.ambient_rng = self.rng.derive("ambient")
        self.combat_rng = self.rng.derive("combat")
        self.encounter_rng = self.rng.derive("encounters")
        self.respawn_rng = self.rng.derive("respawns")
        self.shop_rng = self.rng.derive("shops")
        self.gather_rng = self.rng.derive("gathering")
        self.rules = STANDARD
        self.economy = STANDARD_ECONOMY
        self.world = World()
        self.bus = EventBus()
        self.turn = 0
        self.log: list[str] = []
        # Lines written since the game was made or loaded (not saved): the log is
        # capped, so its length stops growing; this tells the UI which are new.
        self.log_total = 0

        # Per-turn systems, run in this order after every turn-taking command.
        self.systems: list[Callable[[Game], None]] = [
            ambience_system,
            fight.regen_system,
            returns.returns_system,
            shops.restock_system,
            cooking.meal_system,
            crafting.regrow_system,
        ]

        # Subscription order is delivery order: exploration updates state before
        # the narrator describes it, and before encounters start (whose events,
        # like any emitted by a handler, are delivered after this one).
        self.bus.subscribe(LocationEntered, self._explore_location)
        self.bus.subscribe(LocationEntered, lambda e: fight.note_town(self, e))
        self.bus.subscribe(RoomEntered, self._explore_room)
        self.bus.subscribe(RoomEntered, lambda e: crafting.on_room_entered(self, e))
        self.bus.subscribe(RoomEntered, lambda e: questing.on_room_entered(self, e))
        self.bus.subscribe(RoomEntered, lambda e: fight.encounter(self, e))
        self.bus.subscribe(EnemyKilled, lambda e: questing.on_enemy_killed(self, e))
        self.bus.subscribe(GameStarted, lambda e: codex_items.note_recipes(self))
        self.bus.subscribe(RoomEntered, lambda e: codex_items.on_room_entered(self, e))
        self.bus.subscribe(MaterialsGained, lambda e: codex_items.on_materials_gained(self, e))
        self.bus.subscribe(RecipeLearned, lambda e: codex_items.on_recipe_learned(self, e))
        self.bus.subscribe(Event, self._narrate)

    # --- saving ----------------------------------------------------------------------

    def to_state(self) -> GameState:
        next_id, entities = self.world.snapshot()
        return GameState(
            seed=self.seed,
            turn=self.turn,
            log=list(self.log),
            world=self._snapshot,
            rng=RngState(**self.rng.get_state()),
            ambient_rng=RngState(**self.ambient_rng.get_state()),
            combat_rng=RngState(**self.combat_rng.get_state()),
            encounter_rng=RngState(**self.encounter_rng.get_state()),
            respawn_rng=RngState(**self.respawn_rng.get_state()),
            shop_rng=RngState(**self.shop_rng.get_state()),
            gather_rng=RngState(**self.gather_rng.get_state()),
            rules=RulesState(**self.rules.__dict__),
            economy=EconomyState(**self.economy.__dict__),
            next_entity_id=next_id,
            entities=[
                EntityState(id=e, components=dict(encode_component(c) for c in components))
                for e, components in entities.items()
            ],
        )

    @classmethod
    def from_state(cls, state: GameState) -> Game:
        """Resume a saved game exactly where it stopped (RNG streams included)."""
        game = cls.__new__(cls)
        game._setup(state.seed, state.world.to_overworld(), state.world)
        game.rng = Rng.from_state(state.rng.model_dump())
        game.ambient_rng = Rng.from_state(state.ambient_rng.model_dump())
        if state.combat_rng is not None:
            game.combat_rng = Rng.from_state(state.combat_rng.model_dump())
        if state.encounter_rng is not None:
            game.encounter_rng = Rng.from_state(state.encounter_rng.model_dump())
        if state.respawn_rng is not None:
            game.respawn_rng = Rng.from_state(state.respawn_rng.model_dump())
        if state.shop_rng is not None:
            game.shop_rng = Rng.from_state(state.shop_rng.model_dump())
        if state.gather_rng is not None:
            game.gather_rng = Rng.from_state(state.gather_rng.model_dump())
        game.rules = Rules(**state.rules.model_dump())
        game.economy = EconomyRules(**state.economy.model_dump())
        game.turn = state.turn
        game.log = list(state.log)
        game.log_total = len(game.log)
        game.world = World.restore(
            state.next_entity_id,
            {
                e.id: tuple(decode_component(n, f) for n, f in e.components.items())
                for e in state.entities
            },
        )
        game.player = game.world.single(Player)[0]
        if not game.world.has(
            game.player, Stats, Health, Codex, Respawn, Wallet, Materials, Recipes, Meals
        ):
            raise ValueError(
                "the player is missing Stats, Health, Codex, Respawn, Wallet, Materials, "
                "Recipes or Meals"
            )
        for _, (shop,) in game.world.query(Shop):
            for entity in shop.buyback:
                if not game.world.has(entity, Item, Stocked):
                    raise ValueError(f"shop buy-back lists {entity}, which isn't for sale")
        fighting = game.world.try_get(game.player, Fighting)
        if fighting is not None and not game.world.has(fighting.enemy, Enemy, Position):
            raise ValueError("the player is fighting an enemy that isn't there")
        for entity, (_, carried) in game.world.query(Item, Carried):
            if not game.world.exists(carried.by) or game.world.has(entity, Position):
                raise ValueError(f"item {entity} is carried by a missing entity or also placed")
        for entity, (_, stocked) in game.world.query(Item, Stocked):
            if not game.world.has(stocked.shop, Shop) or game.world.has(entity, Carried):
                raise ValueError(f"item {entity} is stocked by a missing shop or also carried")
        for entity, _ in game.world.query(Equipped):
            if not game.world.has(entity, Item, Carried):
                raise ValueError(f"entity {entity} is equipped but isn't a carried item")
        for entity, (position,) in game.world.query(Position):
            location = game.overworld.locations.get(position.location)
            if location is None or position.room not in location.rooms:
                raise ValueError(
                    f"entity {entity} is at unknown room {position.location}/{position.room}"
                )
        return game

    # --- turn loop -------------------------------------------------------------------

    def perform(self, command: Command) -> TurnResult:
        position = self.world.get(self.player, Position)
        location = self.overworld.location(position.location)
        took_turn = False
        fighting = self.world.try_get(self.player, Fighting)

        if fighting is not None and not isinstance(command, ALLOWED_IN_COMBAT):
            enemy = self.world.get(fighting.enemy, Enemy)
            self.bus.emit(ActionRejected(f"You're fighting the {enemy.name}!"))
            return TurnResult(False, tuple(self.bus.flush()))
        if fighting is None and isinstance(command, COMBAT_COMMANDS):
            self.bus.emit(ActionRejected("There's nothing here to fight."))
            return TurnResult(False, tuple(self.bus.flush()))

        match command:
            case Move(exit_label=label):
                exit_ = location.exit(position.room, label)
                if exit_ is None:
                    self.bus.emit(ActionRejected("You can't go that way."))
                else:
                    origin, position.room = position.room, exit_.to
                    self.bus.emit(
                        RoomEntered(
                            self.player,
                            location.id,
                            exit_.to,
                            origin,
                            first_visit=exit_.to
                            not in self._explorer().rooms_visited.get(location.id, set()),
                        )
                    )
                    took_turn = True
            case Travel(location=destination_id):
                if position.room not in location.gates:
                    self.bus.emit(ActionRejected(_leave_from(location)))
                elif destination_id not in location.roads:
                    self.bus.emit(ActionRejected("No road leads there from here."))
                elif (
                    guard := fight.warden_on(self, location.id, position.room, destination_id)
                ) is not None:
                    fight.challenge(self, guard)
                    took_turn = True
                else:
                    destination = self.overworld.location(destination_id)
                    position.location, position.room = destination.id, destination.start
                    explorer = self._explorer()
                    self.bus.emit(
                        LocationEntered(
                            self.player,
                            destination.id,
                            location.id,
                            first_visit=destination.id not in explorer.locations_visited,
                        )
                    )
                    self.bus.emit(
                        RoomEntered(
                            self.player,
                            destination.id,
                            destination.start,
                            None,
                            first_visit=destination.start
                            not in explorer.rooms_visited.get(destination.id, set()),
                        )
                    )
                    took_turn = True
            case Look():
                self.bus.emit(LookedAround(location.id, position.room))
            case Wait():
                self.bus.emit(Waited(location.id, position.room))
                took_turn = True
            case Rest():
                took_turn = shops.rest(self)
            case Buy(item=entity):
                shops.buy(self, entity)
            case Sell(item=entity):
                shops.sell(self, entity)
            case BuyMaterials(material=material_id, count=amount):
                crafting.buy_materials(self, material_id, amount)
            case SellMaterials(material=material_id, count=amount):
                crafting.sell_materials(self, material_id, amount)
            case Craft(recipe=recipe_id):
                crafting.craft(self, recipe_id)
            case Upgrade(item=entity):
                crafting.upgrade(self, entity)
            case Enchant(item=entity, enchant_id=enchant_id, tier=tier):
                enchanting.enchant(self, entity, enchant_id, tier)
            case Cook(meal=meal_id):
                cooking.cook(self, meal_id)
            case BuyMeal(meal=meal_id):
                cooking.buy_meal(self, meal_id)
            case Eat(meal=meal_id):
                cooking.eat(self, meal_id)
            case Attack():
                fight.attack(self)
                took_turn = True
            case Defend():
                fight.defend(self)
                took_turn = True
            case Flee():
                fight.flee(self)
                took_turn = True
            case Take(item=entity):
                took_turn = self._take(entity, position)
            case Drop(item=entity):
                took_turn = self._drop(entity, position)
            case Equip(item=entity):
                took_turn = self._equip(entity)
            case Unequip(item=entity):
                took_turn = self._unequip(entity)
            case AcceptQuest(quest=quest_id):
                questing.accept(self, quest_id)
            case TurnInQuest(quest=quest_id):
                questing.turn_in(self, quest_id)
            case AbandonQuest(quest=quest_id):
                questing.abandon(self, quest_id)
            case _:
                raise TypeError(f"unknown command: {command!r}")

        events = self.bus.flush()
        if took_turn:
            self.turn += 1
            for system in self.systems:
                system(self)
            events += self.bus.flush()
            self.bus.emit(TurnEnded(self.turn))
            events += self.bus.flush()
        return TurnResult(took_turn, tuple(events))

    # --- gear --------------------------------------------------------------------

    def _carried(self, entity: int) -> Item | None:
        """The item `entity` if the player carries it."""
        item = self.world.try_get(entity, Item)
        carried = self.world.try_get(entity, Carried)
        return item if item and carried and carried.by == self.player else None

    def _equipped(self) -> list[Item]:
        return [item for _, item in self._equipped_entities()]

    def _equipped_entities(self) -> list[tuple[int, Item]]:
        return [
            (e, item)
            for e, (item, carried, _) in self.world.query(Item, Carried, Equipped)
            if carried.by == self.player
        ]

    def _take(self, entity: int, here: Position) -> bool:
        item = self.world.try_get(entity, Item)
        spot = self.world.try_get(entity, Position)
        if (
            item is None
            or spot is None
            or (spot.location, spot.room)
            != (
                here.location,
                here.room,
            )
        ):
            self.bus.emit(ActionRejected("That isn't here."))
            return False
        self.world.remove(entity, Position)
        self.world.add(entity, Carried(self.player))
        self.bus.emit(ItemTaken(self.player, entity, item.gear_id, item.display_name))
        return True

    def _drop(self, entity: int, here: Position) -> bool:
        item = self._carried(entity)
        if item is None:
            self.bus.emit(ActionRejected("You aren't carrying that."))
            return False
        if self.world.has(entity, Equipped):
            self.world.remove(entity, Equipped)
            self.bus.emit(ItemUnequipped(self.player, entity, item.gear_id, item.display_name))
        self.world.remove(entity, Carried)
        self.world.add(entity, Position(here.location, here.room))
        self.clamp_health()
        self.bus.emit(ItemDropped(self.player, entity, item.gear_id, item.display_name))
        return True

    def _equip(self, entity: int) -> bool:
        item = self._carried(entity)
        if item is None:
            self.bus.emit(ActionRejected("You aren't carrying that."))
            return False
        if self.world.has(entity, Equipped):
            self.bus.emit(ActionRejected(f"You already have the {item.display_name} on."))
            return False
        taken = set(slots_taken(item))
        replaced = [(e, i) for e, i in self._equipped_entities() if taken & set(slots_taken(i))]
        for other, _ in replaced:
            self.world.remove(other, Equipped)
        self.world.add(entity, Equipped(item.slot))
        self.clamp_health()
        self.bus.emit(
            ItemEquipped(
                self.player,
                entity,
                item.gear_id,
                item.display_name,
                tuple(i.display_name for _, i in replaced),
            )
        )
        return True

    def _unequip(self, entity: int) -> bool:
        item = self._carried(entity)
        if item is None or not self.world.has(entity, Equipped):
            self.bus.emit(ActionRejected("You don't have that on."))
            return False
        self.world.remove(entity, Equipped)
        self.clamp_health()
        self.bus.emit(ItemUnequipped(self.player, entity, item.gear_id, item.display_name))
        return True

    def _items_at(self, location_id: str, room_id: str) -> list[tuple[int, Item]]:
        return [
            (e, item)
            for e, (item, p) in self.world.query(Item, Position)
            if (p.location, p.room) == (location_id, room_id)
        ]

    @contextmanager
    def _building_views(self) -> Iterator[None]:
        """While building one view (nothing can change meanwhile), item views share
        one look-up of your equipped gear and comparison base instead of each
        scanning the world: big packs made every screen update slow (v0.11.0)."""
        outer = self._compare_with is not None
        if not outer:
            base = stats.add(self.world.get(self.player, Stats).base, cooking.buff(self))
            self._compare_with = (self._equipped(), base)
        try:
            yield
        finally:
            if not outer:
                self._compare_with = None

    def _item_view(self, entity: int, item: Item) -> ItemView:
        # Compared with what you have now, meal included, so "You" stays true.
        if self._compare_with is not None:
            equipped, base = self._compare_with
        else:
            equipped = self._equipped()
            base = stats.add(self.world.get(self.player, Stats).base, cooking.buff(self))
        return ItemView(
            id=entity,
            name=item.display_name,
            slot="Both hands" if item.two_handed else SLOT_LABELS[item.slot],
            equipped=entity >= 0 and self.world.has(entity, Equipped),
            base=item_base(item),
            total=item_total(item),
            upgrade=f"+{item.upgrade}/{item.max_upgrade}" if item.max_upgrade else None,
            affixes=tuple(a.name for a in item.affixes),
            gear_set=item.gear_set.name if item.gear_set else None,
            gear_set_id=item.gear_set.id if item.gear_set else None,
            gear_set_color=item.gear_set.color if item.gear_set else None,
            effects=tuple(
                gear_effects.describe(e)
                for e in [*item.effects, *(e for a in item.affixes for e in a.effects)]
            ),
            set_bonuses=set_summary(item.gear_set) if item.gear_set else (),
            comparison=compare(item, equipped, base),
            value=value(item),
            sell_price=sell_price(item, self.economy),
        )

    def clamp_health(self) -> None:
        """Taking off HP gear can lower max HP, but never knocks you out."""
        health = self.world.get(self.player, Health)
        health.damage = min(health.damage, self.max_hp() - 1)

    def max_hp(self) -> int:
        return max(1, self.sheet().total["hp"])

    def hp(self) -> int:
        return max(0, self.max_hp() - self.world.get(self.player, Health).damage)

    def foes(self) -> FoesView:
        return foes_view(self.world.get(self.player, Codex), self._found_in(), self.rules)

    def tides(self) -> TidesView:
        """The Codex's tides section (8c): your tide, what it did to this world,
        and the boons you've kept."""
        return tides_view(self._prestige(), self.rules, self.economy)

    def codex(self) -> codex_items.CodexView:
        """The codex's other sections: materials, ingredients, recipes, meals."""
        return codex_items.view(self)

    def _found_in(self) -> dict[str, str]:
        """Where each enemy kind lives, for the codex: the kinds of place it's in
        (placed, wandering or able to return), grouped by region; a warden says
        which road it guards. Regions you haven't found yet stay unnamed."""
        places: dict[str, list[str]] = {}  # enemy -> location ids, in order found
        guards: dict[str, str] = {}
        for entity, (enemy, position) in self.world.query(Enemy, Position):
            warden = self.world.try_get(entity, Warden)
            if warden is not None:
                region = self.overworld.regions.get(warden.region)
                guards[enemy.enemy_id] = f"Guards {warden.crossing} into " + (
                    region.name if region else "the next region"
                )
            else:
                places.setdefault(enemy.enemy_id, []).append(position.location)
        for _, (spawner,) in self.world.query(Spawner):
            for enemy_id in [e.enemy_id for e in spawner.queue] + [
                t.enemy_id for t in spawner.templates
            ]:
                places.setdefault(enemy_id, []).append(spawner.location)
        found = dict(guards)
        for enemy_id, location_ids in places.items():
            found.setdefault(enemy_id, codex_items.where(self, location_ids) or "")
        return found

    def _combat_view(self) -> CombatView | None:
        fighting = self.world.try_get(self.player, Fighting)
        if fighting is None:
            return None
        enemy = self.world.get(fighting.enemy, Enemy)
        max_hp = fighting.enemy_stats["hp"]
        return CombatView(
            enemy=fighting.enemy,
            name=enemy.name,
            category=enemy.category,
            description=enemy.description,
            hp=max(0, max_hp - fighting.enemy_damage),
            max_hp=max_hp,
            stats=stats.full(fighting.enemy_stats),
        )

    # --- quests --------------------------------------------------------------------

    def _quest_view(self, quest: Quest) -> QuestView:
        def name(location_id: str | None) -> str:
            return self.overworld.location(location_id).name if location_id else "the wild"

        if quest.source == "found":
            source = f"Found in {name(quest.found_in)}"
        else:
            source = f"Posted at {name(quest.board)}"
        return QuestView(
            id=quest.quest_id,
            kind=questing.KIND_LABELS[quest.kind],
            title=quest.title,
            summary=quest.summary,
            source=source,
            progress=questing.progress_text(self, quest),
            state=quest.state,
            reward=self._item_view(-1, quest.reward),  # not in the world until earned
            gold=quest.gold,
            recipe=quest.recipe.name if quest.recipe else None,
        )

    def quests(self) -> QuestLogView:
        with self._building_views():
            return self._quests()

    def _quests(self) -> QuestLogView:
        """The quest log: everything accepted or found, by state."""
        known = questing.all_quests(self)

        def views(state: str) -> tuple[QuestView, ...]:
            return tuple(self._quest_view(q) for q in known if q.state == state)

        return QuestLogView(ready=views("ready"), active=views("active"), done=views("done"))

    def _board(self) -> tuple[QuestView, ...] | None:
        board = questing.board_here(self)
        if board is None:
            return None
        return tuple(
            self._quest_view(q)
            for q in questing.all_quests(self)
            if q.state == "ready" or (q.state == "posted" and q.board == board)
        )

    def _quest_places(self) -> tuple[set[str], set[tuple[str, str]]]:
        """Where active quests send you: target locations, and rooms where a
        bounty you're after has been seen (a visited room it's still in)."""
        explorer = self._explorer()
        active = [q for q in questing.all_quests(self) if q.state == "active"]
        places = {q.location for q in active if q.location and q.kind != "cull"}
        wanted = {q.quest_id for q in active if q.kind == "bounty"}
        rooms = {
            (p.location, p.room)
            for _, (bounty, p) in self.world.query(Bounty, Position)
            if bounty.quest_id in wanted and p.room in explorer.rooms_visited.get(p.location, ())
        }
        return places, rooms  # type: ignore[return-value]

    def _prestige(self) -> Prestige:
        return self.world.try_get(self.player, Prestige) or Prestige()

    def can_ascend(self) -> bool:
        """Whether the player may ride the tide into a new world now (8c): its
        final foe is beaten and you stand where its crown lies, out of a fight.
        Never forced."""
        return (
            self._prestige().tide_turned
            and self._crown_here() is not None
            and not self.world.has(self.player, Fighting)
        )

    def _crown_here(self) -> int | None:
        here = self.world.get(self.player, Position)
        for entity, (_, at) in self.world.query(TideCrown, Position):
            if (at.location, at.room) == (here.location, here.room):
                return entity
        return None

    def _crowned(self) -> tuple[set[str], set[tuple[str, str]]]:
        """Where the final foe or its crown is, for map marks: (places you've been
        to, rooms you've been in)."""
        explorer = self._explorer()
        places, rooms = set(), set()
        spots = [at for _, (_, at) in self.world.query(FinalFoe, Position)]
        spots += [at for _, (_, at) in self.world.query(TideCrown, Position)]
        for at in spots:
            if at.location in explorer.locations_visited:
                places.add(at.location)
            if at.room in explorer.rooms_visited.get(at.location, ()):
                rooms.add((at.location, at.room))
        return places, rooms

    def carry_over(self, codex: Codex, prestige: Prestige) -> None:
        """Start this new world with what survived the tide (8c; GameSession.ascend
        calls it right after making the world): the old codex, with anything this
        world already told you added, and the prestige, one tide on with its new
        boon last. Narrated as waking on a new shore."""
        fresh = self.world.get(self.player, Codex)
        for material_id, entry in fresh.materials.items():
            codex.materials.setdefault(material_id, entry)
        for meal_id, meal in fresh.meals.items():
            codex.meals.setdefault(meal_id, meal)
        self.world.add(self.player, codex)
        self.world.add(self.player, prestige)
        boon = prestige.boons[-1]
        self.bus.emit(TideCarried(prestige.rank, boon.name, boon_text(boon)))
        self.bus.flush()

    def sheet(self) -> StatSheet:
        well_fed = cooking.fed(self)
        meal = (
            [StatSource(f"{well_fed.meal.name} ({well_fed.turns_left} turns)", well_fed.meal.stats)]
            if well_fed and any(well_fed.meal.stats.values())
            else []
        )
        prestige = self.world.try_get(self.player, Prestige)
        boons = boon_stats(prestige.boons) if prestige else {}
        kept = [StatSource("Boons", boons)] if boons else []
        return player_stats(self.world.get(self.player, Stats).base, self._equipped(), kept + meal)

    def _meal_view(self, meal: Meal, count: int) -> MealView:
        return MealView(
            meal.meal_id, meal.name, meal.description, buff_text(meal), meal.turns, count
        )

    def _fed(self) -> FedView | None:
        well_fed = cooking.fed(self)
        if well_fed is None:
            return None
        return FedView(well_fed.meal.name, buff_text(well_fed.meal), well_fed.turns_left)

    def _menu(self, shop: Shop) -> tuple[MenuView, ...]:
        return tuple(self._menu_entry(recipe) for recipe in shop.meals)

    def _menu_entry(self, recipe: MealRecipe) -> MenuView:
        gold = shops.gold(self)
        carried = cooking.held(self)
        fee = cook_fee(recipe.meal, self.economy)
        costs = self._costs(recipe.ingredients)
        price = meal_price(recipe.meal, self.economy) if recipe.sold else None
        count = carried[recipe.meal.meal_id].count if recipe.meal.meal_id in carried else 0
        return MenuView(
            meal=self._meal_view(recipe.meal, count),
            ingredients=costs,
            fee=fee,
            can_cook=fee <= gold and all(c.enough for c in costs),
            price=price,
            affordable=price is not None and price <= gold,
        )

    def quest_states(self) -> dict[str, str]:
        """Each quest's state by id (posted, hidden, active, ready, done), without
        building quest views (cheap: for unread dots)."""
        return {q.quest_id: q.state for q in questing.all_quests(self)}

    def pack_ids(self) -> set[int]:
        """Entity ids of what you carry but don't wear: the pack's ItemView ids,
        without building them (cheap: for unread dots)."""
        return {
            e
            for e, (_, carried) in self.world.query(Item, Carried)
            if carried.by == self.player and not self.world.has(e, Equipped)
        }

    def satchel_keys(self) -> set[tuple[str, str]]:
        """("material", id), ("meal", id) and ("recipe", name) for what's in your
        satchel and the recipes you know (cheap: for unread dots)."""
        return (
            {("material", s.material.material_id) for s in crafting.held(self).values()}
            | {("meal", s.meal.meal_id) for s in cooking.held(self).values()}
            | {("recipe", r.name) for r in crafting.known(self).values()}
        )

    def inventory(self) -> InventoryView:
        with self._building_views():
            return self._inventory()

    def _inventory(self) -> InventoryView:
        equipped = self._equipped_entities()
        by_slot = {item.slot: (e, item) for e, item in equipped}
        slots = []
        for slot in SLOTS:
            filled_by = next(
                (
                    item.display_name
                    for _, item in equipped
                    if item.slot != slot and slot in slots_taken(item)
                ),
                None,
            )
            held = by_slot.get(slot)
            slots.append(
                SlotView(
                    slot=slot,
                    label=SLOT_LABELS[slot],
                    item=self._item_view(*held) if held else None,
                    filled_by=filled_by,
                )
            )
        pack = tuple(
            self._item_view(e, item)
            for e, (item, carried) in self.world.query(Item, Carried)
            if carried.by == self.player and not self.world.has(e, Equipped)
        )
        buyer = shops.buyer_here(self)
        return InventoryView(
            slots=tuple(slots),
            pack=pack,
            sheet=self.sheet(),
            gold=shops.gold(self),
            buyer=buyer[1].name if buyer else None,
            materials=self._materials(),
            recipes=tuple(r.name for r in crafting.known(self).values()),
            meals=tuple(
                self._meal_view(s.meal, s.count)
                for s in sorted(cooking.held(self).values(), key=lambda s: s.meal.name)
            ),
            fed=self._fed(),
        )

    def _materials(self) -> tuple[MaterialView, ...]:
        stacks = sorted(crafting.held(self).values(), key=lambda s: s.material.name)
        return tuple(self._material_view(s.material, s.count) for s in stacks)

    def _material_view(self, material, count: int) -> MaterialView:
        return MaterialView(
            id=material.material_id,
            name=material.name,
            description=material.description,
            count=count,
            sell_price=material_sell_price(material, self.economy),
            ingredient=material.ingredient,
        )

    def _costs(self, needs: list[MaterialStack]) -> tuple[CostView, ...]:
        return tuple(
            CostView(n.material.name, n.count, crafting.count(self, n.material.material_id))
            for n in needs
        )

    def _recipe_view(self, recipe: Recipe) -> RecipeView:
        fee = craft_fee(recipe.makes, self.economy)
        costs = self._costs(recipe.materials)
        return RecipeView(
            id=recipe.recipe_id,
            name=recipe.name,
            item=self._item_view(-1, recipe.makes),
            materials=costs,
            fee=fee,
            can_craft=fee <= shops.gold(self) and all(c.enough for c in costs),
        )

    def _crafting(self, shop: Shop) -> tuple[tuple[RecipeView, ...], tuple[UpgradeView, ...]]:
        gold = shops.gold(self)
        recipes = [self._recipe_view(r) for r in crafting.known(self).values()]
        upgrades = []
        carried = [
            (e, item) for e, (item, c) in self.world.query(Item, Carried) if c.by == self.player
        ]
        for entity, item in sorted(
            carried, key=lambda p: (not self.world.has(p[0], Equipped), p[0])
        ):
            needs = crafting.upgrade_needs(self, item, shop)
            if needs is None:
                continue
            fee = upgrade_fee(item, self.economy)
            costs = self._costs(needs)
            better = copy.deepcopy(item)
            better.upgrade += 1
            upgrades.append(
                UpgradeView(
                    item=self._item_view(entity, item),
                    upgraded=self._item_view(-1, better),
                    materials=costs,
                    fee=fee,
                    can_upgrade=fee <= gold and all(c.enough for c in costs),
                )
            )
        return tuple(recipes), tuple(upgrades)

    def _shops(self, lists_for: bool | str = True) -> tuple[ShopView, ...]:
        gold = shops.gold(self)
        views = []
        for entity, shop in shops.shops_here(self):
            wares = []
            for e, item in shops.wares(self, entity):
                price = buy_price(item, self.economy)
                wares.append(
                    WareView(self._item_view(e, item), price, price <= gold, e in shop.buyback)
                )
            materials = []
            for material in shop.materials:
                price = material_buy_price(material, self.economy)
                view = self._material_view(material, crafting.count(self, material.material_id))
                materials.append(MaterialWareView(view, price, price <= gold))
            lists = lists_for is True or lists_for == shop.name
            recipes, upgrades = self._crafting(shop) if shop.crafts and lists else ((), ())
            views.append(
                ShopView(
                    name=shop.name,
                    wares=tuple(wares),
                    buys_gear=shop.buys_gear,
                    inn_price=self.economy.inn_price if shop.inn else None,
                    materials=tuple(materials),
                    buys_materials=shop.buys_materials,
                    crafts=shop.crafts,
                    recipes=recipes,
                    upgrades=upgrades,
                    cooks=shop.cooks,
                    menu=self._menu(shop) if shop.cooks else (),
                    enchants=bool(shop.enchants),
                    enchantable=self._enchantable(shop) if shop.enchants and lists else (),
                )
            )
        return tuple(views)

    def _enchantable(self, shop: Shop) -> tuple[EnchantableView, ...]:
        """Your gear (worn first, then your pack) with what this Enchanter can put on
        each piece, strongest tier first within each enchantment."""
        gold = shops.gold(self)
        carried = [
            (e, item) for e, (item, by) in self.world.query(Item, Carried) if by.by == self.player
        ]
        carried.sort(key=lambda pair: (not self.world.has(pair[0], Equipped), pair[1].display_name))
        out = []
        for entity, item in carried:
            options = []
            offers = sorted(shop.enchants, key=lambda o: (o.name, -o.tier))
            for offer in offers:
                if not enchanting.fits(offer, item):
                    continue
                costs = self._costs(offer.materials)
                cost = enchanting.fee(offer)
                does = [gear_effects.describe(e) for e in offer.effects]
                does += [f"+{v} {s.upper()}" for s, v in offer.stats.items() if v]
                options.append(
                    EnchantOptionView(
                        offer.enchant_id,
                        offer.tier,
                        f"{offer.name} {enchanting.ROMAN[offer.tier - 1]}",
                        "; ".join(does),
                        offer.description,
                        costs,
                        cost,
                        enchanting.replaces(offer, item),
                        all(c.enough for c in costs) and cost <= gold,
                    )
                )
            if options:
                out.append(EnchantableView(self._item_view(entity, item), tuple(options)))
        return tuple(out)

    def _shop_rooms(self, location_id: str) -> set[str]:
        return {
            p.room for _, (_, p) in self.world.query(Shop, Position) if p.location == location_id
        }

    def _guard(self, location_id: str, to: str) -> str | None:
        """The name of the warden barring the road from here to `to`, if any."""
        location = self.overworld.location(location_id)
        for room_id in location.gates:
            entity = fight.warden_on(self, location_id, room_id, to)
            if entity is not None:
                return self.world.get(entity, Enemy).name
        return None

    def _region_change(self, location_id: str, to: str) -> str | None:
        here, there = self.overworld.region_of(location_id), self.overworld.region_of(to)
        return there.name if there and there != here else None

    def _region_marks(self, shown: MapView) -> tuple[RegionMark, ...]:
        if len(self.overworld.regions) < 2:
            return ()
        marks = []
        for region in self.overworld.regions.values():
            known = [n for n in shown.nodes if self.overworld.locations[n.id].region == region.id]
            if known:
                x = sum(n.x for n in known) / len(known)
                y = sum(n.y for n in known) / len(known)
                marks.append(RegionMark(region.name, round(x, 4), round(y, 4)))
        return tuple(marks)

    @cached_property
    def _grid_side(self) -> int | None:
        """The overworld grid's size, worked out once (places never move)."""
        return grid_side([loc.pos for loc in self.overworld.locations.values()])

    def _region_borders(self, shown: MapView) -> tuple[tuple[float, float, float, float], ...]:
        """Borders between the regions of the places on the map (never further)."""
        if len(self.overworld.regions) < 2:
            return ()
        side = self._grid_side
        if side is None:
            return ()
        key = tuple(n.id for n in shown.nodes)  # they only change as places are found
        cached = self._borders_cache
        if cached.get("key") != key:
            order = {region_id: i for i, region_id in enumerate(self.overworld.regions)}
            places = [
                (n.x, n.y, order[region])
                for n in shown.nodes
                if (region := self.overworld.locations[n.id].region) in order
            ]
            cached.update(key=key, borders=region_borders(places, side))
        return cached["borders"]

    @cached_property
    def _borders_cache(self) -> dict:
        return {}

    def reveal_map(self) -> bool:
        """Dev builds only (the UI offers it there): every place and room known
        and visited, and every warden gone so every road is open. Refused in a
        fight (False). Not a command: it takes no turn and nothing reacts to it."""
        if self.world.has(self.player, Fighting):
            return False
        explorer = self._explorer()
        for loc in self.overworld.locations.values():
            explorer.locations_discovered.add(loc.id)
            explorer.locations_visited.add(loc.id)
            rooms = set(loc.rooms)
            explorer.rooms_discovered.setdefault(loc.id, set()).update(rooms)
            explorer.rooms_visited.setdefault(loc.id, set()).update(rooms)
        for entity, _ in list(self.world.query(Warden)):
            self.world.destroy(entity)
        self._say("(Dev) The whole map is revealed and every road is open.")
        return True

    def skip_to_region(
        self, region_id: str, worn: Iterable[Item], spare: Iterable[Item] = (), gold: int = 0
    ) -> bool:
        """Dev builds only: start over at the town just inside `region_id`, as if
        the regions before it were played through. Their places are known, the
        wardens up to it are gone, the kit is swapped for `worn` (with `spare` in
        the pack) and `gold` is added. Refused in a fight (False). Not a command."""
        if self.world.has(self.player, Fighting):
            return False
        target = self.overworld.regions[region_id]
        towns = [
            loc for loc in self.overworld.locations.values() if loc.region == region_id and loc.town
        ]
        # The town just over the border: the one with a road from a shallower region.
        town = next(
            (
                loc
                for loc in towns
                for n in self.overworld.neighbours(loc.id)
                if (r := self.overworld.region_of(n)) is not None and r.tier < target.tier
            ),
            towns[0],
        )
        explorer = self._explorer()
        for loc in self.overworld.locations.values():
            region = self.overworld.region_of(loc.id)
            if region is not None and region.tier < target.tier:
                explorer.locations_discovered.add(loc.id)
                explorer.locations_visited.add(loc.id)
        for entity, (warden,) in list(self.world.query(Warden)):
            if self.overworld.regions[warden.region].tier <= target.tier:
                self.world.destroy(entity)
        for entity, _ in self._equipped_entities():
            self.world.destroy(entity)
        for item in worn:
            self.world.create(item, Carried(self.player), Equipped(item.slot))
        for item in spare:
            self.world.create(item, Carried(self.player))
        self.world.get(self.player, Wallet).gold += gold
        self.world.get(self.player, Health).damage = 0
        self.world.get(self.player, Position).location = town.id
        self.world.get(self.player, Position).room = town.start
        self._say(f"(Dev) You start in {target.name}, in gear from the regions before it.")
        self.bus.emit(LocationEntered(self.player, town.id, None, first_visit=True))
        self.bus.emit(RoomEntered(self.player, town.id, town.start, None, first_visit=True))
        self.bus.flush()
        return True

    def region(self) -> str | None:
        """The name of the region the player is in (None in a world without regions)."""
        region = self.overworld.region_of(self.world.get(self.player, Position).location)
        return region.name if region else None

    def _explorer(self) -> Explorer:
        return self.world.get(self.player, Explorer)

    def here(self) -> tuple[Location, Room]:
        position = self.world.get(self.player, Position)
        location = self.overworld.location(position.location)
        return location, location.room(position.room)

    # --- view model ------------------------------------------------------------------

    def view(self, lists_for: bool | str = True) -> GameView:
        """What the player sees. `lists_for` says which shops here get their upgrade
        and recipe lists (the slow part, one gear comparison per item you carry):
        True every one, False none, or a shop's name just that one (the open panel;
        the Explore screen asks for nothing else, v0.11.2)."""
        with self._building_views():
            return self._view(lists_for)

    def _view(self, lists_for: bool | str = True) -> GameView:
        location, room = self.here()
        explorer = self._explorer()
        rooms_visited = explorer.rooms_visited.get(location.id, set())
        at_gate = room.id in location.gates
        exits = tuple(
            ExitView(e.label, location.room(e.to).name if e.to in rooms_visited else None)
            for e in room.exits
        )
        roads = tuple(
            RoadView(
                location=to,
                name=self.overworld.location(to).name,
                kind=self.overworld.location(to).kind,
                visited=to in explorer.locations_visited,
                guard=self._guard(location.id, to),
                region=self._region_change(location.id, to),
            )
            for to in location.roads
        )
        room_map = world_map = None
        quest_places, quest_rooms = self._quest_places()
        crowned_places, crowned_rooms = self._crowned()
        if location.has_map:
            room_map = _fog_map(
                nodes=[(r.id, r.pos, r.name) for r in location.rooms.values()],
                neighbours=location.neighbours,
                here=room.id,
                visited=rooms_visited,
                discovered=explorer.rooms_discovered.get(location.id, set()),
                commands={e.to: Move(e.label) for e in room.exits},
                names_on_discovery=False,
                gates=set(location.gates),
                items={
                    p.room
                    for _, (_, p) in self.world.query(Item, Position)
                    if p.location == location.id and p.room in rooms_visited
                },
                quests={r for loc, r in quest_rooms if loc == location.id},
                shops=self._shop_rooms(location.id) & rooms_visited,
                crowns={r for loc, r in crowned_rooms if loc == location.id},
            )
            xs = [r.pos[0] for r in location.rooms.values()]
            ys = [r.pos[1] for r in location.rooms.values()]
            room_map = replace(room_map, bounds=(min(xs), min(ys), max(xs), max(ys)))
        if self.overworld.has_map:
            world_map = _fog_map(
                nodes=[(loc.id, loc.pos, loc.name) for loc in self.overworld.locations.values()],
                neighbours=self.overworld.neighbours,
                here=location.id,
                visited=explorer.locations_visited,
                discovered=explorer.locations_discovered,
                commands={to: Travel(to) for to in location.roads} if at_gate else {},
                blocked={} if at_gate else dict.fromkeys(location.roads, _leave_from(location)),
                names_on_discovery=True,  # signposts name the places a road leads
                kinds={loc.id: loc.kind for loc in self.overworld.locations.values()},
                quests=quest_places,
                charted={
                    loc.id
                    for loc in self.overworld.locations.values()
                    if len(explorer.rooms_visited.get(loc.id, ())) >= len(loc.rooms)
                },
                guarded={w.road for _, (w,) in self.world.query(Warden)},
                crowns=crowned_places,
            )
            world_map = replace(
                world_map,
                regions=self._region_marks(world_map),
                borders=self._region_borders(world_map),
            )
        return GameView(
            location=location.name,
            kind=location.kind,
            room=room.name,
            description=room.description,
            exits=exits,
            at_gate=at_gate,
            gates=tuple(location.room(g).name for g in location.gates),
            roads=roads,
            log=tuple(self.log),
            log_total=self.log_total,
            turn=self.turn,
            seed=self.seed,
            rooms_visited=len(rooms_visited),
            total_rooms=len(location.rooms),
            locations_visited=len(explorer.locations_visited),
            total_locations=len(self.overworld.locations),
            map=room_map,
            world_map=world_map,
            items_here=tuple(
                self._item_view(e, i) for e, i in self._items_at(location.id, room.id)
            ),
            stats=self.sheet().total,
            hp=self.hp(),
            max_hp=self.max_hp(),
            combat=self._combat_view(),
            in_town=location.town,
            board=self._board(),
            gold=shops.gold(self),
            shops=self._shops(lists_for),
            fed=self._fed(),
            tide=self._prestige().rank,
            can_ascend=self.can_ascend(),
            region=self.region(),
        )

    # --- subscribers -----------------------------------------------------------------

    def _explore_location(self, event: LocationEntered) -> None:
        explorer = self.world.try_get(event.entity, Explorer)
        if explorer is None:
            return
        explorer.locations_visited.add(event.location)
        explorer.locations_discovered.add(event.location)
        for neighbour in self.overworld.neighbours(event.location):
            if neighbour not in explorer.locations_discovered:
                explorer.locations_discovered.add(neighbour)
                self.bus.emit(LocationDiscovered(neighbour))

    def _explore_room(self, event: RoomEntered) -> None:
        explorer = self.world.try_get(event.entity, Explorer)
        if explorer is None:
            return
        visited = explorer.rooms_visited.setdefault(event.location, set())
        discovered = explorer.rooms_discovered.setdefault(event.location, set())
        visited.add(event.room)
        discovered.add(event.room)
        for neighbour in self.overworld.location(event.location).neighbours(event.room):
            if neighbour not in discovered:
                discovered.add(neighbour)
                self.bus.emit(RoomDiscovered(event.location, neighbour))

    def _narrate(self, event: Event) -> None:
        match event:
            case LocationEntered(
                entity=entity, location=location_id, from_location=origin, first_visit=first
            ):
                if entity == self.player:
                    location = self.overworld.location(location_id)
                    if origin is not None:
                        self._say(f"You take the road to {location.name}.")
                        crossed = self._region_change(origin, location_id)
                        if crossed:
                            self._say(f"You cross into {crossed}.", important=True)
                    self._say(f"— {location.name} · {location.kind} —")
                    if any(
                        at.location == location_id
                        for _, (_, at) in self.world.query(FinalFoe, Position)
                    ):
                        court = (
                            "A bell tolls somewhere under the water. Deep in this hall"
                            " the Drowned King keeps his court, and waits."
                        )
                        self._say(court, important=True)
                        if first:
                            self.bus.emit(
                                Milestone(
                                    "The Drowned King's hall",
                                    court + " His thanes still guard the way to his"
                                    " throne, in the farthest hall from the shore. He is"
                                    " the hardest fight there is: go in well fed.",
                                )
                            )
            case RoomEntered(
                entity=entity,
                location=location_id,
                room=room_id,
                from_room=origin,
                first_visit=first,
            ):
                if entity == self.player:
                    name = self.overworld.location(location_id).room(room_id).name
                    if origin is None:
                        self._say(f"You stand at {name}.")
                    else:
                        self._say(
                            f"You make your way to {name}." if first else f"You return to {name}."
                        )
                    self._mention_items(location_id, room_id)
                    self._mention_board()
                    self._mention_shops()
                    self._mention_wardens()
                    self._mention_crown()
            case LookedAround(location=location_id, room=room_id):
                scenery = [
                    s.text
                    for _, (s, p) in self.world.query(Scenery, Position)
                    if (p.location, p.room) == (location_id, room_id)
                ]
                items = self._items_at(location_id, room_id)
                for text in scenery or ([] if items else ["Nothing else here catches your eye."]):
                    self._say(text)
                self._mention_items(location_id, room_id)
            case ItemTaken(name=name):
                self._say(f"You take the {name}.")
            case ItemDropped(name=name):
                self._say(f"You put down the {name}.")
            case ItemEquipped(name=name, replaced=replaced):
                if replaced:
                    self._say(f"You put away the {_and(replaced)} and equip the {name}.")
                else:
                    self._say(f"You equip the {name}.")
            case ItemUnequipped(name=name):
                self._say(f"You take off the {name}.")
            case Waited():
                self._say("Time passes.")
            case Rested(price=price):
                self._say(f"You pay {price} gold for a bed and wake whole again.")
            case WayBarred(name=name, crossing=crossing, region=region):
                self._say(f"The {name} bars {crossing} into {region}!", important=True)
            case CombatStarted(enemy=enemy, name=name, wandering=wandering):
                if not self.world.has(enemy, Warden):  # WayBarred said it
                    self._say(
                        f"A {name} comes upon you!" if wandering else f"A {name} blocks your way!"
                    )
            case Attacked(attacker=attacker, target_name=target, attacker_name=by, damage=hit):
                if attacker == self.player:
                    self._say(f"You hit the {target} for {hit}.")
                else:
                    blocked = " You take some of it on your guard." if event.defended else ""
                    self._say(f"The {by} hits you for {hit}.{blocked}")
            case Fled(name=name):
                self._say(f"You break away from the {name} and run.")
            case FleeFailed(name=name):
                self._say(f"You try to run, but the {name} cuts you off.")
            case EnemyKilled(name=name, loot=loot, gold=gold):
                self._say(f"You defeat the {name}.")
                dropped = [f"a {n}" for n in loot] + ([f"{gold} gold"] if gold else [])
                if dropped:
                    self._say(f"It drops {_and(dropped)}.")
            case RegionOpened(name=name):
                self._say(f"The way into {name} lies open.", important=True)
            case TideCarried(rank=rank, boon=boon, boon_text=does):
                self._say(
                    "The Wrack came in the night: one great tide over everything you"
                    " knew. You remember the cold, and the dark, and holding on."
                )
                self._say(
                    f"You wake on a strange shore, the {_ordinal(rank)} tide behind you,"
                    " the land new and the drowned already stirring. You remember all"
                    f" you learned. {boon}: {does}.",
                    important=True,
                )
            case TideTurned(enemy=name):
                turned = (
                    f"The {name} sinks into the black water and does not rise. Far off,"
                    " the sea draws a long breath: the old pact that held it back is"
                    " broken, and the tide is turning."
                )
                how = (
                    "His crown lies on the empty throne. Take it when you're ready and"
                    " the Wrack will carry you to a new shore: you'll start again, keeping"
                    " what you've learned and one boon of your choosing. The tide will"
                    " wait while you finish what you came for."
                )
                self._say(turned, important=True)
                self._say(how)
                self.bus.emit(Milestone("The tide is turning", f"{turned}\n\n{how}"))
            case PlayerDefeated(name=name):
                self._say(f"The {name} strikes you down. Everything goes dark.", important=True)
            case Respawned(location=location_id):
                town = self.overworld.location(location_id).name
                self._say(f"You come to at the edge of {town}, bruised but alive.")
            case QuestAccepted(title=title):
                self._say(f"You take down the notice: {title}.")
            case QuestFound(title=title, clue=clue):
                self._say(clue)
                self._say(f"New quest: {title}.")
            case QuestItemFound(name=name, description=description):
                self._say(f"You find the {name}. {description}")
            case QuestProgress(title=title, progress=done, needed=needed):
                self._say(f"{title}: {done} of {needed}.")
            case QuestReady(title=title):
                self._say(f"Quest ready to turn in: {title}. Any town's notice board will do.")
            case QuestCompleted(title=title, reward=reward, gold=gold):
                paid = f" and {gold} gold" if gold else ""
                self._say(f"Quest done: {title}. Your reward: the {reward}{paid}.")
            case QuestAbandoned(title=title, board=board):
                where = f" at {self.overworld.location(board).name}" if board else ""
                self._say(f"You give up on {title}. The notice goes back up{where}.")
            case ItemBought(name=name, price=price, shop=shop):
                self._say(f"You buy the {name} from the {shop} for {price} gold.")
            case ItemSold(name=name, price=price, shop=shop):
                self._say(f"You sell the {name} to the {shop} for {price} gold.")
            case MaterialsGained(name=name, count=n, source=source):
                if source == "gathered":
                    self._say(f"You gather {n} {name}.")
                elif source == "loot":
                    self._say(f"You take {n} {name}.")
            case MaterialsBought(name=name, count=n, price=price, shop=shop):
                self._say(f"You buy {n} {name} at the {shop} for {price} gold.")
            case MaterialsSold(name=name, count=n, price=price, shop=shop):
                self._say(f"You sell {n} {name} to the {shop} for {price} gold.")
            case RecipeLearned(name=name, source=source):
                how = "You find a recipe" if source == "found" else "You're taught a recipe"
                self._say(f"{how}: {name}. Any smithy can make it.")
            case ItemCrafted(name=name, fee=fee):
                self._say(f"The smith makes you a {name} for {fee} gold.")
            case MealCooked(name=name, fee=fee):
                self._say(f"The cook makes you a {name} for {fee} gold. It keeps until you eat it.")
            case MealBought(name=name, price=price, shop=shop):
                self._say(f"You buy a {name} at the {shop} for {price} gold.")
            case MealEaten(name=name, turns=turns, replaced=replaced):
                gone = f" It takes the place of your {replaced}." if replaced else ""
                self._say(f"You eat the {name}. It'll keep you going for {turns} turns.{gone}")
            case MealWoreOff(name=name):
                self._say(f"The {name} has worn off.")
            case ItemUpgraded(name=name, fee=fee):
                self._say(f"The smith works on it for {fee} gold: it's now a {name}.")
            case ItemEnchanted(name=name, enchantment=what, tier=tier, replaced=old, fee=fee):
                was = f", and the {old} is gone" if old else ""
                self._say(
                    f"For {fee} gold, {what} ({tier}) is worked into it{was}: it's now a {name}."
                )
            case AmbientNoticed(text=text):
                self._say(text)
            case ActionRejected(reason=reason):
                self._say(reason)

    def _mention_items(self, location_id: str, room_id: str) -> None:
        names = [item.display_name for _, item in self._items_at(location_id, room_id)]
        if len(names) == 1:
            self._say(f"A {names[0]} lies here.")
        elif names:
            self._say(f"Lying here: {_and(names)}.")

    def _mention_board(self) -> None:
        board = self._board()
        if not board:
            return
        posted = sum(q.state == "posted" for q in board)
        ready = len(board) - posted
        if posted:
            self._say(
                f"A notice board by the gate has {posted} notice{'s' * (posted != 1)} pinned to it."
            )
        if ready:
            self._say(f"You can turn in {ready} finished quest{'s' * (ready != 1)} here.")

    def _mention_wardens(self) -> None:
        position = self.world.get(self.player, Position)
        for _, (enemy, warden, at) in self.world.query(Enemy, Warden, Position):
            if (at.location, at.room) == (position.location, position.room):
                region = self.overworld.regions[warden.region].name
                self._say(
                    f"A {enemy.name} stands across {warden.crossing} into {region}.",
                    important=True,
                )

    def _mention_crown(self) -> None:
        if self._crown_here() is not None:
            self._say("The Drowned Crown lies on the empty throne.", important=True)

    def _mention_shops(self) -> None:
        for _, shop in shops.shops_here(self):
            if shop.inn:
                cooking_too = " and a kitchen" if shop.cooks else ""
                self._say(
                    f"The {shop.name} has beds for {self.economy.inn_price} gold a night"
                    f"{cooking_too}."
                )
            elif shop.crafts:
                self._say(f"The {shop.name} is open for trade and takes crafting work.")
            elif shop.materials or shop.buys_materials:
                self._say(f"The {shop.name} trades in materials.")
            else:
                self._say(f"The {shop.name} is open for trade.")

    def _say(self, line: str, important: bool = False) -> None:
        """Write a log line; `important` ones start with IMPORTANT, which the UI
        highlights (and toasts while the log is closed)."""
        self.log.append(IMPORTANT + line if important else line)
        self.log_total += 1
        del self.log[:-LOG_LIMIT]


def _leave_from(location: Location) -> str:
    gates = " or ".join(location.room(g).name for g in location.gates)
    return f"You can only leave {location.name} from {gates}."


def _and(names: Iterable[str]) -> str:
    """ "a", "a and b", "a, b and c"."""
    names = list(names)
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


# --- maps --------------------------------------------------------------------------


def _fog_map(
    nodes: list[tuple[str, tuple[float, float] | None, str]],
    neighbours: Callable[[str], list[str]],
    here: str,
    visited: set[str],
    discovered: set[str],
    commands: dict[str, Command],
    names_on_discovery: bool,
    gates: set[str] = frozenset(),  # type: ignore[assignment]
    kinds: dict[str, str] | None = None,
    items: set[str] = frozenset(),  # type: ignore[assignment]
    quests: set[str] = frozenset(),  # type: ignore[assignment]
    charted: set[str] = frozenset(),  # type: ignore[assignment]
    blocked: dict[str, str] | None = None,
    shops: set[str] = frozenset(),  # type: ignore[assignment]
    guarded: set[str] = frozenset(),  # type: ignore[assignment]
    crowns: set[str] = frozenset(),  # type: ignore[assignment]
) -> MapView:
    """Only what the player knows: discovered nodes, and paths out of visited ones."""
    shown = []
    for node_id, pos, name in nodes:  # map order, so output is stable
        if node_id not in discovered:
            continue
        state = "current" if node_id == here else "visited" if node_id in visited else "seen"
        x, y = pos  # type: ignore[misc]  # callers check has_map
        shown.append(
            MapNode(
                id=node_id,
                x=x,
                y=y,
                state=state,
                name=name if names_on_discovery or node_id in visited else None,
                command=commands.get(node_id),
                gate=node_id in gates,
                kind=(kinds or {}).get(node_id),
                items=node_id in items,
                quest=node_id in quests,
                charted=node_id in charted,
                blocked=(blocked or {}).get(node_id),
                shop=node_id in shops,
                guarded=node_id in guarded,
                crown=node_id in crowns,
            )
        )
    edges = sorted({tuple(sorted((a, b))) for a in visited for b in neighbours(a)})
    return MapView(nodes=tuple(shown), edges=tuple(edges), size=len(nodes))  # type: ignore[arg-type]


# --- systems -----------------------------------------------------------------------


def ambience_system(game: Game) -> None:
    """Sometimes play a flavour line for where the player is."""
    if game.world.has(game.player, Fighting):
        return  # no birdsong mid-fight
    location, room = game.here()
    if room.ambient and game.ambient_rng.chance(AMBIENT_CHANCE):
        game.bus.emit(AmbientNoticed(location.id, room.id, game.ambient_rng.choice(room.ambient)))


def buff_text(meal: Meal) -> str:
    """ "ATK +2, faster healing (+2 HP)": what a meal does while it lasts."""
    parts = [f"{stats.STAT_LABELS[s]} +{v}" for s, v in meal.stats.items() if v]
    if meal.regen:
        parts.append(f"faster healing (+{meal.regen} HP)")
    text = ", ".join(parts)
    return text[:1].upper() + text[1:]


def _ordinal(n: int) -> str:
    words = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth"]
    if 1 <= n <= len(words):
        return words[n - 1]
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

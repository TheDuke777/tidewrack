"""Pydantic schemas for content files (CLAUDE.md §3, §9).

Schemas validate data at the boundary, then convert it to the immutable runtime
models the engine uses (e.g. Location), so game code never handles raw dicts.
Unknown keys are rejected so typos in content fail loudly instead of being ignored.
"""

from __future__ import annotations

from string import Formatter
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from tidewrack.core.gear.item import SET_COLORS, SLOTS
from tidewrack.core.gear.stats import DEFAULT_PLAYER_BASE, STATS
from tidewrack.core.world.location import Exit, Location, Room
from tidewrack.core.world.overworld import Overworld, Region

Text = Annotated[str, StringConstraints(min_length=1)]
Unit = Annotated[float, Field(ge=0.0, le=1.0)]
LocalId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]


def content_id(kind: str) -> type[str]:
    """A stable content ID of the form `<kind>.<snake_case_name>` (§9)."""
    return Annotated[str, StringConstraints(pattern=rf"^{kind}\.[a-z][a-z0-9_]*$")]  # type: ignore[return-value]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _known_stats(block: dict[str, int]) -> dict[str, int]:
    unknown = sorted(set(block) - set(STATS))
    if unknown:
        raise ValueError(f"unknown stats {unknown}; stats are {list(STATS)}")
    return block


StatBlock = Annotated[dict[str, int], AfterValidator(_known_stats)]
Slot = Literal[SLOTS]  # type: ignore[valid-type]
Weights = dict[str, Annotated[float, Field(gt=0)]]


def _check_range(name: str, low: int, high: int) -> None:
    if not 0 <= low <= high:
        raise ValueError(f"{name} must satisfy 0 <= min <= max, not [{low}, {high}]")


# --- materials and recipes (step 7b) ------------------------------------------------

Counts = dict[str, Annotated[int, Field(ge=1, le=50)]]  # material id -> how many


class MaterialSchema(Schema):
    """Something crafting uses: hides, ore, timber. Held as counts, not items."""

    id: content_id("material")
    name: Text
    description: Text
    value: int = Field(ge=1, le=100)  # gold; prices derive from it like gear's
    ingredient: bool = False  # used for cooking (step 7c) rather than crafting


class RecipeSchema(Schema):
    """How to craft one piece of gear at a smithy. Known recipes are taught to every
    new world's player; the rest are found (a page in a room, or a quest's extra
    reward). The fee is worked out from what it makes (core.economy.value_model)."""

    id: content_id("recipe")
    makes: content_id("gear")
    affix: content_id("affix") | None = None  # crafted with this affix
    materials: Counts = Field(min_length=1)
    known: bool = False


class MealSchema(Schema):
    """Something a tavern cooks (step 7c). Eating it gives a buff for `turns` turns;
    one meal's buff at a time. Its value is its ingredients' (prices derive from it)."""

    id: content_id("meal")
    name: Text
    description: Text
    ingredients: Counts = Field(min_length=1)  # material ids (ingredients)
    stats: StatBlock = {}
    regen: int = Field(default=0, ge=0, le=20)  # extra HP per regeneration
    turns: int = Field(default=60, ge=5, le=500)
    sold: bool = False  # taverns also sell it ready-made

    @model_validator(mode="after")
    def _check(self) -> MealSchema:
        if not (any(self.stats.values()) or self.regen):
            raise ValueError("a meal needs a buff: stats or regen")
        return self


class MaterialDropSchema(Schema):
    material: content_id("material")
    chance: Unit
    count: tuple[int, int] = (1, 1)

    @model_validator(mode="after")
    def _check(self) -> MaterialDropSchema:
        if not 1 <= self.count[0] <= self.count[1]:
            raise ValueError(f"count must satisfy 1 <= min <= max, not {list(self.count)}")
        return self


# --- gear ----------------------------------------------------------------------------


class GearSchema(Schema):
    """A kind of gear. Each copy found rolls its own bonus and maybe an affix."""

    id: content_id("gear")
    name: Text
    slot: Slot
    two_handed: bool = False
    base: StatBlock
    rolls: dict[str, tuple[int, int]] = {}  # stat -> inclusive [min, max] bonus
    max_upgrade: int = Field(default=0, ge=0, le=10)
    upgrade_step: StatBlock = {}  # added per upgrade level
    upgrade_materials: Counts = {}  # for each level, times the level being reached
    set: content_id("gearset") | None = None
    effects: list[Text] = []

    @model_validator(mode="after")
    def _check(self) -> GearSchema:
        _known_stats(self.rolls)
        for stat, (low, high) in self.rolls.items():
            if low > high:
                raise ValueError(f"roll for {stat} has min {low} above max {high}")
        if self.two_handed and self.slot != "main_hand":
            raise ValueError("two-handed gear must have slot main_hand")
        if self.max_upgrade and not any(self.upgrade_step.values()):
            raise ValueError("upgradable gear needs a non-zero upgrade_step")
        if self.max_upgrade and not self.upgrade_materials:
            raise ValueError("upgradable gear needs upgrade_materials")
        return self


class AffixSchema(Schema):
    """A modifier a found item may roll: "Keen Cutlass", "Boots of the Gull"."""

    id: content_id("affix")
    name: Text
    position: Literal["prefix", "suffix"]
    slots: list[Slot] = Field(min_length=1)  # gear it can appear on
    weight: float = Field(default=1.0, gt=0)
    stats: StatBlock = {}
    effects: list[Text] = []


class SetBonusSchema(Schema):
    pieces: int = Field(ge=2)
    stats: StatBlock = {}
    effects: list[Text] = []


class GearSetSchema(Schema):
    """Gear that grants bonuses when several pieces are worn together."""

    id: content_id("gearset")
    name: Text
    color: Literal[SET_COLORS]  # type: ignore[valid-type]  # its chip's colour
    bonuses: list[SetBonusSchema] = Field(min_length=1)


# --- enemies -------------------------------------------------------------------------

ENEMY_CATEGORIES = ("beast", "person", "spirit")


class LootSchema(Schema):
    chance: Unit = 0.0  # that an enemy drops anything
    gear: Weights = {}  # gear id -> relative weight


class EnemySchema(Schema):
    """Someone or something hostile. People are enemies too (wreckers, smugglers)."""

    id: content_id("enemy")
    name: Text
    category: Literal[ENEMY_CATEGORIES]  # type: ignore[valid-type]
    description: Text
    plural: Text | None = None  # for quests ("Cull 4 …"); defaults to name + "s"
    stats: StatBlock
    rolls: dict[str, tuple[int, int]] = {}  # stat -> inclusive [min, max] bonus
    loot: LootSchema = LootSchema()
    gold: tuple[int, int] = (0, 0)  # inclusive range it carries (people have purses)
    materials: list[MaterialDropSchema] = []  # hides, shells, scraps (each rolled)

    @property
    def plural_name(self) -> str:
        return self.plural or f"{self.name}s"

    @model_validator(mode="after")
    def _check(self) -> EnemySchema:
        _known_stats(self.rolls)
        if self.stats.get("hp", 0) < 1:
            raise ValueError("enemies need at least 1 hp")
        for stat, (low, high) in self.rolls.items():
            if low > high:
                raise ValueError(f"roll for {stat} has min {low} above max {high}")
        if self.loot.chance and not self.loot.gear:
            raise ValueError("loot.chance is set but loot.gear is empty")
        _check_range("gold", *self.gold)
        return self


class EncountersSchema(Schema):
    """Enemies in a roomset's locations: placed at world creation, plus wanderers."""

    placed_chance: Unit = 0.0  # per room (never gate rooms)
    wandering_chance: Unit = 0.0  # per room entered without an enemy in it
    wanderers: int = Field(default=6, ge=0, le=50)  # rolled per location at creation
    pool: Weights = {}  # enemy id -> relative weight


class GatheringSchema(Schema):
    """Materials lying about a roomset's locations (ore, driftwood), gathered when
    you walk in; placed when the world is made."""

    chance: Unit = 0.0  # per room (gate rooms never have any)
    materials: Weights = {}  # material id -> relative weight
    count: tuple[int, int] = (1, 2)


class FindsSchema(Schema):
    """Gear lying about a roomset's locations, placed when the world is made."""

    chance: Unit = 0.0  # per room (gate rooms never have finds)
    gear: Weights = {}  # gear id -> relative weight
    affix_chance: Unit = 0.3


# --- shops ---------------------------------------------------------------------------


class ShopSchema(Schema):
    """A kind of shop. A town that has a room with this `room` noun (e.g. "Smithy")
    gets the shop there; a town without one gets it at its gate.

    Shops sell plain copies (no affixes, rolls in the lower half), so finds and
    quest rewards always beat them: top-tier gear is never for sale (§8.6)."""

    id: content_id("shop")
    name: Text  # shown to players: "Smithy"
    room: Text  # the room archetype noun it moves into
    stock: tuple[int, int] = (0, 0)  # wares for sale at world creation
    wares: int = Field(default=0, ge=0, le=20)  # pre-rolled pieces it restocks from
    gear: Weights = {}  # gear id -> relative weight, for stock and wares
    buys_gear: bool = False
    inn: bool = False  # sells a night's rest (a full heal)
    materials: list[content_id("material")] = []  # always for sale (never run out)
    buys_materials: bool = False
    crafts: bool = False  # upgrades gear and crafts from recipes
    cooks: bool = False  # cooks every meal (and sells the `sold` ones ready-made)

    @model_validator(mode="after")
    def _check(self) -> ShopSchema:
        _check_range("stock", *self.stock)
        if (self.stock[1] or self.wares) and not self.gear:
            raise ValueError("a shop with stock or wares needs gear to sell")
        if not (
            self.gear
            or self.buys_gear
            or self.inn
            or self.materials
            or self.buys_materials
            or self.crafts
            or self.cooks
        ):
            raise ValueError("a shop must trade gear or materials, craft, or be an inn")
        return self


# --- roomsets (raw material for generated locations) -------------------------------


class ArchetypeSchema(Schema):
    """A kind of room: generated rooms are named "<adjective> <noun>"."""

    noun: Text
    weight: float = Field(default=1.0, gt=0)  # relative chance of being picked
    descriptions: list[Text] = Field(min_length=1)
    features: list[Text] = []
    ambient: list[Text] = []


class LayoutSchema(Schema):
    """How a roomset's locations are shaped (see core.procgen.location_gen)."""

    spread: float = Field(default=1.8, ge=1.0, le=4.0)  # grid cells per room
    loops: float = Field(default=0.25, ge=0.0, le=1.0)  # chance adjacent rooms join
    corridors: float = Field(default=0.5, ge=0.0, le=1.0)  # chance to grow from newest


class RoomsetSchema(Schema):
    """A kind of location (town, forest, …) and the rooms it's built from."""

    id: content_id("roomset")
    name: Text  # the location kind shown to players, e.g. "Sea Caves"
    location_names: list[Text] = Field(min_length=1)
    size: tuple[int, int] = (10, 14)  # min/max rooms
    layout: LayoutSchema = LayoutSchema()
    adjectives: list[Text] = Field(min_length=1)
    entrance: ArchetypeSchema  # the gate room travellers arrive in and leave from
    rooms: list[ArchetypeSchema] = Field(min_length=1)
    finds: FindsSchema = FindsSchema()
    gathering: GatheringSchema = GatheringSchema()
    enemies: EncountersSchema = EncountersSchema()
    shops: list[content_id("shop")] = []  # one of each in every location of this kind
    town: bool = False  # safe (no wanderers), with a notice board; the respawn point

    @model_validator(mode="after")
    def _check_size(self) -> RoomsetSchema:
        low, high = self.size
        if not 2 <= low <= high <= 60:
            raise ValueError(f"size must satisfy 2 <= min <= max <= 60, not {list(self.size)}")
        return self


# --- quests --------------------------------------------------------------------------

QUEST_TYPES = ("bounty", "cull", "explore", "recover")
# The placeholders each type's texts may use (core/procgen/quest_gen.py fills them).
QUEST_PLACEHOLDERS = {
    "bounty": {"target", "location"},
    "cull": {"count", "enemies", "location"},
    "explore": {"location"},
    "recover": {"item", "location"},
}


class QuestItemSchema(Schema):
    """Something a Recover quest sends you to find (not gear: it's for the quest)."""

    name: Text
    description: Text


class QuestTemplateSchema(Schema):
    """How one type of quest is written; worlds draw their quests from these."""

    id: content_id("quest")
    type: Literal[QUEST_TYPES]  # type: ignore[valid-type]
    titles: list[Text] = Field(min_length=1)
    summaries: list[Text] = Field(min_length=1)
    clues: list[Text] = Field(min_length=1)  # what you find when it's a found quest
    epithets: dict[Literal[ENEMY_CATEGORIES], list[Text]] = {}  # type: ignore[valid-type]
    strength: float = Field(default=1.5, ge=1.0, le=5.0)  # bounty stats multiplier
    counts: tuple[int, int] = (3, 5)  # cull: how many to defeat
    items: list[QuestItemSchema] = []  # recover: what's lost
    gold: tuple[int, int] = (0, 0)  # paid on turning in, with the reward item

    @model_validator(mode="after")
    def _check(self) -> QuestTemplateSchema:
        allowed = QUEST_PLACEHOLDERS[self.type]
        for text in [*self.titles, *self.summaries, *self.clues]:
            used = {field for _, field, _, _ in Formatter().parse(text) if field is not None}
            if used - allowed:
                raise ValueError(
                    f"{text!r} uses {sorted(used - allowed)}; {self.type} quests may use "
                    f"{sorted(allowed)}"
                )
        if self.type == "bounty" and set(self.epithets) != set(ENEMY_CATEGORIES):
            raise ValueError(f"bounty epithets are needed for {list(ENEMY_CATEGORIES)}")
        if any(not names for names in self.epithets.values()):
            raise ValueError("every epithets list needs at least one name")
        if self.type == "recover" and not self.items:
            raise ValueError("recover quests need at least one item")
        low, high = self.counts
        if not 1 <= low <= high <= 20:
            raise ValueError(f"counts must satisfy 1 <= min <= max <= 20, not {list(self.counts)}")
        _check_range("gold", *self.gold)
        return self


class QuestsRecipeSchema(Schema):
    """How many quests a new world gets."""

    per_board: int = Field(default=0, ge=0, le=10)  # posted on each town's notice board
    found: int = Field(default=0, ge=0, le=10)  # left as clues out in the world
    reward_affix_chance: Unit = 1.0
    recipe_chance: Unit = 0.0  # each found recipe: a quest's extra reward, else a page


# --- world recipes -------------------------------------------------------------------


class RegionSchema(Schema):
    """A kind of region (step 8a): a biome a world's places cluster into, from the
    coast (tier 1) inland. Its first place, just over the border, is a town."""

    id: content_id("region")
    name: Text  # the biome shown to players: "Fens"
    tier: int = Field(ge=1, le=20)  # deeper regions have higher tiers (and are tougher)
    names: list[Text] = Field(min_length=1)  # what a world may call it: "The Sallow Fens"
    town: content_id("roomset")  # the kind of its first place (the start, on the coast)
    roomsets: Weights = Field(min_length=1)  # roomset id -> weight, for the other places
    warden: content_id("enemy") | None = None  # guards every road in (none on the coast)
    crossing: Text = "the road"  # what the warden bars: "the causeway"


class RegionPlanSchema(Schema):
    region: content_id("region")
    locations: int = Field(ge=2, le=20)


class WorldRecipeSchema(Schema):
    """What a new world is made of: its regions, coast first, and how many places
    each has. The world starts in the first region's town."""

    id: content_id("world")
    name: Text
    regions: list[RegionPlanSchema] = Field(min_length=1)
    player: StatBlock = dict(DEFAULT_PLAYER_BASE)  # the player's starting stats
    kit: list[content_id("gear")] = []  # starting gear, equipped
    gold: int = Field(default=0, ge=0)  # starting gold
    quests: QuestsRecipeSchema = QuestsRecipeSchema()

    @model_validator(mode="after")
    def _check(self) -> WorldRecipeSchema:
        ids = [r.region for r in self.regions]
        if len(ids) != len(set(ids)):
            raise ValueError("a region is listed more than once")
        if sum(r.locations for r in self.regions) > 60:
            raise ValueError("a world has at most 60 places")
        return self


# --- locations -----------------------------------------------------------------------


class ExitSchema(Schema):
    label: Text
    to: LocalId


class RoomSchema(Schema):
    id: LocalId
    name: Text
    description: Text
    exits: list[ExitSchema] = []
    features: list[Text] = []
    ambient: list[Text] = []
    pos: tuple[Unit, Unit] | None = None  # map position, north up

    @classmethod
    def from_room(cls, r: Room) -> RoomSchema:
        return cls(
            id=r.id,
            name=r.name,
            description=r.description,
            exits=[ExitSchema(label=e.label, to=e.to) for e in r.exits],
            features=list(r.features),
            ambient=list(r.ambient),
            pos=r.pos,
        )

    def to_room(self) -> Room:
        return Room(
            id=self.id,
            name=self.name,
            description=self.description,
            exits=tuple(Exit(e.label, e.to) for e in self.exits),
            features=tuple(self.features),
            ambient=tuple(self.ambient),
            pos=self.pos,
        )


def _unique_ids(ids: list[str], what: str) -> None:
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"duplicate {what} ids: {', '.join(duplicates)}")


class DungeonSchema(Schema):
    """A hand-authored location (content file), e.g. the tutorial dungeon."""

    id: content_id("dungeon")
    name: Text
    start: LocalId
    gates: list[LocalId] = []  # defaults to [start]
    rooms: list[RoomSchema] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_structure(self) -> DungeonSchema:
        _unique_ids([r.id for r in self.rooms], "room")
        if problems := self.to_location().problems():
            raise ValueError("; ".join(problems))
        return self

    def to_location(self, location_id: str | None = None) -> Location:
        return Location(
            id=location_id or self.id.partition(".")[2],
            name=self.name,
            kind="Dungeon",
            start=self.start,
            rooms={r.id: r.to_room() for r in self.rooms},
            gates=tuple(self.gates or [self.start]),
        )


class LocationSchema(Schema):
    """A location as snapshotted into a save."""

    id: LocalId
    name: Text
    kind: Text
    start: LocalId
    gates: list[LocalId] = Field(min_length=1)
    rooms: list[RoomSchema] = Field(min_length=1)
    pos: tuple[Unit, Unit] | None = None
    roads: list[LocalId] = []
    region: str = ""
    town: bool = False

    @model_validator(mode="after")
    def _check_structure(self) -> LocationSchema:
        _unique_ids([r.id for r in self.rooms], "room")
        if problems := self.to_location().problems():
            raise ValueError("; ".join(problems))
        return self

    @classmethod
    def from_location(cls, loc: Location) -> LocationSchema:
        return cls(
            id=loc.id,
            name=loc.name,
            kind=loc.kind,
            start=loc.start,
            gates=list(loc.gates),
            rooms=[RoomSchema.from_room(r) for r in loc.rooms.values()],
            pos=loc.pos,
            roads=list(loc.roads),
            region=loc.region,
            town=loc.town,
        )

    def to_location(self) -> Location:
        return Location(
            id=self.id,
            name=self.name,
            kind=self.kind,
            start=self.start,
            rooms={r.id: r.to_room() for r in self.rooms},
            gates=tuple(self.gates),
            pos=self.pos,
            roads=tuple(self.roads),
            region=self.region,
            town=self.town,
        )


class RegionStateSchema(Schema):
    """A world's region as snapshotted into a save."""

    id: content_id("region")
    name: Text
    kind: Text
    tier: int = Field(ge=1)


class OverworldSchema(Schema):
    """A whole world as snapshotted into a save: every location, fully generated."""

    start: LocalId
    locations: list[LocationSchema] = Field(min_length=1)
    regions: list[RegionStateSchema] = []

    @model_validator(mode="after")
    def _check_structure(self) -> OverworldSchema:
        _unique_ids([loc.id for loc in self.locations], "location")
        _unique_ids([r.id for r in self.regions], "region")
        if problems := self.to_overworld().problems():
            raise ValueError("; ".join(problems))
        return self

    @classmethod
    def from_overworld(cls, world: Overworld) -> OverworldSchema:
        return cls(
            start=world.start,
            locations=[LocationSchema.from_location(loc) for loc in world.locations.values()],
            regions=[
                RegionStateSchema(id=r.id, name=r.name, kind=r.kind, tier=r.tier)
                for r in world.regions.values()
            ],
        )

    def to_overworld(self) -> Overworld:
        return Overworld(
            start=self.start,
            locations={loc.id: loc.to_location() for loc in self.locations},
            regions={r.id: Region(r.id, r.name, r.kind, r.tier) for r in self.regions},
        )

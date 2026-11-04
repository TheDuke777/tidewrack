"""Pydantic schemas for content files (CLAUDE.md §3, §9).

Schemas validate data at the boundary, then convert it to the immutable runtime
models the engine uses (e.g. Location), so game code never handles raw dicts.
Unknown keys are rejected so typos in content fail loudly instead of being ignored.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from tidewrack.core.world.location import Exit, Location, Room
from tidewrack.core.world.overworld import Overworld

Text = Annotated[str, StringConstraints(min_length=1)]
Unit = Annotated[float, Field(ge=0.0, le=1.0)]
LocalId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]


def content_id(kind: str) -> type[str]:
    """A stable content ID of the form `<kind>.<snake_case_name>` (§9)."""
    return Annotated[str, StringConstraints(pattern=rf"^{kind}\.[a-z][a-z0-9_]*$")]  # type: ignore[return-value]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


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

    @model_validator(mode="after")
    def _check_size(self) -> RoomsetSchema:
        low, high = self.size
        if not 2 <= low <= high <= 60:
            raise ValueError(f"size must satisfy 2 <= min <= max <= 60, not {list(self.size)}")
        return self


# --- world recipes -------------------------------------------------------------------


class WorldRecipeSchema(Schema):
    """What a new world is made of: how many locations, and which kinds."""

    id: content_id("world")
    name: Text
    locations: int = Field(ge=2, le=40)
    start: content_id("roomset")  # the kind of location every game starts in
    roomsets: dict[content_id("roomset"), Annotated[float, Field(gt=0)]] = Field(min_length=1)


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
        )


class OverworldSchema(Schema):
    """A whole world as snapshotted into a save: every location, fully generated."""

    start: LocalId
    locations: list[LocationSchema] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_structure(self) -> OverworldSchema:
        _unique_ids([loc.id for loc in self.locations], "location")
        if problems := self.to_overworld().problems():
            raise ValueError("; ".join(problems))
        return self

    @classmethod
    def from_overworld(cls, world: Overworld) -> OverworldSchema:
        return cls(
            start=world.start,
            locations=[LocationSchema.from_location(loc) for loc in world.locations.values()],
        )

    def to_overworld(self) -> Overworld:
        return Overworld(
            start=self.start, locations={loc.id: loc.to_location() for loc in self.locations}
        )

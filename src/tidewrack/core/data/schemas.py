"""Pydantic schemas for content files (CLAUDE.md §3, §9).

Schemas validate data at the boundary, then convert it to the immutable runtime
models the engine uses (e.g. DungeonMap), so game code never handles raw dicts.
Unknown keys are rejected so typos in content fail loudly instead of being ignored.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from tidewrack.core.world.dungeon import DungeonMap, Exit, Node

Text = Annotated[str, StringConstraints(min_length=1)]
Unit = Annotated[float, Field(ge=0.0, le=1.0)]
LocalId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]


def content_id(kind: str) -> type[str]:
    """A stable content ID of the form `<kind>.<snake_case_name>` (§9)."""
    return Annotated[str, StringConstraints(pattern=rf"^{kind}\.[a-z][a-z0-9_]*$")]  # type: ignore[return-value]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- roomsets (raw material for generated dungeons) ----------------------------


class ArchetypeSchema(Schema):
    """A kind of room: generated rooms are named "<adjective> <noun>"."""

    noun: Text
    weight: float = Field(default=1.0, gt=0)  # relative chance of being picked
    descriptions: list[Text] = Field(min_length=1)
    features: list[Text] = []
    ambient: list[Text] = []


class RoomsetSchema(Schema):
    id: content_id("roomset")
    name: Text
    dungeon_names: list[Text] = Field(min_length=1)
    adjectives: list[Text] = Field(min_length=1)
    entrance: ArchetypeSchema
    rooms: list[ArchetypeSchema] = Field(min_length=1)


# --- dungeons ----------------------------------------------------------------------


class ExitSchema(Schema):
    label: Text
    to: LocalId


class NodeSchema(Schema):
    id: LocalId
    name: Text
    description: Text
    exits: list[ExitSchema] = Field(min_length=1)
    features: list[Text] = []
    ambient: list[Text] = []
    pos: tuple[Unit, Unit] | None = None  # map position, north up


class DungeonSchema(Schema):
    id: content_id("dungeon")
    name: Text
    start: LocalId
    nodes: list[NodeSchema] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_structure(self) -> DungeonSchema:
        ids = [n.id for n in self.nodes]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate node ids: {', '.join(duplicates)}")
        if problems := self.to_map().problems():
            raise ValueError("; ".join(problems))
        return self

    @classmethod
    def from_map(cls, dungeon: DungeonMap) -> DungeonSchema:
        """The inverse of to_map, used to snapshot a map into a save."""
        return cls(
            id=dungeon.id,
            name=dungeon.name,
            start=dungeon.start,
            nodes=[
                NodeSchema(
                    id=n.id,
                    name=n.name,
                    description=n.description,
                    exits=[ExitSchema(label=e.label, to=e.to) for e in n.exits],
                    features=list(n.features),
                    ambient=list(n.ambient),
                    pos=n.pos,
                )
                for n in dungeon.nodes.values()
            ],
        )

    def to_map(self) -> DungeonMap:
        return DungeonMap(
            id=self.id,
            name=self.name,
            start=self.start,
            nodes={
                n.id: Node(
                    id=n.id,
                    name=n.name,
                    description=n.description,
                    exits=tuple(Exit(e.label, e.to) for e in n.exits),
                    features=tuple(n.features),
                    ambient=tuple(n.ambient),
                    pos=n.pos,
                )
                for n in self.nodes
            },
        )

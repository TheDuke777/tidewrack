"""The saved form of a game, validated with pydantic (CLAUDE.md §6, §9).

A GameState is self-contained: it snapshots the whole world (every location and
room) rather than referring to content by ID, so a later release that edits or removes content can
still load old saves. Versions and slot metadata live in the slot envelope
(services/storage), not here.
"""

from __future__ import annotations

import dataclasses
from functools import cache
from typing import Any

from pydantic import Field, TypeAdapter

from tidewrack.core.data.schemas import OverworldSchema, Schema
from tidewrack.core.engine.components import COMPONENTS


class RngState(Schema):
    seed: int = Field(ge=0)
    s: list[int] = Field(min_length=4, max_length=4)


class EntityState(Schema):
    id: int = Field(ge=1)
    components: dict[str, dict[str, Any]]


class GameState(Schema):
    seed: int
    turn: int = Field(ge=0)
    log: list[str]
    world: OverworldSchema
    rng: RngState
    ambient_rng: RngState
    next_entity_id: int = Field(ge=1)
    entities: list[EntityState]


# --- component codec ---------------------------------------------------------------


def encode_component(component: Any) -> tuple[str, dict[str, Any]]:
    name = type(component).__name__
    if COMPONENTS.get(name) is not type(component):
        raise TypeError(f"{name} is not a registered component")
    return name, _jsonable(dataclasses.asdict(component))


def decode_component(name: str, fields: dict[str, Any]) -> Any:
    component_type = COMPONENTS.get(name)
    if component_type is None:
        raise ValueError(f"unknown component {name!r}")
    expected = {f.name for f in dataclasses.fields(component_type)}
    if set(fields) != expected:
        raise ValueError(f"{name} fields {sorted(fields)} don't match {sorted(expected)}")
    return _adapter(component_type).validate_python(fields)


@cache
def _adapter(component_type: type) -> TypeAdapter:
    return TypeAdapter(component_type)


def _jsonable(value: Any) -> Any:
    """Plain JSON values; sets become sorted lists so save files are deterministic."""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, set | frozenset):
        return sorted(_jsonable(v) for v in value)
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    return value

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

from tidewrack.core.combat.rules import STANDARD
from tidewrack.core.data.schemas import OverworldSchema, Schema
from tidewrack.core.economy.value_model import STANDARD_ECONOMY
from tidewrack.core.engine.components import COMPONENTS


class RngState(Schema):
    seed: int = Field(ge=0)
    s: list[int] = Field(min_length=4, max_length=4)


class RulesState(Schema):
    """The world's combat and recovery rules (core.combat.rules.Rules)."""

    flee_chance: float = Field(default=STANDARD.flee_chance, ge=0, le=1)
    regen_every: int = Field(default=STANDARD.regen_every, ge=1)
    regen_fraction: float = Field(default=STANDARD.regen_fraction, ge=0, le=1)
    regen_amount: int = Field(default=STANDARD.regen_amount, ge=0)
    respawn_hp: float = Field(default=STANDARD.respawn_hp, gt=0, le=1)
    enemy_strength: float = Field(default=STANDARD.enemy_strength, gt=0)
    defend_factor: float = Field(default=STANDARD.defend_factor, ge=0, le=1)
    enemy_return_every: int = Field(default=STANDARD.enemy_return_every, ge=1)
    return_loot_factor: float = Field(default=STANDARD.return_loot_factor, ge=0, le=1)


class EconomyState(Schema):
    """The world's prices and shop timing (core.economy.value_model.EconomyRules)."""

    buy_factor: float = Field(default=STANDARD_ECONOMY.buy_factor, gt=0)
    sell_factor: float = Field(default=STANDARD_ECONOMY.sell_factor, ge=0)
    inn_price: int = Field(default=STANDARD_ECONOMY.inn_price, ge=0)
    restock_every: int = Field(default=STANDARD_ECONOMY.restock_every, ge=1)
    material_markup: float = Field(default=STANDARD_ECONOMY.material_markup, ge=1)
    craft_fee: float = Field(default=STANDARD_ECONOMY.craft_fee, ge=0)
    upgrade_fee: float = Field(default=STANDARD_ECONOMY.upgrade_fee, ge=0)
    buyback: int = Field(default=STANDARD_ECONOMY.buyback, ge=0)
    meal_markup: float = Field(default=STANDARD_ECONOMY.meal_markup, ge=1)
    cook_fee: float = Field(default=STANDARD_ECONOMY.cook_fee, ge=0)


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
    combat_rng: RngState | None = None  # None in saves before combat: derived from seed
    encounter_rng: RngState | None = None
    respawn_rng: RngState | None = None  # None in saves before enemies returned (v7)
    shop_rng: RngState | None = None  # None in saves before shops (v8)
    rules: RulesState = RulesState()
    economy: EconomyState = EconomyState()
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

"""Seeded shops: every town's Smithy, Tavern and so on, stocked at world creation.

A location gets one of each shop its roomset lists (content shops/<name>.json).
Each moves into the first room named for it (a "Tarred Smithy" for the Smithy);
a town that didn't roll such a room gets it at its gate, so every town has one
of each. Room layout and names are untouched, so world_hash never changes.

Stock comes from the seed's "shops" substream, one sub-substream per shop, so
worlds, finds, enemies and quests never shift. Shops sell plain copies: no
affixes, rolls in the lower half of their range. Finds and quest rewards
(highest roll, often an affix) therefore always beat shop gear (§8.6 rule 4).
Each shop also gets `wares`, pre-rolled the same way, that it restocks from
later (core.economy.shops), so play never needs the content files.

Any change to this module's output for a given seed must bump
core.versions.GENERATOR_VERSION (tests/core/test_procgen.py pins golden hashes).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import asdict
from typing import NamedTuple

from tidewrack.core.data.loader import Content
from tidewrack.core.data.schemas import GearSchema, ShopSchema
from tidewrack.core.engine.components import Shop
from tidewrack.core.gear.item import Item
from tidewrack.core.gear.stats import STATS
from tidewrack.core.procgen.gear_gen import make_item
from tidewrack.core.rng import Rng
from tidewrack.core.world.location import Location
from tidewrack.core.world.overworld import Overworld


class PlacedShop(NamedTuple):
    """A shop in a room with its stock; Game takes these as (location, room, shop, stock)."""

    location: str
    room: str
    shop: Shop
    stock: list[Item]


def shop_room(location: Location, noun: str) -> str:
    """The first room named for `noun` ("Tarred Smithy", "Tarred Smithy II"), else the gate."""
    pattern = re.compile(rf"(^|\s){re.escape(noun)}(\s[IVXLC]+)?$")
    for room in location.rooms.values():
        if room.id not in location.gates and pattern.search(room.name):
            return room.id
    return location.start


def shop_copy(rng: Rng, gear: GearSchema, content: Content) -> Item:
    """A plain copy for sale: no affix, each roll in the lower half of its range."""
    roll = {}
    for stat in STATS:
        if stat in gear.rolls:
            low, high = gear.rolls[stat]
            roll[stat] = rng.randint(low, low + (high - low) // 2)
    return make_item(gear, content.gearsets, roll)


def _pick(rng: Rng, schema: ShopSchema, content: Content) -> Item:
    choices = sorted(schema.gear)
    gear = content.gear[rng.weighted_choice(choices, [schema.gear[g] for g in choices])]
    return shop_copy(rng, gear, content)


def generate_shops(seed: int, world: Overworld, content: Content) -> list[PlacedShop]:
    rng = Rng(seed).derive("shops")
    roomsets = {r.name: r for _, r in sorted(content.roomsets.items())}
    placed = []
    for location in world.locations.values():
        roomset = roomsets.get(location.kind)
        if roomset is None:
            continue
        for shop_id in roomset.shops:
            schema = content.shops[shop_id]
            shop_rng = rng.derive(f"shop.{location.id}.{shop_id}")
            stock = []
            if schema.gear:
                stock = [
                    _pick(shop_rng, schema, content) for _ in range(shop_rng.randint(*schema.stock))
                ]
            wares = [_pick(shop_rng, schema, content) for _ in range(schema.wares)]
            shop = Shop(
                shop_id=schema.id,
                name=schema.name,
                buys_gear=schema.buys_gear,
                inn=schema.inn,
                cap=schema.stock[1],
                wares=wares,
            )
            placed.append(PlacedShop(location.id, shop_room(location, schema.room), shop, stock))
    return placed


def shops_hash(shops: Iterable[PlacedShop]) -> str:
    """Stable fingerprint of a world's shops, for golden-seed tests (§9)."""
    blob = json.dumps(
        [
            {
                "location": p.location,
                "room": p.room,
                "shop": asdict(p.shop),
                "stock": [asdict(i) for i in p.stock],
            }
            for p in shops
        ],
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()

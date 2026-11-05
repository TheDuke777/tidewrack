"""Upgrade old slot envelopes to the current schema (CLAUDE.md §9, §10).

When the save format changes: bump core.versions.SCHEMA_VERSION to N, add
``MIGRATIONS[N - 1]`` (a pure function from the version N-1 envelope to version
N), and commit a fixture save of the *old* version under tests/fixtures/saves/
so the migration stays tested forever. Never edit a released migration.

The un-migrated file is not lost: the next autosave rotates it into the slot's
backups before writing the upgraded version.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from tidewrack.core.versions import SCHEMA_VERSION
from tidewrack.services.storage.store import SaveError

Envelope = dict[str, Any]


def _v1_to_v2(envelope: Envelope) -> Envelope:
    # v2 only added optional map positions to dungeon nodes; v1 maps have none.
    return envelope


def _v2_to_v3(envelope: Envelope) -> Envelope:
    # v3 nests rooms inside locations inside a world. An old save's single dungeon
    # becomes a world with one location (and no roads out of it).
    game, location_id = envelope["game"], "loc_00"
    dungeon = game.pop("dungeon")
    game["world"] = {
        "start": location_id,
        "locations": [
            {
                "id": location_id,
                "name": dungeon["name"],
                "kind": "Sea Caves" if dungeon["id"] == "dungeon.generated" else "Dungeon",
                "start": dungeon["start"],
                "gates": [dungeon["start"]],
                "rooms": dungeon["nodes"],
            }
        ],
    }
    for entity in game["entities"]:
        components = entity["components"]
        if "Position" in components:
            components["Position"] = {
                "location": location_id,
                "room": components["Position"]["node"],
            }
        if "Explorer" in components:
            old = components["Explorer"]
            components["Explorer"] = {
                "locations_visited": [location_id],
                "locations_discovered": [location_id],
                "rooms_visited": {location_id: old["visited"]},
                "rooms_discovered": {location_id: old["discovered"]},
            }
    old = envelope["meta"]["summary"]
    envelope["meta"]["summary"] = {
        "location": old["dungeon_name"],
        "room": old["location"],
        "turn": old["turn"],
        "locations_visited": 1,
        "total_locations": 1,
    }
    return envelope


def _v3_to_v4(envelope: Envelope) -> Envelope:
    # v4 adds gear: the player gets base stats (the values new worlds started with
    # in v4, written out here so later content changes can't alter this migration)
    # and carries nothing. Old worlds have no finds; their rooms stay empty.
    for entity in envelope["game"]["entities"]:
        components = entity["components"]
        if "Player" in components:
            components["Stats"] = {"base": {"atk": 2, "def": 1, "hp": 20}}
    return envelope


def _v4_to_v5(envelope: Envelope) -> Envelope:
    # v5 adds combat: the player gets full health, an empty codex and a place to
    # wake after a defeat (the world's start, a town in generated worlds). Old
    # worlds have no enemies or wanderers, and keep the Standard rules and
    # seed-derived combat streams that GameState defaults to.
    game = envelope["game"]
    for entity in game["entities"]:
        components = entity["components"]
        if "Player" in components:
            components["Health"] = {"damage": 0}
            components["Codex"] = {"foes": {}, "kills": {}}
            components["Respawn"] = {"location": game["world"]["start"]}
    return envelope


def _v5_to_v6(envelope: Envelope) -> Envelope:
    # v6 adds quests as new components only (Quest, QuestItem, Clue, Bounty), so
    # older worlds load as they are: they just have no notice-board quests.
    return envelope


MIGRATED_CAP = 6  # the wanderer queue size every world had before v7
MIGRATED_LOOT_CHANCE = 0.25  # a typical kind's loot chance (the save doesn't record it)
MIGRATED_LOOT_PIECES = 3


def _v6_to_v7(envelope: Envelope) -> Envelope:
    # v7 lets wanderers return. Every Spawner gets a cap and templates, built only
    # from enemy snapshots already in the save (never content): the enemies left
    # in locations of the same kind, placed or still queued, bounties excluded.
    # A kind of place with no enemy left anywhere gets no templates and stays clear.
    game = envelope["game"]
    kinds = {loc["id"]: loc["kind"] for loc in game["world"]["locations"]}
    seen: dict[str, list[dict]] = {}  # location kind -> enemy snapshots
    for entity in game["entities"]:
        components = entity["components"]
        if "Enemy" in components and "Position" in components and "Bounty" not in components:
            kind = kinds.get(components["Position"]["location"])
            seen.setdefault(kind, []).append(components["Enemy"])
        if "Spawner" in components:
            kind = kinds.get(components["Spawner"]["location"])
            seen.setdefault(kind, []).extend(components["Spawner"]["queue"])
    for entity in game["entities"]:
        spawner = entity["components"].get("Spawner")
        if spawner is not None:
            spawner["cap"] = MIGRATED_CAP
            spawner["templates"] = _templates(seen.get(kinds.get(spawner["location"]), []))
    return envelope


def _templates(enemies: list[dict]) -> list[dict]:
    by_kind: dict[str, list[dict]] = {}
    for enemy in enemies:
        by_kind.setdefault(enemy["enemy_id"], []).append(enemy)
    templates = []
    for enemy_id, copies in sorted(by_kind.items()):
        first = copies[0]
        loot = [item for e in copies for item in e["loot"]][:MIGRATED_LOOT_PIECES]
        templates.append(
            {
                "enemy_id": enemy_id,
                "name": first["name"],
                "category": first["category"],
                "description": first["description"],
                "stats": dict(first["stats"]),
                "rolls": {},
                "drops": list(first["drops"]),
                "loot_chance": MIGRATED_LOOT_CHANCE if loot else 0.0,
                "loot": loot,
                "weight": float(len(copies)),
            }
        )
    return templates


# What v8 gave every world, written out so later content changes can't alter this
# migration: starting gold, gold carried by each enemy category, quest gold.
MIGRATED_START_GOLD = 10
MIGRATED_ENEMY_GOLD = {"person": [2, 6], "spirit": [0, 2]}  # anything else carries none
MIGRATED_QUEST_GOLD = {"bounty": 16, "cull": 11, "explore": 11, "recover": 13}
MIGRATED_SMITHY_STOCK = 4
MIGRATED_SHOPS = (  # (shop_id, name, room noun, buys gear, inn)
    ("shop.smithy", "Smithy", "Smithy", True, False),
    ("shop.tavern", "Tavern", "Tavern", False, True),
)


def _v7_to_v8(envelope: Envelope) -> Envelope:
    # v8 adds the economy. The player gets starting gold; enemies, templates and
    # quests get gold by category or kind; every town gets a Smithy and a Tavern,
    # in rooms named for them or at the gate. The Smithy stocks plain copies (no
    # affixes or rolls) of gear already in the save (returning enemies' loot),
    # never content, so a world with none has an empty Smithy that still buys.
    game = envelope["game"]
    entities = game["entities"]
    loot: dict[str, dict] = {}
    for entity in entities:
        components = entity["components"]
        if "Player" in components:
            components["Wallet"] = {"gold": MIGRATED_START_GOLD}
        if "Enemy" in components:
            components["Enemy"]["gold"] = _enemy_gold(components["Enemy"])
        if "Quest" in components:
            components["Quest"]["gold"] = MIGRATED_QUEST_GOLD.get(components["Quest"]["kind"], 0)
        if "Spawner" in components:
            for enemy in components["Spawner"]["queue"]:
                enemy["gold"] = _enemy_gold(enemy)
            for template in components["Spawner"]["templates"]:
                template["gold"] = list(MIGRATED_ENEMY_GOLD.get(template["category"], [0, 0]))
                for item in template["loot"]:
                    loot.setdefault(item["gear_id"], item)
    plain = [{**item, "roll": {}, "upgrade": 0, "affixes": []} for _, item in sorted(loot.items())]

    next_id = game["next_entity_id"]
    for location in game["world"]["locations"]:
        if location["kind"] != "Town":
            continue
        for shop_id, name, noun, buys_gear, inn in MIGRATED_SHOPS:
            wares = plain if buys_gear else []
            shop_entity = next_id
            entities.append(
                {
                    "id": shop_entity,
                    "components": {
                        "Shop": {
                            "shop_id": shop_id,
                            "name": name,
                            "buys_gear": buys_gear,
                            "inn": inn,
                            "cap": MIGRATED_SMITHY_STOCK if wares else 0,
                            "wares": [dict(w) for w in wares],
                        },
                        "Position": {
                            "location": location["id"],
                            "room": _room_named(location, noun),
                        },
                    },
                }
            )
            next_id += 1
            for item in wares[:MIGRATED_SMITHY_STOCK]:
                entities.append(
                    {
                        "id": next_id,
                        "components": {"Item": dict(item), "Stocked": {"shop": shop_entity}},
                    }
                )
                next_id += 1
    game["next_entity_id"] = next_id
    return envelope


def _enemy_gold(enemy: dict) -> int:
    low, high = MIGRATED_ENEMY_GOLD.get(enemy["category"], [0, 0])
    return (low + high) // 2


def _room_named(location: dict, noun: str) -> str:
    pattern = re.compile(rf"(^|\s){re.escape(noun)}(\s[IVXLC]+)?$")
    for room in location["rooms"]:
        if room["id"] not in location["gates"] and pattern.search(room["name"]):
            return room["id"]
    return location["start"]


# from-version -> function producing the next version's envelope
MIGRATIONS: dict[int, Callable[[Envelope], Envelope]] = {
    1: _v1_to_v2,
    2: _v2_to_v3,
    3: _v3_to_v4,
    4: _v4_to_v5,
    5: _v5_to_v6,
    6: _v6_to_v7,
    7: _v7_to_v8,
}


class NewerSaveError(SaveError):
    """The save was made by a newer version of the app."""


def migrate(envelope: Envelope) -> Envelope:
    version = envelope.get("schema_version")
    if not isinstance(version, int) or version < 1:
        raise ValueError(f"save has no valid schema_version ({version!r})")
    if version > SCHEMA_VERSION:
        raise NewerSaveError(
            f"This world was saved by a newer version of Tidewrack (save format "
            f"{version}, this app reads up to {SCHEMA_VERSION}). Update the app to open it."
        )
    while version < SCHEMA_VERSION:
        envelope = MIGRATIONS[version](envelope)
        version += 1
        envelope["schema_version"] = version
    return envelope

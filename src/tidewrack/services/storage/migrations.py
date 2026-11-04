"""Upgrade old slot envelopes to the current schema (CLAUDE.md §9, §10).

When the save format changes: bump core.versions.SCHEMA_VERSION to N, add
``MIGRATIONS[N - 1]`` (a pure function from the version N-1 envelope to version
N), and commit a fixture save of the *old* version under tests/fixtures/saves/
so the migration stays tested forever. Never edit a released migration.

The un-migrated file is not lost: the next autosave rotates it into the slot's
backups before writing the upgraded version.
"""

from __future__ import annotations

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


# from-version -> function producing the next version's envelope
MIGRATIONS: dict[int, Callable[[Envelope], Envelope]] = {
    1: _v1_to_v2,
    2: _v2_to_v3,
    3: _v3_to_v4,
    4: _v4_to_v5,
    5: _v5_to_v6,
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

"""Turn content file text into validated runtime content.

Pure: callers pass ``{relative path: file text}`` (see
``tidewrack.services.content`` for reading the bundled files), so this runs the
same on Android, desktop, tests and Pyodide. Every problem in every file is
collected and reported together, each prefixed with its file path.

Layout: ``<kind>/<name>.json``, and each file's ``id`` must be ``<prefix>.<name>``
(e.g. ``dungeons/first_descent.json`` holds ``dungeon.first_descent``), which
keeps IDs unique and files easy to find.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import ValidationError

from tidewrack.core.data.schemas import (
    AffixSchema,
    DungeonSchema,
    EnemySchema,
    GearSchema,
    GearSetSchema,
    RoomsetSchema,
    WorldRecipeSchema,
)
from tidewrack.core.world.location import Location

# kind directory -> (schema, id prefix)
KINDS = {
    "affixes": (AffixSchema, "affix"),
    "dungeons": (DungeonSchema, "dungeon"),
    "enemies": (EnemySchema, "enemy"),
    "gear": (GearSchema, "gear"),
    "gearsets": (GearSetSchema, "gearset"),
    "roomsets": (RoomsetSchema, "roomset"),
    "worlds": (WorldRecipeSchema, "world"),
}


class ContentError(Exception):
    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__(f"{len(problems)} content problem(s):\n" + "\n".join(problems))


@dataclass(frozen=True)
class Content:
    dungeons: dict[str, Location]
    roomsets: dict[str, RoomsetSchema]
    worlds: dict[str, WorldRecipeSchema]
    gear: dict[str, GearSchema]
    affixes: dict[str, AffixSchema]
    gearsets: dict[str, GearSetSchema]
    enemies: dict[str, EnemySchema]
    content_hash: str  # identifies this exact content set (saves/sharing, §6 & §9)

    def dungeon(self, dungeon_id: str) -> Location:
        return self.dungeons[dungeon_id]

    def roomset(self, roomset_id: str) -> RoomsetSchema:
        return self.roomsets[roomset_id]

    def world(self, world_id: str) -> WorldRecipeSchema:
        return self.worlds[world_id]


def load_content(files: Mapping[str, str]) -> Content:
    problems: list[str] = []
    loaded: dict[str, dict] = {kind: {} for kind in KINDS}

    for path in sorted(files):
        kind, _, filename = path.partition("/")
        if "/" in filename or not filename.endswith(".json"):
            problems.append(f"{path}: unexpected file; content files are <kind>/<name>.json")
            continue
        if kind not in KINDS:
            problems.append(f"{path}: unknown content kind {kind!r}")
            continue
        schema, prefix = KINDS[kind]

        try:
            data = json.loads(files[path])
        except json.JSONDecodeError as e:
            problems.append(f"{path}: invalid JSON: {e}")
            continue
        try:
            model = schema.model_validate(data)
        except ValidationError as e:
            problems += [f"{path}: {_location(err['loc'])}{err['msg']}" for err in e.errors()]
            continue

        expected_id = f"{prefix}.{filename.removesuffix('.json')}"
        if model.id != expected_id:
            problems.append(f"{path}: id is {model.id!r} but this file must hold {expected_id!r}")
            continue
        loaded[kind][model.id] = model

    problems += _broken_references(loaded)
    if problems:
        raise ContentError(problems)
    return Content(
        dungeons={i: m.to_location() for i, m in loaded["dungeons"].items()},
        roomsets=loaded["roomsets"],
        worlds=loaded["worlds"],
        gear=loaded["gear"],
        affixes=loaded["affixes"],
        gearsets=loaded["gearsets"],
        enemies=loaded["enemies"],
        content_hash=content_hash(files),
    )


def _broken_references(loaded: dict[str, dict]) -> list[str]:
    """IDs one content file uses that no file defines."""
    problems = []

    def check(path: str, ids, kind: str, what: str) -> None:
        problems.extend(f"{path}: unknown {what} {i!r}" for i in ids if i not in loaded[kind])

    for recipe in loaded["worlds"].values():
        path = _path("worlds", recipe.id)
        check(path, [recipe.start, *recipe.roomsets], "roomsets", "roomset")
        check(path, recipe.kit, "gear", "gear")
        slots = [s for g in recipe.kit if g in loaded["gear"] for s in _slots(loaded["gear"][g])]
        if len(slots) != len(set(slots)):
            problems.append(f"{path}: kit has more than one item for a slot")
    names: dict[str, str] = {}
    for roomset in loaded["roomsets"].values():
        path = _path("roomsets", roomset.id)
        check(path, roomset.finds.gear, "gear", "gear")
        if roomset.finds.chance and not roomset.finds.gear:
            problems.append(f"{path}: finds.chance is set but finds.gear is empty")
        check(path, roomset.enemies.pool, "enemies", "enemy")
        encounters = roomset.enemies
        if (encounters.placed_chance or encounters.wandering_chance) and not encounters.pool:
            problems.append(f"{path}: enemies has chances set but an empty pool")
        # Finds map a location's kind (the roomset's name) back to its roomset.
        if roomset.name in names:
            problems.append(f"{path}: name {roomset.name!r} is also used by {names[roomset.name]}")
        names.setdefault(roomset.name, roomset.id)
    for enemy in loaded["enemies"].values():
        check(_path("enemies", enemy.id), enemy.loot.gear, "gear", "gear")
    for gear in loaded["gear"].values():
        if gear.set is not None:
            check(_path("gear", gear.id), [gear.set], "gearsets", "gear set")
    return problems


def _path(kind: str, content_id: str) -> str:
    return f"{kind}/{content_id.partition('.')[2]}.json"


def _slots(gear: GearSchema) -> tuple[str, ...]:
    return ("main_hand", "off_hand") if gear.two_handed else (gear.slot,)


def content_hash(files: Mapping[str, str]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(files[path].encode())
        digest.update(b"\0")
    return digest.hexdigest()


def _location(loc: tuple) -> str:
    return ".".join(str(part) for part in loc) + ": " if loc else ""

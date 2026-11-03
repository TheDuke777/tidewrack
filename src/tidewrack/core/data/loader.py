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

from tidewrack.core.data.schemas import DungeonSchema
from tidewrack.core.world.dungeon import DungeonMap

# kind directory -> (schema, id prefix)
KINDS = {
    "dungeons": (DungeonSchema, "dungeon"),
}


class ContentError(Exception):
    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__(f"{len(problems)} content problem(s):\n" + "\n".join(problems))


@dataclass(frozen=True)
class Content:
    dungeons: dict[str, DungeonMap]
    content_hash: str  # identifies this exact content set (saves/sharing, §6 & §9)

    def dungeon(self, dungeon_id: str) -> DungeonMap:
        return self.dungeons[dungeon_id]


def load_content(files: Mapping[str, str]) -> Content:
    problems: list[str] = []
    dungeons: dict[str, DungeonMap] = {}

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
        dungeons[model.id] = model.to_map()

    if problems:
        raise ContentError(problems)
    return Content(dungeons=dungeons, content_hash=content_hash(files))


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

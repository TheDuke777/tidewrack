from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

SLOT_FORMAT = "tidewrack.slot"
BACKUPS_KEPT = 3


def data_dir() -> Path:
    """The app's private data dir on a device (and under `flet run`), or a
    per-user dev folder when run as a plain script."""
    data = os.environ.get("FLET_APP_STORAGE_DATA")
    return Path(data) if data else Path.home() / ".local" / "share" / "tidewrack"


def saves_dir() -> Path:
    """Where slots live."""
    return data_dir() / "saves"


class SaveError(Exception):
    pass


# --- metadata ----------------------------------------------------------------------


class SlotSummary(BaseModel):
    """What the slot picker shows without loading the game."""

    model_config = ConfigDict(frozen=True)

    location: str  # the location's name
    room: str
    turn: int
    locations_visited: int
    total_locations: int


class SlotMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    slot_id: str
    name: str
    created_at: str  # ISO 8601, UTC
    updated_at: str
    revision: int  # +1 on every save; the basis for cloud sync later (§6)
    summary: SlotSummary


@dataclass(frozen=True)
class SlotListing:
    meta: SlotMeta
    from_backup: bool  # main file was unreadable; this came from a backup


@dataclass(frozen=True)
class LoadedSlot:
    envelope: dict[str, Any]
    from_backup: bool


class SaveStore(Protocol):
    def list_slots(self) -> list[SlotListing]: ...
    def load(self, slot_id: str) -> LoadedSlot: ...
    def save(
        self, slot_id: str, envelope: dict[str, Any], changed: Collection[int] | None = None
    ) -> None:
        """Write a slot. `changed` names the entities that may differ from this
        store's last save of the slot (None: unknown, so everything is written)."""
        ...

    def delete(self, slot_id: str) -> None: ...


def _listing_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """The envelope upgraded to the current format, so old slots list correctly.
    A slot from a newer app is listed as-is if possible; opening it explains."""
    from tidewrack.services.storage.migrations import NewerSaveError, migrate  # circular

    try:
        return migrate(copy.deepcopy(envelope))
    except NewerSaveError:
        return envelope


# --- splitting a slot into parts ------------------------------------------------------
#
# A slot is saved as a small main file plus one part file per place (its entities)
# and one for the world map, so an autosave only rewrites the places that changed
# (CLAUDE.md §6). Parts are named by a hash of their bytes and never rewritten in
# place: the main file lists the parts it was saved with, and replacing it is the
# moment a save happens, so a kill mid-save leaves the previous save whole.

MAIN = "main"
WORLD = "world"


def _parts_of(entities: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]] | None:
    """Entities grouped by place: what's at a place (Position), its wanderers and
    regrowth (Spawner/Grower) and its shops' stock; the player and anything else
    in the main file. None if the entities don't look like a current save."""
    where: dict[int, str] = {}
    last = 0
    for entity in entities:
        entity_id, components = entity.get("id"), entity.get("components")
        if not isinstance(entity_id, int) or entity_id <= last or not isinstance(components, dict):
            return None  # loading sorts by id, so ids must already be in order
        last = entity_id
        where[entity_id] = _place_of(components)
    parts: dict[str, list[dict[str, Any]]] = {MAIN: []}
    for entity in entities:
        place = where[entity["id"]]
        stocked = entity["components"].get("Stocked")
        if place == MAIN and isinstance(stocked, dict):
            place = where.get(stocked.get("shop"), MAIN)  # type: ignore[arg-type]
        parts.setdefault(place, []).append(entity)
    return parts


def _place_of(components: dict[str, Any]) -> str:
    if "Player" in components:
        return MAIN
    for name, key in (("Position", "location"), ("Spawner", "location"), ("Grower", "location")):
        fields = components.get(name)
        if isinstance(fields, dict) and isinstance(fields.get(key), str):
            return f"at:{fields[key]}"
    return MAIN


def _pack(value: Any) -> bytes:
    return gzip.compress(json.dumps(value, sort_keys=True, separators=(",", ":")).encode(), mtime=0)


def _unpack(data: bytes) -> Any:
    return json.loads(gzip.decompress(data))


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# --- file backend ------------------------------------------------------------------


class FileSaveStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.backups = root / "backups"
        # Per slot, what this store last wrote: each part's file name and the ids
        # in it. Lets a save skip parts whose entities didn't change.
        self._written: dict[str, dict[str, tuple[str, frozenset[int]]]] = {}

    def _path(self, slot_id: str) -> Path:
        if not slot_id.isalnum():
            raise ValueError(f"invalid slot id {slot_id!r}")
        return self.root / f"slot_{slot_id}.json.gz"

    def _parts_dir(self, slot_id: str) -> Path:
        return self.root / f"slot_{slot_id}.parts"

    def _backup_paths(self, slot_id: str) -> list[Path]:
        """Newest first."""
        return sorted(self.backups.glob(f"slot_{slot_id}.r*.json.gz"), reverse=True)

    # --- reading -------------------------------------------------------------------

    def list_slots(self) -> list[SlotListing]:
        listings = []
        for path in self.root.glob("slot_*.json.gz"):
            slot_id = path.name.removeprefix("slot_").removesuffix(".json.gz")
            try:
                loaded = self.load(slot_id)
                meta = SlotMeta.model_validate(_listing_envelope(loaded.envelope)["meta"])
            except (SaveError, KeyError, TypeError, ValueError, ValidationError):
                continue  # unreadable everywhere; nothing to show
            listings.append(SlotListing(meta, loaded.from_backup))
        return sorted(listings, key=lambda s: s.meta.updated_at, reverse=True)

    def load(self, slot_id: str) -> LoadedSlot:
        for i, path in enumerate([self._path(slot_id), *self._backup_paths(slot_id)]):
            try:
                envelope = self._assemble(slot_id, _unpack(path.read_bytes()))
            except (OSError, EOFError, gzip.BadGzipFile, json.JSONDecodeError, UnicodeError):
                continue
            except (KeyError, TypeError, AttributeError):
                continue  # a part list that doesn't make sense
            if isinstance(envelope, dict) and envelope.get("format") == SLOT_FORMAT:
                return LoadedSlot(envelope, from_backup=i > 0)
        raise SaveError(f"save {slot_id} is unreadable and has no usable backup")

    def _assemble(self, slot_id: str, envelope: Any) -> Any:
        """A split main file put back together with its parts (others as they are)."""
        if not isinstance(envelope, dict) or "parts" not in envelope:
            return envelope
        names: dict[str, str] = envelope.pop("parts")
        folder = self._parts_dir(slot_id)
        game = envelope["game"]
        entities = list(game["entities"])
        for key, name in names.items():
            value = _unpack((folder / _part_file(name)).read_bytes())
            if key == WORLD:
                game["world"] = value
            else:
                entities.extend(value)
        game["entities"] = sorted(entities, key=lambda e: e["id"])
        return envelope

    # --- writing -------------------------------------------------------------------

    def save(
        self, slot_id: str, envelope: dict[str, Any], changed: Collection[int] | None = None
    ) -> None:
        path = self._path(slot_id)
        self.root.mkdir(parents=True, exist_ok=True)
        game = envelope.get("game")
        parts = None
        if isinstance(game, dict) and isinstance(game.get("entities"), list) and "world" in game:
            parts = _parts_of(game["entities"])
        if parts is None:  # not a current save (old or odd): one whole file
            main, written = envelope, {}
        else:
            main, written = self._write_parts(slot_id, envelope, game, parts, changed)
        data = _pack(main)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            self._back_up(slot_id, path)
        os.replace(tmp, path)
        self._written[slot_id] = written
        self._collect(slot_id, {name for name, _ in written.values()})

    def _write_parts(
        self,
        slot_id: str,
        envelope: dict[str, Any],
        game: dict[str, Any],
        parts: dict[str, list[dict[str, Any]]],
        changed: Collection[int] | None,
    ) -> tuple[dict[str, Any], dict[str, tuple[str, frozenset[int]]]]:
        folder = self._parts_dir(slot_id)
        folder.mkdir(exist_ok=True)
        before = self._written.get(slot_id, {}) if changed is not None else {}
        changed = set(changed or ())
        written: dict[str, tuple[str, frozenset[int]]] = {}
        contents: dict[str, Any] = {WORLD: game["world"]}
        contents.update((k, v) for k, v in parts.items() if k != MAIN)
        for key, value in contents.items():
            ids = frozenset(e["id"] for e in value) if key != WORLD else frozenset()
            old = before.get(key)
            same = old is not None and old[1] == ids and not ids & changed
            if same and (folder / _part_file(old[0])).exists():  # type: ignore[index]
                written[key] = old  # type: ignore[assignment]  # same entities, none changed: the file still holds them
                continue
            data = _pack(value)
            name = hashlib.sha256(data).hexdigest()[:32]
            target = folder / _part_file(name)
            if not target.exists():
                _write_atomic(target, data)
            written[key] = (name, ids)
        main = {k: v for k, v in envelope.items() if k != "game"}
        main["game"] = {k: v for k, v in game.items() if k != "world"}
        main["game"]["entities"] = parts[MAIN]
        main["parts"] = {key: name for key, (name, _) in sorted(written.items())}
        return main, written

    def _collect(self, slot_id: str, keep: set[str]) -> None:
        """Delete part files neither the main file nor a backup uses."""
        folder = self._parts_dir(slot_id)
        if not folder.exists():
            return
        for backup in self._backup_paths(slot_id):
            try:
                keep.update(_unpack(backup.read_bytes()).get("parts", {}).values())
            except (OSError, EOFError, gzip.BadGzipFile, json.JSONDecodeError, UnicodeError):
                continue
            except AttributeError:
                continue
        for part in folder.glob("*.json.gz"):
            if part.name.removesuffix(".json.gz") not in keep:
                part.unlink(missing_ok=True)

    def _back_up(self, slot_id: str, path: Path) -> None:
        self.backups.mkdir(exist_ok=True)
        existing = self._backup_paths(slot_id)
        number = int(existing[0].name.split(".r")[1].split(".")[0]) + 1 if existing else 1
        # Copy, not move: the main file must exist at every instant, or a kill here
        # would make the slot vanish from the list.
        (self.backups / f"slot_{slot_id}.r{number:08d}.json.gz").write_bytes(path.read_bytes())
        for old in self._backup_paths(slot_id)[BACKUPS_KEPT:]:
            old.unlink()

    def delete(self, slot_id: str) -> None:
        for path in [self._path(slot_id), *self._backup_paths(slot_id)]:
            path.unlink(missing_ok=True)
        folder = self._parts_dir(slot_id)
        if folder.exists():
            for part in folder.iterdir():
                part.unlink()
            folder.rmdir()
        self._written.pop(slot_id, None)


def _part_file(name: str) -> str:
    if not name.isalnum():
        raise KeyError(f"invalid part name {name!r}")
    return f"{name}.json.gz"

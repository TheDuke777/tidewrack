from __future__ import annotations

import gzip
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

SLOT_FORMAT = "tidewrack.slot"
BACKUPS_KEPT = 3


def saves_dir() -> Path:
    """Where slots live: the app's private data dir on a device (and under
    `flet run`), or a per-user dev folder when run as a plain script."""
    data = os.environ.get("FLET_APP_STORAGE_DATA")
    base = Path(data) if data else Path.home() / ".local" / "share" / "tidewrack"
    return base / "saves"


class SaveError(Exception):
    pass


# --- metadata ----------------------------------------------------------------------


class SlotSummary(BaseModel):
    """What the slot picker shows without loading the game."""

    model_config = ConfigDict(frozen=True)

    dungeon_name: str
    location: str
    turn: int
    visited: int
    total_nodes: int


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
    def save(self, slot_id: str, envelope: dict[str, Any]) -> None: ...
    def delete(self, slot_id: str) -> None: ...


# --- file backend ------------------------------------------------------------------


class FileSaveStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.backups = root / "backups"

    def _path(self, slot_id: str) -> Path:
        if not slot_id.isalnum():
            raise ValueError(f"invalid slot id {slot_id!r}")
        return self.root / f"slot_{slot_id}.json.gz"

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
                meta = SlotMeta.model_validate(loaded.envelope["meta"])
            except (SaveError, KeyError, ValidationError):
                continue  # unreadable everywhere; nothing to show
            listings.append(SlotListing(meta, loaded.from_backup))
        return sorted(listings, key=lambda s: s.meta.updated_at, reverse=True)

    def load(self, slot_id: str) -> LoadedSlot:
        for i, path in enumerate([self._path(slot_id), *self._backup_paths(slot_id)]):
            try:
                envelope = json.loads(gzip.decompress(path.read_bytes()))
            except (OSError, EOFError, gzip.BadGzipFile, json.JSONDecodeError, UnicodeError):
                continue
            if isinstance(envelope, dict) and envelope.get("format") == SLOT_FORMAT:
                return LoadedSlot(envelope, from_backup=i > 0)
        raise SaveError(f"save {slot_id} is unreadable and has no usable backup")

    # --- writing -------------------------------------------------------------------

    def save(self, slot_id: str, envelope: dict[str, Any]) -> None:
        path = self._path(slot_id)
        self.root.mkdir(parents=True, exist_ok=True)
        data = gzip.compress(
            json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode(), mtime=0
        )
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            self._back_up(slot_id, path)
        os.replace(tmp, path)

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

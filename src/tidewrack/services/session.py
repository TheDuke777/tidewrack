"""A game bound to a save slot, autosaving after every action (CLAUDE.md §6).

Mobile apps get killed without warning, so there's no "save on exit": every
command that produced events is written straight away.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from tidewrack.core.data.loader import Content
from tidewrack.core.data.save import GameState
from tidewrack.core.engine.game import Command, Game, TurnResult
from tidewrack.core.versions import GENERATOR_VERSION, SCHEMA_VERSION
from tidewrack.services.storage import SaveError, SaveStore, SlotMeta, SlotSummary
from tidewrack.services.storage.migrations import migrate
from tidewrack.services.storage.store import SLOT_FORMAT

Clock = Callable[[], str]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class GameSession:
    def __init__(
        self,
        store: SaveStore,
        meta: SlotMeta,
        game: Game,
        content_version: str,
        clock: Clock = utc_now,
        from_backup: bool = False,
    ) -> None:
        self.store = store
        self.meta = meta
        self.game = game
        self.content_version = content_version
        self.clock = clock
        self.from_backup = from_backup

    # --- creating and opening ----------------------------------------------------

    @classmethod
    def new(
        cls,
        store: SaveStore,
        content: Content,
        dungeon_id: str,
        name: str,
        seed: int,
        clock: Clock = utc_now,
    ) -> GameSession:
        game = Game(seed, content.dungeon(dungeon_id))
        now = clock()
        meta = SlotMeta(
            slot_id=uuid.uuid4().hex,
            name=name,
            created_at=now,
            updated_at=now,
            revision=0,
            summary=_summary(game),
        )
        session = cls(store, meta, game, content.content_hash, clock)
        session.save()
        return session

    @classmethod
    def open(
        cls, store: SaveStore, slot_id: str, content: Content, clock: Clock = utc_now
    ) -> GameSession:
        """Load a slot. Raises SaveError (or NewerSaveError) with a readable message."""
        loaded = store.load(slot_id)
        try:
            envelope = migrate(loaded.envelope)
            meta = SlotMeta.model_validate(envelope["meta"])
            game = Game.from_state(GameState.model_validate(envelope["game"]))
        except (KeyError, ValueError, ValidationError, LookupError) as e:
            raise SaveError(f"save {slot_id} is damaged: {e}") from e
        return cls(store, meta, game, content.content_hash, clock, loaded.from_backup)

    # --- playing -----------------------------------------------------------------

    def perform(self, command: Command) -> TurnResult:
        result = self.game.perform(command)
        if result.events:
            self.save()
        return result

    def save(self) -> None:
        self.meta = self.meta.model_copy(
            update={
                "updated_at": self.clock(),
                "revision": self.meta.revision + 1,
                "summary": _summary(self.game),
            }
        )
        self.store.save(self.meta.slot_id, self._envelope())

    def _envelope(self) -> dict[str, Any]:
        return {
            "format": SLOT_FORMAT,
            "schema_version": SCHEMA_VERSION,
            "generator_version": GENERATOR_VERSION,
            "content_version": self.content_version,
            "meta": self.meta.model_dump(mode="json"),
            "game": self.game.to_state().model_dump(mode="json"),
        }


def _summary(game: Game) -> SlotSummary:
    view = game.view()
    return SlotSummary(
        dungeon_name=view.dungeon_name,
        location=view.location,
        turn=view.turn,
        visited=view.visited,
        total_nodes=view.total_nodes,
    )


def next_world_name(existing: list[str]) -> str:
    """ "World N" with N one above the highest existing number."""
    numbers = [int(m.group(1)) for n in existing if (m := re.fullmatch(r"World (\d+)", n))]
    return f"World {max(numbers, default=0) + 1}"

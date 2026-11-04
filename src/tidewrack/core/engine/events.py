"""Typed events and the bus every cross-cutting feature subscribes to (CLAUDE.md §4).

Emitting only queues an event; :meth:`EventBus.flush` delivers queued events in
FIFO order, including any that handlers emit while it runs. Handlers therefore
never re-enter each other, and delivery order is deterministic: by emission, then
by subscription order. Subscribing to a base class receives its subclasses too
(``Event`` receives everything).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

E = TypeVar("E", bound="Event")


@dataclass(frozen=True)
class Event:
    """Base class for all engine events."""


# --- lifecycle -------------------------------------------------------------------


@dataclass(frozen=True)
class GameStarted(Event):
    seed: int


@dataclass(frozen=True)
class TurnEnded(Event):
    turn: int


# --- travel ----------------------------------------------------------------------


@dataclass(frozen=True)
class LocationEntered(Event):
    entity: int
    location: str
    from_location: str | None  # None when placed at the start
    first_visit: bool


@dataclass(frozen=True)
class LocationDiscovered(Event):
    """A location became known (one road from somewhere visited)."""

    location: str


# --- exploration -----------------------------------------------------------------


@dataclass(frozen=True)
class RoomEntered(Event):
    entity: int
    location: str
    room: str
    from_room: str | None  # None on arriving in the location
    first_visit: bool
    fleeing: bool = False  # running from a fight: no wandering enemy finds you here


@dataclass(frozen=True)
class RoomDiscovered(Event):
    """A room became known (seen as an exit), before the player visits it."""

    location: str
    room: str


@dataclass(frozen=True)
class LookedAround(Event):
    location: str
    room: str


@dataclass(frozen=True)
class Waited(Event):
    location: str
    room: str


@dataclass(frozen=True)
class AmbientNoticed(Event):
    location: str
    room: str
    text: str


# --- gear --------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemTaken(Event):
    entity: int
    item: int
    gear_id: str
    name: str


@dataclass(frozen=True)
class ItemDropped(Event):
    entity: int
    item: int
    gear_id: str
    name: str


@dataclass(frozen=True)
class ItemEquipped(Event):
    entity: int
    item: int
    gear_id: str
    name: str
    replaced: tuple[str, ...]  # names of the items it took the place of


@dataclass(frozen=True)
class ItemUnequipped(Event):
    entity: int
    item: int
    gear_id: str
    name: str


# --- combat ------------------------------------------------------------------------


@dataclass(frozen=True)
class CombatStarted(Event):
    enemy: int
    enemy_id: str
    name: str
    wandering: bool  # it came across you, rather than waiting in the room


@dataclass(frozen=True)
class Attacked(Event):
    attacker: int
    target: int
    attacker_name: str
    target_name: str
    damage: int
    defended: bool  # the target was defending


@dataclass(frozen=True)
class Fled(Event):
    enemy: int
    name: str


@dataclass(frozen=True)
class FleeFailed(Event):
    enemy: int
    name: str


@dataclass(frozen=True)
class EnemyKilled(Event):
    enemy: int
    enemy_id: str
    name: str
    category: str
    loot: tuple[str, ...]  # names of what it dropped


@dataclass(frozen=True)
class PlayerDefeated(Event):
    enemy_id: str
    name: str


@dataclass(frozen=True)
class Respawned(Event):
    location: str


@dataclass(frozen=True)
class Rested(Event):
    location: str


@dataclass(frozen=True)
class ActionRejected(Event):
    reason: str


# --- bus ---------------------------------------------------------------------------


Handler = Callable[[Event], None]

MAX_EVENTS_PER_FLUSH = 10_000  # guards against handlers emitting in a loop


class EventBus:
    def __init__(self) -> None:
        self._subscriptions: list[tuple[type[Event], Handler]] = []
        self._queue: deque[Event] = deque()

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> Callable[[], None]:
        """Register `handler`; returns a function that unsubscribes it."""
        entry = (event_type, handler)
        self._subscriptions.append(entry)  # type: ignore[arg-type]
        return lambda: self._subscriptions.remove(entry)  # type: ignore[arg-type]

    def emit(self, event: Event) -> None:
        self._queue.append(event)

    def flush(self) -> list[Event]:
        """Deliver queued events (and any emitted meanwhile); returns them in order."""
        delivered: list[Event] = []
        while self._queue:
            if len(delivered) >= MAX_EVENTS_PER_FLUSH:
                raise RuntimeError("event flush limit hit; a handler is likely looping")
            event = self._queue.popleft()
            delivered.append(event)
            for event_type, handler in list(self._subscriptions):
                if isinstance(event, event_type):
                    handler(event)
        return delivered

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
    dungeon_id: str


@dataclass(frozen=True)
class TurnEnded(Event):
    turn: int


# --- exploration -----------------------------------------------------------------


@dataclass(frozen=True)
class NodeEntered(Event):
    entity: int
    node_id: str
    from_node: str | None  # None when placed at the start
    first_visit: bool


@dataclass(frozen=True)
class NodeDiscovered(Event):
    """A node became known (seen as an exit), before the player visits it."""

    node_id: str


@dataclass(frozen=True)
class LookedAround(Event):
    node_id: str


@dataclass(frozen=True)
class Waited(Event):
    node_id: str


@dataclass(frozen=True)
class AmbientNoticed(Event):
    node_id: str
    text: str


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

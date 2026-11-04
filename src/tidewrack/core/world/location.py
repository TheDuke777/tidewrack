"""A location (town, forest, mine, dungeon…): rooms joined by labelled exits.

Locations are the nodes of the overworld (see overworld.py); rooms are the nodes
of a location's own point-crawl map, where events happen. The player leaves a
location only from one of its gate rooms. Maps are immutable; what the player
knows of them lives in the Explorer component.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Exit:
    label: str  # what the player picks, e.g. "Climb the rope ladder"
    to: str  # destination room id


@dataclass(frozen=True)
class Room:
    id: str
    name: str
    description: str
    exits: tuple[Exit, ...]
    features: tuple[str, ...] = ()  # scenery described by Look
    ambient: tuple[str, ...] = ()  # flavour lines that may play on entering
    pos: tuple[float, float] | None = None  # map position, x/y in 0..1, north up


@dataclass(frozen=True)
class Location:
    id: str
    name: str
    kind: str  # shown to the player: "Town", "Sea Caves", …
    start: str  # the room travellers arrive in
    rooms: dict[str, Room]
    gates: tuple[str, ...]  # rooms the player can travel onward from
    pos: tuple[float, float] | None = None  # overworld map position
    roads: tuple[str, ...] = ()  # neighbouring location ids, in travel-list order

    def room(self, room_id: str) -> Room:
        return self.rooms[room_id]

    def exit(self, room_id: str, label: str) -> Exit | None:
        return next((e for e in self.rooms[room_id].exits if e.label == label), None)

    @property
    def has_map(self) -> bool:
        return all(r.pos is not None for r in self.rooms.values())

    def neighbours(self, room_id: str) -> list[str]:
        return [e.to for e in self.rooms[room_id].exits]

    def problems(self) -> list[str]:
        """Structural errors: dangling exits, duplicate labels, unreachable rooms."""
        found = []
        if self.start not in self.rooms:
            return [f"start room {self.start!r} does not exist"]
        if not self.gates:
            found.append("a location needs at least one gate room")
        found += [f"gate {g!r} is not a room" for g in self.gates if g not in self.rooms]
        for room in self.rooms.values():
            labels = [e.label for e in room.exits]
            if len(labels) != len(set(labels)):
                found.append(f"{room.id}: duplicate exit labels")
            if not room.exits and len(self.rooms) > 1:
                found.append(f"{room.id}: dead end with no exits")
            found += [
                f"{room.id}: exit {e.label!r} leads to unknown room {e.to!r}"
                for e in room.exits
                if e.to not in self.rooms
            ]
        positioned = [r.pos is not None for r in self.rooms.values()]
        if any(positioned) and not all(positioned):
            found.append("map positions must be given for every room or none")
        if not found:
            found += [f"{r}: unreachable from start" for r in self.rooms if r not in self._reach()]
        return found

    def _reach(self) -> set[str]:
        seen, todo = {self.start}, deque([self.start])
        while todo:
            for nxt in self.neighbours(todo.popleft()):
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        return seen

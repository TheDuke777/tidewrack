"""Point-crawl dungeon map: nodes joined by labelled exits.

Hand-authored maps (validated from content files by core.data.schemas) and, from
step 4, generated ones share this model. Maps are immutable; what the player
knows of one lives in the Explorer component.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Exit:
    label: str  # what the player picks, e.g. "Climb the rope ladder"
    to: str  # destination node id


@dataclass(frozen=True)
class Node:
    id: str
    name: str
    description: str
    exits: tuple[Exit, ...]
    features: tuple[str, ...] = ()  # scenery described by Look
    ambient: tuple[str, ...] = ()  # flavour lines that may play on entering
    pos: tuple[float, float] | None = None  # map position, x/y in 0..1, north up


@dataclass(frozen=True)
class DungeonMap:
    id: str
    name: str
    start: str
    nodes: dict[str, Node]

    def node(self, node_id: str) -> Node:
        return self.nodes[node_id]

    def exit(self, node_id: str, label: str) -> Exit | None:
        return next((e for e in self.nodes[node_id].exits if e.label == label), None)

    @property
    def has_map(self) -> bool:
        return all(n.pos is not None for n in self.nodes.values())

    def neighbours(self, node_id: str) -> list[str]:
        return [e.to for e in self.nodes[node_id].exits]

    def problems(self) -> list[str]:
        """Structural errors: dangling exits, duplicate labels, unreachable nodes."""
        found = []
        if self.start not in self.nodes:
            return [f"start node {self.start!r} does not exist"]
        for node in self.nodes.values():
            labels = [e.label for e in node.exits]
            if len(labels) != len(set(labels)):
                found.append(f"{node.id}: duplicate exit labels")
            if not node.exits:
                found.append(f"{node.id}: dead end with no exits")
            found += [
                f"{node.id}: exit {e.label!r} leads to unknown node {e.to!r}"
                for e in node.exits
                if e.to not in self.nodes
            ]
        positioned = [n.pos is not None for n in self.nodes.values()]
        if any(positioned) and not all(positioned):
            found.append("map positions must be given for every node or none")
        if not found:
            seen, todo = {self.start}, deque([self.start])
            while todo:
                for nxt in self.neighbours(todo.popleft()):
                    if nxt not in seen:
                        seen.add(nxt)
                        todo.append(nxt)
            found += [f"{n}: unreachable from start" for n in self.nodes if n not in seen]
        return found

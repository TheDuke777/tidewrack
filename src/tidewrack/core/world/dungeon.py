"""Point-crawl dungeon map: nodes joined by labelled exits.

Hand-authored maps and (from step 4) generated ones share this model. Maps are
immutable; what the player knows of one lives in the Explorer component.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any


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
        if not found:
            seen, todo = {self.start}, deque([self.start])
            while todo:
                for nxt in self.neighbours(todo.popleft()):
                    if nxt not in seen:
                        seen.add(nxt)
                        todo.append(nxt)
            found += [f"{n}: unreachable from start" for n in self.nodes if n not in seen]
        return found

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DungeonMap:
        """Build from plain data (the shape content files will use from step 2)."""
        nodes = {}
        for raw in data["nodes"]:
            nodes[raw["id"]] = Node(
                id=raw["id"],
                name=raw["name"],
                description=raw["description"],
                exits=tuple(Exit(e["label"], e["to"]) for e in raw["exits"]),
                features=tuple(raw.get("features", ())),
                ambient=tuple(raw.get("ambient", ())),
            )
        dungeon = cls(id=data["id"], name=data["name"], start=data["start"], nodes=nodes)
        if problems := dungeon.problems():
            raise ValueError(f"invalid dungeon {data['id']!r}: " + "; ".join(problems))
        return dungeon

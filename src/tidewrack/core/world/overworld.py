"""The overworld: locations joined by roads (CLAUDE.md §1, §14 step 4b).

A save slot's world is one Overworld. Each location carries its own overworld
position and roads; roads are two-way. Called "Overworld" in code so it isn't
confused with the ECS ``World``; players just see "the world".

Locations are grouped into regions (step 8a): clusters of neighbouring places
sharing a biome, deeper ones (higher tier) tougher. A road between two regions
is a border, guarded by the deeper region's warden (core.combat.fight).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from tidewrack.core.world.location import Location


@dataclass(frozen=True)
class Region:
    id: str  # its content id, e.g. "region.fens"
    name: str  # this world's name for it, e.g. "The Sallow Fens"
    kind: str  # the biome, e.g. "Fens"
    tier: int  # 1 on the coast, higher inland: tougher


@dataclass(frozen=True)
class Overworld:
    start: str  # location id where a new game begins
    locations: dict[str, Location]
    regions: dict[str, Region] = field(default_factory=dict)  # empty in old saves

    def region_of(self, location_id: str) -> Region | None:
        return self.regions.get(self.locations[location_id].region)

    def borders(self) -> list[tuple[str, str]]:
        """Roads (from, to) that lead into a deeper region, in location order."""
        found = []
        for loc in self.locations.values():
            for to in loc.roads:
                here, there = self.region_of(loc.id), self.region_of(to)
                if here and there and there.tier > here.tier:
                    found.append((loc.id, to))
        return found

    def location(self, location_id: str) -> Location:
        return self.locations[location_id]

    @property
    def has_map(self) -> bool:
        return all(loc.pos is not None for loc in self.locations.values())

    def neighbours(self, location_id: str) -> list[str]:
        return list(self.locations[location_id].roads)

    def problems(self) -> list[str]:
        if self.start not in self.locations:
            return [f"start location {self.start!r} does not exist"]
        found = []
        for loc in self.locations.values():
            found += [f"{loc.id}: {p}" for p in loc.problems()]
            for to in loc.roads:
                if to not in self.locations:
                    found.append(f"{loc.id}: road leads to unknown location {to!r}")
                elif loc.id not in self.locations[to].roads:
                    found.append(f"{loc.id}: road to {to!r} has no road back")
            if loc.id in loc.roads or len(set(loc.roads)) != len(loc.roads):
                found.append(f"{loc.id}: roads must be distinct and lead elsewhere")
            if self.regions and loc.region not in self.regions:
                found.append(f"{loc.id}: unknown region {loc.region!r}")
        positioned = [loc.pos is not None for loc in self.locations.values()]
        if any(positioned) and not all(positioned):
            found.append("map positions must be given for every location or none")
        if not found:
            seen, todo = {self.start}, deque([self.start])
            while todo:
                for nxt in self.neighbours(todo.popleft()):
                    if nxt not in seen:
                        seen.add(nxt)
                        todo.append(nxt)
            found += [f"{i}: unreachable from start" for i in self.locations if i not in seen]
        return found

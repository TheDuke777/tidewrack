"""Minimal entity-component store.

Entities are ints; components are plain objects (usually dataclasses) keyed by
their type, at most one of each type per entity. Instance-based (one per game) and
insertion-ordered, so queries iterate in entity-creation order and runs are
deterministic. Systems are ordinary functions over a World — see game.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, TypeVar

C = TypeVar("C")


class World:
    def __init__(self) -> None:
        self._next_id = 1
        self._entities: dict[int, dict[type, Any]] = {}

    # --- entities ----------------------------------------------------------------

    def create(self, *components: Any) -> int:
        entity = self._next_id
        self._next_id += 1
        self._entities[entity] = {}
        for component in components:
            self.add(entity, component)
        return entity

    def destroy(self, entity: int) -> None:
        del self._entities[entity]

    def exists(self, entity: int) -> bool:
        return entity in self._entities

    def entities(self) -> list[int]:
        return list(self._entities)

    # --- components --------------------------------------------------------------

    def add(self, entity: int, component: Any) -> None:
        """Attach `component`, replacing any existing component of the same type."""
        self._entities[entity][type(component)] = component

    def remove(self, entity: int, component_type: type[C]) -> C:
        return self._entities[entity].pop(component_type)

    def get(self, entity: int, component_type: type[C]) -> C:
        try:
            return self._entities[entity][component_type]
        except KeyError:
            raise KeyError(f"entity {entity} has no {component_type.__name__}") from None

    def try_get(self, entity: int, component_type: type[C]) -> C | None:
        return self._entities.get(entity, {}).get(component_type)

    def has(self, entity: int, *component_types: type) -> bool:
        components = self._entities.get(entity, {})
        return all(t in components for t in component_types)

    def components(self, entity: int) -> tuple[Any, ...]:
        return tuple(self._entities[entity].values())

    # --- queries -----------------------------------------------------------------

    def query(self, *component_types: type) -> Iterator[tuple[int, tuple[Any, ...]]]:
        """Yield (entity, (components…)) for entities having all `component_types`."""
        for entity, components in list(self._entities.items()):
            if all(t in components for t in component_types):
                yield entity, tuple(components[t] for t in component_types)

    def single(self, component_type: type[C]) -> tuple[int, C]:
        """The one entity with `component_type` (e.g. the player). Errors otherwise."""
        found = [(e, c[0]) for e, c in self.query(component_type)]
        if len(found) != 1:
            raise LookupError(f"expected one {component_type.__name__}, found {len(found)}")
        return found[0]

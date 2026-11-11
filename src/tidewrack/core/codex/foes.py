"""The Foes section of the codex: enemies you've met, filled in as you beat them.

An entry appears when you first meet an enemy (name, kind, description). Its
stats are revealed after STATS_AT defeats and what it can drop after DROPS_AT, so
the codex rewards fighting without hiding anything for good (CLAUDE.md §8.5).
Every entry also says where its kind is found (`found_in`, worked out by the game
from the world: kinds of place, by region, never place names you haven't seen).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from tidewrack.core.engine.components import Codex
from tidewrack.core.gear.stats import StatBlock

STATS_AT = 1
DROPS_AT = 3
CATEGORY_LABELS = {"beast": "Beasts", "person": "People", "spirit": "Spirits"}


@dataclass(frozen=True)
class FoeView:
    enemy_id: str
    name: str
    category: str
    description: str
    defeated: int
    stats: StatBlock | None  # None until STATS_AT defeats
    drops: tuple[str, ...] | None  # None until DROPS_AT defeats; () = drops nothing
    next_reveal: str | None  # what defeating more of them will show, if anything
    found_in: str | None = None  # "Peat Bog, Mere (The Sallow Fens)"; None if nowhere now


@dataclass(frozen=True)
class FoesView:
    foes: tuple[FoeView, ...]  # in the order you met them

    def by_category(self) -> list[tuple[str, tuple[FoeView, ...]]]:
        """(heading, foes) per category, in a fixed order; empty ones left out."""
        groups = []
        for category, label in CATEGORY_LABELS.items():
            found = tuple(f for f in self.foes if f.category == category)
            if found:
                groups.append((label, found))
        others = tuple(f for f in self.foes if f.category not in CATEGORY_LABELS)
        if others:
            groups.append(("Others", others))
        return groups


def foes_view(codex: Codex, found_in: Mapping[str, str] | None = None) -> FoesView:
    found_in = found_in or {}
    views = []
    for enemy_id, entry in codex.foes.items():
        kills = codex.kills.get(enemy_id, 0)
        if kills < STATS_AT:
            left = STATS_AT - kills
            hint = f"Defeat {_count(left)} to learn its strength."
        elif kills < DROPS_AT:
            left = DROPS_AT - kills
            hint = f"Defeat {_count(left)} more to learn what it drops."
        else:
            hint = None
        views.append(
            FoeView(
                enemy_id=enemy_id,
                name=entry.name,
                category=entry.category,
                description=entry.description,
                defeated=kills,
                stats=dict(entry.stats) if kills >= STATS_AT else None,
                drops=tuple(entry.drops) if kills >= DROPS_AT else None,
                next_reveal=hint,
                found_in=found_in.get(enemy_id),
            )
        )
    return FoesView(tuple(views))


def _count(n: int) -> str:
    return "one" if n == 1 else str(n)

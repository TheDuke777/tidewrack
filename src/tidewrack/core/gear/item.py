"""A piece of gear as the game holds it: a fully resolved snapshot.

An Item carries everything needed to compute its stats (its definition's base,
its roll, upgrades, affixes, and its set's bonuses), not just a content ID, so
saves never depend on the content files of a later release (CLAUDE.md §9).
Items are ECS components (registered in engine/components.py), so their class
and field names are part of the save format.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SLOTS = ("main_hand", "off_hand", "head", "body", "feet", "trinket")
SLOT_LABELS = {
    "main_hand": "Main hand",
    "off_hand": "Off hand",
    "head": "Head",
    "body": "Body",
    "feet": "Feet",
    "trinket": "Trinket",
}


@dataclass
class Affix:
    id: str
    name: str  # e.g. "Keen" (prefix) or "of the Gull" (suffix)
    prefix: bool
    stats: dict[str, int] = field(default_factory=dict)
    effects: list[str] = field(default_factory=list)


@dataclass
class SetBonus:
    pieces: int  # applies while at least this many of the set are equipped
    stats: dict[str, int] = field(default_factory=dict)
    effects: list[str] = field(default_factory=list)


SET_COLORS = ("teal", "amber", "indigo", "pink", "green", "orange", "purple", "cyan")


@dataclass
class GearSet:
    id: str
    name: str
    bonuses: list[SetBonus] = field(default_factory=list)
    color: str | None = None  # one of SET_COLORS; None in saves from before v0.5.0


@dataclass
class Item:
    gear_id: str  # the content definition it was made from (for the codex)
    name: str  # the definition's name, without affixes
    slot: str  # one of SLOTS; a two-hander's slot is main_hand
    two_handed: bool = False
    base: dict[str, int] = field(default_factory=dict)  # the definition's base stats
    roll: dict[str, int] = field(default_factory=dict)  # this copy's random bonus
    upgrade: int = 0
    max_upgrade: int = 0
    upgrade_step: dict[str, int] = field(default_factory=dict)  # stats per upgrade level
    affixes: list[Affix] = field(default_factory=list)
    effects: list[str] = field(default_factory=list)
    gear_set: GearSet | None = None

    @property
    def display_name(self) -> str:
        prefixes = [a.name for a in self.affixes if a.prefix]
        suffixes = [a.name for a in self.affixes if not a.prefix]
        name = " ".join([*prefixes, self.name, *suffixes])
        return f"{name} +{self.upgrade}" if self.upgrade else name


def slots_taken(item: Item) -> tuple[str, ...]:
    """The slots `item` occupies when equipped."""
    return ("main_hand", "off_hand") if item.two_handed else (item.slot,)

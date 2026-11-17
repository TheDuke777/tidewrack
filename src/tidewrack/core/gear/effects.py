"""Gear effects: what gear can do besides stats (set bonuses first; v0.13.0).

An effect is written in content as "kind:value" (e.g. "lifesteal:2") on gear, an
affix or a set bonus, and kept that way in item snapshots, so saves need nothing
new. The stat sheet adds up every active effect by kind (`total`); the rules that
read them live where the action is (combat, encounters, regen, looting).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

# kind -> how to describe it for a value (shown on gear cards, the stat sheet, the Codex)
EFFECTS: dict[str, Callable[[int], str]] = {
    "lifesteal": lambda v: f"heal {v} HP with every blow you land",
    "bane": lambda v: f"+{v} ATK against wardens, bounties and the Drowned King",
    "exposed": lambda v: f"take {v} more damage from every blow",
    "sure_footed": lambda v: f"+{v}% chance to get away when you flee",
    "stealth": lambda v: f"{v}% less likely to be ambushed on the road",
    "salvage": lambda v: f"{v}% chance of an extra material when you loot or gather",
    "second_wind": lambda v: f"+{v} HP each time you recover between fights",
}

# Effects that make things harder for you: shown as drawbacks, never "better".
DRAWBACKS = frozenset({"exposed"})


def parse(effect: str) -> tuple[str, int] | None:
    """("lifesteal", 2) for "lifesteal:2"; None for plain text (older items)."""
    kind, sep, value = effect.partition(":")
    if not sep or kind not in EFFECTS:
        return None
    try:
        return kind, int(value)
    except ValueError:
        return None


def problem(effect: str) -> str | None:
    """Why `effect` isn't a valid content effect, or None if it is."""
    kind, sep, value = effect.partition(":")
    if not sep:
        return f"effect {effect!r} must be kind:value"
    if kind not in EFFECTS:
        return f"unknown effect kind {kind!r} (known: {', '.join(sorted(EFFECTS))})"
    try:
        if int(value) <= 0:
            return f"effect {effect!r} needs a positive value"
    except ValueError:
        return f"effect {effect!r} needs a whole-number value"
    return None


def total(effects: Iterable[str]) -> dict[str, int]:
    """Every effect added up by kind, in EFFECTS order (plain text is skipped)."""
    sums: dict[str, int] = {}
    for effect in effects:
        parsed = parse(effect)
        if parsed is not None:
            sums[parsed[0]] = sums.get(parsed[0], 0) + parsed[1]
    return {k: sums[k] for k in EFFECTS if k in sums}


def describe(effect: str) -> str:
    """An effect as players read it; plain text is shown as it is."""
    parsed = parse(effect)
    return effect if parsed is None else EFFECTS[parsed[0]](parsed[1])


def describe_totals(totals: dict[str, int]) -> list[str]:
    return [EFFECTS[k](v) for k, v in totals.items()]

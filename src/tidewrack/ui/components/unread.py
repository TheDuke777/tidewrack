"""Unread dots: what's new since you last looked at a tab.

Each tracked part of the game (quests, codex, pack, satchel) has a set of keys
for what's there now; whatever wasn't there when you last looked is new. "Seen"
starts as everything present when the world opens, and is kept only while it's
open (UI state, not saved), so reopening a world never shows stale dots. A dot
always means a new thing you'll find when you look; the one exception is a quest
ready to turn in, which stays until you hand it in.

Arriving clears the dot (`look`), but the cards behind it keep a "New" chip
while you stay on that tab (`is_new`), so you can tell which ones they are;
leaving the tab (`leave`) clears the chips.
"""

from __future__ import annotations

from collections.abc import Hashable

import flet as ft

from tidewrack.core.codex import items as codex_items
from tidewrack.core.engine.game import Game

PARTS = ("quests", "codex", "pack", "satchel")


def keys(game: Game, part: str) -> set[Hashable]:
    if part == "quests":
        log = game.quests()
        return {q.id for q in (*log.ready, *log.active)}
    if part == "codex":
        # New entries only: more learned about one you know isn't a "new" thing.
        return codex_items.keys(game)
    inventory = game.inventory()
    if part == "pack":
        return {item.id for item in inventory.pack}
    return (
        {("material", m.id) for m in inventory.materials}
        | {("meal", m.id) for m in inventory.meals}
        | {("recipe", r) for r in inventory.recipes}
    )


def dot_icon(icon: ft.IconData, dot: bool) -> ft.Icon:
    """An icon with a dot on it. (Flet only draws badges on icon controls, not on
    navigation destinations or segments themselves.)"""
    return ft.Icon(icon, badge=ft.Badge(small_size=9) if dot else None)


def dot_label(text: str, dot: bool) -> ft.Control | str:
    """A tab label with a dot on its corner, for tabs without an icon. The dot sits
    over the text like an icon badge, so the tab keeps its size."""
    if not dot:
        return text
    return ft.Text(f"{text}\u2002", badge=ft.Badge(small_size=8))  # the dot sits on the space


def new_chip() -> ft.Container:
    """ "New" on a card behind a cleared dot: a word, not only a colour (§11)."""
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
        bgcolor=ft.Colors.PRIMARY_CONTAINER,
        border_radius=ft.BorderRadius.all(10),
        content=ft.Text(
            "New", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_PRIMARY_CONTAINER
        ),
    )


class Unread:
    def __init__(self, game: Game) -> None:
        self.game = game
        self.seen = {part: keys(game, part) for part in PARTS}
        self.fresh: dict[str, set[Hashable]] = {part: set() for part in PARTS}

    def new(self, part: str) -> set[Hashable]:
        return keys(self.game, part) - self.seen[part]

    def mark_seen(self, part: str) -> None:
        self.seen[part] = keys(self.game, part)

    def look(self, part: str) -> None:
        """You're looking at `part`: clear its dot, keep "New" chips on what was new."""
        self.fresh[part] |= self.new(part)
        self.mark_seen(part)

    def leave(self, part: str) -> None:
        """You left the tab showing `part`: its "New" chips go."""
        self.fresh[part] = set()

    def is_new(self, part: str, key: Hashable) -> bool:
        return key in self.fresh[part]

    # --- the dots ----------------------------------------------------------------

    def quests(self) -> bool:
        return bool(self.game.quests().ready) or bool(self.new("quests"))

    def codex(self) -> bool:
        return bool(self.new("codex"))

    def inventory(self) -> bool:
        return bool(self.new("pack") or self.new("satchel"))

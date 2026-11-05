"""Unread dots: what's new since you last looked at a tab.

Each tracked part of the game (quests, codex, pack, satchel) has a set of keys
for what's there now; whatever wasn't there when you last looked is new. "Seen"
starts as everything present when the world opens, and is kept only while it's
open (UI state, not saved), so reopening a world never shows stale dots. Some
dots don't depend on seeing: a quest ready to turn in, a meal about to wear off.
"""

from __future__ import annotations

from collections.abc import Hashable

import flet as ft

from tidewrack.core.engine.game import Game

MEAL_WARNING = 10  # turns left on a meal when the Inventory tab starts warning

PARTS = ("quests", "codex", "pack", "satchel")


def keys(game: Game, part: str) -> set[Hashable]:
    if part == "quests":
        log = game.quests()
        return {q.id for q in (*log.ready, *log.active)}
    if part == "codex":
        found: set[Hashable] = set()
        for foe in game.foes().foes:
            found.add((foe.enemy_id, "met"))
            if foe.stats is not None:
                found.add((foe.enemy_id, "stats"))
            if foe.drops is not None:
                found.add((foe.enemy_id, "drops"))
        return found
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
    """A tab label with a dot after it, for tabs without an icon."""
    if not dot:
        return text
    return ft.Row(
        tight=True,
        spacing=4,
        controls=[
            ft.Text(text),
            ft.Container(width=8, height=8, border_radius=4, bgcolor=ft.Colors.ERROR, data="dot"),
        ],
    )


class Unread:
    def __init__(self, game: Game) -> None:
        self.game = game
        self.seen = {part: keys(game, part) for part in PARTS}

    def new(self, part: str) -> set[Hashable]:
        return keys(self.game, part) - self.seen[part]

    def mark_seen(self, part: str) -> None:
        self.seen[part] = keys(self.game, part)

    # --- the dots ----------------------------------------------------------------

    def quests(self) -> bool:
        return bool(self.game.quests().ready) or bool(self.new("quests"))

    def codex(self) -> bool:
        return bool(self.new("codex"))

    def meal_running_out(self) -> bool:
        fed = self.game.view().fed
        return fed is not None and fed.turns_left <= MEAL_WARNING

    def inventory(self) -> bool:
        return bool(self.new("pack") or self.new("satchel")) or self.meal_running_out()

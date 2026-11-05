"""Which cards in a list are collapsed: gear and quest cards fold down to their top
row and a one-line summary, so long lists stay short.

Each list has a name and a default (DEFAULTS: long shop lists and quest lists
start collapsed, the few things you're deciding about right now start
expanded). "Collapse all" / "Expand all" changes that list's default and
remembers it in the app's settings (Settings.collapsed), so the choice holds
across worlds and restarts; tapping one card only flips that card while the
screen is open. Settings (step 10) will get proper toggles for the defaults.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable

import flet as ft

from tidewrack.services.settings import SettingsStore

# list name -> starts collapsed
DEFAULTS = {
    "buy": True,
    "sell": True,
    "upgrade": True,
    "craft": True,
    "pack": True,
    "equipped": False,
    "ground": False,
    "board": True,
    "quests": True,
}


class Folds:
    def __init__(
        self, name: str, settings: SettingsStore | None, refresh: Callable[[], None]
    ) -> None:
        self.name = name
        self.settings = settings
        self._refresh = refresh
        saved = settings.load().collapsed if settings is not None else {}
        self.default = saved.get(name, DEFAULTS[name])
        self.flipped: set[Hashable] = set()  # cards toggled away from the default

    def collapsed(self, key: Hashable) -> bool:
        return self.default != (key in self.flipped)

    def toggle(self, key: Hashable) -> None:
        self.flipped ^= {key}
        self._refresh()

    def set_all(self, collapsed: bool) -> None:
        self.default = collapsed
        self.flipped.clear()
        if self.settings is not None:
            current = self.settings.load()
            remembered = {**current.collapsed, self.name: collapsed}
            self.settings.save(current.model_copy(update={"collapsed": remembered}))
        self._refresh()

    def all_button(self, keys: Iterable[Hashable]) -> ft.TextButton:
        """ "Collapse all" while any card is open, else "Expand all"."""
        keys = list(keys)
        any_open = any(not self.collapsed(k) for k in keys)
        return ft.TextButton(
            content="Collapse all" if any_open else "Expand all",
            icon=ft.Icons.UNFOLD_LESS if any_open else ft.Icons.UNFOLD_MORE,
            visible=bool(keys),
            on_click=lambda _: self.set_all(any_open),
        )

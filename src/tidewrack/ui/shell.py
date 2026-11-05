"""The open world's screens, switched with a Material 3 navigation bar.

Each tab is a screen object with `control` and `refresh()`; switching refreshes
the tab being shown, since the other one may have changed the game (dropping an
item in the inventory puts it in the room). New tabs are one entry in `tabs`.

Every tab stays mounted and switching only changes which one is visible. Taking
a tab's controls off the page and putting the same objects back later left Flet
diffing later changes against stale list snapshots, so the phone showed rows
twice (duplicate set bonuses, "ghost" pack items) until the next full redraw.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from tidewrack.services.session import GameSession
from tidewrack.services.settings import SettingsStore
from tidewrack.ui.components.pack_list import Confirm, PackChoices
from tidewrack.ui.screens.codex import CodexScreen
from tidewrack.ui.screens.game import GameScreen
from tidewrack.ui.screens.inventory import InventoryScreen
from tidewrack.ui.screens.quests import QuestsScreen


class WorldShell:
    def __init__(
        self,
        session: GameSession,
        settings: SettingsStore,
        on_back: Callable[[], None],
        confirm: Confirm,
        notify: Callable[[str], None],
    ) -> None:
        choices = PackChoices()  # one set of pack filters and sort for the whole world
        self.explore = GameScreen(
            session, settings, on_back=on_back, notify=notify, confirm=confirm, choices=choices
        )
        self.inventory = InventoryScreen(session, confirm=confirm, notify=notify, choices=choices)
        self.quests = QuestsScreen(session, confirm=confirm, notify=notify)
        self.codex = CodexScreen(session)
        self.tabs = [
            (self.explore, "Explore", ft.Icons.EXPLORE_OUTLINED, ft.Icons.EXPLORE),
            (self.inventory, "Inventory", ft.Icons.BACKPACK_OUTLINED, ft.Icons.BACKPACK),
            (self.quests, "Quests", ft.Icons.ASSIGNMENT_OUTLINED, ft.Icons.ASSIGNMENT),
            (self.codex, "Codex", ft.Icons.MENU_BOOK_OUTLINED, ft.Icons.MENU_BOOK),
        ]
        self.body = ft.Column(
            expand=True,
            spacing=0,
            controls=[screen.control for screen, *_ in self.tabs],
        )
        self.navigation_bar = ft.NavigationBar(
            selected_index=0,
            destinations=[
                ft.NavigationBarDestination(icon=icon, selected_icon=selected, label=label)
                for _, label, icon, selected in self.tabs
            ],
            on_change=lambda e: self.select(int(e.control.selected_index)),
        )

        self.select(0)

    @property
    def current(self) -> int:
        return self.navigation_bar.selected_index or 0

    def select(self, index: int) -> None:
        for i, (screen, *_) in enumerate(self.tabs):
            screen.control.visible = i == index
        self.tabs[index][0].refresh()
        self.navigation_bar.selected_index = index

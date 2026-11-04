"""The open world's screens, switched with a Material 3 navigation bar.

Each tab is a screen object with `control` and `refresh()`; switching refreshes
the tab being shown, since the other one may have changed the game (dropping an
item in the inventory puts it in the room). New tabs are one entry in `tabs`.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from tidewrack.services.session import GameSession
from tidewrack.services.settings import SettingsStore
from tidewrack.ui.screens.game import GameScreen
from tidewrack.ui.screens.inventory import Confirm, InventoryScreen


class WorldShell:
    def __init__(
        self,
        session: GameSession,
        settings: SettingsStore,
        on_back: Callable[[], None],
        confirm: Confirm,
    ) -> None:
        self.explore = GameScreen(session, settings, on_back=on_back)
        self.inventory = InventoryScreen(session, confirm=confirm)
        self.tabs = [
            (self.explore, "Explore", ft.Icons.EXPLORE_OUTLINED, ft.Icons.EXPLORE),
            (self.inventory, "Inventory", ft.Icons.BACKPACK_OUTLINED, ft.Icons.BACKPACK),
        ]
        self.body = ft.Container(expand=True, content=self.explore.control)
        self.navigation_bar = ft.NavigationBar(
            selected_index=0,
            destinations=[
                ft.NavigationBarDestination(icon=icon, selected_icon=selected, label=label)
                for _, label, icon, selected in self.tabs
            ],
            on_change=lambda e: self.select(int(e.control.selected_index)),
        )

    def select(self, index: int) -> None:
        screen = self.tabs[index][0]
        screen.refresh()
        self.body.content = screen.control
        self.navigation_bar.selected_index = index

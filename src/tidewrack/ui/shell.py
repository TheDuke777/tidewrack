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
from tidewrack.ui.components.unread import Unread, dot_icon
from tidewrack.ui.screens.codex import CodexScreen
from tidewrack.ui.screens.game import GameScreen
from tidewrack.ui.screens.inventory import InventoryScreen
from tidewrack.ui.screens.quests import QuestsScreen

EXPLORE, INVENTORY, QUESTS, CODEX = range(4)  # the tabs, in order


class WorldShell:
    def __init__(
        self,
        session: GameSession,
        settings: SettingsStore,
        on_back: Callable[[], None],
        confirm: Confirm,
        notify: Callable[[str], None],
    ) -> None:
        self.unread = Unread(session.game)
        choices = PackChoices()  # one set of pack filters and sort for the whole world
        shop_choices = PackChoices()  # and one for every shop's Buy tab
        self.explore = GameScreen(
            session,
            settings,
            on_back=on_back,
            notify=notify,
            confirm=confirm,
            choices=choices,
            shop_choices=shop_choices,
        )
        self.inventory = InventoryScreen(
            session,
            confirm=confirm,
            notify=notify,
            choices=choices,
            settings=settings,
            unread=self.unread,
        )
        self.quests = QuestsScreen(
            session, confirm=confirm, notify=notify, settings=settings, unread=self.unread
        )
        self.codex = CodexScreen(session, unread=self.unread)
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

        session.listeners.append(lambda _: self.update_dots())
        self._shown = 0
        self.select(0)

    @property
    def current(self) -> int:
        return self._shown

    def select(self, index: int) -> None:
        # Our own record of the tab on screen: by the time on_change runs, Flet has
        # already set navigation_bar.selected_index to the tab being opened.
        if index != self._shown:  # leaving a tab clears its "New" chips
            self._leave(self._shown)
        self._shown = index
        for i, (screen, *_) in enumerate(self.tabs):
            screen.control.visible = i == index
        self.navigation_bar.selected_index = index
        if index == QUESTS:
            self.unread.look("quests")
        elif index == CODEX:
            self.unread.look("codex")
        self.tabs[index][0].refresh()  # Inventory marks its own inner tab as seen
        self.update_dots()

    def back(self) -> bool:
        """Android's back gesture inside the world: one step out at a time.

        Another tab → Explore; an open board or shop → closed. False when
        there's nothing left to step out of (the app then leaves the world).
        """
        if self.current != EXPLORE:
            self.select(EXPLORE)
            return True
        if self.explore.opened is not None:
            self.explore.close()
            return True
        return False

    def _leave(self, index: int) -> None:
        if index == QUESTS:
            self.unread.leave("quests")
        elif index == CODEX:
            self.unread.leave("codex")
        elif index == INVENTORY:
            self.inventory.leave()

    def update_dots(self) -> None:
        """A dot on a tab with something new in it (CLAUDE.md §8.5's "unread" marks)."""
        dots = {
            INVENTORY: (self.unread.inventory(), "Something new in your inventory"),
            QUESTS: (self.unread.quests(), "A quest is ready or new"),
            CODEX: (self.unread.codex(), "Something new in the codex"),
        }
        for index, destination in enumerate(self.navigation_bar.destinations):
            dot, why = dots.get(index, (False, ""))
            # The dot is extra: what it points at is always written in the tab itself.
            _, _, icon, selected = self.tabs[index]
            destination.icon = dot_icon(icon, dot)
            destination.selected_icon = dot_icon(selected, dot)
            destination.tooltip = why if dot else None

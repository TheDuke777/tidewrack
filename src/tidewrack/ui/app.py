"""Navigation shell: the slot picker and the game screen."""

from __future__ import annotations

import secrets
from collections.abc import Callable

import flet as ft

from tidewrack.core.data.loader import Content
from tidewrack.services.session import GameSession, next_world_name
from tidewrack.services.settings import SettingsStore
from tidewrack.services.storage import SaveError, SaveStore, SlotListing
from tidewrack.ui import theme
from tidewrack.ui.screens.slot_picker import SlotPickerScreen
from tidewrack.ui.shell import WorldShell
from tidewrack.version import get_build_info, version_label

WORLD_RECIPE = "world.standard"

# The world open in this process. Android rebuilds the app's window on changes
# the manifest doesn't absorb (e.g. a new system colour palette), and Flet then
# runs main() again in the same process; `App.start` reopens this world instead
# of dropping the player at the picker. A cold start begins with None.
_open_world: str | None = None


def new_seed() -> int:
    # The UI picks fresh seeds; core itself never touches system randomness.
    return secrets.randbits(63)


class App:
    def __init__(
        self, page: ft.Page, store: SaveStore, settings: SettingsStore, content: Content
    ) -> None:
        self.page = page
        self.store = store
        self.settings = settings
        self.content = content

    def _show(self, control: ft.Control, navigation_bar: ft.NavigationBar | None = None) -> None:
        self.page.navigation_bar = navigation_bar
        self.page.controls.clear()
        self.page.controls.append(control)
        self.page.update()

    def _notify(self, message: str) -> None:
        self.page.show_dialog(ft.SnackBar(ft.Text(message)))
        # show_dialog updates only the dialog layer, and any explicit update() in an
        # event handler turns off Flet's automatic page update when it returns. So
        # without this, whatever the handler changed besides the toast never reached
        # the screen (a turned-in quest stayed on the notice board).
        self.page.update()

    # --- screens -----------------------------------------------------------------

    def start(self) -> None:
        """The world this process had open, if any (and still loadable); else the picker."""
        if _open_world is not None:
            try:
                self.show_game(GameSession.open(self.store, _open_world, self.content))
                return
            except SaveError:
                pass
        self.show_picker()

    def show_picker(self) -> None:
        global _open_world
        _open_world = None
        theme.redraw = None
        self._show(
            SlotPickerScreen(
                self.store.list_slots(),
                on_open=self.open_slot,
                on_new=self.new_world,
                on_delete=self.confirm_delete,
                footer=version_label(get_build_info()),
            ).control
        )

    def show_game(self, session: GameSession) -> None:
        global _open_world
        _open_world = session.meta.slot_id
        shell = WorldShell(
            session,
            self.settings,
            on_back=self.show_picker,
            confirm=self.confirm,
            notify=self._notify,
        )
        theme.redraw = lambda: shell.select(shell.current)
        self._show(shell.body, shell.navigation_bar)
        if session.from_backup:
            self._notify(
                "The latest save was unreadable, so this world was restored from a backup."
            )

    # --- actions -----------------------------------------------------------------

    def new_world(self) -> None:
        name = next_world_name([s.meta.name for s in self.store.list_slots()])
        seed = new_seed()
        session = GameSession.generate(self.store, self.content, WORLD_RECIPE, name, seed)
        self.show_game(session)

    def open_slot(self, slot_id: str) -> None:
        try:
            session = GameSession.open(self.store, slot_id, self.content)
        except SaveError as e:
            self._notify(str(e))
            return
        self.show_game(session)

    def confirm(
        self, title: str, message: str, action: str, on_confirm: Callable[[], None]
    ) -> None:
        """Ask before doing something the player might regret (drop, later sell)."""

        def confirmed(_: ft.Event) -> None:
            self.page.pop_dialog()
            on_confirm()
            self.page.update()

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(title),
                content=ft.Text(message),
                actions=[
                    ft.TextButton(content="Cancel", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton(content=action, on_click=confirmed),
                ],
            )
        )

    def confirm_delete(self, listing: SlotListing) -> None:
        def delete(_: ft.Event) -> None:
            self.page.pop_dialog()
            self.store.delete(listing.meta.slot_id)
            self.show_picker()

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Delete {listing.meta.name}?"),
                content=ft.Text("This world and its backups will be gone for good."),
                actions=[
                    ft.TextButton(content="Cancel", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton(content="Delete", on_click=delete),
                ],
            )
        )

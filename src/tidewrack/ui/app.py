"""Navigation shell: the slot picker and the game screen."""

from __future__ import annotations

import secrets

import flet as ft

from tidewrack.core.data.loader import Content
from tidewrack.services.session import GameSession, next_world_name
from tidewrack.services.storage import SaveError, SaveStore, SlotListing
from tidewrack.ui.screens.game import GameScreen
from tidewrack.ui.screens.slot_picker import SlotPickerScreen
from tidewrack.version import get_build_info, version_label

START_DUNGEON = "dungeon.first_descent"


def new_seed() -> int:
    # The UI picks fresh seeds; core itself never touches system randomness.
    return secrets.randbits(63)


class App:
    def __init__(self, page: ft.Page, store: SaveStore, content: Content) -> None:
        self.page = page
        self.store = store
        self.content = content

    def _show(self, control: ft.Control) -> None:
        self.page.controls.clear()
        self.page.controls.append(control)
        self.page.update()

    def _notify(self, message: str) -> None:
        self.page.show_dialog(ft.SnackBar(ft.Text(message)))

    # --- screens -----------------------------------------------------------------

    def show_picker(self) -> None:
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
        self._show(GameScreen(session, on_back=self.show_picker).control)
        if session.from_backup:
            self._notify(
                "The latest save was unreadable, so this world was restored from a backup."
            )

    # --- actions -----------------------------------------------------------------

    def new_world(self) -> None:
        name = next_world_name([s.meta.name for s in self.store.list_slots()])
        session = GameSession.new(self.store, self.content, START_DUNGEON, name, new_seed())
        self.show_game(session)

    def open_slot(self, slot_id: str) -> None:
        try:
            session = GameSession.open(self.store, slot_id, self.content)
        except SaveError as e:
            self._notify(str(e))
            return
        self.show_game(session)

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

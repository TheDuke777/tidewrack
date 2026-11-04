"""The inventory: your stats, what you have on, and what's in your pack.

Reads only Game.inventory() and sends only commands, through the GameSession so
every change autosaves (CLAUDE.md §4, §6).
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from tidewrack.core.engine.game import Command, Drop, Equip, InventoryView, ItemView, Unequip
from tidewrack.core.gear.compare import format_stats
from tidewrack.core.gear.stats import STAT_LABELS, STATS
from tidewrack.services.session import GameSession
from tidewrack.ui.components.gear_compare_card import gear_compare_card


class InventoryScreen:
    def __init__(self, session: GameSession, on_back: Callable[[], None]) -> None:
        self.session = session
        self.sheet = ft.Column(spacing=4)
        self.equipped = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.pack = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        header = ft.Row(
            controls=[
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK,
                    tooltip="Back to the game",
                    on_click=lambda _: on_back(),
                ),
                ft.Text("Inventory", size=22, weight=ft.FontWeight.BOLD),
            ]
        )
        self.control = ft.SafeArea(
            expand=True,
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    expand=True,
                    controls=[
                        header,
                        ft.ListView(
                            expand=True,
                            spacing=12,
                            controls=[
                                self.sheet,
                                _heading("Equipped"),
                                self.equipped,
                                _heading("Pack"),
                                self.pack,
                            ],
                        ),
                    ],
                ),
            ),
        )
        self.refresh()

    def act(self, command: Command) -> None:
        self.session.perform(command)  # autosaves
        self.refresh()

    def refresh(self) -> None:
        view = self.session.game.inventory()
        self.sheet.controls = self._sheet(view)
        self.equipped.controls = [self._slot(slot) for slot in view.slots]
        self.pack.controls = [
            gear_compare_card(item, self._buttons(item)) for item in view.pack
        ] or [_muted("Your pack is empty.")]

    def _sheet(self, view: InventoryView) -> list[ft.Control]:
        total = view.sheet.total
        lines: list[ft.Control] = [
            ft.Text(
                "   ".join(f"{STAT_LABELS[s]} {total[s]}" for s in STATS),
                size=20,
                weight=ft.FontWeight.BOLD,
            )
        ]
        base, *gear = view.sheet.sources
        lines.append(
            _muted("Base: " + ", ".join(f"{STAT_LABELS[s]} {base.stats[s]}" for s in STATS))
        )
        lines += [
            _muted(f"{source.label}: {format_stats(source.stats) or 'nothing'}") for source in gear
        ]
        return lines

    def _slot(self, slot) -> ft.Control:
        if slot.item is not None:
            return gear_compare_card(slot.item, self._buttons(slot.item))
        if slot.filled_by is not None:
            return _muted(f"{slot.label}: held by the {slot.filled_by} (both hands)")
        return _muted(f"{slot.label}: empty")

    def _buttons(self, item: ItemView) -> list[ft.Control]:
        buttons: list[ft.Control] = []
        if item.equipped:
            buttons.append(
                ft.OutlinedButton(
                    content="Take off",
                    icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                    on_click=lambda _, i=item.id: self.act(Unequip(i)),
                )
            )
        else:
            buttons.append(
                ft.FilledButton(
                    content="Equip",
                    icon=ft.Icons.CHECK,
                    on_click=lambda _, i=item.id: self.act(Equip(i)),
                )
            )
        buttons.append(
            ft.TextButton(
                content="Drop",
                icon=ft.Icons.FILE_DOWNLOAD_OUTLINED,
                on_click=lambda _, i=item.id: self.act(Drop(i)),
            )
        )
        return buttons


def _heading(text: str) -> ft.Text:
    return ft.Text(text, size=16, weight=ft.FontWeight.BOLD)


def _muted(text: str) -> ft.Text:
    return ft.Text(text, size=14, color=ft.Colors.ON_SURFACE_VARIANT)

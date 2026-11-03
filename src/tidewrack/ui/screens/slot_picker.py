"""Pick a world (save slot): continue one, start a new one, or delete one."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import flet as ft

from tidewrack.services.storage import SlotListing


class SlotPickerScreen:
    def __init__(
        self,
        listings: list[SlotListing],
        on_open: Callable[[str], None],
        on_new: Callable[[], None],
        on_new_large: Callable[[], None],
        on_delete: Callable[[SlotListing], None],
        footer: str,
    ) -> None:
        cards = [self._card(listing, on_open, on_delete) for listing in listings]
        empty = ft.Text(
            "No worlds yet. Start one to begin your descent.",
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        self.control = ft.SafeArea(
            expand=True,
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    expand=True,
                    spacing=12,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Text("Tidewrack", size=28, weight=ft.FontWeight.BOLD),
                        ft.FilledButton(
                            content="New world", icon=ft.Icons.ADD, on_click=lambda _: on_new()
                        ),
                        ft.TextButton(
                            content="Map test world (60 rooms)",
                            icon=ft.Icons.SCIENCE_OUTLINED,
                            on_click=lambda _: on_new_large(),
                        ),
                        ft.ListView(expand=True, spacing=8, controls=cards or [empty]),
                        ft.Text(footer, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                    ],
                ),
            ),
        )

    @staticmethod
    def _card(
        listing: SlotListing,
        on_open: Callable[[str], None],
        on_delete: Callable[[SlotListing], None],
    ) -> ft.Card:
        meta, summary = listing.meta, listing.meta.summary
        lines = [
            f"{summary.location} · {summary.dungeon_name}",
            f"Turn {summary.turn} · Explored {summary.visited}/{summary.total_nodes} · "
            f"Last played {_local_time(meta.updated_at)}",
        ]
        if listing.from_backup:
            lines.append("⚠ Restored from a backup; the latest save was unreadable.")
        return ft.Card(
            content=ft.ListTile(
                title=ft.Text(meta.name, weight=ft.FontWeight.BOLD),
                subtitle=ft.Text("\n".join(lines)),
                is_three_line=True,
                on_click=lambda _: on_open(meta.slot_id),
                trailing=ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    tooltip=f"Delete {meta.name}",
                    on_click=lambda _: on_delete(listing),
                ),
            )
        )


def _local_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%b %d, %H:%M")
    except ValueError:
        return iso

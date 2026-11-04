"""A gear set's chip: its name on a tint of the set's colour.

The name is always written in the chip, so the colour only helps you spot
matching pieces at a glance; it never carries meaning on its own (§11).
"""

from __future__ import annotations

import flet as ft

from tidewrack.core.gear.item import SET_COLORS

PALETTE = {
    "teal": ft.Colors.TEAL,
    "amber": ft.Colors.AMBER,
    "indigo": ft.Colors.INDIGO,
    "pink": ft.Colors.PINK,
    "green": ft.Colors.GREEN,
    "orange": ft.Colors.ORANGE,
    "purple": ft.Colors.PURPLE,
    "cyan": ft.Colors.CYAN,
}
assert set(PALETTE) == set(SET_COLORS)

# Sets that existed before items recorded their colour (v0.5.0), so pieces from
# older saves match new ones. Never add to this: new sets always have a colour.
LEGACY_COLORS = {"gearset.drowned_watch": "teal"}


def set_color(set_id: str, color: str | None) -> str:
    """The chip colour: the set's own, or a fixed pick by id for older saves."""
    color = color or LEGACY_COLORS.get(set_id)
    if color in PALETTE:
        return PALETTE[color]
    return PALETTE[SET_COLORS[sum(map(ord, set_id)) % len(SET_COLORS)]]


def set_chip(name: str, set_id: str, color: str | None) -> ft.Container:
    tint = set_color(set_id, color)
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        bgcolor=ft.Colors.with_opacity(0.22, tint),
        border=ft.Border.all(1, tint),
        border_radius=ft.BorderRadius.all(12),
        content=ft.Row(
            spacing=4,
            tight=True,
            controls=[
                ft.Icon(ft.Icons.WORKSPACES_OUTLINED, size=14, color=ft.Colors.ON_SURFACE),
                ft.Text(f"{name} set", size=13, weight=ft.FontWeight.BOLD),
            ],
        ),
    )

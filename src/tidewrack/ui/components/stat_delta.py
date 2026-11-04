"""A stat change: ▲ +3, ▼ −2 or ＝ 0. Colour always comes with the symbol and the
sign, never on its own (CLAUDE.md §8.4, §11)."""

from __future__ import annotations

import flet as ft

UP, DOWN, SAME = "▲", "▼", "＝"
MINUS = "−"  # a real minus sign, not a hyphen


def signed(value: int) -> str:
    return f"+{value}" if value > 0 else f"{MINUS}{-value}" if value < 0 else "0"


def delta_label(value: int) -> str:
    symbol = UP if value > 0 else DOWN if value < 0 else SAME
    return f"{symbol} {signed(value)}"


def delta_color(value: int) -> str:
    if value > 0:
        return ft.Colors.GREEN
    if value < 0:
        return ft.Colors.ERROR
    return ft.Colors.ON_SURFACE_VARIANT


def stat_delta(value: int, size: int = 14, width: float | None = None) -> ft.Text:
    return ft.Text(
        delta_label(value),
        size=size,
        width=width,
        color=delta_color(value),
        weight=ft.FontWeight.BOLD if value else None,
    )

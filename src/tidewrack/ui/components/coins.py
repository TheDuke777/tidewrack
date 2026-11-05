"""Gold amounts drawn as a number and a coin: "Buy · 12 ◉" instead of "12 gold".

`coins(text)` turns every "N gold" in a sentence into N plus a coin icon, so
callers keep writing plain sentences (and toasts, dialogs and the log keep
the word). The whole sentence stays on the control as `data` and the coin is
labelled "gold", so screen readers and tests still read "12 gold" (§11).
In a button the coin takes the button's text colour, so it dims with it.
"""

from __future__ import annotations

import re

import flet as ft

from tidewrack.ui import theme

COIN = ft.Icons.PAID
PURSE = "icons/money_bag.svg"  # src/assets/icons; Material Symbols, see NOTICE.md
AMOUNT = re.compile(r"(\d+) gold\b")


def coins(
    text: str,
    size: float | None = None,
    color: str | None = None,
    weight: ft.FontWeight | None = None,
) -> ft.Row:
    """`text` with each "N gold" drawn as N and a coin."""
    parts: list[ft.Control] = []
    at = 0
    for match in AMOUNT.finditer(text):
        parts.append(_text(text[at : match.start()] + match.group(1), size, color, weight))
        parts.append(ft.Icon(COIN, size=(size or 14) + 2, color=color, semantics_label="gold"))
        at = match.end()
    if at < len(text) or not parts:
        parts.append(_text(text[at:], size, color, weight))
    # wrap=True so a long line (a quest reward) wraps instead of overflowing.
    return ft.Row(
        tight=True,
        wrap=True,
        spacing=2,
        run_spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=parts,
        data=text,
    )


def purse(amount: int, size: float = 14) -> ft.Row:
    """Your gold total: a gold-tinted money bag and the amount."""
    return ft.Row(
        tight=True,
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        data=f"{amount} gold",
        controls=[
            # Always tinted: untinted, the file's light grey vanishes on light themes.
            ft.Image(
                src=PURSE,
                width=size + 4,
                height=size + 4,
                color=theme.gold(),
                semantics_label="gold",
            ),
            ft.Text(str(amount), size=size, weight=ft.FontWeight.BOLD),
        ],
    )


def label_of(control: ft.Control | str | None) -> str:
    """The plain sentence behind a label: a string, or a coins()/purse() row."""
    if control is None or isinstance(control, str):
        return control or ""
    if isinstance(control, ft.Row) and isinstance(control.data, str):
        return control.data
    return getattr(control, "value", "") or ""


def _text(value, size, color, weight) -> ft.Text:
    return ft.Text(value, size=size, color=color, weight=weight)

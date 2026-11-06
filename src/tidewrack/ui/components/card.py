"""The one card style: filled with surface_container, a tone above the page.

Material 3's default card fill (surface_container_low) sits right next to the
page's surface colour, and some phones' wallpaper (Material You) schemes make
them look the same, so cards vanished into the background. surface_container
is one step further from the page, as in the Material Theme Builder's examples.
"""

from __future__ import annotations

from typing import Any

import flet as ft

FILL = ft.Colors.SURFACE_CONTAINER


def card(content: ft.Control, **kwargs: Any) -> ft.Card:
    return ft.Card(content=content, bgcolor=FILL, **kwargs)

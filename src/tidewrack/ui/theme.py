"""App theming: Material You on Android, flet's built-in Material 3 theme elsewhere.

At launch the last wallpaper scheme (cached in settings) goes on straight away,
then a fresh read runs off the UI thread; it runs again whenever the app comes
back to the front, so a changed wallpaper shows up without a restart. On
Samsung One UI the system palette only changes once the user applies it in
Settings, which is when we pick it up too.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

import flet as ft

from tidewrack.services.settings import SettingsStore
from tidewrack.services.system_colours import SystemColours, read_system_colours


def themes(colours: SystemColours | None) -> tuple[ft.Theme | None, ft.Theme | None]:
    """(light, dark) themes for a wallpaper scheme; (None, None) = flet's defaults."""
    if colours is None:
        return None, None
    return (
        ft.Theme(color_scheme_seed=colours.seed, color_scheme=ft.ColorScheme(**colours.light)),
        ft.Theme(color_scheme_seed=colours.seed, color_scheme=ft.ColorScheme(**colours.dark)),
    )


class Theming:
    def __init__(
        self,
        page: ft.Page,
        settings: SettingsStore,
        read: Callable[[], SystemColours | None] = read_system_colours,
        background: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self.page = page
        self.settings = settings
        self.read = read
        # Our own thread, not page.run_thread: Flet 1.0.5 shuts its shared
        # executor down when Android rebuilds the window (e.g. a new system
        # palette) and keeps using it, so run_thread silently does nothing after.
        self.background = background or (
            lambda job: threading.Thread(target=job, daemon=True).start()
        )
        self.shown: SystemColours | None = None  # what this page is painted with

    def start(self) -> None:
        """Apply the cached scheme now; refresh it in the background."""
        self._apply(self.settings.load().system_colours)
        self.page.on_app_lifecycle_state_change = self._lifecycle
        self.background(self.refresh)

    def refresh(self) -> None:
        """Read the system scheme; cache it and repaint if it changed.

        Compared with what's on screen, not with the cache: after a palette
        change Android rebuilds the window and two refreshes race (start and
        resume); the one that loses finds the cache already updated but must
        still repaint its page. A failed read keeps the current colours.
        """
        colours = self.read()
        current = self.settings.load()
        if colours is None:
            return
        if colours != current.system_colours:
            self.settings.save(current.model_copy(update={"system_colours": colours}))
        if colours != self.shown:
            self._apply(colours)
            self.page.update()

    def _lifecycle(self, e: ft.AppLifecycleStateChangeEvent) -> None:
        if e.state == ft.AppLifecycleState.RESUME:
            self.background(self.refresh)

    def _apply(self, colours: SystemColours | None) -> None:
        self.shown = colours
        self.page.theme, self.page.dark_theme = themes(colours)

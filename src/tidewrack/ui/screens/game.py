"""The game screen: walk the dungeon of the open save slot.

Reads only Game.view() and sends only commands, through the GameSession so every
action autosaves (CLAUDE.md §4, §6). Flet re-renders after each event handler
returns, so handlers just update controls.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from tidewrack.core.engine.game import Command, Look, Move, Wait
from tidewrack.services.session import GameSession
from tidewrack.ui.map_canvas import MapCanvas
from tidewrack.version import get_build_info, version_label

LOG_LINES_SHOWN = 40


class GameScreen:
    def __init__(self, session: GameSession, on_back: Callable[[], None]) -> None:
        self.session = session
        self.version = version_label(get_build_info())

        self.dungeon_name = ft.Text(size=14, color=ft.Colors.ON_SURFACE_VARIANT, expand=True)
        self.location = ft.Text(size=26, weight=ft.FontWeight.BOLD)
        self.description = ft.Text(size=16)
        self.exits = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.log = ft.ListView(expand=True, spacing=6, auto_scroll=True)
        self.status = ft.Text(size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.map = MapCanvas(on_move=lambda label: self.act(Move(label)))
        self.map_toggle = ft.IconButton(
            icon=ft.Icons.MAP, selected_icon=ft.Icons.MAP_OUTLINED, on_click=self._toggle_map
        )

        actions = ft.Row(
            spacing=8,
            controls=[
                ft.OutlinedButton(
                    content="Look around", icon=ft.Icons.VISIBILITY, on_click=self._look
                ),
                ft.OutlinedButton(
                    content="Wait", icon=ft.Icons.HOURGLASS_EMPTY, on_click=self._wait
                ),
            ],
        )
        header = ft.Row(
            controls=[
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK,
                    tooltip="Back to worlds",
                    on_click=lambda _: on_back(),
                ),
                self.dungeon_name,
                self.map_toggle,
            ],
        )
        self.control = ft.SafeArea(
            expand=True,
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    expand=True,
                    spacing=12,
                    controls=[
                        header,
                        self.map.control,
                        self.location,
                        self.description,
                        self.exits,
                        actions,
                        ft.Divider(),
                        self.log,
                        self.status,
                    ],
                ),
            ),
        )
        self.refresh()

    # --- handlers ----------------------------------------------------------------

    def act(self, command: Command) -> None:
        self.session.perform(command)  # autosaves
        self.refresh()

    def _look(self, _: ft.Event) -> None:
        self.act(Look())

    def _wait(self, _: ft.Event) -> None:
        self.act(Wait())

    def _toggle_map(self, _: ft.Event) -> None:
        self.map.control.visible = not self.map.control.visible
        self.refresh()

    # --- rendering ---------------------------------------------------------------

    def refresh(self) -> None:
        view = self.session.game.view()
        self.dungeon_name.value = f"{self.session.meta.name} · {view.dungeon_name}"
        self.location.value = view.location
        self.description.value = view.description
        self.exits.controls = [
            ft.FilledTonalButton(
                content=exit_.label
                if exit_.destination is None
                else f"{exit_.label}  →  {exit_.destination}",
                on_click=lambda _, label=exit_.label: self.act(Move(label)),
            )
            for exit_ in view.exits
        ]
        self.log.controls = [ft.Text(line, size=14) for line in view.log[-LOG_LINES_SHOWN:]]
        self.map_toggle.visible = view.map is not None
        if view.map is None:
            self.map.control.visible = False
        else:
            self.map.show(view.map, view.total_nodes)
        shown = self.map.control.visible
        self.map_toggle.selected = not shown
        self.map_toggle.tooltip = "Hide map" if shown else "Show map"
        self.status.value = (
            f"Turn {view.turn} · Explored {view.visited}/{view.total_nodes} · "
            f"Seed {view.seed:x} · {self.version}"
        )

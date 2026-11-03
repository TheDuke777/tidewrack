"""Step-1 text screen: walk the hand-authored dungeon.

Reads only Game.view() and sends only commands (CLAUDE.md §4). Flet re-renders
after each event handler returns, so handlers just update controls.
"""

from __future__ import annotations

import secrets

import flet as ft

from tidewrack.core.data.loader import Content
from tidewrack.core.engine.game import Command, Game, Look, Move, Wait
from tidewrack.version import get_build_info, version_label

LOG_LINES_SHOWN = 40
START_DUNGEON = "dungeon.first_descent"


def new_seed() -> int:
    # The UI picks fresh seeds; core itself never touches system randomness.
    return secrets.randbits(63)


class GameScreen:
    def __init__(self, content: Content) -> None:
        self.dungeon = content.dungeon(START_DUNGEON)
        self.game = Game(new_seed(), self.dungeon)
        self.version = version_label(get_build_info())

        self.dungeon_name = ft.Text(size=14, color=ft.Colors.ON_SURFACE_VARIANT)
        self.location = ft.Text(size=26, weight=ft.FontWeight.BOLD)
        self.description = ft.Text(size=16)
        self.exits = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.log = ft.ListView(expand=True, spacing=6, auto_scroll=True)
        self.status = ft.Text(size=12, color=ft.Colors.ON_SURFACE_VARIANT)

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
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                self.dungeon_name,
                ft.TextButton(content="New run", icon=ft.Icons.REFRESH, on_click=self._new_run),
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
        self.game.perform(command)
        self.refresh()

    def _look(self, _: ft.Event) -> None:
        self.act(Look())

    def _wait(self, _: ft.Event) -> None:
        self.act(Wait())

    def _new_run(self, _: ft.Event) -> None:
        self.game = Game(new_seed(), self.dungeon)
        self.refresh()

    # --- rendering ---------------------------------------------------------------

    def refresh(self) -> None:
        view = self.game.view()
        self.dungeon_name.value = view.dungeon_name
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
        self.status.value = (
            f"Turn {view.turn} · Explored {view.visited}/{view.total_nodes} · "
            f"Seed {view.seed:x} · {self.version}"
        )

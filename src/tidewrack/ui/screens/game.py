"""The game screen: explore the rooms of a location and travel between locations.

Reads only Game.view() and sends only commands, through the GameSession so every
action autosaves (CLAUDE.md §4, §6). Flet re-renders after each event handler
returns, so handlers just update controls.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from tidewrack.core.engine.game import Command, GameView, Look, Move, Travel, Wait
from tidewrack.services.session import GameSession
from tidewrack.ui.map_canvas import MapCanvas
from tidewrack.version import get_build_info, version_label

LOG_LINES_SHOWN = 40

ROOM_LEGEND = "● visited   ○ unexplored   ◉ you   — tap a ringed room to go there"
WORLD_LEGEND = "● visited   ○ unexplored   ◉ you   — at a gate, tap a ringed place to travel"


class GameScreen:
    def __init__(self, session: GameSession, on_back: Callable[[], None]) -> None:
        self.session = session
        self.version = version_label(get_build_info())

        self.where = ft.Text(size=14, color=ft.Colors.ON_SURFACE_VARIANT, expand=True)
        self.room = ft.Text(size=26, weight=ft.FontWeight.BOLD)
        self.description = ft.Text(size=16)
        self.exits = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.roads = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.log = ft.ListView(expand=2, spacing=6, auto_scroll=True)
        self.status = ft.Text(size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.map = MapCanvas(on_command=self.act)
        # Which map is showing: the rooms here ("area"), the world, or none.
        self.map_choice = ft.SegmentedButton(
            allow_empty_selection=True,
            show_selected_icon=False,
            selected=["area"],
            segments=[
                ft.Segment(value="area", icon=ft.Icons.MAP_OUTLINED, tooltip="Map of this place"),
                ft.Segment(value="world", icon=ft.Icons.PUBLIC, tooltip="World map"),
            ],
            on_change=lambda _: self.refresh(),
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
        # The room text and buttons scroll on their own, under a fixed map, and the
        # log below scrolls separately (it follows the newest line).
        self.details = ft.ListView(
            expand=3,
            spacing=12,
            controls=[self.room, self.description, self.exits, self.roads, actions],
        )
        self._shown_room: tuple[str, str] | None = None
        header = ft.Row(
            controls=[
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK,
                    tooltip="Back to worlds",
                    on_click=lambda _: on_back(),
                ),
                self.where,
                self.map_choice,
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
                        self.details,
                        ft.Divider(height=1),
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

    # --- rendering ---------------------------------------------------------------

    def refresh(self) -> None:
        view = self.session.game.view()
        self.where.value = f"{self.session.meta.name} · {view.location} · {view.kind}"
        self.room.value = view.room
        self.description.value = view.description
        if self._shown_room not in (None, (view.location, view.room)):
            self._scroll_details_to_top()
        self._shown_room = (view.location, view.room)
        self.exits.controls = [
            ft.FilledTonalButton(
                content=exit_.label
                if exit_.destination is None
                else f"{exit_.label}  →  {exit_.destination}",
                on_click=lambda _, label=exit_.label: self.act(Move(label)),
            )
            for exit_ in view.exits
        ]
        self.roads.controls = self._roads(view)
        self.log.controls = [ft.Text(line, size=14) for line in view.log[-LOG_LINES_SHOWN:]]

        # Worlds saved before v0.4 have no world map; the oldest have no room map.
        area, world = self.map_choice.segments
        area.disabled, world.disabled = view.map is None, view.world_map is None
        self.map_choice.visible = not (area.disabled and world.disabled)
        choice = (self.map_choice.selected or [None])[0]
        shown = {"area": view.map, "world": view.world_map}.get(choice)
        self.map.control.visible = shown is not None
        if shown is not None:
            on_world = choice == "world"
            self.map.show(shown, WORLD_LEGEND if on_world else ROOM_LEGEND, labels=on_world)

        self.status.value = (
            f"Turn {view.turn} · Rooms {view.rooms_visited}/{view.total_rooms} · "
            f"Places {view.locations_visited}/{view.total_locations} · "
            f"Seed {view.seed:x} · {self.version}"
        )

    def _scroll_details_to_top(self) -> None:
        """A new room starts at its name, not wherever the last one was scrolled to."""
        try:
            page = self.control.page
        except RuntimeError:  # not on screen yet
            return
        if page is not None:
            page.run_task(self.details.scroll_to, offset=0)

    def _roads(self, view: GameView) -> list[ft.Control]:
        if not view.roads:
            return []
        if not view.at_gate:
            gates = " or ".join(view.gates)
            return [
                ft.Text(
                    f"Roads out of {view.location} leave from {gates}.",
                    size=14,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            ]
        return [
            ft.FilledButton(
                content=f"Travel to {road.name} · {road.kind}"
                + ("" if road.visited else "  (unexplored)"),
                icon=ft.Icons.SIGNPOST_OUTLINED,
                on_click=lambda _, to=road.location: self.act(Travel(to)),
            )
            for road in view.roads
        ]

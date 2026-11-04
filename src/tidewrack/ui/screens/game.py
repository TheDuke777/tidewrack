"""The game screen: explore the rooms of a location and travel between locations.

Reads only Game.view() and sends only commands, through the GameSession so every
action autosaves (CLAUDE.md §4, §6). Flet re-renders after each event handler
returns, so handlers just update controls.

Below the map, the room details and the log share the space. The bar between
them hides or shows the log when tapped and resizes it when dragged (dragging it
to the bottom hides it); the choice is an app-wide setting, not part of the save.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import flet as ft

from tidewrack.core.engine.game import Command, GameView, Look, Move, Travel, Wait
from tidewrack.services.session import GameSession
from tidewrack.services.settings import Settings, SettingsStore
from tidewrack.ui.map_canvas import MapCanvas
from tidewrack.version import get_build_info, version_label

LOG_LINES_SHOWN = 40

ROOM_LEGEND = "● visited   ○ unexplored   ◉ you   — tap a ringed room to go there"
WORLD_LEGEND = "● visited   ○ unexplored   ◉ you   — at a gate, tap a ringed place to travel"

MIN_LOG_SHARE, MAX_LOG_SHARE = 0.1, 0.8  # same bounds as Settings.log_share
HIDE_LOG_BELOW = 0.06  # dragging the log smaller than this hides it


@dataclass
class LogSplit:
    """How the text area below the map is split between room details and the log."""

    visible: bool
    share: float  # the log's fraction while visible; kept while hidden
    _dragged: float = 0.0  # the share the drag has reached, possibly below the minimum

    def toggle(self) -> None:
        self.visible = not self.visible

    def start_drag(self) -> None:
        self._dragged = self.share if self.visible else 0.0

    def drag(self, fraction: float) -> None:
        """Move the bar by `fraction` of the area's height (negative = up = bigger log)."""
        self._dragged = min(MAX_LOG_SHARE, self._dragged - fraction)
        self.visible = self._dragged >= HIDE_LOG_BELOW
        if self.visible:
            self.share = max(MIN_LOG_SHARE, self._dragged)

    def expands(self) -> tuple[int, int]:
        """Flet `expand` weights for (details, log)."""
        if not self.visible:
            return 1, 0
        return round((1 - self.share) * 100), round(self.share * 100)


class GameScreen:
    def __init__(
        self, session: GameSession, settings: SettingsStore, on_back: Callable[[], None]
    ) -> None:
        self.session = session
        self.settings = settings
        saved = settings.load()
        self.split = LogSplit(saved.log_visible, saved.log_share)
        self.version = version_label(get_build_info())

        self.where = ft.Text(size=14, color=ft.Colors.ON_SURFACE_VARIANT, expand=True)
        self.room = ft.Text(size=26, weight=ft.FontWeight.BOLD)
        self.description = ft.Text(size=16)
        self.exits = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.roads = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.log = ft.ListView(spacing=6, auto_scroll=True)
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
            spacing=12,
            controls=[self.room, self.description, self.exits, self.roads, actions],
        )
        self.log_hint = ft.Text(
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            expand=True,
        )
        self.log_chevron = ft.Icon(
            ft.Icons.EXPAND_MORE, size=20, color=ft.Colors.ON_SURFACE_VARIANT
        )
        log_bar = ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.RESIZE_ROW,
            drag_interval=16,
            on_tap=lambda _: self._toggle_log(),
            on_vertical_drag_start=lambda _: self.split.start_drag(),
            on_vertical_drag_update=self._drag_log,
            on_vertical_drag_end=lambda _: self._save_split(),
            content=ft.Container(
                height=36,
                border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
                content=ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.DRAG_HANDLE, size=20, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text("Log", size=13, weight=ft.FontWeight.BOLD),
                        self.log_hint,
                        self.log_chevron,
                    ],
                ),
            ),
        )
        self._panes_height = 400.0  # until the first size report
        self.panes = ft.Column(
            expand=True,
            spacing=0,
            controls=[self.details, log_bar, self.log],
            on_size_change=self._panes_resized,
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
                        self.panes,
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

    def _toggle_log(self) -> None:
        self.split.toggle()
        self._save_split()

    def _drag_log(self, e: ft.DragUpdateEvent) -> None:
        delta = e.primary_delta if e.primary_delta is not None else e.local_delta.y
        self.split.drag(delta / max(self._panes_height, 1.0))
        self._apply_split()

    def _panes_resized(self, e: ft.LayoutSizeChangeEvent) -> None:
        self._panes_height = e.height

    def _save_split(self) -> None:
        self._apply_split()
        self.settings.save(Settings(log_visible=self.split.visible, log_share=self.split.share))

    def _apply_split(self) -> None:
        self.details.expand, self.log.expand = self.split.expands()
        self.log.visible = self.split.visible
        self.log_chevron.icon = ft.Icons.EXPAND_MORE if self.split.visible else ft.Icons.EXPAND_LESS
        # While the log is hidden, its newest line still shows in the bar.
        self.log_hint.visible = not self.split.visible

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
        self.log_hint.value = view.log[-1] if view.log else ""
        self._apply_split()

        # Worlds saved before v0.4 have no world map; the oldest have no room map.
        area, world = self.map_choice.segments
        area.disabled, world.disabled = view.map is None, view.world_map is None
        self.map_choice.visible = not (area.disabled and world.disabled)
        choice = (self.map_choice.selected or [None])[0]
        shown = {"area": view.map, "world": view.world_map}.get(choice)
        self.map.control.visible = shown is not None
        if shown is not None:
            on_world = choice == "world"
            self.map.show(
                shown,
                WORLD_LEGEND if on_world else ROOM_LEGEND,
                key=(choice, view.location),  # a new map or place resets the zoom
                labels=on_world,
            )

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

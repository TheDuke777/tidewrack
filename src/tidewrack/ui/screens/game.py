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

from tidewrack.core.engine.events import QuestCompleted
from tidewrack.core.engine.game import (
    AcceptQuest,
    Command,
    Equip,
    GameView,
    ItemView,
    Look,
    Move,
    Take,
    Travel,
    TurnInQuest,
    Wait,
)
from tidewrack.services.session import GameSession
from tidewrack.services.settings import Settings, SettingsStore
from tidewrack.ui.components.combat_panel import combat_panel
from tidewrack.ui.components.gear_compare_card import gear_compare_card
from tidewrack.ui.components.quest_card import quest_card
from tidewrack.ui.map_canvas import MapCanvas, kinds_legend

LOG_LINES_SHOWN = 40

ROOM_LEGEND = (
    "● visited   ○ unexplored   ◉ you   ■ gate (roads leave from here)\n"
    "✦ items left here   ◆ quest target\n"
    "Tap a ringed room to go there."
)
WORLD_LEGEND = (
    "● visited   ○ unexplored   ◉ you   ✓ fully explored   ◆ quest\n"
    "At a gate, tap a ringed place to travel."
)

MIN_LOG_SHARE, MAX_LOG_SHARE = 0.1, 0.8  # same bounds as Settings.log_share
HIDE_LOG_BELOW = 0.06  # dragging the log smaller than this hides it
LOG_BAR_HEIGHT = 36
DRAG_INTERVAL = 30  # ms between drag updates sent to Python; positions are absolute


@dataclass
class LogSplit:
    """How the text area below the map is split between room details and the log."""

    visible: bool
    share: float  # the log's fraction while visible; kept while hidden
    _start: float = 0.0  # the log's share when the drag began (0 if hidden)

    def toggle(self) -> None:
        self.visible = not self.visible

    def start_drag(self) -> None:
        self._start = self.share if self.visible else 0.0

    def drag_to(self, offset: float) -> None:
        """Put the bar `offset` (a fraction of the area's height) from where the drag
        began; negative = up = bigger log. Absolute, not incremental, so throttled
        or dropped touch events can't make the bar lag behind the finger."""
        reached = min(MAX_LOG_SHARE, self._start - offset)
        self.visible = reached >= HIDE_LOG_BELOW
        if self.visible:
            self.share = max(MIN_LOG_SHARE, reached)

    def expands(self) -> tuple[int, int]:
        """Flet `expand` weights for (details, log)."""
        if not self.visible:
            return 1, 0
        return round((1 - self.share) * 100), round(self.share * 100)


class GameScreen:
    def __init__(
        self,
        session: GameSession,
        settings: SettingsStore,
        on_back: Callable[[], None],
        notify: Callable[[str], None] = lambda _: None,
    ) -> None:
        self.session = session
        self.notify = notify
        self.settings = settings
        saved = settings.load()
        self.split = LogSplit(saved.log_visible, saved.log_share)

        self.where = ft.Text(size=14, color=ft.Colors.ON_SURFACE_VARIANT, expand=True)
        self.room = ft.Text(size=26, weight=ft.FontWeight.BOLD)
        self.description = ft.Text(size=16)
        self.here = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.board = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
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

        self.wait_button = ft.OutlinedButton(
            content="Wait", icon=ft.Icons.HOURGLASS_EMPTY, on_click=self._wait
        )
        self.actions = ft.Row(
            spacing=8,
            controls=[
                ft.OutlinedButton(
                    content="Look around", icon=ft.Icons.VISIBILITY, on_click=self._look
                ),
                self.wait_button,
            ],
        )
        self.combat = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        # The room text and buttons scroll on their own, under a fixed map, and the
        # log below scrolls separately (it follows the newest line).
        self.details = ft.ListView(
            spacing=12,
            controls=[
                self.room,
                self.description,
                self.combat,
                self.board,
                self.here,
                self.exits,
                self.roads,
                self.actions,
            ],
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
            drag_interval=DRAG_INTERVAL,
            on_tap=lambda _: self._toggle_log(),
            on_vertical_drag_start=self._log_drag_started,
            on_vertical_drag_update=self._drag_log,
            on_vertical_drag_end=self._log_drag_ended,
            content=ft.Container(
                height=LOG_BAR_HEIGHT,
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
        self._drag_start_y = 0.0
        self.panes = ft.Column(
            expand=True,
            spacing=0,
            controls=[self.details, log_bar, self.log],
            on_size_change=self._panes_resized,
        )
        self._shown_room: tuple[str, str] | None = None
        self._was_fighting = False
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

    def _log_drag_started(self, e: ft.DragStartEvent) -> None:
        self._drag_start_y = e.global_position.y
        self.split.start_drag()

    def _drag_log(self, e: ft.DragUpdateEvent) -> None:
        self._follow_finger(e.global_position.y)
        self._apply_split()

    def _log_drag_ended(self, e: ft.DragEndEvent) -> None:
        if e.global_position is not None:
            self._follow_finger(e.global_position.y)
        self._save_split()

    def _follow_finger(self, y: float) -> None:
        # The bar itself doesn't stretch; only the two panes share the drag.
        shared = max(self._panes_height - LOG_BAR_HEIGHT, 1.0)
        self.split.drag_to((y - self._drag_start_y) / shared)

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
        self.here.controls = [
            gear_compare_card(item, self._take_buttons(item)) for item in view.items_here
        ]
        # During a fight, the fight panel replaces everything you can't do anyway.
        fighting = view.combat is not None
        if fighting and not self._was_fighting:
            self._scroll_details_to_top()  # the fight panel is the first thing you see
        self._was_fighting = fighting
        self.combat.controls = [combat_panel(view, self.act)] if fighting else []
        self.board.controls = self._board(view)
        for section in (self.board, self.here, self.exits, self.roads, self.actions):
            section.visible = not fighting
        resting = view.in_town and view.hp < view.max_hp
        self.wait_button.content = "Rest" if resting else "Wait"
        self.wait_button.icon = ft.Icons.BED_OUTLINED if resting else ft.Icons.HOURGLASS_EMPTY
        self.log.controls = [ft.Text(line, size=14) for line in view.log[-LOG_LINES_SHOWN:]]
        self.log_hint.value = view.log[-1] if view.log else ""
        self._apply_split()

        # Worlds saved before v0.4 have no world map; the oldest have no room map.
        area, world = self.map_choice.segments
        area.disabled, world.disabled = view.map is None, view.world_map is None
        # A fight takes over the screen: no map, so it's obvious one has started.
        self.map_choice.visible = not (area.disabled and world.disabled) and not fighting
        choice = (self.map_choice.selected or [None])[0]
        shown = {"area": view.map, "world": view.world_map}.get(choice)
        self.map.control.visible = shown is not None and not fighting
        if shown is not None:
            on_world = choice == "world"
            legend = f"{kinds_legend(shown)}\n{WORLD_LEGEND}" if on_world else ROOM_LEGEND
            self.map.show(
                shown,
                legend,
                key=(choice, view.location),  # a new map or place resets the zoom
                labels=on_world,
            )

        # Progress only: stats live in the inventory, and seed and version will go to
        # Settings → About. Settings will also get a toggle to hide this row.
        self.status.value = (
            f"Turn {view.turn} · Rooms {view.rooms_visited}/{view.total_rooms} · "
            f"Places {view.locations_visited}/{view.total_locations}"
        )

    def _scroll_details_to_top(self) -> None:
        """A new room starts at its name, not wherever the last one was scrolled to."""
        try:
            page = self.control.page
        except RuntimeError:  # not on screen yet
            return
        if page is not None:
            page.run_task(self.details.scroll_to, offset=0)

    def _board(self, view: GameView) -> list[ft.Control]:
        if view.board is None:
            return []
        if not view.board:
            heading = "Notice board · nothing new pinned up"
        else:
            heading = "Notice board"
        cards: list[ft.Control] = [ft.Text(heading, size=18, weight=ft.FontWeight.BOLD)]
        for quest in view.board:
            if quest.state == "ready":
                button = ft.FilledButton(
                    content="Turn in",
                    icon=ft.Icons.TASK_ALT,
                    on_click=lambda _, q=quest.id: self._turn_in(q),
                )
            else:
                button = ft.FilledTonalButton(
                    content="Accept",
                    icon=ft.Icons.ADD_TASK,
                    on_click=lambda _, q=quest.id: self.act(AcceptQuest(q)),
                )
            cards.append(quest_card(quest, [button]))
        return cards

    def _turn_in(self, quest: str) -> None:
        result = self.session.perform(TurnInQuest(quest))
        # Refresh first: showing the toast pushes an update to the page at once, and
        # anything changed after it could reach the screen late (the turned-in card
        # stayed on the board until the next tap).
        self.refresh()
        for event in result.events:
            if isinstance(event, QuestCompleted):
                self.notify(f"{event.reward} added to your pack.")

    def _take_buttons(self, item: ItemView) -> list[ft.Control]:
        return [
            ft.FilledButton(
                content="Take & equip",
                icon=ft.Icons.CHECK,
                on_click=lambda _, i=item.id: self._take_and_equip(i),
            ),
            ft.OutlinedButton(
                content="Take",
                icon=ft.Icons.BACKPACK_OUTLINED,
                on_click=lambda _, i=item.id: self.act(Take(i)),
            ),
        ]

    def _take_and_equip(self, item: int) -> None:
        self.session.perform(Take(item))
        self.act(Equip(item))

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

"""Point-crawl map with fog of war, drawn on a Flet canvas (CLAUDE.md §3, §8).

Draws one MapView from Game.view(): the rooms of this location or the locations
of the world, only as far as the player knows them. State is shown by shape as
well as colour (§11): filled = visited, hollow = seen but unvisited, large dot
inside a ring = you, extra outer ring = one step away (tap it to go there).
Gate rooms (where roads leave from) are rounded squares instead of circles, and
on the world map each place's name starts with a glyph for its kind (⌂ town…).

Pinch to zoom and drag to pan. Zooming spreads the map out rather than
magnifying it, so dots and labels stay readable on big maps; the view is handled
here (Viewport) rather than by Flet's InteractiveViewer so taps, "centre on me"
and following the player all use the same coordinates.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass

import flet as ft
import flet.canvas as cv

from tidewrack.core.engine.game import Command, MapNode, MapView

MAP_HEIGHT = 260
BACKGROUND = ft.Colors.SURFACE_CONTAINER_HIGHEST
PAD = 20
DEFAULT_WIDTH = 360  # until the first resize event reports the real size
MIN_TOUCH_RADIUS = 24  # px; generous, since dots can be small on big maps
LABEL_WIDTH = 96  # px; place names wrap onto a second line beyond this
LABEL_SIZE = 11
REGION_SIZE = 13
CHAR_WIDTH = 0.58 * LABEL_SIZE  # rough average glyph width, for estimating label boxes
LINE_HEIGHT = 1.3 * LABEL_SIZE
MAX_ZOOM = 4.0
FOCUS_ZOOM = 2.0  # maps open this far in; "centre on me" zooms in at least this far
FOLLOW_MARGIN = 0.15  # recentre when you walk within this fraction of the edge
REDRAW_INTERVAL = 0.03  # s; at most ~30 redraws a second while pinching/panning

# A glyph per location kind for world-map labels and the legend; unknown kinds
# (new roomsets before this list is updated) fall back to a plain dot.
KIND_GLYPHS = {
    "Town": "⌂",
    "Sea Caves": "≈",
    "Forest": "♣",
    "Mine": "⚒",
    "Dungeon": "▼",
    "Stilt Village": "⌂",
    "Peat Bog": "∴",
    "Reed Maze": "¦",
    "Mere": "○",
    "Hill Farm": "⌂",
    "Heath": "⚘",
    "Barrows": "∩",
    "Standing Stones": "Π",
}
DEFAULT_GLYPH = "•"
# Kinds the legend files under another kind's name (same glyph, same role).
LEGEND_NAMES = {"Stilt Village": "Town", "Hill Farm": "Town"}

Point = tuple[float, float]
Box = tuple[float, float, float, float]  # left, top, right, bottom


@dataclass
class Viewport:
    """Zoom and pan: screen = content * zoom + offset. At zoom 1 the whole map fits."""

    zoom: float = 1.0
    ox: float = 0.0
    oy: float = 0.0

    def to_screen(self, p: Point) -> Point:
        return (p[0] * self.zoom + self.ox, p[1] * self.zoom + self.oy)

    def to_content(self, p: Point) -> Point:
        return ((p[0] - self.ox) / self.zoom, (p[1] - self.oy) / self.zoom)

    def place(self, anchor: Point, screen: Point, zoom: float, size: Point) -> None:
        """Zoom to `zoom` with content point `anchor` under `screen`, kept in bounds."""
        self.zoom = min(MAX_ZOOM, max(1.0, zoom))
        w, h = size
        # The content (w*zoom by h*zoom) must always cover the view: no empty gutters.
        self.ox = min(0.0, max(w - w * self.zoom, screen[0] - anchor[0] * self.zoom))
        self.oy = min(0.0, max(h - h * self.zoom, screen[1] - anchor[1] * self.zoom))

    def centre_on(self, anchor: Point, size: Point, zoom: float | None = None) -> None:
        self.place(anchor, (size[0] / 2, size[1] / 2), zoom or self.zoom, size)

    def shows(self, p: Point, size: Point, margin: float) -> bool:
        x, y = self.to_screen(p)
        mx, my = size[0] * margin, size[1] * margin
        return mx <= x <= size[0] - mx and my <= y <= size[1] - my


class MapCanvas:
    def __init__(
        self,
        on_command: Callable[[Command], None],
        on_blocked: Callable[[str], None] = lambda _: None,
        legend_open: bool = True,
        on_legend: Callable[[bool], None] = lambda _: None,
    ) -> None:
        self.on_command = on_command
        self.on_blocked = on_blocked  # told why a tapped place can't be reached yet
        self.on_legend = on_legend  # told when the legend is shown or hidden (to remember it)
        self.view: MapView | None = None
        self.labels = False
        self.width, self.height = DEFAULT_WIDTH, MAP_HEIGHT
        self.viewport = Viewport()
        self._key: Hashable = None
        # Each kind of map ("area", "world") keeps the zoom you last left it at, so a
        # new place or a new room doesn't throw you back out to the whole map.
        self._zoom_key: Hashable = None
        self._zooms: dict[Hashable, float] = {}
        self._base: dict[str, Point] = {}  # node positions at zoom 1
        self._points: dict[str, Point] = {}  # on screen
        self._gesture: tuple[float, Point] | None = None  # zoom and anchor at start
        # Label spots relative to their dots, kept while a gesture moves the map:
        # placing labels is the slow part of a redraw, so it waits for the end.
        self._label_offsets: dict[str, Point] = {}
        self._last_draw = 0.0

        self.canvas = cv.Canvas(expand=True, on_resize=self._resized, resize_interval=100)
        self.legend = ft.Text(size=12, color=ft.Colors.ON_SURFACE_VARIANT, visible=legend_open)
        self.legend_button = ft.IconButton(
            icon=ft.Icons.LEGEND_TOGGLE_OUTLINED,
            selected_icon=ft.Icons.LEGEND_TOGGLE,
            selected=legend_open,
            icon_size=20,
            tooltip="Show or hide the legend",
            on_click=lambda _: self._toggle_legend(),
        )
        self.fit_button = ft.IconButton(
            icon=ft.Icons.ZOOM_OUT_MAP,
            icon_size=20,
            tooltip="Show the whole map",
            visible=False,
            on_click=lambda _: self._fit(),
        )
        buttons = ft.Container(
            right=4,
            top=4,
            content=ft.Row(
                spacing=0,
                controls=[
                    self.legend_button,
                    self.fit_button,
                    ft.IconButton(
                        icon=ft.Icons.MY_LOCATION,
                        icon_size=20,
                        tooltip="Centre on me",
                        on_click=lambda _: self._centre_on_me(),
                    ),
                ],
            ),
        )
        gestures = ft.GestureDetector(
            content=self.canvas,
            on_tap_up=self._tapped,  # not tap_down: that would fire at the start of a pan
            on_scale_start=self._gesture_started,
            on_scale_update=self._gesture_moved,
            on_scale_end=self._gesture_ended,
        )
        self.control = ft.Column(
            spacing=4,
            controls=[
                ft.Container(
                    height=MAP_HEIGHT,
                    border_radius=12,
                    bgcolor=BACKGROUND,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                    content=ft.Stack(expand=True, controls=[gestures, buttons]),
                ),
                self.legend,
            ],
        )

    def show(
        self,
        view: MapView,
        legend: str,
        key: Hashable,
        labels: bool = False,
        zoom_key: Hashable = None,
    ) -> None:
        """Draw `view`; with `labels`, known node names are written beside them.

        A new `key` (another map, or another location) centres on the player at
        the zoom last used for `zoom_key` (FOCUS_ZOOM at first); otherwise the
        view follows the player if they walk off the edge of it.
        """
        self.view, self.labels = view, labels
        self.legend.value = legend
        self._layout()
        here = self._current()
        if key != self._key:
            self._remember_zoom()
            self._key, self._zoom_key = key, zoom_key
            zoom = self._zooms.get(zoom_key, FOCUS_ZOOM)
            self.viewport = Viewport()
            if here is not None:
                self.viewport.centre_on(here, self._size, zoom)
        elif here is not None and not self.viewport.shows(here, self._size, FOLLOW_MARGIN):
            self.viewport.centre_on(here, self._size)
        self._draw()

    def _remember_zoom(self) -> None:
        if self._key is not None:
            self._zooms[self._zoom_key] = self.viewport.zoom

    def _toggle_legend(self) -> None:
        self.legend.visible = not self.legend.visible
        self.legend_button.selected = self.legend.visible
        self.on_legend(self.legend.visible)
        self._update(self.legend, self.legend_button)

    @staticmethod
    def _update(*controls: ft.Control) -> None:
        for control in controls:
            try:
                control.update()
            except RuntimeError:  # not on a page (tests)
                pass

    @property
    def _size(self) -> Point:
        return (self.width, self.height)

    def _current(self) -> Point | None:
        assert self.view is not None
        return next((self._base[n.id] for n in self.view.nodes if n.state == "current"), None)

    # --- events ------------------------------------------------------------------

    def _resized(self, e: cv.CanvasResizeEvent) -> None:
        if (e.width, e.height) == (self.width, self.height):
            return
        # Keep the zoom (the layout often settles after a move); just stay on you.
        zoom = self.viewport.zoom
        self.width, self.height = e.width, e.height
        self.viewport = Viewport()
        self._layout()
        here = self._current() if self.view else None
        if here is not None:
            self.viewport.centre_on(here, self._size, zoom)
        self._draw()

    def _tapped(self, e: ft.TapEvent) -> None:
        if self.view is None or e.local_position is None:
            return
        tx, ty = e.local_position.x, e.local_position.y
        best, best_distance = None, max(MIN_TOUCH_RADIUS, self._radius() * 2.5)
        for node in self.view.nodes:
            if node.command is None and node.blocked is None:
                continue
            x, y = self._points[node.id]
            distance = math.hypot(x - tx, y - ty)
            if distance <= best_distance:
                best, best_distance = node, distance
        if best is None:
            return
        if best.command is not None:
            self.on_command(best.command)
        elif best.blocked is not None:
            self.on_blocked(best.blocked)

    def _gesture_started(self, e: ft.ScaleStartEvent) -> None:
        focal = (e.local_focal_point.x, e.local_focal_point.y)
        self._gesture = (self.viewport.zoom, self.viewport.to_content(focal))

    def _gesture_moved(self, e: ft.ScaleUpdateEvent) -> None:
        if self._gesture is None:
            return
        zoom, anchor = self._gesture
        focal = (e.local_focal_point.x, e.local_focal_point.y)
        self.viewport.place(anchor, focal, zoom * (e.scale or 1.0), self._size)
        if time.monotonic() - self._last_draw >= REDRAW_INTERVAL:
            self._draw()

    def _gesture_ended(self, _: ft.ScaleEndEvent) -> None:
        self._gesture = None
        self._draw()  # labels placed properly again

    def _centre_on_me(self) -> None:
        here = self._current() if self.view else None
        if here is not None:
            self.viewport.centre_on(here, self._size, max(self.viewport.zoom, FOCUS_ZOOM))
            self._draw()

    def _fit(self) -> None:
        self.viewport = Viewport()
        self._remember_zoom()
        self._draw()

    # --- drawing -----------------------------------------------------------------

    def _radius(self) -> float:
        # Roughly a third of a grid cell, clamped so small maps don't get huge dots;
        # grows a little when zoomed in, much less than the map spreads out.
        side = math.ceil(math.sqrt((self.view.size if self.view else 1) * 1.8))
        base = max(4.0, min(10.0, min(self.width, self.height) / side * 0.28))
        return min(12.0, base * self.viewport.zoom**0.3)

    def _layout(self) -> None:
        if self.view is None:
            return
        w, h = self.width, self.height
        self._base = {
            n.id: (PAD + n.x * (w - 2 * PAD), PAD + n.y * (h - 2 * PAD)) for n in self.view.nodes
        }

    def _draw(self) -> None:
        if self.view is None:
            return
        self._last_draw = time.monotonic()
        self.fit_button.visible = self.viewport.zoom > 1.0
        r = self._radius()
        self._points = {i: self.viewport.to_screen(p) for i, p in self._base.items()}
        path = ft.Paint(color=ft.Colors.OUTLINE, stroke_width=2, style=ft.PaintingStyle.STROKE)
        shapes: list[cv.Shape] = [
            cv.Line(*self._points[a], *self._points[b], paint=path)
            for a, b in self.view.edges
            if self._on_screen_line(self._points[a], self._points[b])
        ]
        for node in self.view.nodes:
            x, y = self._points[node.id]
            if not self._on_screen((x, y), r + 8):
                continue
            mark = _square if node.gate else _circle
            if node.state == "current":
                shapes += [
                    mark(x, y, r + 2, _fill(ft.Colors.PRIMARY)),
                    mark(x, y, r + 6, _ring(ft.Colors.PRIMARY, 2.5)),
                ]
            elif node.state == "visited":
                shapes.append(mark(x, y, r, _fill(ft.Colors.SECONDARY)))
            else:  # hollow; filled with the background so paths don't show through it
                shapes += [
                    mark(x, y, r, _fill(BACKGROUND)),
                    mark(x, y, r, _ring(ft.Colors.ON_SURFACE_VARIANT, 2)),
                ]
            if node.command is not None:
                shapes.append(mark(x, y, r + 5, _ring(ft.Colors.TERTIARY, 1.5)))
            if not self.labels:  # area maps: badges (world maps say it in the labels)
                shapes += _badges(node, x, y, r)
        if self.labels:
            shapes = self._region_names() + shapes + self._labels(r)
        self.canvas.shapes = shapes

    def _region_names(self) -> list[cv.Shape]:
        """Region names behind everything else, faint, where their places are."""
        assert self.view is not None
        w, h = self.width, self.height
        return [
            cv.Text(
                *self.viewport.to_screen(
                    (PAD + mark.x * (w - 2 * PAD), PAD + mark.y * (h - 2 * PAD))
                ),
                mark.name.upper(),
                style=ft.TextStyle(
                    size=REGION_SIZE,
                    color=ft.Colors.OUTLINE,
                    weight=ft.FontWeight.BOLD,
                    letter_spacing=2,
                ),
                alignment=ft.Alignment.CENTER,
                text_align=ft.TextAlign.CENTER,
            )
            for mark in self.view.regions
        ]

    def _on_screen(self, p: Point, margin: float) -> bool:
        return -margin <= p[0] <= self.width + margin and -margin <= p[1] <= self.height + margin

    def _on_screen_line(self, a: Point, b: Point) -> bool:
        return not (
            max(a[0], b[0]) < 0
            or min(a[0], b[0]) > self.width
            or max(a[1], b[1]) < 0
            or min(a[1], b[1]) > self.height
        )

    def _labels(self, r: float) -> list[cv.Shape]:
        assert self.view is not None
        names = {
            n.id: label(n.name, n.kind, quest=n.quest, charted=n.charted, guarded=n.guarded)
            for n in self.view.nodes
            if n.name
        }
        if self._gesture is not None and set(self._label_offsets) == set(names):
            spots = {
                i: (self._points[i][0] + dx, self._points[i][1] + dy)
                for i, (dx, dy) in self._label_offsets.items()
            }
        else:
            spots = place_labels(self._points, names, self.view.edges, r, self.width, self.height)
            self._label_offsets = {
                i: (x - self._points[i][0], y - self._points[i][1]) for i, (x, y) in spots.items()
            }
        return [
            cv.Text(
                x,
                y,
                names[node_id],
                style=ft.TextStyle(size=LABEL_SIZE, color=ft.Colors.ON_SURFACE),
                alignment=ft.Alignment.TOP_CENTER,
                text_align=ft.TextAlign.CENTER,
                max_width=LABEL_WIDTH,
                max_lines=2,
            )
            for node_id, (x, y) in spots.items()
            if self._on_screen((x, y), LABEL_WIDTH)
        ]


QUEST_MARK, CHARTED_MARK, ITEMS_MARK, SHOP_MARK = "◆", "✓", "✦", "¤"
GUARD_MARK = "⚔"


def label(
    name: str,
    kind: str | None,
    quest: bool = False,
    charted: bool = False,
    guarded: bool = False,
) -> str:
    """A node's label: world-map places start with their kind's glyph, and end with
    ✓ once every room is visited, ◆ while an active quest leads there and ⚔ while
    a warden bars the road to it."""
    text = name if kind is None else f"{KIND_GLYPHS.get(kind, DEFAULT_GLYPH)} {name}"
    return (
        text
        + (f" {CHARTED_MARK}" if charted else "")
        + (f" {QUEST_MARK}" if quest else "")
        + (f" {GUARD_MARK}" if guarded else "")
    )


def badges(node: MapNode) -> str:
    """Area-map marks beside a room: a shop or inn, items left lying there, a quest
    target."""
    return (
        (SHOP_MARK if node.shop else "")
        + (ITEMS_MARK if node.items else "")
        + (QUEST_MARK if node.quest else "")
    )


def _badges(node: MapNode, x: float, y: float, r: float) -> list[cv.Shape]:
    text = badges(node)
    if not text:
        return []
    return [
        cv.Text(
            x + r * 1.1,
            y - r * 1.1,
            text,
            style=ft.TextStyle(
                size=LABEL_SIZE, color=ft.Colors.TERTIARY, weight=ft.FontWeight.BOLD
            ),
            alignment=ft.Alignment.BOTTOM_LEFT,
        )
    ]


def kinds_legend(view: MapView) -> str:
    """ "⌂ Town  ≈ Sea Caves": the kinds of the places this map shows, in map order;
    kinds sharing a glyph (a stilt village is a town) get one entry."""
    entries = dict.fromkeys(
        f"{KIND_GLYPHS.get(k, DEFAULT_GLYPH)} {LEGEND_NAMES.get(k, k)}"
        for k in (n.kind for n in view.nodes if n.kind and n.name)
    )
    return "   ".join(entries)


def _circle(x: float, y: float, r: float, paint: ft.Paint) -> cv.Shape:
    return cv.Circle(x, y, r, paint=paint)


def _square(x: float, y: float, r: float, paint: ft.Paint) -> cv.Shape:
    """A rounded square about as heavy as a circle of radius `r` (gate rooms)."""
    side = r * 1.8
    return cv.Rect(x - side / 2, y - side / 2, side, side, border_radius=r * 0.35, paint=paint)


def _fill(color: str) -> ft.Paint:
    return ft.Paint(color=color, style=ft.PaintingStyle.FILL)


def _ring(color: str, width: float) -> ft.Paint:
    return ft.Paint(color=color, stroke_width=width, style=ft.PaintingStyle.STROKE)


# --- label placement ---------------------------------------------------------------


def place_labels(
    points: dict[str, Point],
    names: dict[str, str],
    edges: tuple[tuple[str, str], ...],
    radius: float,
    width: float,
    height: float,
) -> dict[str, Point]:
    """Where to draw each name: the top-centre point of its label.

    Each label tries below, above, right and left of its dot (in that order of
    preference) and takes the spot that least overlaps the dots, the paths, the
    labels already placed and the edges of the map. Text sizes are estimates, so
    this avoids most collisions rather than guaranteeing none.
    """
    pad = radius + 6
    taken: list[Box] = [(x - pad, y - pad, x + pad, y + pad) for x, y in points.values()]
    segments = [(points[a], points[b]) for a, b in edges if a in points and b in points]
    spots = {}
    for node_id, name in names.items():
        x, y = points[node_id]
        w, h = _label_size(name)
        gap = radius + 7
        candidates: list[Box] = [
            (x - w / 2, y + gap, x + w / 2, y + gap + h),  # below
            (x - w / 2, y - gap - h, x + w / 2, y - gap),  # above
            (x + gap, y - h / 2, x + gap + w, y + h / 2),  # right
            (x - gap - w, y - h / 2, x - gap, y + h / 2),  # left
        ]
        box = min(
            candidates,
            key=lambda b: (_collision(b, taken, segments, width, height), candidates.index(b)),
        )
        taken.append(box)
        spots[node_id] = ((box[0] + box[2]) / 2, box[1])
    return spots


def _label_size(name: str) -> Point:
    text_width = len(name) * CHAR_WIDTH
    lines = 1 if text_width <= LABEL_WIDTH else 2
    return min(text_width, LABEL_WIDTH), lines * LINE_HEIGHT


def _collision(
    box: Box, taken: list[Box], segments: list[tuple[Point, Point]], width: float, height: float
) -> float:
    cost = sum(_overlap(box, other) for other in taken)
    for (ax, ay), (bx, by) in segments:  # sample along each path
        cost += 40 * sum(
            _inside(box, ax + (bx - ax) * t / 12, ay + (by - ay) * t / 12) for t in range(13)
        )
    left, top, right, bottom = box
    area = (right - left) * (bottom - top)
    cost += 4 * (area - _overlap(box, (0, 0, width, height)))  # off the map
    return cost


def _overlap(a: Box, b: Box) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _inside(box: Box, x: float, y: float) -> bool:
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]

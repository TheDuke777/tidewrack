"""Point-crawl map with fog of war, drawn on a Flet canvas (CLAUDE.md §3, §8).

Draws one MapView from Game.view(): the rooms of this location or the locations
of the world, only as far as the player knows them. State is shown by shape as
well as colour (§11): filled = visited, hollow = seen but unvisited, large dot
inside a ring = you, extra outer ring = one step away (tap it to go there).
"""

from __future__ import annotations

import math
from collections.abc import Callable

import flet as ft
import flet.canvas as cv

from tidewrack.core.engine.game import Command, MapView

MAP_HEIGHT = 260
BACKGROUND = ft.Colors.SURFACE_CONTAINER_HIGHEST
PAD = 20
DEFAULT_WIDTH = 360  # until the first resize event reports the real size
MIN_TOUCH_RADIUS = 24  # px; generous, since dots can be small on big maps
LABEL_WIDTH = 96  # px; place names wrap onto a second line beyond this
LABEL_SIZE = 11
CHAR_WIDTH = 0.58 * LABEL_SIZE  # rough average glyph width, for estimating label boxes
LINE_HEIGHT = 1.3 * LABEL_SIZE

Point = tuple[float, float]
Box = tuple[float, float, float, float]  # left, top, right, bottom


class MapCanvas:
    def __init__(self, on_command: Callable[[Command], None]) -> None:
        self.on_command = on_command
        self.view: MapView | None = None
        self.labels = False
        self.width, self.height = DEFAULT_WIDTH, MAP_HEIGHT
        self._points: dict[str, tuple[float, float]] = {}

        self.canvas = cv.Canvas(expand=True, on_resize=self._resized, resize_interval=100)
        self.legend = ft.Text(size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.control = ft.Column(
            spacing=4,
            controls=[
                ft.Container(
                    height=MAP_HEIGHT,
                    border_radius=12,
                    bgcolor=BACKGROUND,
                    content=ft.GestureDetector(content=self.canvas, on_tap_down=self._tapped),
                ),
                self.legend,
            ],
        )

    def show(self, view: MapView, legend: str, labels: bool = False) -> None:
        """Draw `view`; with `labels`, known node names are written under them."""
        self.view, self.labels = view, labels
        self.legend.value = legend
        self._draw()

    # --- events ------------------------------------------------------------------

    def _resized(self, e: cv.CanvasResizeEvent) -> None:
        self.width, self.height = e.width, e.height
        self._draw()

    def _tapped(self, e: ft.TapEvent) -> None:
        if self.view is None or e.local_position is None:
            return
        tx, ty = e.local_position.x, e.local_position.y
        best, best_distance = None, max(MIN_TOUCH_RADIUS, self._radius() * 2.5)
        for node in self.view.nodes:
            if node.command is None:
                continue
            x, y = self._points[node.id]
            distance = math.hypot(x - tx, y - ty)
            if distance <= best_distance:
                best, best_distance = node.command, distance
        if best is not None:
            self.on_command(best)

    # --- drawing -----------------------------------------------------------------

    def _radius(self) -> float:
        # Roughly a third of a grid cell, clamped so small maps don't get huge dots.
        side = math.ceil(math.sqrt((self.view.size if self.view else 1) * 1.8))
        return max(4.0, min(10.0, min(self.width, self.height) / side * 0.28))

    def _draw(self) -> None:
        if self.view is None:
            return
        w, h, r = self.width, self.height, self._radius()
        self._points = {
            n.id: (PAD + n.x * (w - 2 * PAD), PAD + n.y * (h - 2 * PAD)) for n in self.view.nodes
        }
        path = ft.Paint(color=ft.Colors.OUTLINE, stroke_width=2, style=ft.PaintingStyle.STROKE)
        shapes: list[cv.Shape] = [
            cv.Line(*self._points[a], *self._points[b], paint=path) for a, b in self.view.edges
        ]
        for node in self.view.nodes:
            x, y = self._points[node.id]
            if node.state == "current":
                shapes += [
                    cv.Circle(x, y, r + 2, paint=_fill(ft.Colors.PRIMARY)),
                    cv.Circle(x, y, r + 6, paint=_ring(ft.Colors.PRIMARY, 2.5)),
                ]
            elif node.state == "visited":
                shapes.append(cv.Circle(x, y, r, paint=_fill(ft.Colors.SECONDARY)))
            else:  # hollow; filled with the background so paths don't show through it
                shapes += [
                    cv.Circle(x, y, r, paint=_fill(BACKGROUND)),
                    cv.Circle(x, y, r, paint=_ring(ft.Colors.ON_SURFACE_VARIANT, 2)),
                ]
            if node.command is not None:
                shapes.append(cv.Circle(x, y, r + 5, paint=_ring(ft.Colors.TERTIARY, 1.5)))
        if self.labels:
            shapes += self._labels(r)
        self.canvas.shapes = shapes

    def _labels(self, r: float) -> list[cv.Shape]:
        assert self.view is not None
        names = {n.id: n.name for n in self.view.nodes if n.name}
        spots = place_labels(self._points, names, self.view.edges, r, self.width, self.height)
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
        ]


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

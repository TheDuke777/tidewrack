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
            if self.labels and node.name:
                shapes.append(
                    cv.Text(
                        x,
                        y + r + 7,
                        node.name,
                        style=ft.TextStyle(size=11, color=ft.Colors.ON_SURFACE),
                        alignment=ft.Alignment.TOP_CENTER,
                        text_align=ft.TextAlign.CENTER,
                        max_width=LABEL_WIDTH,
                        max_lines=2,
                    )
                )
        self.canvas.shapes = shapes


def _fill(color: str) -> ft.Paint:
    return ft.Paint(color=color, style=ft.PaintingStyle.FILL)


def _ring(color: str, width: float) -> ft.Paint:
    return ft.Paint(color=color, stroke_width=width, style=ft.PaintingStyle.STROKE)

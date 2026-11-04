"""The codex: what you've discovered. For now, the foes you've met.

Entries fill in as you beat them (core.codex.foes): unknown details show as
"???", and each card says what defeating more of them will reveal. Every level
collapses: the section (Foes; later Lore, Quests…) and each group inside it
(Beasts, People, Spirits). What's open is remembered while the world is.
"""

from __future__ import annotations

import flet as ft

from tidewrack.core.codex.foes import FoeView
from tidewrack.core.gear.stats import STAT_LABELS, STATS
from tidewrack.services.session import GameSession

UNKNOWN = "???"


class CodexScreen:
    def __init__(self, session: GameSession) -> None:
        self.session = session
        self.open: dict[str, bool] = {}  # section/group key -> expanded (default: open)
        self.sections = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.control = ft.SafeArea(
            expand=True,
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    expand=True,
                    controls=[
                        ft.Text("Codex", size=22, weight=ft.FontWeight.BOLD),
                        ft.ListView(expand=True, spacing=12, controls=[self.sections]),
                    ],
                ),
            ),
        )
        self.refresh()

    def refresh(self) -> None:
        self.sections.controls = [self._foes_section()]

    def _foes_section(self) -> ft.Control:
        foes = self.session.game.foes()
        groups = foes.by_category()
        if groups:
            inner: list[ft.Control] = [
                self._tile(
                    f"foes/{heading}",
                    f"{heading} ({len(group)})",
                    [foe_card(foe) for foe in group],
                    size=15,
                )
                for heading, group in groups
            ]
        else:
            inner = [
                ft.Text(
                    "You haven't met any foes yet. Whatever you fight is recorded here.",
                    size=14,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            ]
        return self._tile("foes", f"Foes ({len(foes.foes)})", inner, size=18)

    def _tile(
        self, key: str, title: str, controls: list[ft.Control], size: int
    ) -> ft.ExpansionTile:
        def changed(e: ft.Event) -> None:
            self.open[key] = bool(e.data)

        return ft.ExpansionTile(
            title=ft.Text(title, size=size, weight=ft.FontWeight.BOLD),
            expanded=self.open.get(key, True),
            maintain_state=True,
            controls_padding=ft.Padding.only(left=8, bottom=8),
            tile_padding=ft.Padding.symmetric(horizontal=4),
            expanded_cross_axis_alignment=ft.CrossAxisAlignment.STRETCH,
            on_change=changed,
            controls=controls,
        )


def foe_lines(foe: FoeView) -> list[str]:
    """The card's text below the description, "???" where still unknown."""
    if foe.stats is None:
        strength = UNKNOWN
    else:
        strength = " · ".join(f"{STAT_LABELS[s]} {foe.stats.get(s, 0)}" for s in STATS)
    if foe.drops is None:
        drops = UNKNOWN
    else:
        drops = ", ".join(foe.drops) or "nothing"
    lines = [f"Defeated: {foe.defeated}", f"Strength: {strength}", f"Drops: {drops}"]
    if foe.next_reveal:
        lines.append(foe.next_reveal)
    return lines


def foe_card(foe: FoeView) -> ft.Card:
    facts = foe_lines(foe)
    return ft.Card(
        content=ft.Container(
            padding=12,
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Text(foe.name, size=17, weight=ft.FontWeight.BOLD),
                    ft.Text(foe.description, size=14),
                    *(ft.Text(line, size=13, color=ft.Colors.ON_SURFACE_VARIANT) for line in facts),
                ],
            ),
        )
    )

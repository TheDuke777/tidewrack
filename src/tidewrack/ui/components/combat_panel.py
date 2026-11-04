"""The fight panel: who you're fighting, both sides' HP, and what you can do.

HP is always written out ("HP 7/12"); the bars only repeat it, so nothing relies
on the bar or its colour alone (CLAUDE.md §11).
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from tidewrack.core.engine.game import Attack, Command, Defend, Flee, GameView
from tidewrack.core.gear.stats import STAT_LABELS

CATEGORY_NAMES = {"beast": "Beast", "person": "Person", "spirit": "Spirit"}


def hp_row(label: str, hp: int, max_hp: int) -> ft.Column:
    return ft.Column(
        spacing=4,
        controls=[
            ft.Text(f"{label}: HP {hp}/{max_hp}", size=14, weight=ft.FontWeight.BOLD),
            ft.ProgressBar(value=hp / max_hp if max_hp else 0, bar_height=8, border_radius=4),
        ],
    )


def combat_panel(view: GameView, on_command: Callable[[Command], None]) -> ft.Card:
    fight = view.combat
    assert fight is not None
    kind = CATEGORY_NAMES.get(fight.category, fight.category.title())
    strength = " · ".join(f"{STAT_LABELS[s]} {v}" for s, v in fight.stats.items() if s != "hp")
    return ft.Card(
        content=ft.Container(
            padding=12,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Text(f"Fighting: {fight.name}", size=18, weight=ft.FontWeight.BOLD),
                    ft.Text(f"{kind} · {strength}", size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(fight.description, size=14),
                    hp_row(fight.name, fight.hp, fight.max_hp),
                    hp_row("You", view.hp, view.max_hp),
                    ft.Row(
                        wrap=True,
                        spacing=8,
                        run_spacing=8,
                        controls=[
                            ft.FilledButton(
                                content="Attack",
                                icon=ft.Icons.SPORTS_MARTIAL_ARTS,
                                on_click=lambda _: on_command(Attack()),
                            ),
                            ft.OutlinedButton(
                                content="Defend",
                                icon=ft.Icons.SHIELD_OUTLINED,
                                on_click=lambda _: on_command(Defend()),
                            ),
                            ft.TextButton(
                                content="Flee",
                                icon=ft.Icons.DIRECTIONS_RUN,
                                on_click=lambda _: on_command(Flee()),
                            ),
                        ],
                    ),
                ],
            ),
        )
    )

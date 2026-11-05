"""A meal's card: what it does and for how long, what it takes, and its buttons.
Used at a tavern (to cook or buy) and in the satchel (to eat)."""

from __future__ import annotations

from collections.abc import Sequence

import flet as ft

from tidewrack.core.engine.game import FedView, MealView
from tidewrack.ui.components.unread import new_chip


def buff_line(meal: MealView) -> str:
    return f"{meal.buff} for {meal.turns} turns"


def fed_line(fed: FedView | None) -> str:
    if fed is None:
        return "You haven't eaten. A meal's buff lasts a while; only one at a time."
    return f"Well fed: {fed.name} · {fed.buff} · {fed.turns_left} turns left"


def meal_card(
    meal: MealView,
    actions: Sequence[ft.Control] = (),
    details: Sequence[ft.Control] = (),
    new: bool = False,  # a "New" chip: it's behind a dot you just cleared
) -> ft.Card:
    carried = f"You have {meal.count}" if meal.count else None
    return ft.Card(
        content=ft.Container(
            padding=12,
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(meal.name, size=17, weight=ft.FontWeight.BOLD, expand=True),
                            *([new_chip()] if new else []),
                            *(
                                [ft.Text(carried, size=13, color=ft.Colors.ON_SURFACE_VARIANT)]
                                if carried
                                else []
                            ),
                        ]
                    ),
                    ft.Text(buff_line(meal), size=14, weight=ft.FontWeight.BOLD),
                    ft.Text(meal.description, size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                    *details,
                    *(
                        [ft.Row(wrap=True, spacing=8, run_spacing=8, controls=list(actions))]
                        if actions
                        else []
                    ),
                ],
            ),
        )
    )

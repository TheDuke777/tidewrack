"""The New world dialog: pick a difficulty (fixed for the world's life, 8b), and
in dev builds the region to start in (core.procgen.head_start)."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from tidewrack.core.data.loader import Content
from tidewrack.services.session import DEFAULT_DIFFICULTY

COAST = ""  # the region choice meaning "start at the beginning"


class NewWorldDialog:
    def __init__(
        self,
        content: Content,
        recipe_id: str,
        on_start: Callable[[str, str | None], None],  # (difficulty id, region id or None)
        on_cancel: Callable[[], None],
        regions: bool = False,  # dev builds: offer a later region to start in
    ) -> None:
        def described(value: str, label: str, description: str | None = None) -> ft.Control:
            radio = ft.Radio(value=value, label=label)
            if description is None:
                return radio
            return ft.Column(
                spacing=0,
                controls=[
                    radio,
                    ft.Container(
                        padding=ft.Padding(left=48, top=0, right=0, bottom=4),
                        content=ft.Text(description, size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                    ),
                ],
            )

        self.difficulty = ft.RadioGroup(
            value=DEFAULT_DIFFICULTY,
            content=ft.Column(
                spacing=0,
                controls=[
                    described(d.id, d.name, d.description) for d in content.difficulty_choices()
                ],
            ),
        )
        controls: list[ft.Control] = [
            ft.Text("Difficulty can't be changed later.", color=ft.Colors.ON_SURFACE_VARIANT),
            self.difficulty,
        ]
        self.region: ft.RadioGroup | None = None
        if regions:
            plans = content.world(recipe_id).regions
            self.region = ft.RadioGroup(
                value=COAST,
                content=ft.Column(
                    spacing=0,
                    controls=[
                        described(COAST, content.regions[plans[0].region].name),
                        *(described(p.region, content.regions[p.region].name) for p in plans[1:]),
                    ],
                ),
            )
            controls += [
                ft.Divider(),
                ft.Text("Start in (dev)", weight=ft.FontWeight.BOLD),
                ft.Text(
                    "A later region: earlier wardens beaten, wearing the best gear of the "
                    "regions before it, fully upgraded.",
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                self.region,
            ]

        def start(_: ft.Event) -> None:
            region = self.region.value if self.region is not None else COAST
            on_start(self.difficulty.value or DEFAULT_DIFFICULTY, region or None)

        self.control = ft.AlertDialog(
            modal=True,
            title=ft.Text("New world"),
            content=ft.Column(tight=True, scroll=ft.ScrollMode.AUTO, controls=controls),
            actions=[
                ft.TextButton(content="Cancel", on_click=lambda _: on_cancel()),
                ft.FilledButton(content="Start", on_click=start),
            ],
        )

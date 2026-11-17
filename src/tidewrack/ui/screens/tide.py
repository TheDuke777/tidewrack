"""The Ride the tide dialog (step 8c): once the world's final foe has fallen, the
player may let the Wrack take this world and wake on a new shore, choosing one
boon to keep (core.progression.prestige)."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from tidewrack.core.engine.components import Boon
from tidewrack.core.progression.prestige import boon_text


class TideDialog:
    def __init__(
        self,
        tide: int,  # the tide you'd reach (1 = the first ascent)
        boons: list[Boon],  # on offer, sized for that tide
        kept: list[Boon],  # chosen on earlier tides
        on_ride: Callable[[str], None],  # (boon id)
        on_cancel: Callable[[], None],
    ) -> None:
        def choice(boon: Boon) -> ft.Control:
            return ft.Column(
                spacing=0,
                controls=[
                    ft.Radio(value=boon.boon_id, label=f"{boon.name}: {boon_text(boon)}"),
                    ft.Container(
                        padding=ft.Padding(left=48, top=0, right=0, bottom=4),
                        content=ft.Text(
                            boon.description, size=13, color=ft.Colors.ON_SURFACE_VARIANT
                        ),
                    ),
                ],
            )

        self.boon = ft.RadioGroup(
            value=None,
            content=ft.Column(spacing=0, controls=[choice(b) for b in boons]),
        )
        ride = ft.FilledButton(content="Ride the tide", disabled=True)

        def picked(_: ft.Event) -> None:
            ride.disabled = not self.boon.value

        self.boon.on_change = picked
        ride.on_click = lambda _: on_ride(self.boon.value) if self.boon.value else None

        controls: list[ft.Control] = [
            ft.Text(
                "The pact is broken and the sea is coming. Let the Wrack take this world"
                " and you'll wake on a new, harsher shore: no gear, no gold, no map, but"
                " you'll remember everything you learned, and keep one boon for good."
            ),
            ft.Text(
                "This world will be gone. Finish anything you want to here first;"
                " the tide will wait.",
                size=13,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Divider(),
            ft.Text("Choose a boon", weight=ft.FontWeight.BOLD),
            self.boon,
        ]
        if kept:
            controls += [
                ft.Divider(),
                ft.Text("Already yours", weight=ft.FontWeight.BOLD),
                *(
                    ft.Text(
                        f"{b.name}: {boon_text(b)}", size=13, color=ft.Colors.ON_SURFACE_VARIANT
                    )
                    for b in kept
                ),
            ]
        self.control = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Ride the tide (tide {tide})"),
            content=ft.Column(tight=True, scroll=ft.ScrollMode.AUTO, controls=controls),
            actions=[ft.TextButton(content="Not yet", on_click=lambda _: on_cancel()), ride],
        )

"""The quest log: quests you've taken or found, by state.

Ready to turn in first (that's what you'll want to act on), then active, then
done. Quests are accepted and turned in at a town's notice board, on the
Explore screen; this tab only shows them. Each section collapses, and what's
open is remembered while the world is (like the Codex).
"""

from __future__ import annotations

import flet as ft

from tidewrack.core.engine.game import QuestView
from tidewrack.services.session import GameSession
from tidewrack.ui.components.quest_card import quest_card

EMPTY = "No quests yet. Check the notice board at a town gate, or keep an eye out on your travels."
SECTIONS = (
    ("ready", "Ready to turn in", "Take these to any town's notice board."),
    ("active", "Active", None),
    ("done", "Done", None),
)


class QuestsScreen:
    def __init__(self, session: GameSession) -> None:
        self.session = session
        self.open: dict[str, bool] = {"done": False}  # done starts folded away
        self.sections = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.control = ft.SafeArea(
            expand=True,
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    expand=True,
                    controls=[
                        ft.Text("Quests", size=22, weight=ft.FontWeight.BOLD),
                        ft.ListView(expand=True, spacing=12, controls=[self.sections]),
                    ],
                ),
            ),
        )
        self.refresh()

    def refresh(self) -> None:
        log = self.session.game.quests()
        groups: dict[str, tuple[QuestView, ...]] = {
            "ready": log.ready,
            "active": log.active,
            "done": log.done,
        }
        if not any(groups.values()):
            self.sections.controls = [ft.Text(EMPTY, size=14, color=ft.Colors.ON_SURFACE_VARIANT)]
            return
        self.sections.controls = [
            self._tile(key, f"{title} ({len(groups[key])})", hint, groups[key])
            for key, title, hint in SECTIONS
            if groups[key]
        ]

    def _tile(
        self, key: str, title: str, hint: str | None, quests: tuple[QuestView, ...]
    ) -> ft.ExpansionTile:
        def changed(e: ft.Event) -> None:
            self.open[key] = bool(e.data)

        controls: list[ft.Control] = []
        if hint:
            controls.append(ft.Text(hint, size=13, color=ft.Colors.ON_SURFACE_VARIANT))
        controls += [quest_card(q, full_reward=key != "done") for q in quests]
        return ft.ExpansionTile(
            title=ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
            expanded=self.open.get(key, True),
            maintain_state=True,
            controls_padding=ft.Padding.only(left=8, bottom=8),
            tile_padding=ft.Padding.symmetric(horizontal=4),
            expanded_cross_axis_alignment=ft.CrossAxisAlignment.STRETCH,
            on_change=changed,
            controls=controls,
        )

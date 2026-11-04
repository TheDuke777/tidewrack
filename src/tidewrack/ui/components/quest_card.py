"""A quest's card: what it asks, where it came from, how far along it is, and
its reward. On a notice board the reward is one line with its verdict, so the
board stays short; in the quest log it's the full gear comparison card."""

from __future__ import annotations

from collections.abc import Sequence

import flet as ft

from tidewrack.core.engine.game import QuestView
from tidewrack.ui.components.gear_compare_card import gear_compare_card, verdict_chip

KIND_ICONS = {
    "Bounty": ft.Icons.GPS_FIXED,
    "Cull": ft.Icons.GROUPS_OUTLINED,
    "Explore": ft.Icons.MAP_OUTLINED,
    "Recover": ft.Icons.SEARCH,
}


def kind_chip(kind: str) -> ft.Container:
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        border=ft.Border.all(1, ft.Colors.OUTLINE),
        border_radius=ft.BorderRadius.all(12),
        content=ft.Row(
            spacing=4,
            tight=True,
            controls=[
                ft.Icon(KIND_ICONS.get(kind, ft.Icons.FLAG_OUTLINED), size=14),
                ft.Text(kind, size=13, weight=ft.FontWeight.BOLD),
            ],
        ),
    )


def reward_line(quest: QuestView) -> ft.Row:
    reward = quest.reward
    if quest.state == "done":
        return ft.Row(controls=[ft.Text(f"Reward: {reward.name}", size=14)])
    return ft.Row(
        wrap=True,
        spacing=8,
        run_spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text(f"Reward: {reward.name} ({reward.slot})", size=14),
            verdict_chip(reward.comparison.verdict),
        ],
    )


def quest_card(
    quest: QuestView, actions: Sequence[ft.Control] = (), full_reward: bool = False
) -> ft.Card:
    body: list[ft.Control] = [
        ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Text(quest.title, size=17, weight=ft.FontWeight.BOLD, expand=True),
                kind_chip(quest.kind),
            ],
        ),
        ft.Text(quest.source, size=13, color=ft.Colors.ON_SURFACE_VARIANT),
        ft.Text(quest.summary, size=14),
        ft.Text(quest.progress, size=13, weight=ft.FontWeight.BOLD),
    ]
    if full_reward:
        body += [ft.Text("Reward", size=13), gear_compare_card(quest.reward)]
    else:
        body.append(reward_line(quest))
    if actions:
        body.append(ft.Row(wrap=True, spacing=8, run_spacing=8, controls=list(actions)))
    return ft.Card(
        content=ft.Container(padding=12, content=ft.Column(spacing=8, controls=body)),
    )

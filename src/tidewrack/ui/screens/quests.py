"""The quest log: quests you've taken or found, by state.

Ready to turn in first (that's what you'll want to act on), then active, then
done. Quests are accepted and turned in at a town's notice board, on the
Explore screen; here an active quest can be abandoned (after asking), which
puts its notice back on a board. Each section collapses, and what's open is
remembered while the world is (like the Codex).
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from tidewrack.core.engine.events import ActionRejected
from tidewrack.core.engine.game import AbandonQuest, QuestView
from tidewrack.services.session import GameSession
from tidewrack.services.settings import SettingsStore
from tidewrack.ui.components.folds import Folds
from tidewrack.ui.components.quest_card import quest_card

EMPTY = "No quests yet. Check the notice board at a town gate, or keep an eye out on your travels."
SECTIONS = (
    ("ready", "Ready to turn in", "Take these to any town's notice board."),
    ("active", "Active", None),
    ("done", "Done", None),
)


# (title, message, confirm button label, what to do if confirmed)
Confirm = Callable[[str, str, str, Callable[[], None]], None]


def _no_confirm(_title: str, _message: str, _action: str, then: Callable[[], None]) -> None:
    then()


class QuestsScreen:
    def __init__(
        self,
        session: GameSession,
        confirm: Confirm = _no_confirm,
        notify: Callable[[str], None] = lambda _: None,
        settings: SettingsStore | None = None,
    ) -> None:
        self.folds = Folds("quests", settings, lambda: self.refresh())
        self.fold_all = ft.Row()
        self.session = session
        self.confirm = confirm
        self.notify = notify
        self.open: dict[str, bool] = {"done": False}  # done starts folded away
        self.sections = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.control = ft.SafeArea(
            expand=True,
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    expand=True,
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Text("Quests", size=22, weight=ft.FontWeight.BOLD, expand=True),
                                self.fold_all,
                            ]
                        ),
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
        shown = [q.id for key, *_ in SECTIONS for q in groups[key]]
        self.fold_all.controls = [self.folds.all_button(shown)]
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
        controls += [
            quest_card(
                q,
                self._actions(q),
                full_reward=key != "done",
                collapsed=self.folds.collapsed(q.id),
                on_toggle=lambda i=q.id: self.folds.toggle(i),
            )
            for q in quests
        ]
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

    def _actions(self, quest: QuestView) -> list[ft.Control]:
        if quest.state != "active":
            return []
        return [
            ft.TextButton(
                content="Abandon",
                icon=ft.Icons.CLOSE,
                on_click=lambda _, q=quest: self._abandon(q),
            )
        ]

    def _abandon(self, quest: QuestView) -> None:
        def abandon() -> None:
            result = self.session.perform(AbandonQuest(quest.id))
            self.refresh()
            for event in result.events:
                if isinstance(event, ActionRejected):
                    self.notify(event.reason)

        restart = " A cull's count starts again." if quest.kind == "Cull" else ""
        self.confirm(
            f"Abandon {quest.title}?",
            f"Its notice goes back on a town's board, where you can take it up again.{restart}",
            "Abandon",
            abandon,
        )

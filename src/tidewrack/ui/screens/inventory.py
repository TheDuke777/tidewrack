"""The inventory: your stats, what you have on, and what's in your pack.

Reads only Game.inventory() and sends only commands, through the GameSession so
every change autosaves (CLAUDE.md §4, §6). The pack is a PackList (filters,
sort and select mode, shared with a smithy's sell list); select mode drops, or
sells while you're at a shop that buys gear. Dropping and selling always ask
first.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from tidewrack.core.engine.events import ActionRejected
from tidewrack.core.engine.game import (
    Command,
    Drop,
    Equip,
    InventoryView,
    ItemView,
    Sell,
    TurnResult,
    Unequip,
)
from tidewrack.core.gear.compare import format_stats
from tidewrack.core.gear.stats import STAT_LABELS, STATS
from tidewrack.services.session import GameSession
from tidewrack.ui.components.gear_compare_card import gear_compare_card
from tidewrack.ui.components.pack_list import (
    BulkAction,
    Confirm,
    PackChoices,
    PackList,
    name_list,
    sell_message,
)


class InventoryScreen:
    def __init__(
        self,
        session: GameSession,
        confirm: Confirm,
        notify: Callable[[str], None],
        choices: PackChoices | None = None,
    ) -> None:
        self.session = session
        self.confirm = confirm
        self.notify = notify  # a toast, for actions the game refuses (e.g. mid-fight)
        self._buyer: str | None = None  # the shop here that buys gear

        self.sheet = ft.Column(spacing=4)
        self.materials = ft.Column(spacing=4)
        self.recipes = ft.Column(spacing=4)
        self.equipped = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.pack_list = PackList(
            choices if choices is not None else PackChoices(),
            actions=self._pack_actions,
            bulk=self._bulk_actions,
            refresh=lambda: self.refresh(),
        )
        self.pack = self.pack_list.cards
        self.control = ft.SafeArea(
            expand=True,
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    expand=True,
                    controls=[
                        ft.Text("Inventory", size=22, weight=ft.FontWeight.BOLD),
                        ft.ListView(
                            expand=True,
                            spacing=12,
                            controls=[
                                self.sheet,
                                _heading("Equipped"),
                                self.equipped,
                                self.pack_list.control,
                                _heading("Materials"),
                                self.materials,
                                _heading("Recipes you know"),
                                self.recipes,
                            ],
                        ),
                    ],
                ),
            ),
        )
        self.refresh()

    # --- actions -----------------------------------------------------------------

    def act(self, command: Command) -> None:
        result = self.session.perform(command)  # autosaves
        self.refresh()  # before any toast: showing one updates the page at once
        self._tell(result)

    def _tell(self, *results: TurnResult) -> None:
        """Toast the first reason the game refused something (the log has them all)."""
        for result in results:
            for event in result.events:
                if isinstance(event, ActionRejected):
                    self.notify(event.reason)
                    return

    def _drop(self, item: ItemView) -> None:
        def drop() -> None:
            self.act(Drop(item.id))

        where = "You'll leave it here; you can pick it up again."
        self.confirm(f"Drop the {item.name}?", where, "Drop", drop)

    def _bulk_actions(self) -> list[BulkAction]:
        actions = [BulkAction("Drop selected", ft.Icons.FILE_DOWNLOAD_OUTLINED, self._drop_all)]
        if self._buyer:
            actions.append(BulkAction("Sell selected", ft.Icons.SELL_OUTLINED, self._sell_all))
        return actions

    def _all(self, command: Callable[[int], Command], chosen: list[ItemView]) -> None:
        results = [self.session.perform(command(item.id)) for item in chosen]
        self.pack_list.end_selection()
        self.refresh()
        self._tell(*results)

    def _drop_all(self, chosen: list[ItemView]) -> None:
        if chosen:
            self.confirm(
                f"Drop {len(chosen)} item{'s' if len(chosen) != 1 else ''}?",
                f"{name_list(chosen)}. You'll leave them here; you can pick them up again.",
                "Drop all",
                lambda: self._all(Drop, chosen),
            )

    def _sell_all(self, chosen: list[ItemView]) -> None:
        if chosen and self._buyer:
            self.confirm(*sell_message(chosen, self._buyer), lambda: self._all(Sell, chosen))

    def _sell(self, item: ItemView) -> None:
        if self._buyer:
            self.confirm(*sell_message([item], self._buyer), lambda: self.act(Sell(item.id)))

    # --- rendering ---------------------------------------------------------------

    def refresh(self) -> None:
        view = self.session.game.inventory()
        self._buyer = view.buyer
        self.sheet.controls = self._sheet(view)
        self.equipped.controls = [self._slot(slot) for slot in view.slots]
        self.pack_list.show(view.pack)
        self.materials.controls = [
            ft.Column(
                spacing=0,
                controls=[
                    ft.Text(f"{m.name} × {m.count}", size=15, weight=ft.FontWeight.BOLD),
                    _muted(m.description),
                ],
            )
            for m in view.materials
        ] or [_muted("None yet. Defeated beasts, wild places and markets all have some.")]
        self.recipes.controls = (
            [ft.Text(", ".join(view.recipes) + ". Craft them at any smithy.", size=14)]
            if view.recipes
            else [_muted("None yet.")]
        )

    def _sheet(self, view: InventoryView) -> list[ft.Control]:
        total = view.sheet.total
        game = self.session.game
        top = [f"HP {game.hp()}/{game.max_hp()}"]
        top += [f"{STAT_LABELS[s]} {total[s]}" for s in STATS if s != "hp"]
        top.append(f"{view.gold} gold")
        lines: list[ft.Control] = [
            ft.Text(
                "   ".join(top),
                size=20,
                weight=ft.FontWeight.BOLD,
            )
        ]
        base, *gear = view.sheet.sources
        lines.append(
            _muted("Base: " + ", ".join(f"{STAT_LABELS[s]} {base.stats[s]}" for s in STATS))
        )
        lines += [
            _muted(f"{source.label}: {format_stats(source.stats) or 'nothing'}") for source in gear
        ]
        return lines

    def _slot(self, slot) -> ft.Control:
        if slot.item is not None:
            return gear_compare_card(slot.item, self._equipped_actions(slot.item))
        if slot.filled_by is not None:
            return _muted(f"{slot.label}: held by the {slot.filled_by} (both hands)")
        return _muted(f"{slot.label}: empty")

    def _equipped_actions(self, item: ItemView) -> list[ft.Control]:
        return [
            ft.OutlinedButton(
                content="Take off",
                icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                on_click=lambda _, i=item.id: self.act(Unequip(i)),
            ),
            self._drop_button(item),
        ]

    def _pack_actions(self, item: ItemView) -> list[ft.Control]:
        actions: list[ft.Control] = [
            ft.FilledButton(
                content="Equip",
                icon=ft.Icons.CHECK,
                on_click=lambda _, i=item.id: self.act(Equip(i)),
            ),
        ]
        if self._buyer:
            actions.append(
                ft.FilledTonalButton(
                    content=f"Sell · {item.sell_price} gold",
                    icon=ft.Icons.SELL_OUTLINED,
                    on_click=lambda _, i=item: self._sell(i),
                )
            )
        actions.append(self._drop_button(item))
        return actions

    def _drop_button(self, item: ItemView) -> ft.Control:
        return ft.TextButton(
            content="Drop",
            icon=ft.Icons.FILE_DOWNLOAD_OUTLINED,
            on_click=lambda _, i=item: self._drop(i),
        )


def _heading(text: str) -> ft.Text:
    return ft.Text(text, size=16, weight=ft.FontWeight.BOLD)


def _muted(text: str) -> ft.Text:
    return ft.Text(text, size=14, color=ft.Colors.ON_SURFACE_VARIANT)

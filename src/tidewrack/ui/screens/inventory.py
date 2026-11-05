"""The inventory: your stats, what you have on, and what's in your pack.

Reads only Game.inventory() and sends only commands, through the GameSession so
every change autosaves (CLAUDE.md §4, §6). Under the stat sheet, tabs show
what you have on, your pack, or your satchel (materials and known recipes).
The pack is a PackList (filters, sort and select mode, shared with a smithy's
sell list); select mode drops, or
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
    Eat,
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
from tidewrack.services.settings import SettingsStore
from tidewrack.ui.components.coins import coins, purse
from tidewrack.ui.components.folds import Folds
from tidewrack.ui.components.gear_compare_card import gear_compare_card
from tidewrack.ui.components.meal_card import fed_line, meal_card
from tidewrack.ui.components.pack_list import (
    BulkAction,
    Confirm,
    PackChoices,
    PackList,
    name_list,
    sell_message,
)
from tidewrack.ui.components.unread import Unread, dot_icon, new_chip

EQUIPPED, PACK, SATCHEL = "equipped", "pack", "satchel"


class InventoryScreen:
    def __init__(
        self,
        session: GameSession,
        confirm: Confirm,
        notify: Callable[[str], None],
        choices: PackChoices | None = None,
        settings: SettingsStore | None = None,
        unread: Unread | None = None,
    ) -> None:
        self.unread = unread
        self.equipped_folds = Folds("equipped", settings, lambda: self.refresh())
        self.session = session
        self.confirm = confirm
        self.notify = notify  # a toast, for actions the game refuses (e.g. mid-fight)
        self._buyer: str | None = None  # the shop here that buys gear

        self.sheet = ft.Column(spacing=4)
        self.materials = ft.Column(spacing=4)
        self.ingredients = ft.Column(spacing=4)
        self.meals = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.fed = ft.Text(size=14)
        self.recipes = ft.Column(spacing=4)
        # Collapsible sections (open or folded while the world is open), like the
        # Quests tab's; filled in by refresh with their counts.
        self.satchel_open: dict[str, bool] = {}
        self.satchel = ft.Column(spacing=8)
        self.tab = EQUIPPED  # kept while the world is open
        self.tabs = ft.SegmentedButton(
            selected=[self.tab],
            show_selected_icon=False,
            segments=[
                ft.Segment(value=EQUIPPED, icon=ft.Icons.SHIELD_OUTLINED),
                ft.Segment(value=PACK, icon=ft.Icons.BACKPACK_OUTLINED),
                ft.Segment(value=SATCHEL, icon=ft.Icons.INVENTORY_2_OUTLINED),
            ],
            on_change=lambda e: self.show_tab((e.control.selected or [EQUIPPED])[0]),
        )
        self.equipped = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.pack_list = PackList(
            choices if choices is not None else PackChoices(),
            actions=self._pack_actions,
            bulk=self._bulk_actions,
            refresh=lambda: self.refresh(),
            folds=Folds("pack", settings, lambda: self.refresh()),
            is_new=lambda item: self._new(PACK, item.id),
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
                                self.tabs,
                                self.equipped,
                                self.pack_list.control,
                                self.satchel,
                            ],
                        ),
                    ],
                ),
            ),
        )
        self.refresh()

    def show_tab(self, tab: str) -> None:
        if tab != self.tab:
            self.leave()
        self.tab = tab
        self.refresh()

    def leave(self) -> None:
        """Leaving the open inner tab (or the Inventory): its "New" chips go."""
        if self.unread is not None and self.tab in (PACK, SATCHEL):
            self.unread.leave(self.tab)

    def _new(self, part: str, key) -> bool:
        return self.unread is not None and self.unread.is_new(part, key)

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

    def _eat(self, meal, fed) -> None:
        if fed is None:
            self.act(Eat(meal.id))
            return
        self.confirm(
            f"Eat the {meal.name}?",
            f"It replaces your {fed.name} ({fed.turns_left} turns left). "
            f"You'll have {meal.buff} for {meal.turns} turns.",
            "Eat",
            lambda: self.act(Eat(meal.id)),
        )

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
        # First, so the cards drawn below know what was new: you're looking at it
        # now, which clears the dot and leaves "New" chips on those cards.
        if self.unread is not None and self.control.visible and self.tab in (PACK, SATCHEL):
            self.unread.look(self.tab)
        view = self.session.game.inventory()
        self._buyer = view.buyer
        self.sheet.controls = self._sheet(view)
        self.equipped.controls = [self._slot(slot) for slot in view.slots]
        self.pack_list.show(view.pack)
        worn = sum(1 for slot in view.slots if slot.item)
        equipped, pack, satchel = self.tabs.segments
        equipped.label = f"Equipped ({worn})"
        pack.label = f"Pack ({len(view.pack)})"
        satchel.label = f"Satchel ({len(view.materials) + len(view.meals)})"
        self.tabs.selected = [self.tab]
        if self.unread is not None and self.control.visible:
            pack.icon = dot_icon(ft.Icons.BACKPACK_OUTLINED, bool(self.unread.new(PACK)))
            satchel.icon = dot_icon(ft.Icons.INVENTORY_2_OUTLINED, bool(self.unread.new(SATCHEL)))
        self.equipped.visible = self.tab == EQUIPPED
        self.pack_list.control.visible = self.tab == PACK
        self.satchel.visible = self.tab == SATCHEL

        def listed(materials) -> list[ft.Control]:
            return [
                ft.Column(
                    spacing=0,
                    controls=[
                        ft.Row(
                            spacing=8,
                            controls=[
                                ft.Text(
                                    f"{m.name} × {m.count}", size=15, weight=ft.FontWeight.BOLD
                                ),
                                *([new_chip()] if self._new(SATCHEL, ("material", m.id)) else []),
                            ],
                        ),
                        _muted(m.description),
                    ],
                )
                for m in materials
            ]

        crafting = [m for m in view.materials if not m.ingredient]
        food = [m for m in view.materials if m.ingredient]
        self.materials.controls = listed(crafting) or [
            _muted("None yet. Defeated beasts, wild places and markets all have some.")
        ]
        self.ingredients.controls = listed(food) or [
            _muted("None yet. Look in wild places, at what beasts drop, and at markets.")
        ]
        self.fed.value = fed_line(view.fed)
        self.meals.controls = [
            meal_card(
                m,
                [
                    ft.FilledButton(
                        content="Eat",
                        icon=ft.Icons.RESTAURANT,
                        on_click=lambda _, meal=m: self._eat(meal, view.fed),
                    )
                ],
                new=self._new(SATCHEL, ("meal", m.id)),
            )
            for m in view.meals
        ] or [_muted("None yet. Cook or buy meals at any tavern.")]
        new_recipes = [r for r in view.recipes if self._new(SATCHEL, ("recipe", r))]
        self.recipes.controls = (
            [
                *(
                    ft.Row(spacing=8, controls=[new_chip(), ft.Text(r, size=14)])
                    for r in new_recipes
                ),
                ft.Text(", ".join(view.recipes) + ". Craft them at any smithy.", size=14),
            ]
            if view.recipes
            else [_muted("None yet.")]
        )
        self.satchel.controls = [
            self.fed,
            self._section("meals", "Meals", len(view.meals), self.meals),
            self._section("ingredients", "Ingredients", len(food), self.ingredients),
            self._section("materials", "Materials", len(crafting), self.materials),
            self._section("recipes", "Recipes you know", len(view.recipes), self.recipes),
        ]

    def _section(self, key: str, title: str, count: int, body: ft.Control) -> ft.ExpansionTile:
        def changed(e: ft.Event) -> None:
            self.satchel_open[key] = bool(e.data)

        return ft.ExpansionTile(
            title=ft.Text(f"{title} ({count})", size=16, weight=ft.FontWeight.BOLD),
            expanded=self.satchel_open.get(key, True),
            maintain_state=True,
            controls_padding=ft.Padding.only(left=4, bottom=8),
            tile_padding=ft.Padding.symmetric(horizontal=4),
            expanded_cross_axis_alignment=ft.CrossAxisAlignment.STRETCH,
            on_change=changed,
            controls=[body],
        )

    def _sheet(self, view: InventoryView) -> list[ft.Control]:
        total = view.sheet.total
        game = self.session.game
        top = [f"HP {game.hp()}/{game.max_hp()}"]
        top += [f"{STAT_LABELS[s]} {total[s]}" for s in STATS if s != "hp"]
        stats = "   ".join(top)
        lines: list[ft.Control] = [
            ft.Row(
                wrap=True,
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                data=f"{stats}   {view.gold} gold",  # what it says, for tests and coins.label_of
                controls=[
                    ft.Text(stats, size=20, weight=ft.FontWeight.BOLD),
                    purse(view.gold, size=20),
                ],
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
            return gear_compare_card(
                slot.item,
                self._equipped_actions(slot.item),
                collapsed=self.equipped_folds.collapsed(slot.item.id),
                on_toggle=lambda i=slot.item.id: self.equipped_folds.toggle(i),
            )
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
                    content=coins(f"Sell · {item.sell_price} gold"),
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

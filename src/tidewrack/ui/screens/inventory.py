"""The inventory: your stats, what you have on, and what's in your pack.

Reads only Game.inventory() and sends only commands, through the GameSession so
every change autosaves (CLAUDE.md §4, §6). The pack can be filtered by slot,
affix and set, and a select mode acts on several items at once (drop now; sell
once shops exist). Dropping always asks first.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

import flet as ft

from tidewrack.core.engine.game import Command, Drop, Equip, InventoryView, ItemView, Unequip
from tidewrack.core.gear.compare import format_stats
from tidewrack.core.gear.stats import STAT_LABELS, STATS
from tidewrack.services.session import GameSession
from tidewrack.ui.components.gear_compare_card import gear_compare_card

# (title, message, confirm button label, what to do if confirmed)
Confirm = Callable[[str, str, str, Callable[[], None]], None]

ALL = "all"
ANY_AFFIX, NO_AFFIX, NO_SET = "any", "none", "none"


@dataclass(frozen=True)
class PackFilter:
    slot: str = ALL  # a slot label ("Both hands" included), or ALL
    affix: str = ALL  # an affix name, ANY_AFFIX, NO_AFFIX, or ALL
    gear_set: str = ALL  # a set name, NO_SET, or ALL

    @property
    def active(self) -> bool:
        return self != PackFilter()

    def keeps(self, item: ItemView) -> bool:
        if self.slot != ALL and item.slot != self.slot:
            return False
        if self.affix == ANY_AFFIX and not item.affixes:
            return False
        if self.affix == NO_AFFIX and item.affixes:
            return False
        if self.affix not in (ALL, ANY_AFFIX, NO_AFFIX) and self.affix not in item.affixes:
            return False
        if self.gear_set == NO_SET and item.gear_set is not None:
            return False
        return self.gear_set in (ALL, NO_SET) or item.gear_set == self.gear_set


def filter_options(pack: Iterable[ItemView]) -> dict[str, list[tuple[str, str]]]:
    """(key, text) choices for each filter, from what's actually in the pack."""
    pack = list(pack)
    slots = sorted({i.slot for i in pack})
    affixes = sorted({a for i in pack for a in i.affixes})
    sets = sorted({i.gear_set for i in pack if i.gear_set})
    return {
        "slot": [(ALL, "Any slot"), *((s, s) for s in slots)],
        "affix": [
            (ALL, "Any affix or none"),
            (ANY_AFFIX, "Has an affix"),
            (NO_AFFIX, "No affix"),
            *((a, a) for a in affixes),
        ],
        "gear_set": [(ALL, "Any set or none"), (NO_SET, "Not in a set"), *((s, s) for s in sets)],
    }


class InventoryScreen:
    def __init__(self, session: GameSession, confirm: Confirm) -> None:
        self.session = session
        self.confirm = confirm
        self.filter = PackFilter()
        self.selecting = False
        self.selected: set[int] = set()
        self._shown: list[ItemView] = []  # the pack after filtering

        self.sheet = ft.Column(spacing=4)
        self.equipped = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.pack = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.pack_heading = ft.Text(size=16, weight=ft.FontWeight.BOLD, expand=True)
        self.select_button = ft.TextButton(icon=ft.Icons.CHECKLIST, on_click=self._toggle_select)
        self.filters = {
            name: ft.Dropdown(
                label=label,
                dense=True,
                expand=True,
                on_select=lambda _, n=name: self._filter_changed(n),
            )
            for name, label in (("slot", "Slot"), ("affix", "Affix"), ("gear_set", "Set"))
        }
        self.selection_bar = ft.Row(wrap=True, spacing=8, run_spacing=4)
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
                                ft.Row(controls=[self.pack_heading, self.select_button]),
                                ft.Row(spacing=8, controls=list(self.filters.values())),
                                self.selection_bar,
                                self.pack,
                            ],
                        ),
                    ],
                ),
            ),
        )
        self.refresh()

    # --- actions -----------------------------------------------------------------

    def act(self, command: Command) -> None:
        self.session.perform(command)  # autosaves
        self.refresh()

    def _drop(self, item: ItemView) -> None:
        def drop() -> None:
            self.act(Drop(item.id))

        where = "You'll leave it here; you can pick it up again."
        self.confirm(f"Drop the {item.name}?", where, "Drop", drop)

    def _drop_selected(self, _: ft.Event) -> None:
        chosen = [i for i in self._shown if i.id in self.selected]
        if not chosen:
            return

        def drop() -> None:
            for item in chosen:
                self.session.perform(Drop(item.id))
            self.selected.clear()
            self.selecting = False
            self.refresh()

        names = ", ".join(i.name for i in chosen[:3]) + (" …" if len(chosen) > 3 else "")
        self.confirm(
            f"Drop {len(chosen)} item{'s' if len(chosen) != 1 else ''}?",
            f"{names}. You'll leave them here; you can pick them up again.",
            "Drop all",
            drop,
        )

    def _toggle_select(self, _: ft.Event) -> None:
        self.selecting = not self.selecting
        self.selected.clear()
        self.refresh()

    def _select(self, item_id: int, on: bool) -> None:
        (self.selected.add if on else self.selected.discard)(item_id)
        self.refresh()

    def _select_all_shown(self, _: ft.Event) -> None:
        self.selected = {i.id for i in self._shown}
        self.refresh()

    def _filter_changed(self, name: str) -> None:
        values = {n: d.value or ALL for n, d in self.filters.items()}
        self.filter = PackFilter(**values)
        self.refresh()

    # --- rendering ---------------------------------------------------------------

    def refresh(self) -> None:
        view = self.session.game.inventory()
        self.sheet.controls = self._sheet(view)
        self.equipped.controls = [self._slot(slot) for slot in view.slots]

        options = filter_options(view.pack)
        for name, dropdown in self.filters.items():
            dropdown.options = [ft.DropdownOption(key=k, text=t) for k, t in options[name]]
            current = getattr(self.filter, name)
            dropdown.value = current if current in {k for k, _ in options[name]} else ALL
        self.filter = PackFilter(**{n: d.value for n, d in self.filters.items()})

        self._shown = [i for i in view.pack if self.filter.keeps(i)]
        self.selected &= {i.id for i in self._shown}
        count = len(view.pack)
        self.pack_heading.value = (
            f"Pack ({len(self._shown)} of {count} shown)"
            if self.filter.active
            else f"Pack ({count})"
        )
        self.select_button.content = "Done" if self.selecting else "Select"
        self.select_button.visible = bool(view.pack)
        for dropdown in self.filters.values():
            dropdown.visible = bool(view.pack)
        self.selection_bar.visible = self.selecting
        self.selection_bar.controls = [
            ft.Text(f"{len(self.selected)} selected", size=14),
            ft.TextButton(content="Select all shown", on_click=self._select_all_shown),
            ft.FilledTonalButton(
                content="Drop selected",
                icon=ft.Icons.FILE_DOWNLOAD_OUTLINED,
                disabled=not self.selected,
                on_click=self._drop_selected,
            ),
        ]
        if not view.pack:
            self.pack.controls = [_muted("Your pack is empty.")]
        elif not self._shown:
            self.pack.controls = [_muted("Nothing in your pack matches these filters.")]
        else:
            self.pack.controls = [gear_compare_card(i, self._pack_actions(i)) for i in self._shown]

    def _sheet(self, view: InventoryView) -> list[ft.Control]:
        total = view.sheet.total
        lines: list[ft.Control] = [
            ft.Text(
                "   ".join(f"{STAT_LABELS[s]} {total[s]}" for s in STATS),
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
        if self.selecting:
            return [
                ft.Checkbox(
                    label="Selected",
                    value=item.id in self.selected,
                    on_change=lambda e, i=item.id: self._select(i, bool(e.control.value)),
                )
            ]
        return [
            ft.FilledButton(
                content="Equip",
                icon=ft.Icons.CHECK,
                on_click=lambda _, i=item.id: self.act(Equip(i)),
            ),
            self._drop_button(item),
        ]

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

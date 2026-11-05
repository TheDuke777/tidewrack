"""Your pack as a list you can filter, sort and select from.

Used by the Inventory tab and by a shop that buys gear, so both look and behave
the same. Filters (slot, affix, set) and the sort (name, ATK, DEF, HP, verdict or
sale price, either way round) live in a PackChoices shared by every PackList in an
open world, so what you pick in one place carries over to the other. Select mode
is per list: the owner says which bulk actions it offers (drop, sell, ...).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import flet as ft

from tidewrack.core.engine.game import ItemView
from tidewrack.core.gear.stats import STAT_LABELS, STATS
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


BY_NAME, BY_PRICE = "name", "price"
SORTS = [
    (BY_NAME, "Name"),
    *((s, STAT_LABELS[s]) for s in STATS),
    ("verdict", "Verdict"),
    (BY_PRICE, "Sale price"),
]
VERDICT_RANK = {"better": 3, "mixed": 2, "same": 1, "worse": 0}


def sort_pack(items: Iterable[ItemView], by: str, descending: bool = True) -> list[ItemView]:
    """The pack in `by` order; `descending` puts the most first (Z→A for names).
    Ties fall back to the verdict, then the name, so the order never jumps around
    between refreshes."""
    items = list(items)
    if by == BY_NAME:
        return sorted(items, key=lambda i: (i.name.casefold(), i.id), reverse=descending)

    def gain(item: ItemView) -> int:
        return sum(row.change for row in item.comparison.rows)

    def key(item: ItemView) -> tuple:
        verdict = VERDICT_RANK[item.comparison.verdict]
        if by == "verdict":
            return (verdict, gain(item))
        if by == BY_PRICE:
            return (item.sell_price, verdict, gain(item))
        return (item.total[by], verdict, gain(item))

    ranked = sorted(items, key=lambda i: (i.name.casefold(), i.id))  # A→Z breaks ties
    return sorted(ranked, key=key, reverse=descending)


@dataclass
class PackChoices:
    """Filters and sort, shared by every pack list in an open world (UI only)."""

    filter: PackFilter = field(default_factory=PackFilter)
    sort_by: str = BY_NAME
    descending: bool = False  # names A→Z; stats, verdict and price most first


@dataclass(frozen=True)
class BulkAction:
    """A select-mode button: what it says and what it does with the chosen items."""

    label: str
    icon: ft.IconData
    run: Callable[[list[ItemView]], None]


class PackList:
    """Heading, Select button, filters, sort, the selection bar and the item cards."""

    def __init__(
        self,
        choices: PackChoices,
        actions: Callable[[ItemView], list[ft.Control]],
        bulk: Callable[[], list[BulkAction]],
        refresh: Callable[[], None],
        title: str = "Pack",
        empty: str = "Your pack is empty.",
    ) -> None:
        self.choices = choices
        self._refresh = refresh  # the owner re-reads the game and calls show()
        self._actions = actions
        self._bulk = bulk
        self.title, self.empty = title, empty
        self.selecting = False
        self.selected: set[int] = set()
        self.items: list[ItemView] = []
        self.shown: list[ItemView] = []  # after filtering and sorting

        self.heading = ft.Text(size=16, weight=ft.FontWeight.BOLD, expand=True)
        self.select_button = ft.TextButton(icon=ft.Icons.CHECKLIST, on_click=self._toggle_select)
        self.filters = {
            name: ft.Dropdown(
                label=label,
                dense=True,
                expand=True,
                on_select=lambda _: self._filter_changed(),
            )
            for name, label in (("slot", "Slot"), ("affix", "Affix"), ("gear_set", "Set"))
        }
        self.sort = ft.Dropdown(
            label="Sort",
            dense=True,
            expand=True,
            options=[ft.DropdownOption(key=k, text=t) for k, t in SORTS],
            on_select=lambda _: self._sort_changed(),
        )
        self.order_button = ft.TextButton(on_click=lambda _: self._flip_order())
        self.filter_row = ft.Row(spacing=8, controls=list(self.filters.values()))
        self.sort_row = ft.Row(spacing=8, controls=[self.sort, self.order_button])
        self.selection_bar = ft.Row(wrap=True, spacing=8, run_spacing=4)
        self.cards = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.control = ft.Column(
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Row(controls=[self.heading, self.select_button]),
                self.filter_row,
                self.sort_row,
                self.selection_bar,
                self.cards,
            ],
        )

    def show(self, items: Iterable[ItemView]) -> None:
        """Lay out these items under the shared filters and sort."""
        self.items = list(items)
        choices = self.choices
        options = filter_options(self.items)
        for name, dropdown in self.filters.items():
            dropdown.options = [ft.DropdownOption(key=k, text=t) for k, t in options[name]]
            current = getattr(choices.filter, name)
            # A choice that matches nothing here shows as "any" but is kept for later.
            dropdown.value = current if current in {k for k, _ in options[name]} else ALL
        shown_filter = PackFilter(**{n: d.value for n, d in self.filters.items()})

        kept = [i for i in self.items if shown_filter.keeps(i)]
        self.shown = sort_pack(kept, choices.sort_by, choices.descending)
        self.sort.value = choices.sort_by
        self.sort_row.visible = len(self.items) > 1
        self.filter_row.visible = self.select_button.visible = bool(self.items)
        self.order_button.icon = (
            ft.Icons.ARROW_DOWNWARD if choices.descending else ft.Icons.ARROW_UPWARD
        )
        self.order_button.content = _order_label(choices.sort_by, choices.descending)
        self.selected &= {i.id for i in self.shown}
        count = len(self.items)
        self.heading.value = (
            f"{self.title} ({len(self.shown)} of {count} shown)"
            if shown_filter.active
            else f"{self.title} ({count})"
        )
        self.select_button.content = "Done" if self.selecting else "Select"
        self.selection_bar.visible = self.selecting
        self.selection_bar.controls = [
            ft.Text(f"{len(self.selected)} selected", size=14),
            ft.TextButton(content="Select all shown", on_click=self._select_all_shown),
            *(
                ft.FilledTonalButton(
                    content=action.label,
                    icon=action.icon,
                    disabled=not self.selected,
                    on_click=lambda _, a=action: a.run(self.chosen()),
                )
                for action in self._bulk()
            ),
        ]
        if not self.items:
            self.cards.controls = [_muted(self.empty)]
        elif not self.shown:
            self.cards.controls = [_muted("Nothing in your pack matches these filters.")]
        else:
            self.cards.controls = [gear_compare_card(i, self._card_actions(i)) for i in self.shown]

    def chosen(self) -> list[ItemView]:
        return [i for i in self.shown if i.id in self.selected]

    def end_selection(self) -> None:
        """After a bulk action: leave select mode (the owner then refreshes)."""
        self.selected.clear()
        self.selecting = False

    def _card_actions(self, item: ItemView) -> list[ft.Control]:
        if not self.selecting:
            return self._actions(item)
        return [
            ft.Checkbox(
                label="Selected",
                value=item.id in self.selected,
                on_change=lambda e, i=item.id: self._select(i, bool(e.control.value)),
            )
        ]

    def _redraw(self) -> None:
        self._refresh()

    def _toggle_select(self, _: ft.Event) -> None:
        self.selecting = not self.selecting
        self.selected.clear()
        self._redraw()

    def _select(self, item_id: int, on: bool) -> None:
        (self.selected.add if on else self.selected.discard)(item_id)
        self._redraw()

    def _select_all_shown(self, _: ft.Event) -> None:
        self.selected = {i.id for i in self.shown}
        self._redraw()

    def _sort_changed(self) -> None:
        self.choices.sort_by = self.sort.value or BY_NAME
        # Stats, verdict and price read most first; names read A→Z.
        self.choices.descending = self.choices.sort_by != BY_NAME
        self._redraw()

    def _flip_order(self) -> None:
        self.choices.descending = not self.choices.descending
        self._redraw()

    def _filter_changed(self) -> None:
        self.choices.filter = PackFilter(**{n: d.value or ALL for n, d in self.filters.items()})
        self._redraw()


def sell_message(items: list[ItemView], buyer: str) -> tuple[str, str, str]:
    """(title, message, button) for the confirm before selling these items."""
    total = sum(i.sell_price for i in items)
    if len(items) == 1:
        [item] = items
        return (
            f"Sell the {item.name}?",
            f"The {buyer} pays {total} gold. Buying it back costs more.",
            f"Sell for {total} gold",
        )
    return (
        f"Sell {len(items)} items?",
        f"{name_list(items)}. The {buyer} pays {total} gold for them.",
        f"Sell for {total} gold",
    )


def name_list(items: list[ItemView]) -> str:
    return ", ".join(i.name for i in items[:3]) + (" …" if len(items) > 3 else "")


def _order_label(by: str, descending: bool) -> str:
    if by == BY_NAME:
        return "Z to A" if descending else "A to Z"
    if by == BY_PRICE:
        return "Highest first" if descending else "Lowest first"
    return "Best first" if descending else "Worst first"


def _muted(text: str) -> ft.Text:
    return ft.Text(text, size=14, color=ft.Colors.ON_SURFACE_VARIANT)

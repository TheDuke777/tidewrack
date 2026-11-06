"""The gear comparison card, used wherever gear appears (CLAUDE.md §8.4).

It shows, against what the player has on now: a verdict chip, what the item
would replace, the base Δ and total Δ for every stat, the player's stats before
and after, set bonuses and effects gained or lost, and what the item could reach
fully upgraded. Everything comes from one Comparison (core.gear.compare), so the
card can't disagree with the game.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import flet as ft

from tidewrack.core.engine.game import ItemView
from tidewrack.core.gear.compare import Comparison, format_stats
from tidewrack.core.gear.stats import STAT_LABELS, STATS
from tidewrack.ui import theme
from tidewrack.ui.components.card import card
from tidewrack.ui.components.set_chip import set_chip
from tidewrack.ui.components.stat_delta import delta_color, stat_delta
from tidewrack.ui.components.unread import new_chip

VERDICTS = {
    "better": ("▲ Better", None),  # theme.good(), which depends on brightness
    "worse": ("▼ Worse", ft.Colors.ERROR),
    "mixed": ("◆ Mixed", ft.Colors.TERTIARY),
    "same": ("＝ Same", ft.Colors.ON_SURFACE_VARIANT),
}
STAT_COLUMN, DELTA_COLUMN = 44, 64


def verdict_chip(verdict: str) -> ft.Container:
    label, color = VERDICTS[verdict]
    color = color or theme.good()
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        border=ft.Border.all(1, color),
        border_radius=ft.BorderRadius.all(12),
        content=ft.Text(label, size=13, color=color, weight=ft.FontWeight.BOLD),
    )


def chips(item: ItemView) -> list[ft.Control]:
    """Top-right of the card: the verdict (unless equipped) and the item's set."""
    found: list[ft.Control] = []
    if not item.comparison.equipped:
        found.append(verdict_chip(item.comparison.verdict))
    if item.gear_set and item.gear_set_id:
        found.append(set_chip(item.gear_set, item.gear_set_id, item.gear_set_color))
    return found


def impact_line(comparison: Comparison) -> str:
    """ "ATK 4 → 7 · DEF 3 → 2 · HP 20": the player's stats before → after."""
    parts = []
    for row in comparison.rows:
        label = STAT_LABELS[row.stat]
        parts.append(
            f"{label} {row.before}" if row.change == 0 else f"{label} {row.before} → {row.after}"
        )
    return " · ".join(parts)


def subtitle(item: ItemView) -> str:
    comparison = item.comparison
    parts = [item.slot]
    if item.upgrade:
        parts.append(f"upgrade {item.upgrade}")
    if comparison.equipped:
        parts.append("equipped")
    elif comparison.replaces:
        parts.append("replaces " + " and ".join(comparison.replaces))
    else:
        parts.append("empty slot")
    return " · ".join(parts)


def notes(item: ItemView) -> list[str]:
    """Lines under the stat table: sets, effects, upgrade potential."""
    comparison = item.comparison
    lines = [f"Gains set bonus: {s}" for s in comparison.sets_gained]
    lines += [f"Loses set bonus: {s}" for s in comparison.sets_lost]
    lines += [f"New effect: {e}" for e in comparison.effects_gained]
    lines += [f"Loses effect: {e}" for e in comparison.effects_lost]
    if comparison.equipped:
        lines += [f"Effect: {e}" for e in item.effects]
    if comparison.at_max is not None:
        maxed = " · ".join(f"{STAT_LABELS[s]} {comparison.at_max[s]}" for s in STATS)
        lines.append(f"Fully upgraded, you'd have {maxed}")
    return lines


def summary(item: ItemView) -> ft.Control:
    """A collapsed card's one line: what it changes ("ATK ▲ +2  DEF ▼ −1")."""
    comparison = item.comparison
    if comparison.equipped:
        return ft.Text(f"Gives {format_stats(item.total) or 'no stats'}", size=14)
    # What happens to *your* stats (set bonuses included), like the table's You column.
    changes = [row for row in comparison.rows if row.change]
    sets = [ft.Text(f"Gains set bonus: {s}", size=13) for s in comparison.sets_gained]
    sets += [ft.Text(f"Loses set bonus: {s}", size=13) for s in comparison.sets_lost]
    if not changes:
        line: ft.Control = ft.Text("No change to your stats", size=14)
        return ft.Column(spacing=2, controls=[line, *sets]) if sets else line
    line = ft.Row(
        wrap=True,
        spacing=12,
        run_spacing=2,
        controls=[
            ft.Row(
                spacing=4,
                tight=True,
                controls=[
                    ft.Text(STAT_LABELS[row.stat], size=14, weight=ft.FontWeight.BOLD),
                    stat_delta(row.change),
                ],
            )
            for row in changes
        ],
    )
    return ft.Column(spacing=2, controls=[line, *sets]) if sets else line


def fold_button(collapsed: bool, on_toggle: Callable[[], None]) -> ft.IconButton:
    """The chevron that opens or folds a card; it says what it does to screen readers."""
    return ft.IconButton(
        icon=ft.Icons.EXPAND_MORE if collapsed else ft.Icons.EXPAND_LESS,
        tooltip="Show details" if collapsed else "Hide details",
        on_click=lambda _: on_toggle(),
    )


def gear_compare_card(
    item: ItemView,
    actions: Sequence[ft.Control] = (),
    details: Sequence[ft.Control] = (),  # e.g. what crafting it costs, above the actions
    collapsed: bool = False,  # top row, a one-line summary, details and actions only
    on_toggle: Callable[[], None] | None = None,  # makes it foldable (tap the top row)
    new: bool = False,  # a "New" chip: it's behind a dot you just cleared
) -> ft.Card:
    comparison = item.comparison
    # Top row: name, verdict, the fold arrow. Under it, full width: the set chip and
    # the slot/upgrade/replaces line, so neither is squeezed beside the chips.
    verdict = [] if comparison.equipped else [verdict_chip(comparison.verdict)]
    gear_set = (
        [set_chip(item.gear_set, item.gear_set_id, item.gear_set_color)]
        if item.gear_set and item.gear_set_id
        else []
    )
    header = ft.Column(
        spacing=4,
        controls=[
            ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(item.name, size=17, weight=ft.FontWeight.BOLD, expand=True),
                    *([new_chip()] if new else []),
                    *verdict,
                    *([fold_button(collapsed, on_toggle)] if on_toggle else []),
                ],
            ),
            ft.Row(
                wrap=True,
                spacing=8,
                run_spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    *gear_set,
                    ft.Text(subtitle(item), size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                ],
            ),
        ],
    )
    top: ft.Control = (
        ft.Container(content=header, on_click=lambda _: on_toggle()) if on_toggle else header
    )
    body: list[ft.Control] = [top]
    if collapsed:
        body.append(summary(item))
    elif comparison.equipped:
        # Nothing to compare against: show what it gives instead.
        body.append(ft.Text(f"Gives {format_stats(item.total) or 'no stats'}", size=14))
    else:
        body.append(
            ft.Column(spacing=4, controls=[_table_header(), *map(_table_row, comparison.rows)])
        )
        body.append(ft.Text(f"You: {impact_line(comparison)}", size=13))
    if not collapsed:
        body += [ft.Text(n, size=13, color=ft.Colors.ON_SURFACE_VARIANT) for n in notes(item)]
    body += list(details)
    if actions:
        body.append(ft.Row(wrap=True, spacing=8, run_spacing=8, controls=list(actions)))
    return card(
        ft.Container(padding=12, content=ft.Column(spacing=10, controls=body)),
    )


def _table_header() -> ft.Row:
    style = {"size": 12, "color": ft.Colors.ON_SURFACE_VARIANT}
    return ft.Row(
        spacing=8,
        controls=[
            ft.Text("", width=STAT_COLUMN, **style),
            ft.Text("Base", width=DELTA_COLUMN, **style),
            ft.Text("Total", width=DELTA_COLUMN, **style),
            ft.Text("You", **style),
        ],
    )


def _table_row(row) -> ft.Row:
    you = str(row.before) if row.change == 0 else f"{row.before} → {row.after}"
    return ft.Row(
        spacing=8,
        controls=[
            ft.Text(STAT_LABELS[row.stat], width=STAT_COLUMN, size=14, weight=ft.FontWeight.BOLD),
            stat_delta(row.base_delta, width=DELTA_COLUMN),
            stat_delta(row.total_delta, width=DELTA_COLUMN),
            ft.Text(you, size=14, color=delta_color(row.change)),
        ],
    )

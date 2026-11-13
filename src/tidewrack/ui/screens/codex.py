"""The codex: what you've discovered. Foes, materials, ingredients, recipes, meals.

Foe entries fill in as you beat them (core.codex.foes): unknown details show as
"???", and each card says what defeating more of them will reveal. Materials and
ingredients (core.codex.items) say where they're gathered, who drops them, which
markets sell them and what uses them; recipes and meals say what they need and
what you have.

Every level collapses: the section and each group inside it (Beasts, People…;
regions for materials). Sections start closed so the codex reads as a list of
contents, except one holding something new, which opens with a "New" chip on
its heading. What you open or close is remembered while the world is open.
"""

from __future__ import annotations

import flet as ft

from tidewrack.core.codex.foes import FoeView
from tidewrack.core.codex.items import CodexView, MaterialEntryView
from tidewrack.core.engine.game import CostView, MenuView, RecipeView
from tidewrack.core.gear.stats import STAT_LABELS, STATS
from tidewrack.services.session import GameSession
from tidewrack.ui.components.card import card
from tidewrack.ui.components.coins import coins
from tidewrack.ui.components.meal_card import meal_card
from tidewrack.ui.components.unread import Unread, new_chip

UNKNOWN = "???"
NOWHERE = "You don't know of anywhere to find more."


class CodexScreen:
    def __init__(self, session: GameSession, unread: Unread | None = None) -> None:
        self.session = session
        self.unread = unread  # for "New" chips
        self.open: dict[str, bool] = {}  # section/group key -> expanded, once you choose
        self.sections = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.control = ft.SafeArea(
            expand=True,
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    expand=True,
                    controls=[
                        ft.Text("Codex", size=22, weight=ft.FontWeight.BOLD),
                        ft.ListView(expand=True, spacing=12, controls=[self.sections]),
                    ],
                ),
            ),
        )
        self.refresh()

    def refresh(self) -> None:
        book = self.session.game.codex()
        self.sections.controls = [
            self._foes_section(),
            self._materials_section(
                "materials",
                "Materials",
                book.materials,
                "No materials yet. Whatever you gather, loot or see for sale is recorded here.",
            ),
            self._materials_section(
                "ingredients",
                "Ingredients",
                book.ingredients,
                "No ingredients yet. Whatever you gather, loot or see on a menu is recorded here.",
            ),
            self._recipes_section(book.recipes.known, book.recipes.to_find),
            self._meals_section(book.meals),
        ]

    # --- sections ------------------------------------------------------------------

    def _foes_section(self) -> ft.Control:
        foes = self.session.game.foes()
        groups = foes.by_category()
        inner: list[ft.Control] = [
            self._tile(
                f"foes/{heading}",
                f"{heading} ({len(group)})",
                [foe_card(foe, new=self._new("foe", foe.enemy_id)) for foe in group],
                size=15,
                new=any(self._new("foe", f.enemy_id) for f in group),
            )
            for heading, group in groups
        ] or [_empty("You haven't met any foes yet. Whatever you fight is recorded here.")]
        new = any(self._new("foe", f.enemy_id) for f in foes.foes)
        return self._tile("foes", f"Foes ({len(foes.foes)})", inner, size=18, new=new, top=True)

    def _materials_section(
        self, key: str, title: str, entries: tuple[MaterialEntryView, ...], empty: str
    ) -> ft.Control:
        def is_new(entry: MaterialEntryView) -> bool:
            return self._new("material", entry.material.id)

        inner: list[ft.Control] = [
            self._tile(
                f"{key}/{region}",
                f"{region} ({len(group)})",
                [material_card(e, new=is_new(e)) for e in group],
                size=15,
                new=any(is_new(e) for e in group),
            )
            for region, group in CodexView.by_region(entries)
        ] or [_empty(empty)]
        new = any(is_new(e) for e in entries)
        return self._tile(key, f"{title} ({len(entries)})", inner, size=18, new=new, top=True)

    def _recipes_section(self, known: tuple[RecipeView, ...], to_find: str | None) -> ft.Control:
        inner: list[ft.Control] = [
            recipe_card(r, new=self._new("recipe", r.id)) for r in known
        ] or [_empty("You don't know any recipes yet.")]
        if to_find:
            inner.append(_empty(to_find))
        new = any(self._new("recipe", r.id) for r in known)
        return self._tile("recipes", f"Recipes ({len(known)})", inner, size=18, new=new, top=True)

    def _meals_section(self, meals: tuple[MenuView, ...]) -> ft.Control:
        inner: list[ft.Control] = [
            meal_card(m.meal, details=meal_details(m), new=self._new("meal", m.meal.id))
            for m in meals
        ] or [_empty("No meals yet. Every tavern's menu is recorded here once you've been in.")]
        new = any(self._new("meal", m.meal.id) for m in meals)
        return self._tile("meals", f"Meals ({len(meals)})", inner, size=18, new=new, top=True)

    def _new(self, kind: str, key: str) -> bool:
        return self.unread is not None and self.unread.is_new("codex", (kind, key))

    def _tile(
        self,
        key: str,
        title: str,
        controls: list[ft.Control],
        size: int,
        new: bool = False,
        top: bool = False,  # a section: closed unless it holds something new
    ) -> ft.ExpansionTile:
        def changed(e: ft.Event) -> None:
            self.open[key] = bool(e.data)

        default = new or not top
        return ft.ExpansionTile(
            title=ft.Row(
                spacing=8,
                controls=[
                    ft.Text(title, size=size, weight=ft.FontWeight.BOLD),
                    *([new_chip()] if new else []),
                ],
            ),
            expanded=self.open.get(key, default),
            maintain_state=True,
            controls_padding=ft.Padding.only(left=8, bottom=8),
            tile_padding=ft.Padding.symmetric(horizontal=4),
            expanded_cross_axis_alignment=ft.CrossAxisAlignment.STRETCH,
            on_change=changed,
            controls=controls,
        )


def _empty(text: str) -> ft.Text:
    return ft.Text(text, size=14, color=ft.Colors.ON_SURFACE_VARIANT)


def _fact(text: str) -> ft.Control:
    return coins(text, size=13, color=ft.Colors.ON_SURFACE_VARIANT)


def _costs(costs: tuple[CostView, ...]) -> str:
    return ", ".join(f"{c.name} {c.have}/{c.need}" for c in costs)


def _entry(title: str, top_right: str | None, new: bool, body: list[ft.Control]) -> ft.Card:
    return card(
        ft.Container(
            padding=12,
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Row(
                        spacing=8,
                        controls=[
                            ft.Text(title, size=17, weight=ft.FontWeight.BOLD, expand=True),
                            *([new_chip()] if new else []),
                            *(
                                [ft.Text(top_right, size=13, color=ft.Colors.ON_SURFACE_VARIANT)]
                                if top_right
                                else []
                            ),
                        ],
                    ),
                    *body,
                ],
            ),
        )
    )


# --- foes --------------------------------------------------------------------------


def foe_lines(foe: FoeView) -> list[str]:
    """The card's text below the description, "???" where still unknown."""
    if foe.stats is None:
        strength = UNKNOWN
    else:
        strength = " · ".join(f"{STAT_LABELS[s]} {foe.stats.get(s, 0)}" for s in STATS)
    if foe.drops is None:
        drops = UNKNOWN
    else:
        drops = ", ".join(foe.drops) or "nothing"
    lines = [f"Defeated: {foe.defeated}", f"Strength: {strength}", f"Drops: {drops}"]
    if foe.found_in:
        lines.append(
            foe.found_in if foe.found_in.startswith("Guards") else f"Found in: {foe.found_in}"
        )
    if foe.next_reveal:
        lines.append(foe.next_reveal)
    return lines


def foe_card(foe: FoeView, new: bool = False) -> ft.Card:
    return _entry(
        foe.name,
        None,
        new,
        [
            ft.Text(foe.description, size=14),
            *(_fact(line) for line in foe_lines(foe)),
        ],
    )


# --- materials and ingredients -----------------------------------------------------


def material_lines(entry: MaterialEntryView) -> list[str]:
    """Where to find it, what uses it, and what a market pays."""
    lines = []
    if entry.gathered:
        lines.append(f"Gathered in: {entry.gathered}")
    if entry.dropped_by:
        lines.append(f"Dropped by: {entry.dropped_by}")
    if entry.sold_at:
        lines.append(f"Sold at: {entry.sold_at}")
    if not lines:
        lines.append(NOWHERE)
    lines.extend(entry.uses)
    lines.append(f"Markets pay {entry.material.sell_price} gold each")
    return lines


def material_card(entry: MaterialEntryView, new: bool = False) -> ft.Card:
    material = entry.material
    return _entry(
        material.name,
        f"You have {material.count}" if material.count else None,
        new,
        [
            ft.Text(material.description, size=14),
            *(_fact(line) for line in material_lines(entry)),
        ],
    )


# --- recipes and meals -------------------------------------------------------------


def recipe_lines(recipe: RecipeView) -> list[str]:
    item = recipe.item
    stats = " · ".join(f"{STAT_LABELS[s]} {item.total[s]}" for s in STATS if item.total.get(s))
    makes = " · ".join(p for p in (item.slot, stats) if p)
    return [
        f"Makes: {makes}",
        f"Needs: {_costs(recipe.materials)}",
        f"Craft at any Smithy for {recipe.fee} gold",
    ]


def recipe_card(recipe: RecipeView, new: bool = False) -> ft.Card:
    return _entry(
        recipe.name,
        "Can craft" if recipe.can_craft else None,
        new,
        [_fact(line) for line in recipe_lines(recipe)],
    )


def meal_lines(menu: MenuView) -> list[str]:
    lines = [
        f"Ingredients: {_costs(menu.ingredients)}",
        f"Cook at any Tavern for {menu.fee} gold",
    ]
    if menu.price is not None:
        lines.append(f"Taverns sell it ready-made for {menu.price} gold")
    return lines


def meal_details(menu: MenuView) -> list[ft.Control]:
    return [_fact(line) for line in meal_lines(menu)]

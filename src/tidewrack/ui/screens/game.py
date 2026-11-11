"""The game screen: explore the rooms of a location and travel between locations.

Reads only Game.view() and sends only commands, through the GameSession so every
action autosaves (CLAUDE.md §4, §6). Flet re-renders after each event handler
returns, so handlers just update controls.

Below the map, the room details and the log share the space. The bar between
them hides or shows the log when tapped and resizes it when dragged (dragging it
to the bottom hides it); the choice is an app-wide setting, not part of the save.

A notice board or shop shows in the room as one button. Tapping it opens a panel
that takes over the screen like a fight does (no map or room details) until you
leave it or anything moves you; which panel is open is UI state, not saved.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

import flet as ft

from tidewrack.core.engine.events import (
    ActionRejected,
    ItemBought,
    ItemCrafted,
    ItemSold,
    ItemUpgraded,
    MaterialsBought,
    MaterialsSold,
    MealBought,
    MealCooked,
    QuestCompleted,
)
from tidewrack.core.engine.game import (
    AcceptQuest,
    Buy,
    BuyMaterials,
    BuyMeal,
    Command,
    Cook,
    CostView,
    Craft,
    Equip,
    GameView,
    ItemView,
    Look,
    Move,
    RecipeView,
    Rest,
    Sell,
    SellMaterials,
    ShopView,
    Take,
    Travel,
    TurnInQuest,
    Upgrade,
    UpgradeView,
    Wait,
)
from tidewrack.services.session import GameSession
from tidewrack.services.settings import SettingsStore
from tidewrack.ui.components.card import card
from tidewrack.ui.components.coins import coins
from tidewrack.ui.components.combat_panel import combat_panel
from tidewrack.ui.components.folds import Folds
from tidewrack.ui.components.gear_compare_card import gear_compare_card
from tidewrack.ui.components.meal_card import fed_line, meal_card
from tidewrack.ui.components.pack_list import (
    BulkAction,
    Confirm,
    PackChoices,
    PackList,
    sell_message,
)
from tidewrack.ui.components.quest_card import quest_card
from tidewrack.ui.components.unread import dot_icon, dot_label
from tidewrack.ui.map_canvas import MapCanvas, kinds_legend

LOG_LINES_SHOWN = 40

ROOM_LEGEND = (
    "● visited   ○ unexplored   ◉ you   ■ gate (roads leave from here)\n"
    "¤ shop or inn   ✦ items left here   ◆ quest target\n"
    "Tap a ringed room to go there."
)
WORLD_LEGEND = (
    "● visited   ○ unexplored   ◉ you   ✓ fully explored   ◆ quest   ⚔ guarded\n"
    "At a gate, tap a ringed place to travel."
)

MIN_LOG_SHARE, MAX_LOG_SHARE = 0.1, 0.8  # same bounds as Settings.log_share
HIDE_LOG_BELOW = 0.06  # dragging the log smaller than this hides it
LOG_BAR_HEIGHT = 36
DRAG_INTERVAL = 30  # ms between drag updates sent to Python; positions are absolute

BOARD = "board"  # GameScreen.opened for the notice board; a shop is opened by its name
BUY_TAB, SELL_TAB, UPGRADE_TAB, CRAFT_TAB = "buy", "sell", "upgrade", "craft"
MENU_TAB, COOK_TAB = "menu", "cook"
BULK = 5  # "Buy 5" at a market


def _confirm_now(_title: str, _message: str, _action: str, then: Callable[[], None]) -> None:
    then()


@dataclass
class LogSplit:
    """How the text area below the map is split between room details and the log."""

    visible: bool
    share: float  # the log's fraction while visible; kept while hidden
    _start: float = 0.0  # the log's share when the drag began (0 if hidden)

    def toggle(self) -> None:
        self.visible = not self.visible

    def start_drag(self) -> None:
        self._start = self.share if self.visible else 0.0

    def drag_to(self, offset: float) -> None:
        """Put the bar `offset` (a fraction of the area's height) from where the drag
        began; negative = up = bigger log. Absolute, not incremental, so throttled
        or dropped touch events can't make the bar lag behind the finger."""
        reached = min(MAX_LOG_SHARE, self._start - offset)
        self.visible = reached >= HIDE_LOG_BELOW
        if self.visible:
            self.share = max(MIN_LOG_SHARE, reached)

    def expands(self) -> tuple[int, int]:
        """Flet `expand` weights for (details, log)."""
        if not self.visible:
            return 1, 0
        return round((1 - self.share) * 100), round(self.share * 100)


class GameScreen:
    def __init__(
        self,
        session: GameSession,
        settings: SettingsStore,
        on_back: Callable[[], None],
        notify: Callable[[str], None] = lambda _: None,
        confirm: Confirm = _confirm_now,
        choices: PackChoices | None = None,
        shop_choices: PackChoices | None = None,
    ) -> None:
        self.session = session
        self.notify = notify
        self.confirm = confirm
        self.opened: str | None = None  # BOARD, a shop's name, or None
        self._buyer: str | None = None  # the open shop that buys gear
        self.shop_tab = BUY_TAB  # a shop that buys gear has Buy and Sell tabs
        self.craftable_only = False  # Craft tab: hide recipes you lack materials for
        self.settings = settings
        saved = settings.load()
        self.split = LogSplit(saved.log_visible, saved.log_share)

        self.where = ft.Text(size=14, color=ft.Colors.ON_SURFACE_VARIANT, expand=True)
        self.room = ft.Text(size=26, weight=ft.FontWeight.BOLD)
        self.description = ft.Text(size=16)
        self.here = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        # One button per board or shop in the room; the open one's panel below.
        self.entrances = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.panel_heading = ft.Row()
        # A smithy's sell list: your pack, with the Inventory tab's filters and sort.
        self.ground_folds = Folds("ground", settings, self.refresh)
        self.board_folds = Folds("board", settings, self.refresh)
        self.sell_list = PackList(
            choices if choices is not None else PackChoices(),
            folds=Folds("sell", settings, self.refresh),
            actions=self._sell_actions,
            bulk=lambda: [BulkAction("Sell selected", ft.Icons.SELL_OUTLINED, self._sell)],
            refresh=lambda: self.refresh(),
            empty="Nothing in your pack to sell. Take off worn gear on the Inventory "
            "tab to sell it.",
        )
        # A shop's wares on its Buy tab: filters and sort of their own, kept while open.
        self._prices: dict[int, int] = {}  # ware item id -> what it costs
        self._affordable: set[int] = set()
        self._sold: set[int] = set()  # wares on the buy-back shelf
        self._doable_seen: dict[str, set] = {}  # shop tab -> what you've seen doable there
        # Shop tab -> what became doable since you last looked: "New" chips on those
        # cards while you stay on that tab (cleared on switching tab or leaving).
        self._doable_fresh: dict[str, set] = {}
        # A crafting smithy's Upgrade and Craft tabs: filterable lists of their own
        # (one set of choices shared by both), sorted by fee for "Price".
        self._upgrades: dict[int, UpgradeView] = {}
        self._recipes: dict[int, RecipeView] = {}
        craft_choices = PackChoices()
        self.upgrade_list = PackList(
            craft_choices,
            folds=Folds("upgrade", settings, self.refresh),
            actions=self._upgrade_actions,
            bulk=None,
            refresh=lambda: self.refresh(),
            title="Upgrades",
            price=lambda item: self._upgrades[item.id].fee,
            details=self._upgrade_details,
            is_new=lambda item: (
                _upgrade_key(self._upgrades[item.id]) in self._doable_fresh.get(UPGRADE_TAB, set())
            ),
        )
        self.craft_list = PackList(
            craft_choices,
            folds=Folds("craft", settings, self.refresh),
            actions=self._craft_actions,
            bulk=None,
            refresh=lambda: self.refresh(),
            title="Recipes",
            price=lambda item: self._recipes[item.id].fee,
            details=lambda item: [_costs(self._recipes[item.id].materials)],
            is_new=lambda item: (
                self._recipes[item.id].id in self._doable_fresh.get(CRAFT_TAB, set())
            ),
        )
        self.buy_list = PackList(
            shop_choices if shop_choices is not None else PackChoices(),
            folds=Folds("buy", settings, self.refresh),
            actions=self._buy_actions,
            bulk=None,
            refresh=lambda: self.refresh(),
            title="For sale",
            empty="Nothing for sale right now.",
            price=lambda item: self._prices.get(item.id, 0),
        )
        self.board = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.shops = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.exits = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.roads = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.log = ft.ListView(spacing=6, auto_scroll=True)
        self._log_total: int | None = None  # view.log_total at the last refresh (None: not yet)
        self._fresh_from = 0  # log_total index where your latest action's lines begin
        self.status = ft.Text(size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.map = MapCanvas(
            on_command=self.act,
            on_blocked=self.notify,
            legend_open=saved.legend_open,
            on_legend=self._save_legend,
        )
        # Which map is showing: the rooms here ("area"), the world, or none.
        self.map_choice = ft.SegmentedButton(
            allow_empty_selection=True,
            show_selected_icon=False,
            selected=["area"],
            segments=[
                ft.Segment(value="area", icon=ft.Icons.MAP_OUTLINED, tooltip="Map of this place"),
                ft.Segment(value="world", icon=ft.Icons.PUBLIC, tooltip="World map"),
            ],
            on_change=lambda _: self.refresh(),
        )

        self.wait_button = ft.OutlinedButton(
            content="Wait", icon=ft.Icons.HOURGLASS_EMPTY, on_click=self._wait
        )
        self.actions = ft.Row(
            spacing=8,
            controls=[
                ft.OutlinedButton(
                    content="Look around", icon=ft.Icons.VISIBILITY, on_click=self._look
                ),
                self.wait_button,
            ],
        )
        self.combat = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        # The room text and buttons scroll on their own, under a fixed map, and the
        # log below scrolls separately (it follows the newest line).
        self.details = ft.ListView(
            spacing=12,
            controls=[
                self.room,
                self.description,
                self.combat,
                self.panel_heading,
                self.board,
                self.shops,
                self.entrances,
                self.here,
                self.exits,
                self.roads,
                self.actions,
            ],
        )
        self.log_hint = ft.Text(
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            expand=True,
        )
        self.log_chevron = ft.Icon(
            ft.Icons.EXPAND_MORE, size=20, color=ft.Colors.ON_SURFACE_VARIANT
        )
        log_bar = ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.RESIZE_ROW,
            drag_interval=DRAG_INTERVAL,
            on_tap=lambda _: self._toggle_log(),
            on_vertical_drag_start=self._log_drag_started,
            on_vertical_drag_update=self._drag_log,
            on_vertical_drag_end=self._log_drag_ended,
            content=ft.Container(
                height=LOG_BAR_HEIGHT,
                border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
                content=ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.DRAG_HANDLE, size=20, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text("Log", size=13, weight=ft.FontWeight.BOLD),
                        self.log_hint,
                        self.log_chevron,
                    ],
                ),
            ),
        )
        self._panes_height = 400.0  # until the first size report
        self._drag_start_y = 0.0
        self.panes = ft.Column(
            expand=True,
            spacing=0,
            controls=[self.details, log_bar, self.log],
            on_size_change=self._panes_resized,
        )
        self._shown_room: tuple[str, str] | None = None
        self._was_fighting = False
        header = ft.Row(
            controls=[
                # A menu, not a back arrow: an arrow up here reads as "back one
                # step" and kept leaving the world when a panel was meant.
                # Settings and Help will join Switch world here (step 10).
                ft.PopupMenuButton(
                    icon=ft.Icons.MENU,
                    tooltip="Menu",
                    items=[
                        ft.PopupMenuItem(
                            content="Switch world",
                            icon=ft.Icons.PUBLIC,
                            on_click=lambda _: on_back(),
                        ),
                    ],
                ),
                self.where,
                self.map_choice,
            ],
        )
        self.control = ft.SafeArea(
            expand=True,
            content=ft.Container(
                # Little below the status row: it's the last thing on screen.
                padding=ft.Padding(left=16, top=16, right=16, bottom=4),
                content=ft.Column(
                    expand=True,
                    spacing=12,
                    controls=[
                        header,
                        self.map.control,
                        # The status row sits close under the log, not a full gap away.
                        ft.Column(expand=True, spacing=2, controls=[self.panes, self.status]),
                    ],
                ),
            ),
        )
        self.refresh()

    # --- handlers ----------------------------------------------------------------

    def act(self, command: Command) -> None:
        self.session.perform(command)  # autosaves
        self.refresh()

    def _look(self, _: ft.Event) -> None:
        self.act(Look())

    def _wait(self, _: ft.Event) -> None:
        self.act(Wait())

    def open(self, place: str) -> None:
        """Open the notice board (BOARD) or the shop with this name."""
        self._doable_fresh.clear()
        self.opened = place
        self.shop_tab = BUY_TAB
        self._scroll_details_to_top()
        self.refresh()

    def close(self) -> None:
        self._doable_fresh.clear()
        self.opened = None
        self.refresh()

    def _toggle_log(self) -> None:
        # Opening the log jumps straight to its newest line instead of gliding
        # down from the top; new lines still glide in (refresh turns it back on).
        self.log.auto_scroll_animation = 0
        self.split.toggle()
        self._save_split()

    def _log_drag_started(self, e: ft.DragStartEvent) -> None:
        self._drag_start_y = e.global_position.y
        self.split.start_drag()

    def _drag_log(self, e: ft.DragUpdateEvent) -> None:
        self._follow_finger(e.global_position.y)
        self._apply_split()

    def _log_drag_ended(self, e: ft.DragEndEvent) -> None:
        if e.global_position is not None:
            self._follow_finger(e.global_position.y)
        self._save_split()

    def _follow_finger(self, y: float) -> None:
        # The bar itself doesn't stretch; only the two panes share the drag.
        shared = max(self._panes_height - LOG_BAR_HEIGHT, 1.0)
        self.split.drag_to((y - self._drag_start_y) / shared)

    def _panes_resized(self, e: ft.LayoutSizeChangeEvent) -> None:
        self._panes_height = e.height

    def _save_legend(self, open_: bool) -> None:
        current = self.settings.load()  # keep the other settings
        self.settings.save(current.model_copy(update={"legend_open": open_}))

    def _save_split(self) -> None:
        self._apply_split()
        current = self.settings.load()  # keep the other settings
        self.settings.save(
            current.model_copy(
                update={"log_visible": self.split.visible, "log_share": self.split.share}
            )
        )

    def _apply_split(self) -> None:
        self.details.expand, self.log.expand = self.split.expands()
        self.log.visible = self.split.visible
        self.log_chevron.icon = ft.Icons.EXPAND_MORE if self.split.visible else ft.Icons.EXPAND_LESS
        # While the log is hidden, its newest line still shows in the bar.
        self.log_hint.visible = not self.split.visible

    # --- rendering ---------------------------------------------------------------

    def refresh(self) -> None:
        view = self.session.game.view()
        self.where.value = f"{self.session.meta.name} · {view.location} · {view.kind}"
        self.room.value = view.room
        self.description.value = view.description
        if self._shown_room not in (None, (view.location, view.room)):
            self._scroll_details_to_top()
            self.opened = None  # moving (or waking somewhere after a defeat) leaves it
        self._shown_room = (view.location, view.room)
        self.exits.controls = [
            ft.FilledTonalButton(
                content=exit_.label
                if exit_.destination is None
                else f"{exit_.label}  →  {exit_.destination}",
                on_click=lambda _, label=exit_.label: self.act(Move(label)),
            )
            for exit_ in view.exits
        ]
        self.roads.controls = self._roads(view)
        self.here.controls = [
            gear_compare_card(
                item,
                self._take_buttons(item),
                collapsed=self.ground_folds.collapsed(item.id),
                on_toggle=lambda i=item.id: self.ground_folds.toggle(i),
            )
            for item in view.items_here
        ]
        # During a fight, the fight panel replaces everything you can't do anyway.
        fighting = view.combat is not None
        if fighting and not self._was_fighting:
            self._scroll_details_to_top()  # the fight panel is the first thing you see
        self._was_fighting = fighting
        self.combat.controls = [combat_panel(view, self.act)] if fighting else []
        shop = next((s for s in view.shops if s.name == self.opened), None)
        if fighting or (shop is None and not (self.opened == BOARD and view.board is not None)):
            self.opened = None
        self.board.controls = self._board(view) if self.opened == BOARD else []
        self.shops.controls = self._shop(view, shop) if shop is not None else []
        self.entrances.controls = self._entrances(view)
        self.panel_heading.controls = self._panel_heading(view)
        # A fight or an open board/shop takes over the screen; the log stays.
        busy = fighting or self.opened is not None
        self.panel_heading.visible = self.opened is not None
        self.room.visible = self.description.visible = self.opened is None
        for section in (self.entrances, self.here, self.exits, self.roads, self.actions):
            section.visible = not busy
        if self._log_total is None:
            self.log.auto_scroll_animation = 0  # a world just opened: already at the end
            self._fresh_from = view.log_total  # nothing is "latest" yet
        elif view.log_total != self._log_total:
            self.log.auto_scroll_animation = None  # Flet's default glide for new lines
            self._fresh_from = self._log_total
        self._log_total = view.log_total
        self.log.controls = log_lines(view.log[-LOG_LINES_SHOWN:], view.log_total, self._fresh_from)
        self.log_hint.value = view.log[-1] if view.log else ""
        self._apply_split()

        # Worlds saved before v0.4 have no world map; the oldest have no room map.
        area, world = self.map_choice.segments
        area.disabled, world.disabled = view.map is None, view.world_map is None
        # A fight takes over the screen: no map, so it's obvious one has started.
        self.map_choice.visible = not (area.disabled and world.disabled) and not busy
        choice = (self.map_choice.selected or [None])[0]
        shown = {"area": view.map, "world": view.world_map}.get(choice)
        self.map.control.visible = shown is not None and not busy
        if shown is not None:
            on_world = choice == "world"
            legend = f"{kinds_legend(shown)}\n{WORLD_LEGEND}" if on_world else ROOM_LEGEND
            self.map.show(
                shown,
                legend,
                key=(choice, view.location),  # a new map or place: centre on you
                labels=on_world,
                zoom_key=choice,  # each map keeps its own zoom
            )

        # Progress only: stats live in the inventory, and seed and version will go to
        # Settings → About. Settings will also get a toggle to hide this row.
        fed = f" · Fed: {view.fed.name} ({view.fed.turns_left})" if view.fed else ""
        self.status.value = (
            f"Turn {view.turn} · Rooms {view.rooms_visited}/{view.total_rooms} · "
            f"Places {view.locations_visited}/{view.total_locations}{fed}"
        )

    def _scroll_details_to_top(self) -> None:
        """A new room starts at its name, not wherever the last one was scrolled to."""
        try:
            page = self.control.page
        except RuntimeError:  # not on screen yet
            return
        if page is not None:
            page.run_task(self.details.scroll_to, offset=0)

    def _entrances(self, view: GameView) -> list[ft.Control]:
        """The room's notice board and shops, one button each."""
        buttons: list[ft.Control] = []
        if view.board is not None:
            ready = sum(q.state == "ready" for q in view.board)
            posted = len(view.board) - ready
            parts = [f"{posted} posted"] if posted else []
            parts += [f"{ready} ready to turn in"] if ready else []
            label = "Notice board · " + (" · ".join(parts) or "nothing new")
            kind = ft.FilledButton if ready else ft.FilledTonalButton
            buttons.append(
                kind(
                    content=label,
                    icon=ft.Icons.PUSH_PIN_OUTLINED,
                    on_click=lambda _: self.open(BOARD),
                )
            )
        for shop in view.shops:
            parts = []
            if shop.inn_price is not None:
                parts.append(f"beds {shop.inn_price} gold")
            if shop.cooks:
                parts.append("kitchen")
            if shop.materials or shop.buys_materials:
                parts.append("materials")
            elif shop.wares or shop.inn_price is None:
                parts.append(f"{len(shop.wares)} for sale")
            if shop.buys_gear:
                parts.append("buys gear")
            if shop.crafts:
                parts.append("crafts")
            buttons.append(
                ft.FilledTonalButton(
                    content=coins(f"{shop.name} · " + " · ".join(parts)),
                    icon=ft.Icons.BED_OUTLINED
                    if shop.inn_price is not None
                    else ft.Icons.STOREFRONT_OUTLINED,
                    on_click=lambda _, name=shop.name: self.open(name),
                )
            )
        return buttons

    def _panel_heading(self, view: GameView) -> list[ft.Control]:
        """The open panel's title, your gold, and the way back to the room."""
        if self.opened is None:
            return []
        # No back arrow: the one at the top of the screen goes back to the worlds.
        title = "Notice board" if self.opened == BOARD else self.opened
        return [
            ft.Column(
                spacing=0,
                expand=True,
                controls=[
                    ft.Text(title, size=22, weight=ft.FontWeight.BOLD),
                    coins(
                        f"{view.room} · {view.gold} gold",
                        size=13,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
            ),
            ft.OutlinedButton(
                content="Leave",
                icon=ft.Icons.LOGOUT,
                tooltip=f"Back to {view.room}",
                on_click=lambda _: self.close(),
            ),
        ]

    def _board(self, view: GameView) -> list[ft.Control]:
        assert view.board is not None
        if not view.board:
            return [
                ft.Text(
                    "Nothing new is pinned up. Quests you give up come back here.",
                    size=14,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            ]
        cards: list[ft.Control] = []
        for quest in view.board:
            if quest.state == "ready":
                button = ft.FilledButton(
                    content="Turn in",
                    icon=ft.Icons.TASK_ALT,
                    on_click=lambda _, q=quest.id: self._turn_in(q),
                )
            else:
                button = ft.FilledTonalButton(
                    content="Accept",
                    icon=ft.Icons.ADD_TASK,
                    on_click=lambda _, q=quest.id: self.act(AcceptQuest(q)),
                )
            cards.append(
                quest_card(
                    quest,
                    [button],
                    collapsed=self.board_folds.collapsed(quest.id),
                    on_toggle=lambda q=quest.id: self.board_folds.toggle(q),
                )
            )
        return cards

    def _shop(self, view: GameView, shop: ShopView) -> list[ft.Control]:
        """The inn's bed, the wares for sale, and (at a buyer) your pack to sell from."""
        controls: list[ft.Control] = []
        if shop.inn_price is not None:
            full = view.hp >= view.max_hp
            controls += [
                ft.Text(f"HP {view.hp}/{view.max_hp}", size=14),
                ft.FilledTonalButton(
                    content=coins(
                        f"Rest the night · {shop.inn_price} gold"
                        + ("  (you're rested)" if full else "")
                    ),
                    icon=ft.Icons.BED_OUTLINED,
                    disabled=full,
                    on_click=lambda _: self._act_and_tell(Rest()),
                ),
            ]
        if shop.cooks:
            return controls + self._kitchen(shop)
        if shop.materials or shop.buys_materials:
            return controls + self._market(view, shop)
        pack = self.session.game.inventory().pack if shop.buys_gear else ()
        if shop.buys_gear:
            # Tabs, so a shelf full of your old gear doesn't bury the sell list (and
            # the other way round), and crafting has room of its own.
            tabs = [
                (BUY_TAB, f"Buy ({len(shop.wares)})", ft.Icons.SHOPPING_BAG_OUTLINED),
                (SELL_TAB, f"Sell ({len(pack)})", ft.Icons.SELL_OUTLINED),
            ]
            dots: set[str] = set()
            if shop.crafts:
                tabs.append((UPGRADE_TAB, f"Upgrade ({len(shop.upgrades)})", ft.Icons.UPGRADE))
                tabs.append((CRAFT_TAB, f"Craft ({len(shop.recipes)})", ft.Icons.HANDYMAN_OUTLINED))
                # New things you can do: an upgrade for gear you have on, a recipe to craft.
                dots = self._new_doable(
                    {
                        UPGRADE_TAB: {
                            _upgrade_key(u)
                            for u in shop.upgrades
                            if u.can_upgrade and u.item.equipped
                        },
                        CRAFT_TAB: {r.id for r in shop.recipes if r.can_craft},
                    }
                )
            controls.append(self._tabs(tabs, dots=dots))
        if shop.buys_gear and self.shop_tab == SELL_TAB:
            self._buyer = shop.name
            self.sell_list.show(pack)
            controls.append(self.sell_list.control)
            return controls
        if shop.crafts and self.shop_tab == UPGRADE_TAB:
            return controls + self._upgrade_tab(shop)
        if shop.crafts and self.shop_tab == CRAFT_TAB:
            return controls + self._craft_tab(shop)
        if shop.wares or shop.inn_price is None:
            self._prices = {w.item.id: w.price for w in shop.wares}
            self._affordable = {w.item.id for w in shop.wares if w.affordable}
            self._sold = {w.item.id for w in shop.wares if w.sold_by_you}
            self.buy_list.show(w.item for w in shop.wares)
            controls.append(self.buy_list.control)
        return controls

    def _tabs(
        self,
        tabs: list[tuple[str, str, ft.IconData]],
        default: str = BUY_TAB,
        dots: set[str] = frozenset(),  # type: ignore[assignment]  # tabs with something to do
    ) -> ft.SegmentedButton:
        if self.shop_tab not in {value for value, _, _ in tabs}:
            self.shop_tab = default
        # Four tabs don't fit a phone with icons; the labels say it all.
        icons = len(tabs) <= 3

        def dotted(tab: str) -> bool:  # something to do there, and you're not on it
            return tab in dots and tab != self.shop_tab

        return ft.SegmentedButton(
            selected=[self.shop_tab],
            show_selected_icon=False,
            segments=[
                ft.Segment(
                    value=v,
                    label=label if icons else dot_label(label, dotted(v)),
                    icon=dot_icon(icon, dotted(v)) if icons else None,
                )
                for v, label, icon in tabs
            ],
            on_change=lambda e: self._shop_tab(e.control.selected),
        )

    # --- crafting at a smithy ------------------------------------------------------

    def _new_doable(self, doable: dict[str, set]) -> set[str]:
        """Tabs with something you can now do that you haven't seen there yet. The tab
        you're on counts as seen, so a dot clears once you look (and stays clear
        until something new becomes doable)."""
        tab = self.shop_tab
        if tab in doable:
            fresh = doable[tab] - self._doable_seen.get(tab, set())
            self._doable_fresh[tab] = (self._doable_fresh.get(tab, set()) | fresh) & doable[tab]
            self._doable_seen[tab] = set(doable[tab])
        return {tab for tab, now in doable.items() if now - self._doable_seen.get(tab, set())}

    def _materials_line(self, ingredients: bool = False) -> ft.Text:
        """What you have that this counter uses: crafting materials, or ingredients."""
        materials = [
            m for m in self.session.game.inventory().materials if m.ingredient == ingredients
        ]
        have = ", ".join(f"{m.name} {m.count}" for m in materials) or "none yet"
        what = "ingredients" if ingredients else "materials"
        return _muted(f"Your {what}: {have}. Markets sell the common ones.")

    def _hide_switch(self) -> ft.Switch:
        return ft.Switch(
            label="Hide what I can't make",
            value=self.craftable_only,
            on_change=lambda e: self._craftable_only(bool(e.control.value)),
        )

    def _upgrade_tab(self, shop: ShopView) -> list[ft.Control]:
        """Each piece of gear you carry, one level up, in a filterable list."""
        ups = [u for u in shop.upgrades if not self.craftable_only or _enough(u.materials)]
        # Shown as the upgraded item, but under the real item's id (what Upgrade takes).
        self._upgrades = {u.item.id: u for u in ups}
        self.upgrade_list.show(replace(u.upgraded, id=u.item.id) for u in ups)
        controls: list[ft.Control] = [self._materials_line(), self._hide_switch()]
        if not shop.upgrades:
            controls.append(_muted("Nothing you carry can be upgraded further here."))
        elif not ups:
            controls.append(_muted("You don't have the materials for any upgrade yet."))
        else:
            controls.append(self.upgrade_list.control)
        return controls

    def _upgrade_actions(self, item: ItemView) -> list[ft.Control]:
        up = self._upgrades[item.id]
        return [
            ft.FilledButton(
                content=coins(f"Upgrade · {up.fee} gold"),
                icon=ft.Icons.UPGRADE,
                disabled=not up.can_upgrade,
                on_click=lambda _, i=item.id: self._act_and_tell(Upgrade(i)),
            )
        ]

    def _upgrade_details(self, item: ItemView) -> list[ft.Control]:
        up = self._upgrades[item.id]
        worn = " (worn)" if up.item.equipped else ""
        return [_muted(f"Your {up.item.name}{worn}, one level up."), _costs(up.materials)]

    def _craft_tab(self, shop: ShopView) -> list[ft.Control]:
        """Every recipe you know, in a filterable list."""
        recipes = [r for r in shop.recipes if not self.craftable_only or _enough(r.materials)]
        # Recipe items aren't in the world yet; give each a stand-in id for the list,
        # from its place among all known recipes so it's stable while filtering.
        place = {r.id: n for n, r in enumerate(shop.recipes)}
        self._recipes = {-(place[r.id] + 1): r for r in recipes}
        self.craft_list.show(replace(r.item, id=i) for i, r in self._recipes.items())
        controls: list[ft.Control] = [self._materials_line(), self._hide_switch()]
        if not shop.recipes:
            controls.append(_muted("You don't know any recipes yet."))
        elif not recipes:
            controls.append(_muted("You don't have the materials for any recipe yet."))
        else:
            controls.append(self.craft_list.control)
        controls.append(_muted("Find more recipes out in the world, or earn them from quests."))
        return controls

    def _craft_actions(self, item: ItemView) -> list[ft.Control]:
        recipe = self._recipes[item.id]
        return [
            ft.FilledButton(
                content=coins(f"Craft · {recipe.fee} gold"),
                icon=ft.Icons.HANDYMAN_OUTLINED,
                disabled=not recipe.can_craft,
                on_click=lambda _, r=recipe.id: self._act_and_tell(Craft(r)),
            )
        ]

    # --- a tavern's kitchen ------------------------------------------------------------

    def _kitchen(self, shop: ShopView) -> list[ft.Control]:
        """What you've eaten, then the ready meals (Menu) or what you can cook (Cook)."""
        view_fed = self.session.game.view().fed
        sold = [m for m in shop.menu if m.price is not None]
        if self.shop_tab not in (MENU_TAB, COOK_TAB):
            self.shop_tab = MENU_TAB
        tabs = [
            (MENU_TAB, f"Menu ({len(sold)})", ft.Icons.RESTAURANT_MENU),
            (COOK_TAB, f"Cook ({len(shop.menu)})", ft.Icons.SOUP_KITCHEN_OUTLINED),
        ]
        controls: list[ft.Control] = [
            ft.Text(fed_line(view_fed), size=14),
            self._tabs(
                tabs,
                default=MENU_TAB,
                dots=self._new_doable({COOK_TAB: {m.meal.id for m in shop.menu if m.can_cook}}),
            ),
        ]
        if self.shop_tab == MENU_TAB:
            controls.append(_muted("Ready to eat. Cooking it yourself is cheaper."))
            for item in sold:
                controls.append(
                    meal_card(
                        item.meal,
                        [
                            ft.FilledButton(
                                content=coins(f"Buy · {item.price} gold"),
                                icon=ft.Icons.SHOPPING_BAG_OUTLINED,
                                disabled=not item.affordable,
                                on_click=lambda _, m=item.meal.id: self._act_and_tell(BuyMeal(m)),
                            )
                        ],
                    )
                )
            return controls
        cookable = [m for m in shop.menu if not self.craftable_only or _enough(m.ingredients)]
        controls += [self._materials_line(ingredients=True), self._hide_switch()]
        if not cookable:
            controls.append(_muted("You don't have the ingredients for any meal yet."))
        for item in cookable:
            controls.append(
                meal_card(
                    item.meal,
                    [
                        ft.FilledButton(
                            content=coins(f"Cook · {item.fee} gold"),
                            icon=ft.Icons.SOUP_KITCHEN_OUTLINED,
                            disabled=not item.can_cook,
                            on_click=lambda _, m=item.meal.id: self._act_and_tell(Cook(m)),
                        )
                    ],
                    details=[_costs(item.ingredients)],
                    new=item.meal.id in self._doable_fresh.get(COOK_TAB, set()),
                )
            )
        controls.append(_muted("Ingredients come from the wild, from beasts, and from any market."))
        return controls

    # --- a market --------------------------------------------------------------------

    def _market(self, view: GameView, shop: ShopView) -> list[ft.Control]:
        held = self.session.game.inventory().materials
        tabs = [(BUY_TAB, f"Buy ({len(shop.materials)})", ft.Icons.SHOPPING_BAG_OUTLINED)]
        if shop.buys_materials:
            tabs.append((SELL_TAB, f"Sell ({len(held)})", ft.Icons.SELL_OUTLINED))
        controls: list[ft.Control] = [self._tabs(tabs)]
        if self.shop_tab == SELL_TAB:
            if not held:
                controls.append(_muted("You have no materials to sell."))
            for material in held:
                total = material.sell_price * material.count
                controls.append(
                    _material_card(
                        material.name,
                        material.description,
                        f"You have {material.count} · {material.sell_price} gold each",
                        [
                            ft.FilledTonalButton(
                                content=coins(f"Sell 1 · {material.sell_price} gold"),
                                icon=ft.Icons.SELL_OUTLINED,
                                on_click=lambda _, m=material.id: self._act_and_tell(
                                    SellMaterials(m, 1)
                                ),
                            ),
                            ft.OutlinedButton(
                                content=coins(f"Sell all {material.count} · {total} gold"),
                                on_click=lambda _, m=material, s=shop.name: self._sell_all_of(m, s),
                            ),
                        ],
                    )
                )
            return controls
        for ware in shop.materials:
            m = ware.material
            controls.append(
                _material_card(
                    m.name,
                    m.description,
                    f"You have {m.count} · {ware.price} gold each",
                    [
                        ft.FilledButton(
                            content=coins(f"Buy 1 · {ware.price} gold"),
                            icon=ft.Icons.SHOPPING_BAG_OUTLINED,
                            disabled=not ware.affordable,
                            on_click=lambda _, i=m.id: self._act_and_tell(BuyMaterials(i, 1)),
                        ),
                        ft.OutlinedButton(
                            content=coins(f"Buy {BULK} · {ware.price * BULK} gold"),
                            disabled=ware.price * BULK > view.gold,
                            on_click=lambda _, i=m.id: self._act_and_tell(BuyMaterials(i, BULK)),
                        ),
                    ],
                )
            )
        if shop.materials:
            controls.append(_muted("Rarer materials come from what you defeat and find."))
        return controls

    def _sell_all_of(self, material, shop: str) -> None:
        total = material.sell_price * material.count
        self.confirm(
            f"Sell all your {material.name}?",
            f"The {shop} pays {total} gold for {material.count}. Buying them back costs more.",
            f"Sell for {total} gold",
            lambda: self._act_and_tell(SellMaterials(material.id, material.count)),
        )

    def _buy_actions(self, item: ItemView) -> list[ft.Control]:
        price, affordable = self._prices[item.id], item.id in self._affordable
        label = f"{'Buy back' if item.id in self._sold else 'Buy'} · {price} gold"
        return [
            ft.FilledButton(
                content=coins(label if affordable else f"{label} (not enough)"),
                icon=ft.Icons.SHOPPING_BAG_OUTLINED,
                disabled=not affordable,
                on_click=lambda _, i=item.id: self._act_and_tell(Buy(i)),
            )
        ]

    def _craftable_only(self, on: bool) -> None:
        self.craftable_only = on
        self.refresh()

    def _shop_tab(self, selected: list[str] | None) -> None:
        tab = (selected or [BUY_TAB])[0]
        if tab != self.shop_tab:
            self._doable_fresh.pop(self.shop_tab, None)  # left that tab: its chips go
        self.shop_tab = tab
        self._scroll_details_to_top()
        self.refresh()

    def _sell_actions(self, item: ItemView) -> list[ft.Control]:
        return [
            ft.OutlinedButton(
                content=coins(f"Sell · {item.sell_price} gold"),
                icon=ft.Icons.SELL_OUTLINED,
                on_click=lambda _, i=item: self._sell([i]),
            )
        ]

    def _sell(self, items: list[ItemView]) -> None:
        if items and self._buyer:
            self.confirm(*sell_message(items, self._buyer), lambda: self._sell_now(items))

    def _sell_now(self, items: list[ItemView]) -> None:
        results = [self.session.perform(Sell(item.id)) for item in items]
        self.sell_list.end_selection()
        self.refresh()  # before any toast: showing one updates the page at once
        events = [e for r in results for e in r.events]
        refused = next((e for e in events if isinstance(e, ActionRejected)), None)
        sold = [e for e in events if isinstance(e, ItemSold)]
        if refused is not None:
            self.notify(refused.reason)
        elif len(sold) == 1:
            self.notify(f"Sold the {sold[0].name} for {sold[0].price} gold.")
        elif sold:
            self.notify(f"Sold {len(sold)} items for {sum(e.price for e in sold)} gold.")

    def _act_and_tell(self, command: Command) -> None:
        """Do it, then toast the outcome: what was bought, or why it was refused."""
        result = self.session.perform(command)
        self.refresh()  # before any toast: showing one updates the page at once
        for event in result.events:
            if isinstance(event, ActionRejected):
                self.notify(event.reason)
                return
            if isinstance(event, ItemBought):
                self.notify(f"{event.name} added to your pack for {event.price} gold.")
                return
            if isinstance(event, ItemCrafted):
                self.notify(f"{event.name} added to your pack, for a {event.fee} gold fee.")
                return
            if isinstance(event, ItemUpgraded):
                self.notify(f"It's now a {event.name}, for a {event.fee} gold fee.")
                return
            if isinstance(event, MealCooked):
                self.notify(f"{event.name} cooked, for a {event.fee} gold fee. Eat it any time.")
                return
            if isinstance(event, MealBought):
                self.notify(f"{event.name} bought for {event.price} gold. Eat it any time.")
                return
            if isinstance(event, MaterialsBought | MaterialsSold):
                verb = "Bought" if isinstance(event, MaterialsBought) else "Sold"
                self.notify(f"{verb} {event.count} {event.name} for {event.price} gold.")
                return

    def _turn_in(self, quest: str) -> None:
        result = self.session.perform(TurnInQuest(quest))
        # Refresh first: showing the toast pushes an update to the page at once, and
        # anything changed after it could reach the screen late (the turned-in card
        # stayed on the board until the next tap).
        self.refresh()
        for event in result.events:
            if isinstance(event, QuestCompleted):
                paid = f", and {event.gold} gold" if event.gold else ""
                self.notify(f"{event.reward} added to your pack{paid}.")

    def _take_buttons(self, item: ItemView) -> list[ft.Control]:
        return [
            ft.FilledButton(
                content="Take & equip",
                icon=ft.Icons.CHECK,
                on_click=lambda _, i=item.id: self._take_and_equip(i),
            ),
            ft.OutlinedButton(
                content="Take",
                icon=ft.Icons.BACKPACK_OUTLINED,
                on_click=lambda _, i=item.id: self.act(Take(i)),
            ),
        ]

    def _take_and_equip(self, item: int) -> None:
        self.session.perform(Take(item))
        self.act(Equip(item))

    def _roads(self, view: GameView) -> list[ft.Control]:
        if not view.roads:
            return []
        if not view.at_gate:
            gates = " or ".join(view.gates)
            return [
                ft.Text(
                    f"Roads out of {view.location} leave from {gates}.",
                    size=14,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            ]
        return [
            ft.FilledButton(
                content=_road_label(road),
                icon=ft.Icons.SHIELD_OUTLINED if road.guard else ft.Icons.SIGNPOST_OUTLINED,
                on_click=lambda _, to=road.location: self.act(Travel(to)),
            )
            for road in view.roads
        ]


def _road_label(road) -> str:
    """ "Travel to Thornea · Stilt Village", plus what's unknown or in the way."""
    text = f"Travel to {road.name} · {road.kind}"
    if road.region:
        text += f" · into {road.region}"
    if road.guard:
        return text + f"  (the {road.guard} bars the way)"
    return text + ("" if road.visited else "  (unexplored)")


def _heading(text: str) -> ft.Text:
    return ft.Text(text, size=16, weight=ft.FontWeight.BOLD)


def _upgrade_key(up) -> tuple:
    """What an upgrade is, for "newly doable": the item and the level it reaches."""
    return (up.item.id, up.upgraded.name)


def log_lines(shown, total: int, fresh_from: int) -> list[ft.Control]:
    """The log, with your latest action's lines in bold under a thin divider.

    `shown` are the last lines of a log whose lines ever written number `total`;
    those numbered `fresh_from` and up came from the latest action. Weight and a
    divider mark them, never colour alone (§11).
    """
    first = total - len(shown)  # the running number of shown[0]
    controls: list[ft.Control] = []
    for i, line in enumerate(shown):
        fresh = first + i >= fresh_from
        if fresh and i > 0 and first + i == fresh_from:
            controls.append(ft.Divider(height=1, thickness=1, color=ft.Colors.OUTLINE_VARIANT))
        controls.append(ft.Text(line, size=14, weight=ft.FontWeight.BOLD if fresh else None))
    return controls


def _muted(text: str) -> ft.Text:
    return ft.Text(text, size=13, color=ft.Colors.ON_SURFACE_VARIANT)


def _costs(costs: tuple[CostView, ...]) -> ft.Row:
    """What a craft or upgrade needs, with what you have: "Iron Ore 1/2 ✗ short".
    Short materials are marked in words and with ✗, not only in colour."""
    return ft.Row(
        wrap=True,
        spacing=12,
        run_spacing=2,
        controls=[ft.Text("Needs:", size=13, weight=ft.FontWeight.BOLD)]
        + [
            ft.Text(
                f"{c.name} {c.have}/{c.need} " + ("✓" if c.enough else "✗ short"),
                size=13,
                color=None if c.enough else ft.Colors.ERROR,
            )
            for c in costs
        ],
    )


def _material_card(name: str, description: str, line: str, actions: list[ft.Control]) -> ft.Card:
    return card(
        ft.Container(
            padding=12,
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Text(name, size=17, weight=ft.FontWeight.BOLD),
                    _muted(description),
                    coins(line, size=14),
                    ft.Row(wrap=True, spacing=8, run_spacing=8, controls=actions),
                ],
            ),
        )
    )


def _enough(costs: tuple[CostView, ...]) -> bool:
    return all(c.enough for c in costs)

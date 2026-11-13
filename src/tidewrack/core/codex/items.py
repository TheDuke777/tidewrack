"""The codex's item sections: materials, ingredients, recipes and meals (v0.10.2).

Discovery is event-driven (subscribers, CLAUDE.md §4): a material or ingredient
gets an entry once you've heard of it, meaning you got some, saw it for sale at a
market, or know a recipe or meal that needs it. A meal gets an entry once you've
seen it on a tavern's menu. Recipes are the ones you know (`Recipes`).

Entries fill in from the world as you learn it, like a foe's "found in": where a
material is gathered and sold (kinds of place by region; regions you haven't
found stay unnamed), which foes drop it (named once you've had it from them or
have beaten enough to learn their drops), and what uses it (your recipes, the
meals you've seen, upgrades for gear you carry).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from tidewrack.core.codex.foes import DROPS_AT
from tidewrack.core.economy import crafting
from tidewrack.core.engine.components import (
    Carried,
    Codex,
    Enemy,
    Grower,
    Material,
    MaterialEntry,
    MaterialStack,
    Position,
    Quest,
    RecipePage,
    Shop,
    Spawner,
)
from tidewrack.core.engine.events import MaterialsGained, RecipeLearned, RoomEntered
from tidewrack.core.gear.item import Item

if TYPE_CHECKING:
    from tidewrack.core.engine.game import (
        Game,
        MaterialView,
        MenuView,
        RecipeView,
    )

UNFOUND_PLACES = "places you haven't found yet"
UNFOUND_MARKETS = "markets you haven't found yet"
UNKNOWN_FOES = "foes you've yet to learn about"
ELSEWHERE = "Further afield"  # the group for materials whose home you haven't found


# --- discovery ---------------------------------------------------------------------


def codex(game: Game) -> Codex:
    return game.world.get(game.player, Codex)


def note_material(game: Game, material: Material, looted_from: str | None = None) -> None:
    entries = codex(game).materials
    entry = entries.get(material.material_id)
    if entry is None:
        entry = entries[material.material_id] = MaterialEntry(_copy(material))
    if looted_from and looted_from not in entry.looted_from:
        entry.looted_from.append(looted_from)


def _copy(material: Material) -> Material:
    return Material(
        material.material_id,
        material.name,
        material.description,
        material.value,
        material.ingredient,
    )


def note_recipes(game: Game) -> None:
    """Everything your known recipes need (at the start, and as you learn more)."""
    for recipe in crafting.known(game).values():
        for need in recipe.materials:
            note_material(game, need.material)


def on_materials_gained(game: Game, event: MaterialsGained) -> None:
    stack = crafting.held(game).get(event.material_id)
    if stack is not None:
        note_material(game, stack.material, event.enemy_id)


def on_recipe_learned(game: Game, event: RecipeLearned) -> None:
    note_recipes(game)


def on_room_entered(game: Game, event: RoomEntered) -> None:
    """A market's wares and a tavern's menu go in the codex once you've been there."""
    if event.entity != game.player:
        return
    entries = codex(game).meals
    for _, (shop, position) in game.world.query(Shop, Position):
        if (position.location, position.room) != (event.location, event.room):
            continue
        for material in shop.materials:
            note_material(game, material)
        for recipe in shop.meals:
            if recipe.meal.meal_id not in entries:
                entries[recipe.meal.meal_id] = recipe
            for need in recipe.ingredients:
                note_material(game, need.material)


# --- views -------------------------------------------------------------------------


@dataclass(frozen=True)
class MaterialEntryView:
    material: MaterialView  # id, name, description, how many you have, what markets pay
    region: str  # the group it's listed under: the first region it turns up in
    gathered: str | None  # "Peat Bog, Reed Maze (The Sallow Fens)"; None: not gathered
    dropped_by: str | None  # "Bog Toad; foes you've yet to learn about"
    sold_at: str | None  # "Markets in The Wrack Coast"
    uses: tuple[str, ...]  # "Crafting: Stone Maul ×2", "Cooking: …", "Upgrading: …"


@dataclass(frozen=True)
class RecipesView:
    known: tuple[RecipeView, ...]  # in the order learned
    to_find: str | None  # how many more are out there, and how they turn up


@dataclass(frozen=True)
class CodexView:
    materials: tuple[MaterialEntryView, ...]  # crafting materials, by region then name
    ingredients: tuple[MaterialEntryView, ...]  # for cooking, likewise
    recipes: RecipesView
    meals: tuple[MenuView, ...]  # every meal you've seen on a menu, by name

    @staticmethod
    def by_region(
        entries: tuple[MaterialEntryView, ...],
    ) -> list[tuple[str, tuple[MaterialEntryView, ...]]]:
        """(region, entries) in the order the entries come (deepest region last)."""
        groups: dict[str, list[MaterialEntryView]] = {}
        for entry in entries:
            groups.setdefault(entry.region, []).append(entry)
        return [(region, tuple(group)) for region, group in groups.items()]


def keys(game: Game) -> set[tuple[str, str]]:
    """Every codex entry, cheaply (for unread dots): new entries, never more detail."""
    book = codex(game)
    return (
        {("foe", f) for f in book.foes}
        | {("material", m) for m in book.materials}
        | {("meal", m) for m in book.meals}
        | {("recipe", r) for r in crafting.known(game)}
    )


def view(game: Game) -> CodexView:
    book = codex(game)
    sources = _Sources(game)
    known_regions = known_region_ids(game)
    tiers = {r.id: (r.tier, i) for i, r in enumerate(game.overworld.regions.values())}
    entries = []
    for material_id, entry in book.materials.items():
        material = entry.material
        homes = sources.homes(material_id)
        home = min(homes, key=lambda r: tiers.get(r, (99, 99)), default=None)
        if home in known_regions and home in game.overworld.regions:
            region, order = game.overworld.regions[home].name, tiers[home]
        else:  # nowhere left, or only in regions you haven't found
            region, order = ELSEWHERE, (100, 0)
        view = MaterialEntryView(
            material=game._material_view(material, crafting.count(game, material_id)),
            region=region,
            gathered=where(game, sources.gathered.get(material_id, [])),
            dropped_by=_dropped_by(game, entry, sources.droppers.get(material_id, [])),
            sold_at=_markets(game, sources.markets.get(material_id, [])),
            uses=_uses(game, material_id),
        )
        entries.append((order, material.name, view))
    entries.sort(key=lambda t: (t[0], t[1]))
    return CodexView(
        materials=tuple(v for _, _, v in entries if not v.material.ingredient),
        ingredients=tuple(v for _, _, v in entries if v.material.ingredient),
        recipes=RecipesView(
            known=tuple(game._recipe_view(r) for r in crafting.known(game).values()),
            to_find=_to_find(game),
        ),
        meals=tuple(
            game._menu_entry(r) for r in sorted(book.meals.values(), key=lambda r: r.meal.name)
        ),
    )


class _Sources:
    """Where every material turns up in the world, worked out once per view."""

    def __init__(self, game: Game) -> None:
        self.gathered: dict[str, list[str]] = {}  # material -> location ids
        self.droppers: dict[str, list[tuple[str, str]]] = {}  # -> (enemy id, location id)
        self.markets: dict[str, list[str]] = {}  # material -> location ids
        world = game.world
        for _, (grower,) in world.query(Grower):
            for grow in grower.materials:
                _add(self.gathered, grow.material.material_id, grower.location)
        for _, (stack, position) in world.query(MaterialStack, Position):
            _add(self.gathered, stack.material.material_id, position.location)
        for _, (enemy, position) in world.query(Enemy, Position):
            for stack in enemy.materials:
                _add(self.droppers, stack.material.material_id, (enemy.enemy_id, position.location))
        for _, (spawner,) in world.query(Spawner):
            for enemy in spawner.queue:
                for stack in enemy.materials:
                    _add(
                        self.droppers,
                        stack.material.material_id,
                        (enemy.enemy_id, spawner.location),
                    )
            for template in spawner.templates:
                for drop in template.materials:
                    _add(
                        self.droppers,
                        drop.material.material_id,
                        (template.enemy_id, spawner.location),
                    )
        for _, (shop, position) in world.query(Shop, Position):
            for material in shop.materials:
                _add(self.markets, material.material_id, position.location)
        self.region_of = {i: loc.region for i, loc in game.overworld.locations.items()}

    def homes(self, material_id: str) -> set[str]:
        """The regions it turns up in, any way."""
        places = [
            *self.gathered.get(material_id, []),
            *(loc for _, loc in self.droppers.get(material_id, [])),
            *self.markets.get(material_id, []),
        ]
        return {self.region_of[p] for p in places if p in self.region_of}


def _add(index: dict, key: str, value) -> None:
    values = index.setdefault(key, [])
    if value not in values:
        values.append(value)


def known_region_ids(game: Game) -> set[str]:
    explorer = game._explorer()
    return {
        game.overworld.location(i).region
        for i in explorer.locations_discovered | explorer.locations_visited
    }


def where(game: Game, location_ids: Iterable[str]) -> str | None:
    """The kinds of place these are, grouped by region ("Peat Bog, Mere (The
    Sallow Fens)"); regions you haven't found yet are only hinted at."""
    by_region: dict[str, list[str]] = {}
    for location_id in location_ids:
        location = game.overworld.location(location_id)
        kinds = by_region.setdefault(location.region, [])
        if location.kind not in kinds:
            kinds.append(location.kind)
    if not by_region:
        return None
    known = known_region_ids(game)
    parts, unknown = [], False
    for region_id, kinds in by_region.items():
        region = game.overworld.regions.get(region_id)
        if region is None:
            parts.append(", ".join(kinds))
        elif region_id in known:
            parts.append(f"{', '.join(kinds)} ({region.name})")
        else:
            unknown = True
    if unknown:
        parts.append(UNFOUND_PLACES)
    return "; ".join(parts)


def _markets(game: Game, location_ids: list[str]) -> str | None:
    if not location_ids:
        return None
    known = known_region_ids(game)
    names, unknown = [], False
    for location_id in location_ids:
        region_id = game.overworld.location(location_id).region
        region = game.overworld.regions.get(region_id)
        if region is not None and region_id not in known:
            unknown = True
            continue
        name = f"Markets in {region.name}" if region else "Markets"
        if name not in names:
            names.append(name)
    if unknown:
        names.append(UNFOUND_MARKETS)
    return "; ".join(names)


def _dropped_by(game: Game, entry: MaterialEntry, droppers: list[tuple[str, str]]) -> str | None:
    """Foes named once you've had it from them or know their drops."""
    book = codex(game)
    named, unknown = [], False
    for enemy_id in dict.fromkeys(e for e, _ in droppers):
        foe = book.foes.get(enemy_id)
        if foe is not None and (
            enemy_id in entry.looted_from or book.kills.get(enemy_id, 0) >= DROPS_AT
        ):
            named.append(foe.name)
        else:
            unknown = True
    for enemy_id in entry.looted_from:  # since gone from the world
        foe = book.foes.get(enemy_id)
        if foe is not None and foe.name not in named:
            named.append(foe.name)
    if not named and not unknown:
        return None
    text = ", ".join(sorted(named))
    if unknown:
        text = f"{text}; {UNKNOWN_FOES}" if text else UNKNOWN_FOES
    return text


def _uses(game: Game, material_id: str) -> tuple[str, ...]:
    def needs(stacks: list[MaterialStack]) -> int:
        return sum(s.count for s in stacks if s.material.material_id == material_id)

    crafts = [f"{r.name} ×{n}" for r in crafting.known(game).values() if (n := needs(r.materials))]
    cooks = [
        f"{r.meal.name} ×{n}"
        for r in sorted(codex(game).meals.values(), key=lambda r: r.meal.name)
        if (n := needs(r.ingredients))
    ]
    smithy = next((s for _, (s,) in game.world.query(Shop) if s.crafts), None)
    upgrades = []
    if smithy is not None:
        for _, (item, carried) in game.world.query(Item, Carried):
            if carried.by != game.player:
                continue
            per_level = smithy.upgrades.get(item.gear_id, [])
            if item.upgrade < item.max_upgrade and needs(per_level) and (item.name not in upgrades):
                upgrades.append(item.name)
    uses = []
    if crafts:
        uses.append("Crafting: " + ", ".join(crafts))
    if cooks:
        uses.append("Cooking: " + ", ".join(cooks))
    if upgrades:
        uses.append("Upgrading your " + _and(sorted(upgrades)))
    return tuple(uses)


def _to_find(game: Game) -> str | None:
    """How many recipes you don't know yet are out there, and how they turn up."""
    known = crafting.known(game)
    pages = {
        page.recipe.recipe_id
        for _, (page,) in game.world.query(RecipePage)
        if page.recipe.recipe_id not in known
    }
    rewards = {
        quest.recipe.recipe_id
        for _, (quest,) in game.world.query(Quest)
        if quest.recipe is not None
        and quest.state != "done"
        and quest.recipe.recipe_id not in known
    } - pages
    total = len(pages) + len(rewards)
    if not total:
        return None
    how = []
    if pages:
        how.append(f"{len(pages)} written down somewhere in the wild")
    if rewards:
        n = len(rewards)
        how.append("1 as a quest reward" if n == 1 else f"{n} as quest rewards")
    more = "1 more recipe" if total == 1 else f"{total} more recipes"
    return f"{more} to find: {_and(how)}."


def _and(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]

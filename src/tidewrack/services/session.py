"""A game bound to a save slot, autosaving after every action (CLAUDE.md §6).

Mobile apps get killed without warning, so there's no "save on exit": every
command that produced events is written straight away.
"""

from __future__ import annotations

import copy
import re
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from tidewrack.core.combat.rules import STANDARD, Rules
from tidewrack.core.data.loader import Content
from tidewrack.core.data.save import EconomyState, GameState, RulesState, encode_component
from tidewrack.core.economy.value_model import STANDARD_ECONOMY, EconomyRules
from tidewrack.core.engine.components import (
    Bounty,
    Clue,
    Enemy,
    Grower,
    MaterialStack,
    Quest,
    QuestItem,
    Recipe,
    RecipePage,
    Shop,
    Spawner,
    Warden,
)
from tidewrack.core.engine.game import Command, Game, TurnResult
from tidewrack.core.gear.item import Item
from tidewrack.core.gear.stats import DEFAULT_PLAYER_BASE
from tidewrack.core.procgen.enemy_gen import generate_enemies, generate_wardens
from tidewrack.core.procgen.gear_gen import generate_finds, generate_kit
from tidewrack.core.procgen.material_gen import (
    generate_gathering,
    generate_growers,
    generate_recipes,
    known_recipes,
)
from tidewrack.core.procgen.quest_gen import generate_quests
from tidewrack.core.procgen.shop_gen import generate_shops
from tidewrack.core.procgen.world_gen import generate_world
from tidewrack.core.versions import GENERATOR_VERSION, SCHEMA_VERSION
from tidewrack.core.world.overworld import Overworld
from tidewrack.services.storage import SaveError, SaveStore, SlotMeta, SlotSummary
from tidewrack.services.storage.migrations import migrate
from tidewrack.services.storage.store import SLOT_FORMAT

Clock = Callable[[], str]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class GameSession:
    def __init__(
        self,
        store: SaveStore,
        meta: SlotMeta,
        game: Game,
        content_version: str,
        clock: Clock = utc_now,
        from_backup: bool = False,
    ) -> None:
        self.store = store
        self.meta = meta
        self.game = game
        self.content_version = content_version
        self.clock = clock
        self.from_backup = from_backup
        self._encoder = StateEncoder()
        # Called after every command (e.g. the UI's unread dots); not saved.
        self.listeners: list[Callable[[TurnResult], None]] = []

    # --- creating and opening ----------------------------------------------------

    @classmethod
    def generate(
        cls,
        store: SaveStore,
        content: Content,
        recipe_id: str,
        name: str,
        seed: int,
        clock: Clock = utc_now,
    ) -> GameSession:
        """Generate a fresh world from a recipe (layout, kit, finds, enemies,
        quests, shops, materials and recipes) in a new slot."""
        recipe = content.world(recipe_id)
        world = generate_world(seed, recipe, content.roomsets, content.regions)
        enemies, spawners = generate_enemies(seed, world, content)
        wardens = generate_wardens(seed, world, content)
        plan = generate_quests(seed, world, content, recipe, enemies, spawners)
        recipes = generate_recipes(seed, world, content, recipe, plan.quests)
        quests = [replace(q, recipe=recipes.rewards.get(q.quest_id)) for q in plan.quests]
        return cls.new(
            store,
            content,
            world,
            name,
            seed,
            clock,
            player_base=recipe.player,
            kit=generate_kit(recipe, content),
            finds=generate_finds(seed, world, content),
            enemies=enemies,
            spawners=spawners,
            quests=quests,
            bounties=plan.bounties,
            quest_things=plan.placed,
            gold=recipe.gold,
            shops=generate_shops(seed, world, content),
            gathering=generate_gathering(seed, world, content),
            recipes=known_recipes(content),
            recipe_pages=recipes.pages,
            growers=generate_growers(world, content),
            wardens=wardens,
        )

    @classmethod
    def new(
        cls,
        store: SaveStore,
        content: Content,
        world: Overworld,
        name: str,
        seed: int,
        clock: Clock = utc_now,
        *,
        player_base: Mapping[str, int] = DEFAULT_PLAYER_BASE,
        kit: Iterable[Item] = (),
        finds: Iterable[tuple[str, str, Item]] = (),
        enemies: Iterable[tuple[str, str, Enemy]] = (),
        spawners: Iterable[Spawner] = (),
        rules: Rules = STANDARD,
        quests: Iterable[Quest] = (),
        bounties: Iterable[tuple[str, str, Enemy, Bounty]] = (),
        quest_things: Iterable[tuple[str, str, QuestItem | Clue]] = (),
        gold: int = 0,
        shops: Iterable[tuple[str, str, Shop, Iterable[Item]]] = (),
        economy: EconomyRules = STANDARD_ECONOMY,
        gathering: Iterable[tuple[str, str, MaterialStack]] = (),
        recipes: Iterable[Recipe] = (),
        recipe_pages: Iterable[tuple[str, str, RecipePage]] = (),
        growers: Iterable[Grower] = (),
        wardens: Iterable[tuple[str, str, Enemy, Warden]] = (),
    ) -> GameSession:
        """Start a world in a new slot (saved immediately)."""
        game = Game(
            seed,
            world,
            player_base,
            kit,
            finds,
            enemies,
            spawners,
            rules,
            quests,
            bounties,
            quest_things,
            gold,
            shops,
            economy,
            gathering,
            recipes,
            recipe_pages,
            growers,
            wardens,
        )
        now = clock()
        meta = SlotMeta(
            slot_id=uuid.uuid4().hex,
            name=name,
            created_at=now,
            updated_at=now,
            revision=0,
            summary=_summary(game),
        )
        session = cls(store, meta, game, content.content_hash, clock)
        session.save()
        return session

    @classmethod
    def open(
        cls, store: SaveStore, slot_id: str, content: Content, clock: Clock = utc_now
    ) -> GameSession:
        """Load a slot. Raises SaveError (or NewerSaveError) with a readable message."""
        loaded = store.load(slot_id)
        try:
            envelope = migrate(loaded.envelope)
            meta = SlotMeta.model_validate(envelope["meta"])
            game = Game.from_state(GameState.model_validate(envelope["game"]))
        except (KeyError, ValueError, ValidationError, LookupError) as e:
            raise SaveError(f"save {slot_id} is damaged: {e}") from e
        return cls(store, meta, game, content.content_hash, clock, loaded.from_backup)

    # --- playing -----------------------------------------------------------------

    def perform(self, command: Command) -> TurnResult:
        result = self.game.perform(command)
        if result.events:
            self.save()
        for listener in self.listeners:
            listener(result)
        return result

    def save(self) -> None:
        self.meta = self.meta.model_copy(
            update={
                "updated_at": self.clock(),
                "revision": self.meta.revision + 1,
                "summary": _summary(self.game),
            }
        )
        self._write()

    def _write(self) -> None:
        game, changed, done = self._encoder.encode(self.game)
        envelope = {
            "format": SLOT_FORMAT,
            "schema_version": SCHEMA_VERSION,
            "generator_version": GENERATOR_VERSION,
            "content_version": self.content_version,
            "meta": self.meta.model_dump(mode="json"),
            "game": game,
        }
        self.store.save(self.meta.slot_id, envelope, changed)
        done()  # only once it's written, so a failed save is retried in full

    def rename(self, name: str) -> None:
        """Give the world a new name (stripped, at most MAX_NAME characters).

        A new revision for sync, but not "played": updated_at stays, so the
        world keeps its place in the list. A blank name is refused.
        """
        name = " ".join(name.split())[:MAX_NAME]
        if not name:
            raise ValueError("A world needs a name.")
        self.meta = self.meta.model_copy(update={"name": name, "revision": self.meta.revision + 1})
        self._write()


class StateEncoder:
    """A game's saved form (what `Game.to_state()` dumps to), worked out fast.

    Autosave runs after every action, but most entities don't change from one
    action to the next, so each entity's encoding is kept with a copy of its
    components and only redone when they no longer compare equal. The world map
    never changes once made. `encode` also says which entities changed, so the
    store can skip rewriting places where nothing did.
    """

    def __init__(self) -> None:
        self._world: tuple[object, dict[str, Any]] | None = None
        self._entities: dict[int, tuple[tuple[Any, ...], dict[str, Any]]] = {}

    def encode(self, game: Game) -> tuple[dict[str, Any], set[int] | None, Callable[[], None]]:
        """(the state as JSON values, ids changed since the last committed
        encoding or None if there's none, a function that commits this one)."""
        if self._world is None or self._world[0] is not game._snapshot:
            world = (game._snapshot, game._snapshot.model_dump(mode="json"))
        else:
            world = self._world
        next_id, snapshot = game.world.snapshot()
        cache = self._entities
        fresh = self._world is None or self._world[0] is not game._snapshot
        updated: dict[int, tuple[tuple[Any, ...], dict[str, Any]]] = {}
        changed: set[int] = set()
        entities = []
        for entity, components in snapshot.items():
            known = cache.get(entity)
            if known is None or known[0] != components:
                encoded = {
                    "id": entity,
                    "components": dict(encode_component(c) for c in components),
                }
                known = (copy.deepcopy(components), encoded)
                changed.add(entity)
            updated[entity] = known
            entities.append(known[1])
        changed.update(cache.keys() - updated.keys())  # destroyed

        def commit() -> None:
            self._world = world
            self._entities = updated

        def rng(stream: Any) -> dict[str, Any]:
            return stream.get_state()

        state = {
            "seed": game.seed,
            "turn": game.turn,
            "log": list(game.log),
            "world": world[1],
            "rng": rng(game.rng),
            "ambient_rng": rng(game.ambient_rng),
            "combat_rng": rng(game.combat_rng),
            "encounter_rng": rng(game.encounter_rng),
            "respawn_rng": rng(game.respawn_rng),
            "shop_rng": rng(game.shop_rng),
            "gather_rng": rng(game.gather_rng),
            "rules": RulesState(**game.rules.__dict__).model_dump(mode="json"),
            "economy": EconomyState(**game.economy.__dict__).model_dump(mode="json"),
            "next_entity_id": next_id,
            "entities": entities,
        }
        return state, None if fresh else changed, commit


def _summary(game: Game) -> SlotSummary:
    """What the world list shows (the same numbers as `game.view()`, without
    working out the rest of the view on every autosave)."""
    location, room = game.here()
    return SlotSummary(
        location=location.name,
        room=room.name,
        turn=game.turn,
        locations_visited=len(game._explorer().locations_visited),
        total_locations=len(game.overworld.locations),
    )


MAX_NAME = 40  # characters in a world's name


def next_world_name(existing: list[str]) -> str:
    """ "World N" with N one above the highest existing number."""
    numbers = [int(m.group(1)) for n in existing if (m := re.fullmatch(r"World (\d+)", n))]
    return f"World {max(numbers, default=0) + 1}"

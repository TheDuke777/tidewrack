"""Seeded quests: what each town's notice board posts, and quests found in the wild.

Everything is decided at world creation (CLAUDE.md §9), on the seed's "quests"
substream (one sub-substream per board, one for found quests), so worlds, finds
and enemies never shift. Quests are snapshots with their reward rolled now; the
things they send you after (a bounty's enemy, a lost item, a found quest's clue)
are placed now too, in rooms that aren't gates and hold no other enemy.

Types (content quests/<type>.json): bounty (a tougher, named enemy), cull
(defeat N of a kind, counted after accepting), explore (visit every room of a
location) and recover (find an item and bring it back). Every quest is turned
in at any town's notice board.

Any change to this module's output for a given seed must bump
core.versions.GENERATOR_VERSION (tests/core/test_procgen.py pins golden hashes).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, replace
from math import ceil
from typing import NamedTuple

from tidewrack.core.combat.fight import TOWN
from tidewrack.core.data.loader import Content
from tidewrack.core.data.schemas import (
    QUEST_TYPES,
    QuestTemplateSchema,
    RoomsetSchema,
    WorldRecipeSchema,
)
from tidewrack.core.engine.components import Bounty, Clue, Enemy, Quest, QuestItem, Spawner
from tidewrack.core.gear.item import Item
from tidewrack.core.procgen.enemy_gen import PlacedEnemy, make_enemy
from tidewrack.core.procgen.gear_gen import make_item
from tidewrack.core.rng import Rng
from tidewrack.core.world.location import Location
from tidewrack.core.world.overworld import Overworld


class PlacedBounty(NamedTuple):
    location: str
    room: str
    enemy: Enemy
    bounty: Bounty


class Placed(NamedTuple):
    """A quest item or clue in a room; Game takes these as (location, room, thing)."""

    location: str
    room: str
    thing: QuestItem | Clue


class QuestPlan(NamedTuple):
    quests: list[Quest]
    bounties: list[PlacedBounty]
    placed: list[Placed]  # quest items and clues


class _Builder:
    """Shared state while one world's quests are made: what's where, what's used."""

    def __init__(
        self,
        world: Overworld,
        content: Content,
        recipe: WorldRecipeSchema,
        enemies: Iterable[PlacedEnemy],
        spawners: Iterable[Spawner],
    ) -> None:
        self.world = world
        self.content = content
        self.recipe = recipe
        self.templates = {t.type: t for _, t in sorted(content.quests.items())}
        roomsets = {r.name: r for _, r in sorted(content.roomsets.items())}
        self.roomset: dict[str, RoomsetSchema] = {
            loc.id: roomsets[loc.kind] for loc in world.locations.values() if loc.kind in roomsets
        }
        self.towns = [loc for loc in world.locations.values() if loc.kind == TOWN]
        # Generated places outside towns: where quests send you.
        self.wild = [
            loc for loc in world.locations.values() if loc.kind != TOWN and loc.id in self.roomset
        ]
        self.hunting = [loc for loc in self.wild if self.roomset[loc.id].enemies.pool]
        enemies = list(enemies)
        self.taken = {(p.location, p.room) for p in enemies}
        self.supply = Counter(p.enemy.enemy_id for p in enemies)
        for spawner in spawners:
            self.supply.update(e.enemy_id for e in spawner.queue)
        self.charted: set[str] = set()  # explore targets, one quest each
        self.culled: set[str] = set()  # cull targets, one quest each
        self.items_used: set[str] = set()
        self.words: dict[str, dict] = {}  # quest id -> its placeholder values (for clues)
        self.plan = QuestPlan([], [], [])

    def free_room(self, rng: Rng, location: Location) -> str | None:
        rooms = [
            r
            for r in location.rooms
            if r not in location.gates and (location.id, r) not in self.taken
        ]
        if not rooms:
            return None
        room = rng.choice(rooms)
        self.taken.add((location.id, room))
        return room

    def reward(self, rng: Rng, location: Location | None) -> Item:
        """A cut above a find: from the target's finds (towns' if none), best roll."""
        roomset = self.roomset.get(location.id) if location else None
        pools = [roomset] if roomset and roomset.finds.gear else []
        pools += [r for r in (self.roomset[t.id] for t in self.towns) if r.finds.gear]
        pools += [r for _, r in sorted(self.content.roomsets.items()) if r.finds.gear]
        gear_pool = pools[0].finds.gear
        choices = sorted(gear_pool)
        gear = self.content.gear[rng.weighted_choice(choices, [gear_pool[g] for g in choices])]
        affixes = []
        if rng.chance(self.recipe.quests.reward_affix_chance):
            eligible = [a for _, a in sorted(self.content.affixes.items()) if gear.slot in a.slots]
            if eligible:
                affixes.append(rng.weighted_choice(eligible, [a.weight for a in eligible]))
        roll = {s: high for s, (_, high) in gear.rolls.items()}
        return make_item(gear, self.content.gearsets, roll, affixes)

    # --- one quest of each type --------------------------------------------------------

    def make(self, rng: Rng, kind: str, quest_id: str) -> Quest | None:
        template = self.templates.get(kind)
        if template is None:
            return None
        return getattr(self, f"_{kind}")(rng, template, quest_id)

    def _bounty(self, rng: Rng, t: QuestTemplateSchema, quest_id: str) -> Quest | None:
        if not self.hunting:
            return None
        location = rng.choice(self.hunting)
        room = self.free_room(rng, location)
        if room is None:
            return None
        pool = self.roomset[location.id].enemies.pool
        choices = sorted(pool)
        schema = self.content.enemies[rng.weighted_choice(choices, [pool[e] for e in choices])]
        ordinary = make_enemy(rng, schema, self.content)
        name = f"{rng.choice(t.epithets[schema.category])} {schema.name}"
        enemy = replace(
            ordinary,
            name=name,
            stats={s: ceil(v * t.strength) for s, v in ordinary.stats.items()},
            gold=ceil(ordinary.gold * t.strength),
        )
        bounty = Bounty(quest_id, schema.name, dict(ordinary.stats))
        self.plan.bounties.append(PlacedBounty(location.id, room, enemy, bounty))
        words = {"target": name, "location": location.name}
        return self._quest(rng, t, quest_id, words, location, target=name)

    def _cull(self, rng: Rng, t: QuestTemplateSchema, quest_id: str) -> Quest | None:
        low, high = t.counts
        options = [
            (loc, e)
            for loc in self.hunting
            for e in sorted(self.roomset[loc.id].enemies.pool)
            if e not in self.culled and self.supply[e] >= 2 * low
        ]
        if not options:
            return None
        location, enemy_id = rng.choice(options)
        self.culled.add(enemy_id)
        count = min(rng.randint(low, high), self.supply[enemy_id] // 2)
        plural = self.content.enemies[enemy_id].plural_name
        words = {"count": count, "enemies": plural, "location": location.name}
        return self._quest(
            rng, t, quest_id, words, location, target=plural, enemy_id=enemy_id, needed=count
        )

    def _explore(self, rng: Rng, t: QuestTemplateSchema, quest_id: str) -> Quest | None:
        options = [
            loc for loc in self.wild if loc.id not in self.charted and loc.id != self.world.start
        ]
        if not options:
            return None
        location = rng.choice(options)
        self.charted.add(location.id)
        words = {"location": location.name}
        return self._quest(rng, t, quest_id, words, location, needed=len(location.rooms))

    def _recover(self, rng: Rng, t: QuestTemplateSchema, quest_id: str) -> Quest | None:
        items = [i for i in t.items if i.name not in self.items_used] or list(t.items)
        if not self.wild:
            return None
        location = rng.choice(self.wild)
        room = self.free_room(rng, location)
        if room is None:
            return None
        item = rng.choice(items)
        self.items_used.add(item.name)
        self.plan.placed.append(
            Placed(location.id, room, QuestItem(quest_id, item.name, item.description))
        )
        words = {"item": item.name, "location": location.name}
        return self._quest(rng, t, quest_id, words, location, target=item.name)

    def _quest(
        self,
        rng: Rng,
        t: QuestTemplateSchema,
        quest_id: str,
        words: dict,
        location: Location,
        **fields,
    ) -> Quest:
        self.words[quest_id] = words
        return Quest(
            quest_id=quest_id,
            kind=t.type,
            title=rng.choice(t.titles).format(**words),
            summary=rng.choice(t.summaries).format(**words),
            reward=self.reward(rng, location),
            location=location.id,
            gold=rng.randint(*t.gold),
            **fields,
        )


def generate_quests(
    seed: int,
    world: Overworld,
    content: Content,
    recipe: WorldRecipeSchema,
    enemies: Iterable[PlacedEnemy] = (),
    spawners: Iterable[Spawner] = (),
) -> QuestPlan:
    """Each town's board, then the found quests, each type in a shuffled turn."""
    rng = Rng(seed).derive("quests")
    builder = _Builder(world, content, recipe, enemies, spawners)
    for town in builder.towns:
        board_rng = rng.derive(f"board.{town.id}")
        for quest in _batch(board_rng, builder, recipe.quests.per_board, town.id):
            builder.plan.quests.append(replace(quest, board=town.id))
    found_rng = rng.derive("found")
    for quest in _batch(found_rng, builder, recipe.quests.found, "found"):
        # Every quest needs a wild place, so there is one. A clue may share a room.
        location = found_rng.choice(builder.wild)
        room = found_rng.choice([r for r in location.rooms if r not in location.gates])
        template = builder.templates[quest.kind]
        builder.plan.placed.append(
            Placed(
                location.id,
                room,
                Clue(
                    quest.quest_id,
                    found_rng.choice(template.clues).format(**builder.words[quest.quest_id]),
                ),
            )
        )
        builder.plan.quests.append(replace(quest, source="found", state="hidden"))
    return builder.plan


def _batch(rng: Rng, builder: _Builder, count: int, prefix: str) -> list[Quest]:
    """Up to `count` quests, cycling through the types in a shuffled order so a
    board gets a mix; a type that can't be made in this world is skipped."""
    kinds: list[str] = list(QUEST_TYPES)
    rng.shuffle(kinds)
    quests: list[Quest] = []
    for attempt in range(count * len(kinds)):
        if len(quests) == count:
            break
        kind = kinds[attempt % len(kinds)]
        quest = builder.make(rng, kind, f"quest.{prefix}.{len(quests)}")
        if quest is not None:
            quests.append(quest)
    return quests


def quests_hash(plan: QuestPlan) -> str:
    """Stable fingerprint of a world's quests, for golden-seed tests (§9)."""
    blob = json.dumps(
        {
            "quests": [asdict(q) for q in plan.quests],
            "bounties": [
                {
                    "location": b.location,
                    "room": b.room,
                    "enemy": asdict(b.enemy),
                    "bounty": asdict(b.bounty),
                }
                for b in plan.bounties
            ],
            "placed": [
                {
                    "location": p.location,
                    "room": p.room,
                    "kind": type(p.thing).__name__,
                    "thing": asdict(p.thing),
                }
                for p in plan.placed
            ],
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()

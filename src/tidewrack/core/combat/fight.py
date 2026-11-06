"""Fights, round by round, plus recovery (CLAUDE.md §14 step 6).

Functions over a Game, like its per-turn systems; Game.perform calls them for
Attack, Defend and Flee, and its event bus calls `encounter` and `note_town`.
All numbers come from the world's Rules; all randomness from the saved combat
and encounter streams, so a reloaded game fights exactly as it would have.

A round: the player acts first (attack, brace or run), then the enemy strikes
back if it's still standing and the player is still there. Winning drops the
enemy's pre-rolled loot. Losing wakes you at the edge of the last town you
visited; the enemy stays, at full strength.
"""

from __future__ import annotations

from math import ceil
from typing import TYPE_CHECKING

from tidewrack.core.combat.rules import damage, regen, scaled
from tidewrack.core.economy import cooking, crafting, shops
from tidewrack.core.engine.components import (
    Bounty,
    Codex,
    Enemy,
    Explorer,
    Fighting,
    FoeEntry,
    Health,
    Position,
    Respawn,
    Spawner,
    Warden,
)
from tidewrack.core.engine.events import (
    Attacked,
    CombatStarted,
    EnemyKilled,
    Fled,
    FleeFailed,
    LocationEntered,
    PlayerDefeated,
    RegionOpened,
    Respawned,
    RoomEntered,
    WayBarred,
)

if TYPE_CHECKING:
    from tidewrack.core.engine.game import Game


# --- starting fights ---------------------------------------------------------------


def note_town(game: Game, event: LocationEntered) -> None:
    """Remember the last town visited: that's where a defeat wakes you."""
    if event.entity == game.player and game.overworld.location(event.location).town:
        game.world.get(game.player, Respawn).location = event.location


def encounter(game: Game, event: RoomEntered) -> None:
    """Entering a room with an enemy in it, or meeting a wanderer, starts a fight."""
    if event.entity != game.player or game.world.has(game.player, Fighting):
        return
    for entity, (enemy, position) in game.world.query(Enemy, Position):
        here = (position.location, position.room) == (event.location, event.room)
        if here and not game.world.has(entity, Warden):  # wardens wait to be challenged
            _start(game, entity, enemy, event.from_room or event.room, wandering=False)
            return
    location = game.overworld.location(event.location)
    if event.fleeing or event.room in location.gates or location.town:
        return
    spawner = next(
        (s for _, (s,) in game.world.query(Spawner) if s.location == event.location), None
    )
    if spawner and spawner.queue and game.encounter_rng.chance(spawner.chance):
        enemy = spawner.queue.pop(0)
        entity = game.world.create(enemy, Position(event.location, event.room))
        _start(game, entity, enemy, event.from_room or event.room, wandering=True)


def warden_on(game: Game, location_id: str, room_id: str, road: str) -> int | None:
    """The warden barring `road` from this room, if one still stands there."""
    for entity, (warden, position) in game.world.query(Warden, Position):
        if warden.road == road and (position.location, position.room) == (location_id, room_id):
            return entity
    return None


def challenge(game: Game, entity: int) -> None:
    """Take a guarded road: its warden steps in. Fleeing keeps you where you are."""
    enemy, warden = game.world.get(entity, Enemy), game.world.get(entity, Warden)
    region = game.overworld.regions[warden.region]
    game.bus.emit(WayBarred(entity, enemy.name, warden.crossing, region.name))
    _start(game, entity, enemy, game.world.get(entity, Position).room, wandering=False)


def _start(game: Game, entity: int, enemy: Enemy, retreat_room: str, wandering: bool) -> None:
    game.world.add(
        game.player,
        Fighting(
            enemy=entity,
            retreat_room=retreat_room,
            enemy_stats=scaled(enemy.stats, game.rules),
        ),
    )
    codex = game.world.get(game.player, Codex)
    if enemy.enemy_id not in codex.foes:
        # A bounty is a named, tougher one: the codex records its ordinary kind.
        bounty = game.world.try_get(entity, Bounty)
        codex.foes[enemy.enemy_id] = FoeEntry(
            enemy_id=enemy.enemy_id,
            name=bounty.kind_name if bounty else enemy.name,
            category=enemy.category,
            description=enemy.description,
            stats=dict(bounty.kind_stats if bounty else enemy.stats),
            drops=list(enemy.drops),
        )
    game.bus.emit(CombatStarted(entity, enemy.enemy_id, enemy.name, wandering))


# --- rounds ------------------------------------------------------------------------


def attack(game: Game) -> None:
    if not _player_strikes(game):
        _enemy_strikes(game, defending=False)


def defend(game: Game) -> None:
    _enemy_strikes(game, defending=True)


def flee(game: Game) -> None:
    fighting = game.world.get(game.player, Fighting)
    enemy = game.world.get(fighting.enemy, Enemy)
    if not game.combat_rng.chance(game.rules.flee_chance):
        game.bus.emit(FleeFailed(fighting.enemy, enemy.name))
        _enemy_strikes(game, defending=False)
        return
    game.world.remove(game.player, Fighting)
    position = game.world.get(game.player, Position)
    origin, position.room = position.room, fighting.retreat_room
    game.bus.emit(Fled(fighting.enemy, enemy.name))
    game.bus.emit(
        RoomEntered(
            game.player,
            position.location,
            position.room,
            origin,
            first_visit=False,
            fleeing=True,
        )
    )


def _player_strikes(game: Game) -> bool:
    """The player's blow; True if it wins the fight."""
    fighting = game.world.get(game.player, Fighting)
    enemy = game.world.get(fighting.enemy, Enemy)
    you = game.sheet().total
    hit = damage(game.combat_rng, you["atk"], fighting.enemy_stats.get("def", 0), False, game.rules)
    fighting.enemy_damage += hit
    game.bus.emit(Attacked(game.player, fighting.enemy, "You", enemy.name, hit, defended=False))
    if fighting.enemy_damage >= fighting.enemy_stats["hp"]:
        _win(game, fighting, enemy)
        return True
    return False


def _enemy_strikes(game: Game, defending: bool) -> None:
    fighting = game.world.get(game.player, Fighting)
    enemy = game.world.get(fighting.enemy, Enemy)
    you = game.sheet().total
    hit = damage(
        game.combat_rng, fighting.enemy_stats.get("atk", 0), you["def"], defending, game.rules
    )
    game.world.get(game.player, Health).damage += hit
    game.bus.emit(Attacked(fighting.enemy, game.player, enemy.name, "you", hit, defending))
    if game.hp() <= 0:
        _lose(game, fighting, enemy)


def _win(game: Game, fighting: Fighting, enemy: Enemy) -> None:
    position = game.world.get(fighting.enemy, Position)
    for item in enemy.loot:
        game.world.create(item, Position(position.location, position.room))
    codex = game.world.get(game.player, Codex)
    codex.kills[enemy.enemy_id] = codex.kills.get(enemy.enemy_id, 0) + 1
    bounty = game.world.try_get(fighting.enemy, Bounty)
    warden = game.world.try_get(fighting.enemy, Warden)
    game.world.remove(game.player, Fighting)
    game.world.destroy(fighting.enemy)
    game.bus.emit(
        EnemyKilled(
            fighting.enemy,
            enemy.enemy_id,
            enemy.name,
            enemy.category,
            tuple(item.display_name for item in enemy.loot),
            bounty.quest_id if bounty else None,
            enemy.gold,
        )
    )
    shops.gain(game, enemy.gold, "loot")
    for stack in enemy.materials:
        crafting.add(game, stack, "loot")
    if warden is not None:
        game.bus.emit(RegionOpened(warden.region, game.overworld.regions[warden.region].name))


def _lose(game: Game, fighting: Fighting, enemy: Enemy) -> None:
    """Wake at the last town's gate with some HP back. The enemy stays put."""
    game.world.remove(game.player, Fighting)
    town = game.overworld.location(game.world.get(game.player, Respawn).location)
    position = game.world.get(game.player, Position)
    position.location, position.room = town.id, town.start
    max_hp = game.max_hp()
    woken = max(1, ceil(max_hp * game.rules.respawn_hp))
    game.world.get(game.player, Health).damage = max_hp - woken
    explorer = game.world.get(game.player, Explorer)
    game.bus.emit(PlayerDefeated(enemy.enemy_id, enemy.name))
    game.bus.emit(Respawned(town.id))
    game.bus.emit(
        LocationEntered(
            game.player, town.id, None, first_visit=town.id not in explorer.locations_visited
        )
    )
    game.bus.emit(
        RoomEntered(
            game.player,
            town.id,
            town.start,
            None,
            first_visit=town.start not in explorer.rooms_visited.get(town.id, set()),
        )
    )


# --- recovery ----------------------------------------------------------------------


def regen_system(game: Game) -> None:
    """Out of a fight, slowly heal by a share of max HP (a night at an inn heals fully)."""
    if game.world.has(game.player, Fighting):
        return
    health = game.world.get(game.player, Health)
    if health.damage and game.turn % game.rules.regen_every == 0:
        healed = regen(game.max_hp(), game.rules) + cooking.extra_regen(game)
        health.damage = max(0, health.damage - healed)

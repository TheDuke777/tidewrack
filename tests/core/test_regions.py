"""Regions and their wardens (CLAUDE.md §14 step 8a)."""

from dataclasses import replace

from tidewrack.core.data.save import GameState
from tidewrack.core.engine.components import Enemy, Explorer, Position, Stats, Warden
from tidewrack.core.engine.events import (
    CombatStarted,
    LocationEntered,
    PlayerDefeated,
    RegionOpened,
    WayBarred,
)
from tidewrack.core.engine.game import Attack, Flee, Game, Travel, Wait
from tidewrack.core.procgen.enemy_gen import generate_wardens
from tidewrack.core.procgen.world_gen import generate_world
from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()
SEED = 7
WORLD = generate_world(SEED, CONTENT.world("world.standard"), CONTENT.roomsets, CONTENT.regions)
WARDENS = generate_wardens(SEED, WORLD, CONTENT)
[(NEAR, FAR)] = WORLD.borders()
STRONG = {"atk": 200, "def": 100, "hp": 500}
WEAK = {"atk": 1, "def": 0, "hp": 1}


def game_at_border(stats=None) -> Game:
    game = Game(SEED, WORLD, wardens=WARDENS)
    if stats:
        game.world.get(game.player, Stats).base = dict(stats)
    position = game.world.get(game.player, Position)
    position.location, position.room = NEAR, WORLD.location(NEAR).start
    return game


def kinds(result) -> list[str]:
    return [type(e).__name__ for e in result.events]


def test_the_warden_waits_at_the_gate_and_only_fights_when_challenged():
    game = game_at_border()
    assert "CombatStarted" not in kinds(game.perform(Wait()))
    road = next(r for r in game.view().roads if r.location == FAR)
    assert road.guard == "Reed Warden"
    assert road.region == WORLD.regions["region.fens"].name
    others = [r for r in game.view().roads if r.location != FAR]
    assert all(r.guard is None and r.region is None for r in others)

    result = game.perform(Travel(FAR))
    assert [type(e) for e in result.events][:2] == [WayBarred, CombatStarted]
    assert game.world.get(game.player, Position).location == NEAR  # you didn't get past
    fens = WORLD.regions["region.fens"].name
    assert game.log[-1] == f"The Reed Warden bars the causeway into {fens}!"


def test_beating_the_warden_opens_the_region_for_good():
    game = game_at_border(STRONG)
    game.perform(Travel(FAR))
    result = game.perform(Attack())
    opened = [e for e in result.events if isinstance(e, RegionOpened)]
    assert opened == [RegionOpened("region.fens", WORLD.regions["region.fens"].name)]
    assert game.log[-1] == f"The way into {opened[0].name} lies open."
    assert not list(game.world.query(Warden))
    assert all(r.guard is None for r in game.view().roads)

    result = game.perform(Travel(FAR))
    assert any(isinstance(e, LocationEntered) and e.location == FAR for e in result.events)
    assert game.view().region == WORLD.regions["region.fens"].name
    assert FAR in game.world.get(game.player, Explorer).locations_visited


def test_fleeing_a_warden_leaves_you_at_the_gate_and_it_stays():
    game = game_at_border()
    game.perform(Travel(FAR))
    game.rules = replace(game.rules, flee_chance=1.0)
    game.perform(Flee())
    position = game.world.get(game.player, Position)
    assert (position.location, position.room) == (NEAR, WORLD.location(NEAR).start)
    assert len(list(game.world.query(Warden))) == 1
    assert "CombatStarted" not in kinds(game.perform(Wait()))  # it doesn't follow you


def test_losing_to_a_warden_sends_you_back_to_town():
    game = game_at_border(WEAK)
    game.perform(Travel(FAR))
    result = game.perform(Attack())
    assert any(isinstance(e, PlayerDefeated) for e in result.events)
    assert game.world.get(game.player, Position).location == WORLD.start
    [(entity, (enemy,))] = list(game.world.query(Enemy))
    assert game.world.has(entity, Warden)


def test_wardens_survive_saving():
    game = game_at_border()
    loaded = Game.from_state(GameState.model_validate_json(game.to_state().model_dump_json()))
    assert loaded.overworld.regions == WORLD.regions
    assert next(r for r in loaded.view().roads if r.location == FAR).guard == "Reed Warden"
    assert loaded.view().region == WORLD.regions["region.wrack_coast"].name

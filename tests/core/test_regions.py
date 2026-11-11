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
BORDERS = {WORLD.location(far).region: (near, far) for near, far in WORLD.borders()}
NEAR, FAR = BORDERS["region.fens"]
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
    assert all(r.guard is None for r in game.view().roads)
    assert len(list(game.world.query(Warden))) == 1  # the Moors' warden is still there

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
    assert len(list(game.world.query(Warden))) == 2  # it stays, as does the Moors' one
    assert "CombatStarted" not in kinds(game.perform(Wait()))  # it doesn't follow you


def test_losing_to_a_warden_sends_you_back_to_town():
    game = game_at_border(WEAK)
    game.perform(Travel(FAR))
    result = game.perform(Attack())
    assert any(isinstance(e, PlayerDefeated) for e in result.events)
    assert game.world.get(game.player, Position).location == WORLD.start
    fighting = [e for e, (enemy,) in game.world.query(Enemy) if game.world.has(e, Warden)]
    assert len(fighting) == 2  # neither warden beaten


def test_wardens_survive_saving():
    game = game_at_border()
    loaded = Game.from_state(GameState.model_validate_json(game.to_state().model_dump_json()))
    assert loaded.overworld.regions == WORLD.regions
    assert next(r for r in loaded.view().roads if r.location == FAR).guard == "Reed Warden"
    assert loaded.view().region == WORLD.regions["region.wrack_coast"].name


def test_every_region_past_the_coast_has_its_warden_on_its_one_road_in():
    assert set(BORDERS) == {"region.fens", "region.moors"}
    guards = {w.region: (enemy.name, w.road) for _, _, enemy, w in WARDENS}
    assert guards == {
        "region.fens": ("Reed Warden", BORDERS["region.fens"][1]),
        "region.moors": ("Barrow Warden", BORDERS["region.moors"][1]),
    }
    near, _ = BORDERS["region.moors"]
    assert WORLD.location(near).region == "region.fens"  # the Moors lie beyond the Fens


def test_the_codex_says_where_foes_are_found():
    from tidewrack.core.engine.components import Codex, FoeEntry

    from tidewrack.core.procgen.enemy_gen import generate_enemies

    enemies, spawners = generate_enemies(SEED, WORLD, CONTENT)
    game = Game(SEED, WORLD, enemies=enemies, spawners=spawners, wardens=WARDENS)
    codex = game.world.get(game.player, Codex)
    for enemy_id in ("enemy.bog_toad", "enemy.reed_warden", "enemy.barrow_wight"):
        codex.foes[enemy_id] = FoeEntry(enemy_id, enemy_id, "beast", "", {})
    found = {f.enemy_id: f.found_in for f in game.foes().foes}
    fens = WORLD.regions["region.fens"].name
    assert found["enemy.reed_warden"] == f"Guards the causeway into {fens}"
    assert found["enemy.bog_toad"] == "places you haven't found yet"  # the Fens aren't known
    assert found["enemy.barrow_wight"] == "places you haven't found yet"

    game.world.get(game.player, Explorer).locations_discovered.add(FAR)
    found = {f.enemy_id: f.found_in for f in game.foes().foes}
    assert "Peat Bog" in found["enemy.bog_toad"] and found["enemy.bog_toad"].endswith(f"({fens})")

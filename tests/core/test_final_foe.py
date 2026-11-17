"""The Drowned King: the world's final foe, whose defeat turns the tide (step 8c)."""

from tidewrack.core.data.save import GameState
from tidewrack.core.engine.components import (
    Clue,
    Enemy,
    FinalFoe,
    Position,
    Prestige,
    QuestItem,
    Stats,
)
from tidewrack.core.engine.events import (
    CombatStarted,
    LocationEntered,
    PlayerDefeated,
    TideTurned,
)
from tidewrack.core.engine.game import Attack, Game, Move
from tidewrack.core.procgen.enemy_gen import generate_final
from tidewrack.core.procgen.world_gen import generate_world
from tidewrack.services.content import load_bundled_content
from tidewrack.services.session import GameSession
from tidewrack.services.storage import FileSaveStore

CONTENT = load_bundled_content()
RECIPE = CONTENT.world("world.standard")
SEED = 7
WORLD = generate_world(SEED, RECIPE, CONTENT.roomsets, CONTENT.regions)
FINAL = generate_final(SEED, WORLD, CONTENT, RECIPE)
STRONG = {"atk": 400, "def": 200, "hp": 900}
WEAK = {"atk": 1, "def": 0, "hp": 1}


def game_beside_the_king(stats=None) -> tuple[Game, str]:
    """A game with the player in a room next to the king's; returns the exit in."""
    game = Game(SEED, WORLD, finals=[FINAL])
    if stats:
        game.world.get(game.player, Stats).base = dict(stats)
    location = WORLD.location(FINAL.location)
    beside = next(r.id for r in location.rooms.values() if any(e.to == FINAL.room for e in r.exits))
    position = game.world.get(game.player, Position)
    position.location, position.room = location.id, beside
    label = next(e.label for e in location.room(beside).exits if e.to == FINAL.room)
    return game, label


def test_a_new_game_starts_with_no_tides_lived_through():
    game = Game(SEED, WORLD, finals=[FINAL])
    assert game.world.get(game.player, Prestige) == Prestige(rank=0, tide_turned=False)


def test_the_king_fights_whoever_walks_into_his_hall():
    game, way_in = game_beside_the_king()
    result = game.perform(Move(way_in))
    started = [e for e in result.events if isinstance(e, CombatStarted)]
    assert [e.name for e in started] == ["Drowned King"]


def test_beating_the_king_turns_the_tide():
    game, way_in = game_beside_the_king(STRONG)
    game.perform(Move(way_in))
    result = game.perform(Attack())
    region = WORLD.regions[FINAL.final.region].name
    assert [e for e in result.events if isinstance(e, TideTurned)] == [
        TideTurned("Drowned King", region)
    ]
    assert game.world.get(game.player, Prestige).tide_turned
    assert not list(game.world.query(FinalFoe))
    assert any("the tide is turning" in line for line in game.log[-3:])


def test_losing_to_the_king_leaves_the_tide_where_it_was():
    game, way_in = game_beside_the_king(WEAK)
    game.perform(Move(way_in))
    result = game.perform(Attack())
    assert any(isinstance(e, PlayerDefeated) for e in result.events)
    assert not game.world.get(game.player, Prestige).tide_turned
    assert len(list(game.world.query(FinalFoe))) == 1


def test_the_tide_survives_saving():
    game, way_in = game_beside_the_king(STRONG)
    game.perform(Move(way_in))
    game.perform(Attack())
    loaded = Game.from_state(GameState.model_validate_json(game.to_state().model_dump_json()))
    assert loaded.world.get(loaded.player, Prestige).tide_turned


def test_a_generated_world_has_the_king_alone_in_his_room(tmp_path):
    session = GameSession.generate(FileSaveStore(tmp_path), CONTENT, "world.standard", "W", SEED)
    game = session.game
    [(king, (enemy, final, at))] = list(game.world.query(Enemy, FinalFoe, Position))
    assert (at.location, at.room) == (FINAL.location, FINAL.room)
    others = [
        e
        for e, (_, p) in game.world.query(Enemy, Position)
        if e != king and (p.location, p.room) == (at.location, at.room)
    ]
    assert others == []
    # No bounty (an enemy, checked above), quest item or clue is put in his room.
    for kind in (QuestItem, Clue):
        for _, (_, p) in game.world.query(kind, Position):
            assert (p.location, p.room) != (at.location, at.room)


def test_his_hall_says_who_waits_in_it():
    game = Game(SEED, WORLD, finals=[FINAL])
    game.bus.emit(LocationEntered(game.player, FINAL.location, None, first_visit=True))
    game.bus.flush()
    assert "the Drowned King keeps his court" in game.log[-1]

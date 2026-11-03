import json

import pytest
from pydantic import ValidationError

from tidewrack.core.data.save import GameState, decode_component, encode_component
from tidewrack.core.engine.components import Explorer, Position
from tidewrack.core.engine.ecs import World
from tidewrack.core.engine.game import Game, Look, Move, Wait
from tidewrack.services.content import load_bundled_content

FIRST_DESCENT = load_bundled_content().dungeon("dungeon.first_descent")

OPENING = [Move("Descend the cliff stair"), Wait(), Look(), Move("Keep descending")]
CONTINUATION = [Wait(), Move("Follow the barnacled tunnel"), Wait(), Wait(), Look()]


def _through_json(game: Game) -> Game:
    blob = json.dumps(game.to_state().model_dump(mode="json"))
    return Game.from_state(GameState.model_validate(json.loads(blob)))


def test_loaded_game_continues_exactly_like_the_original():
    original = Game(99, FIRST_DESCENT)
    for command in OPENING:
        original.perform(command)
    loaded = _through_json(original)
    assert loaded.view() == original.view()
    for command in CONTINUATION:
        assert loaded.perform(command) == original.perform(command)  # same events, same RNG
    assert loaded.log == original.log


def test_save_is_deterministic():
    def state(game: Game) -> str:
        return json.dumps(game.to_state().model_dump(mode="json"), sort_keys=True)

    a, b = Game(5, FIRST_DESCENT), Game(5, FIRST_DESCENT)
    for game in (a, b):
        game.perform(Move("Walk out to the wreck"))
    assert state(a) == state(b)
    assert state(_through_json(a)) == state(a)


def test_save_snapshots_the_map():
    # Saves must not depend on content files that a later release may change (§9).
    state = Game(1, FIRST_DESCENT).to_state()
    assert state.dungeon.to_map() == FIRST_DESCENT


def test_rejects_unknown_component():
    data = Game(1, FIRST_DESCENT).to_state().model_dump(mode="json")
    data["entities"][0]["components"]["Jetpack"] = {}
    with pytest.raises(ValueError, match="unknown component 'Jetpack'"):
        Game.from_state(GameState.model_validate(data))


def test_rejects_position_outside_the_map():
    data = Game(1, FIRST_DESCENT).to_state().model_dump(mode="json")
    data["entities"][0]["components"]["Position"]["node"] = "the_moon"
    with pytest.raises(ValueError, match="unknown node 'the_moon'"):
        Game.from_state(GameState.model_validate(data))


def test_rejects_malformed_state():
    data = Game(1, FIRST_DESCENT).to_state().model_dump(mode="json")
    data["turn"] = -1
    with pytest.raises(ValidationError):
        GameState.model_validate(data)


def test_component_codec():
    explorer = Explorer(visited={"b", "a"}, discovered={"c", "a", "b"})
    name, fields = encode_component(explorer)
    assert (name, fields) == ("Explorer", {"visited": ["a", "b"], "discovered": ["a", "b", "c"]})
    assert decode_component(name, fields) == explorer
    with pytest.raises(ValueError, match="fields"):
        decode_component("Position", {"node": "x", "extra": 1})


def test_world_restore_keeps_ids_and_order():
    world = World()
    a = world.create(Position("x"))
    world.destroy(world.create())
    c = world.create(Position("y"))
    restored = World.restore(*world.snapshot())
    assert [e for e, _ in restored.query(Position)] == [a, c]
    assert restored.create() == c + 1  # ids never reused after loading
    with pytest.raises(ValueError):
        World.restore(1, {5: ()})

import json

import pytest
from pydantic import ValidationError

from tidewrack.core.data.save import GameState, decode_component, encode_component
from tidewrack.core.engine.components import Explorer, Position
from tidewrack.core.engine.ecs import World
from tidewrack.core.engine.game import Game, Look, Move, Wait
from tidewrack.core.procgen.world_gen import generate_world
from tidewrack.core.world.overworld import Overworld
from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()
FIRST_DESCENT = CONTENT.dungeon("dungeon.first_descent")
WORLD = Overworld(FIRST_DESCENT.id, {FIRST_DESCENT.id: FIRST_DESCENT})

OPENING = [Move("Descend the cliff stair"), Wait(), Look(), Move("Keep descending")]
CONTINUATION = [Wait(), Move("Follow the barnacled tunnel"), Wait(), Wait(), Look()]


def _through_json(game: Game) -> Game:
    blob = json.dumps(game.to_state().model_dump(mode="json"))
    return Game.from_state(GameState.model_validate(json.loads(blob)))


def test_loaded_game_continues_exactly_like_the_original():
    original = Game(99, WORLD)
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

    a, b = Game(5, WORLD), Game(5, WORLD)
    for game in (a, b):
        game.perform(Move("Walk out to the wreck"))
    assert state(a) == state(b)
    assert state(_through_json(a)) == state(a)


def test_save_snapshots_the_whole_world():
    # Saves must not depend on content files that a later release may change (§9).
    world = generate_world(3, CONTENT.world("world.standard"), CONTENT.roomsets)
    state = Game(1, world).to_state()
    assert state.world.to_overworld() == world
    assert Game.from_state(GameState.model_validate(state.model_dump())).overworld == world


def test_rejects_unknown_component():
    data = Game(1, WORLD).to_state().model_dump(mode="json")
    data["entities"][0]["components"]["Jetpack"] = {}
    with pytest.raises(ValueError, match="unknown component 'Jetpack'"):
        Game.from_state(GameState.model_validate(data))


def test_rejects_position_outside_the_map():
    data = Game(1, WORLD).to_state().model_dump(mode="json")
    data["entities"][0]["components"]["Position"]["room"] = "the_moon"
    with pytest.raises(ValueError, match="unknown room first_descent/the_moon"):
        Game.from_state(GameState.model_validate(data))


def test_rejects_malformed_state():
    data = Game(1, WORLD).to_state().model_dump(mode="json")
    data["turn"] = -1
    with pytest.raises(ValidationError):
        GameState.model_validate(data)


def test_component_codec():
    explorer = Explorer(
        locations_visited={"b", "a"},
        locations_discovered={"c", "a", "b"},
        rooms_visited={"a": {"y", "x"}},
        rooms_discovered={"a": {"z", "x", "y"}},
    )
    name, fields = encode_component(explorer)
    assert (name, fields) == (
        "Explorer",
        {
            "locations_visited": ["a", "b"],
            "locations_discovered": ["a", "b", "c"],
            "rooms_visited": {"a": ["x", "y"]},
            "rooms_discovered": {"a": ["x", "y", "z"]},
        },
    )
    assert decode_component(name, fields) == explorer
    with pytest.raises(ValueError, match="fields"):
        decode_component("Position", {"location": "a", "room": "x", "extra": 1})


def test_world_restore_keeps_ids_and_order():
    world = World()
    a = world.create(Position("l", "x"))
    world.destroy(world.create())
    c = world.create(Position("l", "y"))
    restored = World.restore(*world.snapshot())
    assert [e for e, _ in restored.query(Position)] == [a, c]
    assert restored.create() == c + 1  # ids never reused after loading
    with pytest.raises(ValueError):
        World.restore(1, {5: ()})

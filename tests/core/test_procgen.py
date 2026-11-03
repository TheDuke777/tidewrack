import pytest

from tidewrack.core.engine.game import Game, Move
from tidewrack.core.procgen.dungeon_gen import (
    DIRECTIONS,
    generate_dungeon,
    generate_world,
    world_hash,
)
from tidewrack.core.rng import Rng
from tidewrack.core.versions import GENERATOR_VERSION
from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()
SEA_CAVES = CONTENT.roomset("roomset.sea_caves")


def test_golden_world():
    # If this fails, the same seed now builds a different world: if that's intended,
    # bump core.versions.GENERATOR_VERSION and update the hash (§9).
    assert GENERATOR_VERSION == 1
    assert world_hash(generate_world(20261103, SEA_CAVES, 14)) == GOLDEN_14


GOLDEN_14 = "2d92f8fbb001ced45b6d765e785801b3c25289cd8b71860ccd6d4844768ae112"


@pytest.mark.parametrize("size", [2, 7, 14, 30, 60])
def test_many_seeds_produce_valid_connected_dungeons(size):
    for seed in range(60):
        dungeon = generate_world(seed, SEA_CAVES, size)
        assert dungeon.problems() == []  # all exits valid, everything reachable
        assert len(dungeon.nodes) == size
        assert dungeon.has_map
        names = [n.name for n in dungeon.nodes.values()]
        assert len(set(names)) == size, "room names must be unique"


def test_layout_rules():
    dungeon = generate_world(7, SEA_CAVES, 30)
    start = dungeon.node(dungeon.start)
    assert start.name == "The Cave Mouth"
    assert start.pos[1] > 0.8  # entrance on the south edge
    labels = {f"Go {d}" for d in DIRECTIONS.values()}
    for node in dungeon.nodes.values():
        assert {e.label for e in node.exits} <= labels
        assert all(0 <= v <= 1 for v in node.pos)
        for exit_ in node.exits:  # every path is two-way
            assert any(e.to == node.id for e in dungeon.node(exit_.to).exits)


def test_same_seed_same_world_and_seeds_differ():
    assert generate_world(5, SEA_CAVES, 20) == generate_world(5, SEA_CAVES, 20)
    assert world_hash(generate_world(5, SEA_CAVES, 20)) != world_hash(
        generate_world(6, SEA_CAVES, 20)
    )


def test_naming_does_not_change_layout():
    # Layout and names use separate substreams: renaming content keeps world shapes.
    a = generate_dungeon(Rng(1), SEA_CAVES, 20)
    renamed = SEA_CAVES.model_copy(update={"adjectives": ["Odd"] + SEA_CAVES.adjectives})
    b = generate_dungeon(Rng(1), renamed, 20)
    assert [(n.id, n.pos, n.exits) for n in a.nodes.values()] == [
        (n.id, n.pos, n.exits) for n in b.nodes.values()
    ]


def test_rejects_tiny_dungeons():
    with pytest.raises(ValueError):
        generate_world(1, SEA_CAVES, 1)


# --- fog-of-war map view -----------------------------------------------------------


def test_map_view_shows_only_what_is_known():
    dungeon = generate_world(11, SEA_CAVES, 14)
    game = Game(11, dungeon)
    view = game.view().map
    start = dungeon.node(dungeon.start)

    assert {n.id for n in view.nodes} == {start.id, *(e.to for e in start.exits)}
    states = {n.id: n.state for n in view.nodes}
    assert states.pop(start.id) == "current"
    assert set(states.values()) == {"seen"}
    assert all(n.name is None for n in view.nodes if n.state == "seen")
    assert set(view.edges) == {tuple(sorted((start.id, e.to))) for e in start.exits}
    steps = {n.id: n.exit_label for n in view.nodes if n.exit_label}
    assert steps == {e.to: e.label for e in start.exits}

    first = start.exits[0]
    game.perform(Move(first.label))
    after = {n.id: n for n in game.view().map.nodes}
    assert after[start.id].state == "visited" and after[start.id].name == start.name
    assert after[first.to].state == "current"


def test_map_view_is_none_without_positions():
    dungeon = CONTENT.dungeon("dungeon.first_descent")
    unmapped = type(dungeon)(
        dungeon.id,
        dungeon.name,
        dungeon.start,
        {k: type(n)(**{**n.__dict__, "pos": None}) for k, n in dungeon.nodes.items()},
    )
    assert Game(1, unmapped).view().map is None
    assert Game(1, dungeon).view().map is not None

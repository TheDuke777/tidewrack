import pytest

from tidewrack.core.engine.components import Explorer, Position
from tidewrack.core.engine.events import (
    ActionRejected,
    NodeDiscovered,
    NodeEntered,
    TurnEnded,
)
from tidewrack.core.engine.game import Game, Look, Move, Wait
from tidewrack.core.world.dungeon import DungeonMap
from tidewrack.core.world.first_descent import FIRST_DESCENT, FIRST_DESCENT_DATA

# A walk that visits every node of the first dungeon.
FULL_TOUR = [
    "Descend the cliff stair",
    "Enter the archway",
    "Leave through the archway",
    "Keep descending",
    "Follow the barnacled tunnel",
    "Head toward the wreck",
    "Climb back up to the deck",
    "Return to the cove",
]


def _kinds(result):
    return [type(e).__name__ for e in result.events]


# --- dungeon data ----------------------------------------------------------------


def test_first_descent_is_valid():
    assert FIRST_DESCENT.problems() == []
    assert len(FIRST_DESCENT.nodes) == 7


def test_dungeon_validation_catches_errors():
    broken = {
        "id": "dungeon.broken",
        "name": "Broken",
        "start": "a",
        "nodes": [
            {"id": "a", "name": "A", "description": "", "exits": [{"label": "x", "to": "nowhere"}]},
            {"id": "island", "name": "I", "description": "", "exits": [{"label": "y", "to": "a"}]},
        ],
    }
    with pytest.raises(ValueError, match="unknown node 'nowhere'"):
        DungeonMap.from_dict(broken)
    broken["nodes"][0]["exits"][0]["to"] = "a"
    with pytest.raises(ValueError, match="island: unreachable"):
        DungeonMap.from_dict(broken)


# --- turn loop -------------------------------------------------------------------


def test_start_state():
    game = Game(seed=1)
    view = game.view()
    assert view.location == "Wrack Cove"
    assert view.turn == 0
    assert view.visited == 1
    assert all(e.destination is None for e in view.exits)
    assert game.log[:2] == ["— The First Descent —", "You stand at Wrack Cove."]


def test_move_takes_a_turn_and_reveals_neighbours():
    game = Game(seed=1)
    result = game.perform(Move("Descend the cliff stair"))
    assert result.took_turn
    kinds = _kinds(result)
    assert kinds[0] == "NodeEntered" and kinds[-1] == "TurnEnded"
    discovered = {e.node_id for e in result.events if isinstance(e, NodeDiscovered)}
    assert discovered == {"tide_shrine", "sea_cave"}  # wrack_cove was already known
    assert game.world.get(game.player, Position).node == "cliff_stair"
    assert game.view().turn == 1


def test_rejected_move_is_free():
    game = Game(seed=1)
    result = game.perform(Move("Fly away"))
    assert not result.took_turn
    assert [type(e) for e in result.events] == [ActionRejected]
    assert game.turn == 0
    assert game.log[-1] == "You can't go that way."


def test_look_is_free_and_describes_scenery():
    game = Game(seed=1)
    result = game.perform(Look())
    assert not result.took_turn
    assert "Gulls watch you from the rocks and do not cry out." in game.log


def test_wait_takes_a_turn():
    game = Game(seed=1)
    result = game.perform(Wait())
    assert result.took_turn and isinstance(result.events[-1], TurnEnded)
    assert "Time passes." in game.log


def test_revisits_are_marked_and_exits_show_known_destinations():
    game = Game(seed=1)
    game.perform(Move("Descend the cliff stair"))
    result = game.perform(Move("Climb back to the cove"))
    entered = next(e for e in result.events if isinstance(e, NodeEntered))
    assert not entered.first_visit
    assert "You return to Wrack Cove." in game.log[-2:]  # may be followed by an ambient line
    exits = {e.label: e.destination for e in game.view().exits}
    assert exits == {"Descend the cliff stair": "The Cliff Stair", "Walk out to the wreck": None}


def test_full_tour_explores_everything():
    game = Game(seed=1)
    for label in FULL_TOUR:
        assert game.perform(Move(label)).took_turn, label
    explorer = game.world.get(game.player, Explorer)
    assert explorer.visited == set(FIRST_DESCENT.nodes)
    assert game.view().visited == game.view().total_nodes == 7


def test_same_seed_and_commands_give_identical_runs():
    def run(seed):
        game = Game(seed)
        events = []
        for label in FULL_TOUR:
            events += game.perform(Move(label)).events
            events += game.perform(Wait()).events
        return game.log, events

    assert run(2024) == run(2024)
    assert run(2024)[0] != run(2025)[0]  # ambient lines differ between seeds


def test_dungeon_data_is_not_mutated_by_play():
    before = repr(FIRST_DESCENT_DATA)
    game = Game(seed=3)
    for label in FULL_TOUR:
        game.perform(Move(label))
    assert repr(FIRST_DESCENT_DATA) == before

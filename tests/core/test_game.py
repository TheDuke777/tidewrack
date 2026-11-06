from tidewrack.core.data.save import GameState
from tidewrack.core.engine.components import Explorer, Position
from tidewrack.core.engine.events import (
    ActionRejected,
    RoomDiscovered,
    RoomEntered,
    TurnEnded,
)
from tidewrack.core.engine.game import Drop, Equip, Game, Look, Move, Take, Unequip, Wait
from tidewrack.core.gear.item import Item
from tidewrack.core.procgen.gear_gen import generate_kit, make_item
from tidewrack.core.world.overworld import Overworld
from tidewrack.services.content import load_bundled_content

FIRST_DESCENT = load_bundled_content().dungeon("dungeon.first_descent")
WORLD = Overworld(FIRST_DESCENT.id, {FIRST_DESCENT.id: FIRST_DESCENT})

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


def new_game(seed: int) -> Game:
    return Game(seed, WORLD)


def _kinds(result):
    return [type(e).__name__ for e in result.events]


# --- turn loop -------------------------------------------------------------------


def test_start_state():
    game = new_game(1)
    view = game.view()
    assert (view.location, view.kind, view.room) == ("The First Descent", "Dungeon", "Wrack Cove")
    assert view.turn == 0
    assert view.rooms_visited == 1
    assert view.at_gate and view.roads == ()
    assert all(e.destination is None for e in view.exits)
    assert game.log[:2] == ["— The First Descent · Dungeon —", "You stand at Wrack Cove."]


def test_move_takes_a_turn_and_reveals_neighbours():
    game = new_game(1)
    result = game.perform(Move("Descend the cliff stair"))
    assert result.took_turn
    kinds = _kinds(result)
    assert kinds[0] == "RoomEntered" and kinds[-1] == "TurnEnded"
    discovered = {e.room for e in result.events if isinstance(e, RoomDiscovered)}
    assert discovered == {"tide_shrine", "sea_cave"}  # wrack_cove was already known
    assert game.world.get(game.player, Position).room == "cliff_stair"
    assert game.view().turn == 1


def test_rejected_move_is_free():
    game = new_game(1)
    result = game.perform(Move("Fly away"))
    assert not result.took_turn
    assert [type(e) for e in result.events] == [ActionRejected]
    assert game.turn == 0
    assert game.log[-1] == "You can't go that way."


def test_look_is_free_and_describes_scenery():
    game = new_game(1)
    result = game.perform(Look())
    assert not result.took_turn
    assert "Gulls watch you from the rocks and do not cry out." in game.log


def test_wait_takes_a_turn():
    game = new_game(1)
    result = game.perform(Wait())
    assert result.took_turn and isinstance(result.events[-1], TurnEnded)
    assert "Time passes." in game.log


def test_revisits_are_marked_and_exits_show_known_destinations():
    game = new_game(1)
    game.perform(Move("Descend the cliff stair"))
    result = game.perform(Move("Climb back to the cove"))
    entered = next(e for e in result.events if isinstance(e, RoomEntered))
    assert not entered.first_visit
    assert "You return to Wrack Cove." in game.log[-2:]  # may be followed by an ambient line
    exits = {e.label: e.destination for e in game.view().exits}
    assert exits == {"Descend the cliff stair": "The Cliff Stair", "Walk out to the wreck": None}


def test_full_tour_explores_everything():
    game = new_game(1)
    for label in FULL_TOUR:
        assert game.perform(Move(label)).took_turn, label
    explorer = game.world.get(game.player, Explorer)
    assert explorer.rooms_visited == {FIRST_DESCENT.id: set(FIRST_DESCENT.rooms)}
    assert game.view().rooms_visited == game.view().total_rooms == 7


def test_same_seed_and_commands_give_identical_runs():
    def run(seed):
        game = new_game(seed)
        events = []
        for label in FULL_TOUR:
            events += game.perform(Move(label)).events
            events += game.perform(Wait()).events
        return game.log, events

    assert run(2024) == run(2024)
    assert run(2024)[0] != run(2025)[0]  # ambient lines differ between seeds


# --- gear --------------------------------------------------------------------------

CONTENT = load_bundled_content()
RECIPE = CONTENT.world("world.standard")


def gear_item(gear_id, **roll):
    return make_item(CONTENT.gear[gear_id], CONTENT.gearsets, roll)


def geared_game() -> Game:
    """Kit on; a Harpoon and a Buckler at the start, a Cutlass one room down."""
    return Game(
        1,
        WORLD,
        RECIPE.player,
        kit=generate_kit(RECIPE, CONTENT),
        finds=[
            (FIRST_DESCENT.id, "wrack_cove", gear_item("gear.harpoon")),
            (FIRST_DESCENT.id, "wrack_cove", gear_item("gear.buckler")),
            (FIRST_DESCENT.id, "cliff_stair", gear_item("gear.cutlass", atk=1)),
        ],
    )


def here(game, name):
    return next(i for i in game.view().items_here if i.name == name)


def test_the_kit_is_equipped_and_counts_toward_stats():
    game = geared_game()
    slots = {s.slot: s.item.name for s in game.inventory().slots if s.item}
    assert slots == {"main_hand": "Driftwood Club", "body": "Patched Coat"}
    assert game.view().stats == {"atk": 4, "def": 2, "hp": 20}
    assert [i.name for i in game.view().items_here] == ["Harpoon", "Buckler"]
    assert "Lying here: Harpoon and Buckler." in game.log


def test_take_then_equip_a_two_hander_frees_both_hands():
    game = geared_game()
    buckler = here(game, "Buckler")
    assert game.perform(Take(buckler.id)).took_turn
    game.perform(Equip(buckler.id))
    assert game.view().stats["def"] == 4

    harpoon = here(game, "Harpoon")
    assert harpoon.comparison.replaces == ("Driftwood Club", "Buckler")
    game.perform(Take(harpoon.id))
    result = game.perform(Equip(harpoon.id))
    assert "ItemEquipped" in _kinds(result)
    assert game.log[-1] == "You put away the Driftwood Club and Buckler and equip the Harpoon."
    inventory = game.inventory()
    off_hand = next(s for s in inventory.slots if s.slot == "off_hand")
    assert off_hand.item is None and off_hand.filled_by == "Harpoon"
    assert [i.name for i in inventory.pack] == ["Driftwood Club", "Buckler"]
    assert game.view().stats == {"atk": 9, "def": 2, "hp": 20}


def test_unequip_and_drop():
    game = geared_game()
    coat = next(s.item for s in game.inventory().slots if s.slot == "body")
    game.perform(Unequip(coat.id))
    assert game.view().stats["def"] == 1
    assert [i.name for i in game.inventory().pack] == ["Patched Coat"]
    game.perform(Move("Descend the cliff stair"))
    game.perform(Drop(coat.id))
    assert [i.name for i in game.view().items_here] == ["Patched Coat", "Cutlass"]
    assert game.log[-1] == "You put down the Patched Coat."


def test_dropping_an_equipped_item_takes_it_off_first():
    game = geared_game()
    club = next(s.item for s in game.inventory().slots if s.slot == "main_hand")
    result = game.perform(Drop(club.id))
    assert _kinds(result)[:2] == ["ItemUnequipped", "ItemDropped"]
    assert game.view().stats["atk"] == 2


def test_gear_actions_on_the_wrong_item_are_rejected_and_free():
    game = geared_game()
    cutlass = next(
        e
        for e, (item, position) in game.world.query(Item, Position)
        if position.room == "cliff_stair"
    )
    club = next(s.item for s in game.inventory().slots if s.slot == "main_hand")
    for command, reason in [
        (Take(cutlass), "That isn't here."),
        (Equip(cutlass), "You aren't carrying that."),
        (Drop(cutlass), "You aren't carrying that."),
        (Unequip(cutlass), "You don't have that on."),
        (Equip(club.id), "You already have the Driftwood Club on."),
        (Take(9999), "That isn't here."),
    ]:
        result = game.perform(command)
        assert not result.took_turn
        assert [e.reason for e in result.events if isinstance(e, ActionRejected)] == [reason]
    assert game.turn == 0


def test_gear_survives_a_save_round_trip():
    game = geared_game()
    harpoon = here(game, "Harpoon")
    game.perform(Take(harpoon.id))
    game.perform(Equip(harpoon.id))
    restored = Game.from_state(GameState.model_validate_json(game.to_state().model_dump_json()))
    assert restored.view() == game.view()
    assert restored.inventory() == game.inventory()
    move = Move("Descend the cliff stair")
    assert restored.perform(move) == game.perform(move)
    take = Take(here(game, "Cutlass").id)
    assert restored.perform(take) == game.perform(take)
    assert restored.to_state() == game.to_state()


def test_log_total_keeps_counting_past_the_log_limit_and_isnt_saved():
    from tidewrack.core.engine.game import LOG_LIMIT

    game = new_game(1)
    start = game.view().log_total
    assert start == len(game.log)
    for _ in range(LOG_LIMIT):
        game.perform(Look())
    view = game.view()
    assert len(view.log) == LOG_LIMIT  # capped
    assert view.log_total > start + LOG_LIMIT - 1  # still counting
    restored = Game.from_state(GameState.model_validate_json(game.to_state().model_dump_json()))
    assert restored.view().log_total == LOG_LIMIT  # starts again from what was kept
    assert "log_total" not in game.to_state().model_dump()

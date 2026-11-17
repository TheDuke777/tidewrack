"""Ascending (CLAUDE.md §14 step 8c): the tide turns, and a new world in the same slot."""

import pytest

from tidewrack.core.engine.components import (
    Codex,
    Fighting,
    FinalFoe,
    Health,
    Position,
    Prestige,
    TideCrown,
    Wallet,
)
from tidewrack.core.engine.game import Wait
from tidewrack.core.progression.prestige import BOON_DECAY, boon_size, make_boon, next_seed
from tidewrack.services.content import load_bundled_content
from tidewrack.services.session import GameSession
from tidewrack.services.storage import FileSaveStore

CONTENT = load_bundled_content()


def session_with_turned_tide(tmp_path, difficulty="difficulty.standard") -> GameSession:
    session = GameSession.generate(
        FileSaveStore(tmp_path), CONTENT, "world.standard", "W", 11, difficulty=difficulty
    )
    turn_the_tide(session.game)
    return session


def turn_the_tide(game) -> None:
    """As if the king fell where the player stands: the tide turned, his crown here."""
    game.world.get(game.player, Prestige).tide_turned = True
    here = game.world.get(game.player, Position)
    game.world.create(TideCrown(), Position(here.location, here.room))


def test_you_cant_ascend_until_the_tide_turns(tmp_path):
    session = GameSession.generate(FileSaveStore(tmp_path), CONTENT, "world.standard", "W", 11)
    assert not session.game.view().can_ascend
    assert not session.ascend(CONTENT, "boon.keen_edge")
    assert session.game.seed == 11


def test_you_cant_ascend_mid_fight_or_with_an_unknown_boon(tmp_path):
    session = session_with_turned_tide(tmp_path)
    assert not session.ascend(CONTENT, "boon.nonsense")
    game = session.game
    game.world.add(game.player, Fighting(enemy=0, retreat_room="room_00", enemy_stats={}))
    assert not game.can_ascend()
    assert not session.ascend(CONTENT, "boon.keen_edge")


def test_ascending_makes_a_new_world_in_the_same_slot(tmp_path):
    session = session_with_turned_tide(tmp_path, "difficulty.hard")
    old = session.game
    old.world.get(old.player, Wallet).gold = 999
    old.world.get(old.player, Codex).kills["enemy.wild_boar"] = 7
    slot, revision = session.meta.slot_id, session.meta.revision
    assert old.view().can_ascend

    assert session.ascend(CONTENT, "boon.keen_edge")
    game = session.game
    assert game is not old
    assert game.seed == next_seed(11, 0) != 11
    assert game.rules.difficulty == "Hard"  # the slot's difficulty carries on
    assert game.turn == 0 and game.view().gold == CONTENT.world("world.standard").gold
    assert game.world.get(game.player, Codex).kills == {"enemy.wild_boar": 7}
    prestige = game.world.get(game.player, Prestige)
    assert (prestige.rank, prestige.tide_turned) == (1, False)
    assert [b.boon_id for b in prestige.boons] == ["boon.keen_edge"]
    assert len(list(game.world.query(FinalFoe))) == 1  # a new king waits
    assert "You wake on a strange shore, the first tide behind you" in game.log[-1]
    assert game.view().tide == 1 and not game.view().can_ascend

    assert session.meta.slot_id == slot and session.meta.revision == revision + 1
    assert session.meta.summary.tide == 1
    reopened = GameSession.open(session.store, slot, CONTENT)
    assert reopened.game.seed == game.seed
    assert reopened.game.world.get(reopened.game.player, Prestige) == prestige


def test_boons_add_up_and_shrink_each_tide(tmp_path):
    session = session_with_turned_tide(tmp_path)
    base = session.game.sheet().total["atk"]
    assert [b.stats for b in session.boon_choices(CONTENT)][:2] == [{"atk": 2}, {"def": 2}]
    session.ascend(CONTENT, "boon.keen_edge")
    assert session.game.sheet().total["atk"] == base + 2
    game = session.game
    turn_the_tide(game)
    choices = {b.boon_id: b for b in session.boon_choices(CONTENT)}
    assert choices["boon.deep_lungs"].stats == {"hp": boon_size(8, 2)} == {"hp": 6}
    assert choices["boon.wreckers_luck"].gold_pct == 16
    session.ascend(CONTENT, "boon.keen_edge")
    game = session.game
    assert game.world.get(game.player, Prestige).rank == 2
    assert game.sheet().total["atk"] == base + 2 + boon_size(2, 2)
    assert "the second tide behind you" in game.log[-1]


@pytest.mark.parametrize("tide", range(1, 12))
def test_a_boon_never_shrinks_to_nothing(tide):
    for schema in CONTENT.boon_choices():
        boon = make_boon(schema, tide)
        assert any(boon.stats.values()) or boon.gold_pct >= 5 or boon.meal_turns_pct >= 5
    assert BOON_DECAY < 1


def test_wreckers_luck_adds_to_loot_and_quest_gold_but_not_sales(tmp_path):
    from tidewrack.core.economy import shops

    session = session_with_turned_tide(tmp_path)
    session.ascend(CONTENT, "boon.wreckers_luck")
    game = session.game
    wallet = game.world.get(game.player, Wallet)
    before = wallet.gold
    shops.gain(game, 100, "loot")
    assert wallet.gold == before + 120
    shops.gain(game, 100, "sale")
    assert wallet.gold == before + 220


def test_long_table_makes_meals_last_longer(tmp_path):
    from tidewrack.core.economy import cooking
    from tidewrack.core.engine.components import MealStack, WellFed
    from tidewrack.core.procgen.material_gen import make_meal

    session = session_with_turned_tide(tmp_path)
    session.ascend(CONTENT, "boon.long_table")
    game = session.game
    meal = make_meal(CONTENT.meals["meal.boar_roast"], CONTENT)
    cooking.held(game)[meal.meal_id] = MealStack(meal, 1)
    cooking.eat(game, meal.meal_id)
    assert game.world.get(game.player, WellFed).turns_left == meal.turns * 3 // 2


def test_a_new_world_still_plays(tmp_path):
    session = session_with_turned_tide(tmp_path)
    session.ascend(CONTENT, "boon.sea_hardened")
    session.perform(Wait())
    assert session.game.turn == 1
    assert session.game.world.get(session.game.player, Health).damage == 0


def test_the_crown_must_be_in_your_room(tmp_path):
    session = session_with_turned_tide(tmp_path)
    game = session.game
    [(crown, _)] = list(game.world.query(TideCrown))
    game.world.get(crown, Position).room = "elsewhere"
    assert not game.can_ascend() and not game.view().can_ascend
    assert not session.ascend(CONTENT, "boon.keen_edge")

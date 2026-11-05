"""Combat, recovery and the Foes codex (CLAUDE.md §14 step 6a)."""

from math import ceil

from tidewrack.core.codex.foes import DROPS_AT, STATS_AT, foes_view
from tidewrack.core.combat.rules import STANDARD, Rules, damage, regen
from tidewrack.core.data.save import GameState
from tidewrack.core.engine.components import Codex, Enemy, FoeEntry, Health, Position, Spawner
from tidewrack.core.engine.events import ActionRejected, Attacked, CombatStarted, Rested
from tidewrack.core.engine.game import (
    Attack,
    Defend,
    Equip,
    Flee,
    Game,
    Look,
    Move,
    Take,
    Wait,
)
from tidewrack.core.gear.item import Item
from tidewrack.core.procgen.world_gen import generate_world
from tidewrack.core.rng import Rng
from tidewrack.core.world.overworld import Overworld
from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()
FIRST_DESCENT = CONTENT.dungeon("dungeon.first_descent")
WORLD = Overworld(FIRST_DESCENT.id, {FIRST_DESCENT.id: FIRST_DESCENT})
CAVE = FIRST_DESCENT.id
DOWN = "Descend the cliff stair"  # wrack_cove (the gate) -> cliff_stair


def crab(**stats) -> Enemy:
    return Enemy(
        enemy_id="enemy.shore_crab",
        name="Shore Crab",
        category="beast",
        description="A big crab.",
        stats={"atk": 3, "def": 2, "hp": 8, **stats},
        drops=["Sealskin Boots"],
        loot=[Item(gear_id="gear.sealskin_boots", name="Sealskin Boots", slot="feet")],
    )


def game_with(enemy=None, player=None, rules=STANDARD, spawners=(), room="cliff_stair") -> Game:
    enemies = [(CAVE, room, enemy)] if enemy else []
    return Game(
        1,
        WORLD,
        player or {"atk": 4, "def": 2, "hp": 20},
        enemies=enemies,
        spawners=spawners,
        rules=rules,
    )


def kinds(result):
    return [type(e).__name__ for e in result.events]


def rejected(result):
    return [e.reason for e in result.events if isinstance(e, ActionRejected)]


# --- rules -------------------------------------------------------------------------


def test_damage_is_at_least_one_and_defending_halves_it():
    rng = Rng(3)
    for _ in range(200):
        hit = damage(rng, 9, 3, False, STANDARD)
        assert 6 <= hit <= 9  # 9 − 3 + 0..3
        assert damage(rng, 1, 50, False, STANDARD) == 1
        assert damage(rng, 1, 50, True, STANDARD) == 1
    assert {damage(Rng(5), 10, 0, True, STANDARD) for _ in range(1)} <= set(range(5, 8))


# --- fights ------------------------------------------------------------------------


def test_entering_a_room_with_an_enemy_starts_a_fight():
    game = game_with(crab())
    result = game.perform(Move(DOWN))
    assert "CombatStarted" in kinds(result)
    view = game.view()
    assert view.combat is not None and view.combat.name == "Shore Crab"
    assert (view.combat.hp, view.combat.max_hp) == (8, 8)
    assert game.log[-1] == "A Shore Crab blocks your way!"
    assert [f.name for f in game.foes().foes] == ["Shore Crab"]


def test_winning_drops_loot_and_counts_in_the_codex():
    game = game_with(crab(), player={"atk": 50, "def": 2, "hp": 20})
    game.perform(Move(DOWN))
    result = game.perform(Attack())
    assert kinds(result)[:2] == ["Attacked", "EnemyKilled"]
    assert game.view().combat is None
    assert [i.name for i in game.view().items_here] == ["Sealskin Boots"]
    assert "It drops a Sealskin Boots." in game.log
    assert game.world.get(game.player, Codex).kills == {"enemy.shore_crab": 1}
    [foe] = game.foes().foes
    assert foe.stats == {"atk": 3, "def": 2, "hp": 8} and foe.drops is None
    assert game.perform(Move("Keep descending")).took_turn  # free to go on


def test_the_enemy_strikes_back_and_defending_softens_it():
    game = game_with(crab(atk=10), player={"atk": 1, "def": 0, "hp": 100})
    game.perform(Move(DOWN))
    hits = [e for e in game.perform(Attack()).events if isinstance(e, Attacked)]
    assert [h.attacker_name for h in hits] == ["You", "Shore Crab"]
    assert 10 <= hits[1].damage <= 14
    braced = [e for e in game.perform(Defend()).events if isinstance(e, Attacked)]
    assert len(braced) == 1 and braced[0].defended and 5 <= braced[0].damage <= 7
    assert game.view().hp == 100 - hits[1].damage - braced[0].damage


def test_only_fighting_and_looking_are_allowed_mid_fight():
    game = game_with(crab())
    game.perform(Move(DOWN))
    for command in [Move("Keep descending"), Wait(), Take(999), Equip(999)]:
        result = game.perform(command)
        assert rejected(result) == ["You're fighting the Shore Crab!"]
        assert not result.took_turn
    assert not game.perform(Look()).took_turn and not rejected(game.perform(Look()))
    calm = game_with()
    assert rejected(calm.perform(Attack())) == ["There's nothing here to fight."]


def test_fleeing_returns_you_and_the_enemy_waits():
    game = game_with(crab(), rules=Rules(flee_chance=1.0))
    game.perform(Move(DOWN))
    result = game.perform(Flee())
    assert "Fled" in kinds(result) and "CombatStarted" not in kinds(result)
    assert game.view().room == FIRST_DESCENT.room("wrack_cove").name
    assert game.view().combat is None
    assert "CombatStarted" in kinds(game.perform(Move(DOWN)))  # still there


def test_a_failed_flee_gives_the_enemy_a_free_blow():
    game = game_with(crab(), rules=Rules(flee_chance=0.0))
    game.perform(Move(DOWN))
    result = game.perform(Flee())
    assert kinds(result)[:2] == ["FleeFailed", "Attacked"]
    assert game.view().combat is not None


def test_losing_wakes_you_at_the_respawn_point_and_the_enemy_stays():
    game = game_with(crab(atk=50), player={"atk": 1, "def": 0, "hp": 10})
    game.perform(Move(DOWN))
    result = game.perform(Attack())
    assert "PlayerDefeated" in kinds(result) and "Respawned" in kinds(result)
    view = game.view()
    assert view.combat is None and view.room == FIRST_DESCENT.room("wrack_cove").name
    assert view.hp == ceil(10 * STANDARD.respawn_hp)
    assert any(isinstance(c, Enemy) for c in game.world.components(_enemy_at(game, "cliff_stair")))


def _enemy_at(game, room):
    return next(e for e, (_, p) in game.world.query(Enemy, Position) if p.room == room)


def test_enemy_strength_scales_fights():
    game = game_with(crab(), rules=Rules(enemy_strength=2.0))
    game.perform(Move(DOWN))
    assert game.view().combat.stats == {"atk": 6, "def": 4, "hp": 16}


# --- recovery ----------------------------------------------------------------------


def test_regeneration_out_of_fights():
    game = game_with()
    game.world.get(game.player, Health).damage = 5
    for _ in range(STANDARD.regen_every):
        game.perform(Wait())
    assert game.view().hp == 20 - 5 + 1  # 5% of 20


def test_regeneration_scales_with_max_hp():
    game = game_with(player={"atk": 4, "def": 2, "hp": 200})
    game.world.get(game.player, Health).damage = 50
    for _ in range(STANDARD.regen_every):
        game.perform(Wait())
    assert game.view().hp == 200 - 50 + 10  # 5% of 200
    assert regen(5, STANDARD) == STANDARD.regen_amount  # small bars still heal


def test_waiting_in_a_town_no_longer_rests_you_for_free():
    # Since v0.7: a full rest is a paid night at an inn (tests/core/test_economy.py).
    world = generate_world(7, CONTENT.world("world.standard"), CONTENT.roomsets)
    game = Game(7, world)
    game.world.get(game.player, Health).damage = 9
    assert game.view().in_town
    result = game.perform(Wait())
    assert not any(isinstance(e, Rested) for e in result.events)
    assert game.view().hp < game.view().max_hp


def test_taking_off_hp_gear_never_knocks_you_out():
    charm = Item(gear_id="gear.charm", name="Charm", slot="trinket", base={"hp": 10})
    game = Game(1, WORLD, {"atk": 4, "def": 2, "hp": 5}, kit=[charm])
    game.world.get(game.player, Health).damage = 12  # 3 of 15 HP left
    from tidewrack.core.engine.game import Unequip

    game.perform(Unequip(next(s.item.id for s in game.inventory().slots if s.item)))
    assert game.view().hp == 1


# --- wandering enemies -------------------------------------------------------------


def test_wanderers_come_from_the_queue_but_never_at_gates():
    spawner = Spawner(CAVE, 1.0, [crab(), crab(hp=3)])
    game = game_with(spawners=[spawner])
    result = game.perform(Move(DOWN))
    started = [e for e in result.events if isinstance(e, CombatStarted)]
    assert len(started) == 1 and started[0].wandering
    assert game.log[-1] == "A Shore Crab comes upon you!"
    assert len(game.world.get(next(e for e, _ in game.world.query(Spawner)), Spawner).queue) == 1


def test_no_wanderer_finds_you_while_fleeing_or_in_a_gate():
    spawner = Spawner(CAVE, 1.0, [crab(), crab(), crab()])
    game = game_with(crab(), rules=Rules(flee_chance=1.0), spawners=[spawner])
    game.perform(Move(DOWN))  # the placed crab
    result = game.perform(Flee())  # back to the gate: no wanderer
    assert "CombatStarted" not in kinds(result)


# --- saving ------------------------------------------------------------------------


def test_a_fight_survives_a_save_round_trip():
    game = game_with(crab(), rules=Rules(flee_chance=0.3, enemy_strength=1.5))
    game.perform(Move(DOWN))
    game.perform(Defend())
    restored = Game.from_state(GameState.model_validate_json(game.to_state().model_dump_json()))
    assert restored.view() == game.view() and restored.rules == game.rules
    for command in [Attack(), Flee(), Attack(), Defend(), Attack()]:
        assert restored.perform(command) == game.perform(command)
    assert restored.to_state() == game.to_state()


# --- codex -------------------------------------------------------------------------


def test_foes_reveal_more_as_you_win():
    entry = FoeEntry("enemy.rat", "Cave Rat", "beast", "Fat.", {"atk": 2, "hp": 5}, ["Helm"])
    codex = Codex(foes={"enemy.rat": entry})
    [foe] = foes_view(codex).foes
    assert foe.stats is None and foe.drops is None
    assert foe.next_reveal == "Defeat one to learn its strength."
    codex.kills["enemy.rat"] = STATS_AT
    [foe] = foes_view(codex).foes
    assert foe.stats == {"atk": 2, "hp": 5} and foe.drops is None
    assert foe.next_reveal == f"Defeat {DROPS_AT - STATS_AT} more to learn what it drops."
    codex.kills["enemy.rat"] = DROPS_AT
    [foe] = foes_view(codex).foes
    assert foe.drops == ("Helm",) and foe.next_reveal is None
    assert [h for h, _ in foes_view(codex).by_category()] == ["Beasts"]

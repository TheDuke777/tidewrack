"""Enemies coming back: wanderer queues refill slowly (CLAUDE.md §14 step 6c)."""

from tidewrack.core.combat.returns import from_template
from tidewrack.core.combat.rules import STANDARD, Rules
from tidewrack.core.data.save import GameState
from tidewrack.core.engine.components import EnemyTemplate, Spawner
from tidewrack.core.engine.game import Game, Wait
from tidewrack.core.gear.item import Item
from tidewrack.core.procgen.enemy_gen import generate_enemies
from tidewrack.core.procgen.world_gen import generate_world
from tidewrack.core.rng import Rng
from tidewrack.core.world.overworld import Overworld
from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()
FIRST_DESCENT = CONTENT.dungeon("dungeon.first_descent")
WORLD = Overworld(FIRST_DESCENT.id, {FIRST_DESCENT.id: FIRST_DESCENT})
BOOTS = Item(gear_id="gear.sealskin_boots", name="Sealskin Boots", slot="feet")


def crab_template(**fields) -> EnemyTemplate:
    defaults = dict(
        enemy_id="enemy.shore_crab",
        name="Shore Crab",
        category="beast",
        description="A big crab.",
        stats={"atk": 3, "def": 2, "hp": 8},
        rolls={"hp": [0, 2]},
        drops=["Sealskin Boots"],
        loot_chance=1.0,
        loot=[BOOTS],
    )
    return EnemyTemplate(**{**defaults, **fields})


def game_with(spawner: Spawner, rules: Rules = STANDARD) -> Game:
    return Game(1, WORLD, spawners=[spawner], rules=rules)


def queue(game: Game) -> list:
    [(_, (spawner,))] = list(game.world.query(Spawner))
    return spawner.queue


def test_a_template_rolls_its_stats_and_maybe_its_loot():
    rng = Rng(4)
    for _ in range(50):
        enemy = from_template(rng, crab_template(), loot_factor=1.0)
        assert 8 <= enemy.stats["hp"] <= 10 and enemy.stats["atk"] == 3
        assert [i.name for i in enemy.loot] == ["Sealskin Boots"]
        assert enemy.loot[0] is not BOOTS  # a copy, not the template's own
        assert from_template(rng, crab_template(), loot_factor=0.0).loot == []


def test_wanderers_come_back_every_few_turns_up_to_the_cap():
    spawner = Spawner(FIRST_DESCENT.id, 0.0, [], cap=2, templates=[crab_template()])
    game = game_with(spawner, Rules(enemy_return_every=3))
    for turn in range(1, 10):
        game.perform(Wait())
        assert len(queue(game)) == min(2, turn // 3)
    assert {e.name for e in queue(game)} == {"Shore Crab"}


def test_nothing_comes_back_without_templates():
    game = game_with(Spawner(FIRST_DESCENT.id, 0.0, [], cap=4), Rules(enemy_return_every=1))
    for _ in range(5):
        game.perform(Wait())
    assert queue(game) == []


def test_returns_survive_a_save_round_trip():
    spawner = Spawner(FIRST_DESCENT.id, 0.0, [], cap=10, templates=[crab_template()])
    game = game_with(spawner, Rules(enemy_return_every=2, return_loot_factor=0.5))
    for _ in range(3):
        game.perform(Wait())
    restored = Game.from_state(GameState.model_validate_json(game.to_state().model_dump_json()))
    assert restored.rules == game.rules
    for _ in range(8):
        assert restored.perform(Wait()) == game.perform(Wait())
    assert restored.to_state() == game.to_state()
    assert queue(restored) == queue(game) and len(queue(game)) == 5


def test_new_worlds_give_every_wild_location_templates():
    world = generate_world(7, CONTENT.world("world.standard"), CONTENT.roomsets, CONTENT.regions)
    _, spawners = generate_enemies(7, world, CONTENT)
    assert spawners
    for spawner in spawners:
        location = world.location(spawner.location)
        roomset = next(r for r in CONTENT.roomsets.values() if r.name == location.kind)
        assert spawner.cap == roomset.enemies.wanderers == len(spawner.queue)
        assert sorted(t.enemy_id for t in spawner.templates) == sorted(roomset.enemies.pool)
        for template in spawner.templates:
            kind = CONTENT.enemies[template.enemy_id]
            assert template.loot_chance == kind.loot.chance
            assert all(item.gear_id in kind.loot.gear for item in template.loot)

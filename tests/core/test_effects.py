"""Gear effects (v0.13.0): what set bonuses and gear do besides stats."""

import pytest

from tidewrack.core.combat.rules import STANDARD, Rules
from tidewrack.core.economy import crafting
from tidewrack.core.engine.components import Bounty, Enemy, Health, MaterialStack, Spawner
from tidewrack.core.engine.events import CombatStarted
from tidewrack.core.engine.game import Attack, Game, Move, Wait
from tidewrack.core.gear import effects
from tidewrack.core.gear.item import GearSet, Item, SetBonus
from tidewrack.core.procgen.material_gen import make_material
from tidewrack.core.world.overworld import Overworld
from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()
FIRST_DESCENT = CONTENT.dungeon("dungeon.first_descent")
WORLD = Overworld(FIRST_DESCENT.id, {FIRST_DESCENT.id: FIRST_DESCENT})
CAVE = FIRST_DESCENT.id
DOWN = "Descend the cliff stair"  # wrack_cove (the gate) -> cliff_stair


def charm(*found: str) -> Item:
    return Item(gear_id="gear.test", name="Test Charm", slot="trinket", effects=list(found))


def foe(atk=3, defence=2, hp=8) -> Enemy:
    return Enemy(
        "enemy.shore_crab", "Shore Crab", "beast", "A crab.", {"atk": atk, "def": defence, "hp": hp}
    )


def game_with(*found: str, enemy=None, bounty=False, player=None, rules=STANDARD, spawners=()):
    enemies, bounties = [], []
    if enemy is not None:
        if bounty:
            bounties = [(CAVE, "cliff_stair", enemy, Bounty("quest.x", "Shore Crab", enemy.stats))]
        else:
            enemies = [(CAVE, "cliff_stair", enemy)]
    return Game(
        1,
        WORLD,
        player or {"atk": 4, "def": 2, "hp": 40},
        kit=[charm(*found)] if found else [],
        enemies=enemies,
        bounties=bounties,
        spawners=spawners,
        rules=rules,
    )


def test_effects_parse_add_up_and_read_well():
    assert effects.parse("lifesteal:2") == ("lifesteal", 2)
    assert effects.parse("glows faintly") is None  # plain text from older items
    assert effects.total(["bane:3", "lifesteal:1", "bane:4"]) == {"lifesteal": 1, "bane": 7}
    assert effects.describe("salvage:15") == (
        "15% chance of an extra material when you loot or gather"
    )
    assert effects.problem("lifesteal:2") is None
    assert "unknown effect kind" in effects.problem("fireball:3")
    assert "kind:value" in effects.problem("lifesteal")


def test_set_bonuses_bring_their_effects_into_the_stat_sheet():
    reiver = GearSet("gearset.r", "Reiver", [SetBonus(2, {}, ["bane:4"])])
    pieces = [Item(gear_id=f"gear.{s}", name=s, slot=s, gear_set=reiver) for s in ("head", "body")]
    game = Game(1, WORLD, {"atk": 4, "def": 2, "hp": 20}, kit=pieces)
    assert game.sheet().effects == {"bane": 4}


def test_lifesteal_heals_with_every_blow():
    game = game_with("lifesteal:3", enemy=foe(atk=1, defence=0, hp=100))
    game.world.get(game.player, Health).damage = 10
    game.perform(Move(DOWN))
    game.perform(Attack())  # +3 back for your blow, then the crab's blow (1)
    assert game.world.get(game.player, Health).damage == 10 - 3 + 1


def test_bane_hits_bounties_wardens_and_kings_harder():
    tough = foe(atk=1, defence=500, hp=20)
    plain = game_with("bane:600", enemy=tough)
    plain.perform(Move(DOWN))
    plain.perform(Attack())
    assert plain.view().combat is not None  # an ordinary foe: no bane, a 1-point blow
    hunted = game_with("bane:600", enemy=foe(atk=1, defence=500, hp=20), bounty=True)
    hunted.perform(Move(DOWN))
    hunted.perform(Attack())
    assert hunted.view().combat is None  # a bounty: bane carries the blow


def test_exposed_adds_to_every_blow_you_take():
    game = game_with("exposed:5", enemy=foe(atk=0, defence=0, hp=1000))
    game.perform(Move(DOWN))
    game.perform(Attack())
    assert game.world.get(game.player, Health).damage == 1 + 5  # the minimum blow, +5


def test_stealth_keeps_wanderers_off_you():
    crabs = [foe(), foe(), foe()]
    seen = game_with(spawners=[Spawner(CAVE, 1.0, list(crabs))])
    assert any(isinstance(e, CombatStarted) for e in seen.perform(Move(DOWN)).events)
    hidden = game_with("stealth:100", spawners=[Spawner(CAVE, 1.0, list(crabs))])
    assert not any(isinstance(e, CombatStarted) for e in hidden.perform(Move(DOWN)).events)


def test_sure_footed_flees_more_often_but_never_always():
    from tidewrack.core.engine.game import Flee

    escapes = 0
    for seed in range(40):
        game = game_with("sure_footed:100", enemy=foe(hp=1000), rules=Rules(flee_chance=0.0))
        game.combat_rng = game.rng.derive(f"flee.{seed}")
        game.perform(Move(DOWN))
        game.perform(Flee())
        escapes += game.view().combat is None
    assert 30 <= escapes < 40  # capped at 95%


def test_salvage_finds_an_extra_material():
    game = game_with("salvage:100")
    hide = make_material(CONTENT.materials["material.hide"])
    crafting.add(game, MaterialStack(hide, 2), "gathered")
    assert crafting.held(game)["material.hide"].count == 3


def test_second_wind_adds_to_each_recovery():
    game = game_with("second_wind:4", player={"atk": 4, "def": 2, "hp": 20})
    game.world.get(game.player, Health).damage = 10
    for _ in range(STANDARD.regen_every):
        game.perform(Wait())
    assert game.world.get(game.player, Health).damage == 10 - 1 - 4


def test_content_effects_are_all_known():
    for schema in [*CONTENT.gear.values(), *CONTENT.affixes.values()]:
        assert all(effects.problem(e) is None for e in schema.effects), schema.id
    for gear_set in CONTENT.gearsets.values():
        for bonus in gear_set.bonuses:
            assert all(effects.problem(e) is None for e in bonus.effects), gear_set.id


@pytest.mark.parametrize("bad", ["lifesteal", "fireball:2", "bane:0", "bane:x"])
def test_content_with_a_bad_effect_is_refused(bad):
    from pydantic import ValidationError

    from tidewrack.core.data.schemas import SetBonusSchema

    with pytest.raises(ValidationError):
        SetBonusSchema(pieces=2, effects=[bad])

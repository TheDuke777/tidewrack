"""Enchanting at a town's Enchanter (v0.13.0)."""

from tidewrack.core.economy import crafting
from tidewrack.core.economy.enchanting import fee
from tidewrack.core.engine.components import (
    Equipped,
    MaterialStack,
    Position,
    Shop,
    Wallet,
)
from tidewrack.core.engine.events import ActionRejected, ItemEnchanted
from tidewrack.core.engine.game import Enchant
from tidewrack.core.gear.item import Item
from tidewrack.core.procgen.material_gen import make_material
from tidewrack.services.content import load_bundled_content
from tidewrack.services.session import GameSession
from tidewrack.services.storage import FileSaveStore

CONTENT = load_bundled_content()


def at_the_enchanter(tmp_path, gold=100, **materials):
    session = GameSession.generate(FileSaveStore(tmp_path), CONTENT, "world.standard", "W", 5)
    game = session.game
    here = game.world.get(game.player, Position)
    [(_, (shop, at))] = [
        (e, c)
        for e, c in game.world.query(Shop, Position)
        if c[0].enchants and c[1].location == here.location
    ]
    here.room = at.room
    for name, count in materials.items():
        stack = MaterialStack(make_material(CONTENT.materials[f"material.{name}"]), count)
        crafting.add(game, stack, "bought")
    game.world.get(game.player, Wallet).gold = gold
    return game, shop


def worn(game, slot):
    return next(e for e, (_, eq) in game.world.query(Item, Equipped) if eq.slot == slot)


def test_every_town_has_an_enchanter_up_to_its_regions_tier(tmp_path):
    game, shop = at_the_enchanter(tmp_path)
    assert shop.name == "Tide-Priest"
    assert {o.tier for o in shop.enchants} == {1}  # the coast: tier I only
    tiers = {
        s.name: max(o.tier for o in s.enchants) for _, (s,) in game.world.query(Shop) if s.enchants
    }
    assert tiers == {"Tide-Priest": 1, "Bog-Wife": 2, "Stone-Reader": 3, "Rune-Carver": 4}


def test_enchanting_puts_the_effect_on_the_item_for_materials_and_a_fee(tmp_path):
    game, shop = at_the_enchanter(tmp_path, iron_ore=2, wisp_essence=1)
    weapon = worn(game, "main_hand")
    result = game.perform(Enchant(weapon, "enchant.baneful", 1))
    assert any(isinstance(e, ItemEnchanted) for e in result.events)
    item = game.world.get(weapon, Item)
    assert item.display_name.startswith("Baneful ")
    assert game.sheet().effects == {"bane": 1}
    assert "material.iron_ore" not in crafting.held(game)
    assert game.world.get(game.player, Wallet).gold == 100 - fee(shop.enchants[0])


def test_a_new_enchantment_replaces_the_one_in_its_slot(tmp_path):
    game, _ = at_the_enchanter(tmp_path, iron_ore=4, wisp_essence=3, eel_skin=2)
    weapon = worn(game, "main_hand")
    game.perform(Enchant(weapon, "enchant.baneful", 1))
    game.perform(Enchant(weapon, "enchant.leech", 1))  # a suffix: both stay
    assert game.sheet().effects == {"lifesteal": 1, "bane": 1}
    game.perform(Enchant(weapon, "enchant.baneful", 1))  # prefix again: replaces
    assert [a.name for a in game.world.get(weapon, Item).affixes] == ["of the Leech", "Baneful"]


def test_enchanting_refuses_the_wrong_slot_a_higher_tier_or_too_few_materials(tmp_path):
    game, _ = at_the_enchanter(tmp_path, iron_ore=1)
    weapon, body = worn(game, "main_hand"), worn(game, "body")

    def refused(command) -> str:
        return next(e.reason for e in game.perform(command).events if isinstance(e, ActionRejected))

    assert "can't go on" in refused(Enchant(body, "enchant.baneful", 1))
    assert "can't do that" in refused(Enchant(weapon, "enchant.baneful", 2))
    assert "You need" in refused(Enchant(weapon, "enchant.baneful", 1))
    assert not game.world.get(weapon, Item).affixes


def test_every_slot_can_take_an_enchantment():
    from tidewrack.core.gear.item import SLOTS

    covered = {slot for e in CONTENT.enchantments.values() for slot in e.slots}
    assert covered == set(SLOTS)

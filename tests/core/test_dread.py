"""Dread bounties, legendary materials and enchanted drops (v0.13.0)."""

from tidewrack.core.economy import crafting
from tidewrack.core.engine.components import (
    Bounty,
    Enemy,
    Position,
    Quest,
    Sealed,
)
from tidewrack.core.engine.events import (
    DreadPosted,
    Milestone,
    RegionOpened,
    RoomEntered,
    TideTurned,
)
from tidewrack.core.engine.game import IMPORTANT
from tidewrack.core.quests import quests as questing
from tidewrack.services.content import load_bundled_content
from tidewrack.services.session import GameSession
from tidewrack.services.storage import FileSaveStore

CONTENT = load_bundled_content()


def world(tmp_path, seed=13):
    return GameSession.generate(FileSaveStore(tmp_path), CONTENT, "world.standard", "W", seed).game


def dread(game):
    return [q for _, (q,) in game.world.query(Quest) if q.source == "dread"]


def emit(game, event):
    game.bus.emit(event)
    game.bus.flush()


def test_each_region_has_sealed_dread_bounties_on_its_border_towns_board(tmp_path):
    game = world(tmp_path)
    quests = dread(game)
    assert len(quests) == 2 * len(game.overworld.regions)
    for quest in quests:
        assert quest.state == "sealed" and quest.kind == "bounty"
        board = game.overworld.location(quest.board)
        assert board.town
        region = game.overworld.regions[board.region]
        first_town = next(
            loc for loc in game.overworld.locations.values() if loc.region == region.id and loc.town
        )
        assert board.id == first_town.id
        legendary = CONTENT.regions[region.id].legendary
        assert [m.material.material_id for m in quest.materials] == [legendary]
        assert any(a.id.startswith("enchant.") for a in quest.reward.affixes)  # enchanted
    sealed = [e for e, (b,) in game.world.query(Bounty) if game.world.has(e, Sealed)]
    assert len(sealed) == len(quests)


def test_a_sealed_dread_bounty_fights_no_one(tmp_path):
    from tidewrack.core.engine.components import Fighting

    game = world(tmp_path)
    entity = next(e for e, _ in game.world.query(Sealed))
    at = game.world.get(entity, Position)
    here = game.world.get(game.player, Position)
    here.location, here.room = at.location, at.room
    emit(game, RoomEntered(game.player, at.location, at.room, None, False))
    assert not game.world.has(game.player, Fighting)


def test_opening_a_region_posts_the_dread_bounties_of_the_one_before(tmp_path):
    game = world(tmp_path)
    regions = sorted(game.overworld.regions.values(), key=lambda r: r.tier)
    coast, fens = regions[0], regions[1]
    seen = []
    game.bus.subscribe(DreadPosted, seen.append)
    milestones = []
    game.bus.subscribe(Milestone, milestones.append)
    emit(game, RegionOpened(fens.id, fens.name))
    posted = [q for q in dread(game) if q.state == "posted"]
    assert {game.overworld.location(q.board).region for q in posted} == {coast.id}
    assert len(posted) == 2 and len(seen) == 1 and seen[0].region == coast.name
    assert milestones and milestones[-1].title == "Dread bounties"
    assert any(line.startswith(IMPORTANT) and "dread bount" in line for line in game.log[-3:])
    ids = {q.quest_id for q in posted}
    for entity, (bounty,) in game.world.query(Bounty):
        if bounty.quest_id in ids:
            assert not game.world.has(entity, Sealed)  # awake now


def test_the_kings_fall_posts_the_deepest_regions_dread_bounties(tmp_path):
    game = world(tmp_path)
    deepest = max(game.overworld.regions.values(), key=lambda r: r.tier)
    emit(game, TideTurned("Drowned King", deepest.name))
    posted = [q for q in dread(game) if q.state == "posted"]
    assert {game.overworld.location(q.board).region for q in posted} == {deepest.id}


def test_turning_in_a_dread_bounty_pays_its_legendary_material(tmp_path):
    game = world(tmp_path)
    quest = dread(game)[0]
    quest.state = "ready"
    here = game.world.get(game.player, Position)
    board = game.overworld.location(quest.board)
    here.location, here.room = board.id, board.start
    questing.turn_in(game, quest.quest_id)
    game.bus.flush()
    material = quest.materials[0]
    held = crafting.held(game)[material.material.material_id]
    assert held.count == material.count
    assert quest.state == "done"


def test_some_foes_drop_enchanted_gear(tmp_path):
    game = world(tmp_path)
    loot = [i for _, (e,) in game.world.query(Enemy) for i in e.loot]
    enchanted = [i for i in loot if any(a.id.startswith("enchant.") for a in i.affixes)]
    assert loot and enchanted  # a few, at their region's tier
    assert len(enchanted) < len(loot)

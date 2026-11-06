import gzip
import itertools
import json
from pathlib import Path

import pytest

from tidewrack.core.combat.rules import STANDARD
from tidewrack.core.engine.game import Attack, Defend, Look, Move, Wait
from tidewrack.core.world.overworld import Overworld
from tidewrack.services.content import load_bundled_content
from tidewrack.services.session import GameSession, next_world_name
from tidewrack.services.storage import FileSaveStore, SaveError
from tidewrack.services.storage.migrations import NewerSaveError, migrate
from tidewrack.services.storage.store import BACKUPS_KEPT

CONTENT = load_bundled_content()
FIRST_DESCENT = CONTENT.dungeon("dungeon.first_descent")
WORLD = Overworld(FIRST_DESCENT.id, {FIRST_DESCENT.id: FIRST_DESCENT})
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "saves"


def fake_clock():
    counter = itertools.count()
    return lambda: f"2026-11-03T12:{next(counter):02d}:00+00:00"


def new_session(store, name="World 1", seed=7, clock=None):
    return GameSession.new(store, CONTENT, WORLD, name, seed, clock=clock or fake_clock())


# --- session + autosave ------------------------------------------------------------


def test_new_world_is_saved_immediately(tmp_path):
    store = FileSaveStore(tmp_path)
    session = new_session(store)
    [listing] = store.list_slots()
    assert listing.meta.slot_id == session.meta.slot_id
    assert listing.meta.revision == 1
    assert listing.meta.summary.room == "Wrack Cove"


def test_every_action_autosaves_and_reopens_identically(tmp_path):
    store = FileSaveStore(tmp_path)
    session = new_session(store)
    for command in [Move("Descend the cliff stair"), Wait(), Look()]:
        session.perform(command)
    assert session.meta.revision == 4

    reopened = GameSession.open(store, session.meta.slot_id, CONTENT)
    assert reopened.game.view() == session.game.view()
    assert reopened.meta == session.meta
    for command in [Move("Keep descending"), Wait(), Wait()]:
        assert reopened.perform(command) == session.perform(command)


def test_listing_is_newest_first(tmp_path):
    store = FileSaveStore(tmp_path)
    clock = fake_clock()
    first = new_session(store, "World 1", clock=clock)
    second = new_session(store, "World 2", clock=clock)
    assert [s.meta.name for s in store.list_slots()] == ["World 2", "World 1"]
    first.perform(Wait())
    assert [s.meta.slot_id for s in store.list_slots()] == [first.meta.slot_id, second.meta.slot_id]


def test_delete_removes_slot_and_backups(tmp_path):
    store = FileSaveStore(tmp_path)
    session = new_session(store)
    session.perform(Wait())
    store.delete(session.meta.slot_id)
    assert store.list_slots() == []
    assert not any(tmp_path.rglob("*.gz"))


def test_next_world_name():
    assert next_world_name([]) == "World 1"
    assert next_world_name(["World 1", "World 3", "Custom"]) == "World 4"


# --- file safety -------------------------------------------------------------------


def test_writes_are_atomic_and_deterministic(tmp_path):
    store = FileSaveStore(tmp_path)
    session = new_session(store)
    session.perform(Wait())
    assert not list(tmp_path.glob("*.tmp"))
    path = tmp_path / f"slot_{session.meta.slot_id}.json.gz"
    first = path.read_bytes()
    store.save(session.meta.slot_id, store.load(session.meta.slot_id).envelope)
    assert path.read_bytes() == first  # gzip mtime=0 + sorted keys


def test_backups_are_capped(tmp_path):
    store = FileSaveStore(tmp_path)
    session = new_session(store)
    for _ in range(10):
        session.perform(Wait())
    assert len(list((tmp_path / "backups").glob("*.gz"))) == BACKUPS_KEPT


def test_corrupt_save_falls_back_to_latest_backup(tmp_path):
    store = FileSaveStore(tmp_path)
    session = new_session(store)
    session.perform(Move("Descend the cliff stair"))
    session.perform(Wait())  # revision 3; backups hold revisions 1 and 2
    (tmp_path / f"slot_{session.meta.slot_id}.json.gz").write_bytes(b"\x1f\x8bgarbage")

    [listing] = store.list_slots()
    assert listing.from_backup and listing.meta.revision == 2
    reopened = GameSession.open(store, session.meta.slot_id, CONTENT)
    assert reopened.from_backup
    assert reopened.game.view().room == "The Cliff Stair"


def test_unreadable_everywhere_is_an_error(tmp_path):
    store = FileSaveStore(tmp_path)
    session = new_session(store)
    (tmp_path / f"slot_{session.meta.slot_id}.json.gz").write_bytes(b"nope")
    assert store.list_slots() == []
    with pytest.raises(SaveError, match="no usable backup"):
        store.load(session.meta.slot_id)


def test_damaged_contents_raise_save_error(tmp_path):
    store = FileSaveStore(tmp_path)
    session = new_session(store)
    envelope = store.load(session.meta.slot_id).envelope
    envelope["game"]["turn"] = "lots"
    store.save(session.meta.slot_id, envelope)
    with pytest.raises(SaveError, match="damaged"):
        GameSession.open(store, session.meta.slot_id, CONTENT)


def test_rejects_unsafe_slot_ids(tmp_path):
    with pytest.raises(ValueError):
        FileSaveStore(tmp_path).load("../../etc/passwd")


# --- versions and migrations -------------------------------------------------------


def test_newer_saves_are_refused_with_a_clear_message():
    with pytest.raises(NewerSaveError, match="newer version of Tidewrack"):
        migrate({"schema_version": 999})


def _install(tmp_path, envelope) -> str:
    slot_id = envelope["meta"]["slot_id"]
    (tmp_path / f"slot_{slot_id}.json.gz").write_bytes(gzip.compress(json.dumps(envelope).encode()))
    return slot_id


@pytest.mark.parametrize("fixture", sorted(FIXTURES.glob("*.json")), ids=lambda p: p.name)
def test_every_released_save_format_still_opens(tmp_path, fixture):
    """Fixture saves from each released schema must open, list and keep playing (§9)."""
    store = FileSaveStore(tmp_path)
    envelope = json.loads(fixture.read_text(encoding="utf-8"))
    slot_id = _install(tmp_path, envelope)
    [listing] = store.list_slots()
    session = GameSession.open(store, slot_id, CONTENT)
    assert listing.meta == session.meta
    session.perform(Defend() if session.game.view().combat else Wait())  # a fight may be on
    assert session.game.turn == envelope["game"]["turn"] + 1


def test_v2_saves_become_a_one_location_world(tmp_path):
    envelope = json.loads((FIXTURES / "v2_generated.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    view = session.game.view()
    assert (view.location, view.kind, view.room) == (
        "The Gullet Caves",
        "Sea Caves",
        "Brackish Grotto",
    )
    assert (view.rooms_visited, view.total_rooms, view.total_locations) == (3, 14, 1)
    assert view.roads == () and view.map is not None
    assert session.game.log == envelope["game"]["log"]


def test_newer_saves_are_still_listed(tmp_path):
    store = FileSaveStore(tmp_path)
    session = new_session(store)
    envelope = store.load(session.meta.slot_id).envelope
    envelope["schema_version"] = 999
    store.save(session.meta.slot_id, envelope)
    assert [s.meta.name for s in store.list_slots()] == ["World 1"]
    with pytest.raises(NewerSaveError):
        GameSession.open(store, session.meta.slot_id, CONTENT)


def test_there_is_a_fixture_for_every_schema_version():
    from tidewrack.core.versions import SCHEMA_VERSION

    versions = {json.loads(p.read_text())["schema_version"] for p in FIXTURES.glob("*.json")}
    assert versions == set(range(1, SCHEMA_VERSION + 1))


def test_v3_saves_get_default_stats_and_no_gear(tmp_path):
    envelope = json.loads((FIXTURES / "v3_world.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    assert session.game.view().stats == {"atk": 2, "def": 1, "hp": 20}
    inventory = session.game.inventory()
    assert inventory.pack == () and all(s.item is None for s in inventory.slots)


def test_v4_gear_fixture_keeps_its_gear(tmp_path):
    envelope = json.loads((FIXTURES / "v4_gear.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    equipped = {s.slot: s.item.name for s in session.game.inventory().slots if s.item}
    assert equipped == {
        "main_hand": "Driftwood Club",
        "off_hand": "Salted Buckler",
        "body": "Patched Coat",
    }
    assert session.game.view().stats == {"atk": 4, "def": 6, "hp": 20}  # buckler rolled +1


def test_v4_saves_get_full_health_an_empty_codex_and_peace(tmp_path):
    envelope = json.loads((FIXTURES / "v4_gear.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    view = session.game.view()
    assert view.hp == view.max_hp and view.combat is None
    assert session.game.foes().foes == ()
    assert session.game.rules == STANDARD


def test_v5_fixture_resumes_mid_fight(tmp_path):
    envelope = json.loads((FIXTURES / "v5_combat.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    view = session.game.view()
    assert view.combat is not None and view.combat.name == "Conger Eel"
    assert [f.name for f in session.game.foes().foes] == ["Conger Eel"]
    assert session.perform(Attack()).took_turn


def test_v5_saves_load_with_no_quests(tmp_path):
    envelope = json.loads((FIXTURES / "v5_combat.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    log = session.game.quests()
    assert log.active == log.ready == log.done == ()


def test_v6_fixture_keeps_its_quests(tmp_path):
    envelope = json.loads((FIXTURES / "v6_quests.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    log = session.game.quests()
    assert sorted(q.kind for q in log.active) == ["Bounty", "Cull", "Recover"]
    assert session.game.view().board == ()  # all taken


def test_v6_saves_get_returning_wanderers_from_their_own_snapshots(tmp_path):
    from tidewrack.core.engine.components import Spawner

    envelope = json.loads((FIXTURES / "v6_quests.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    spawners = [s for _, (s,) in session.game.world.query(Spawner)]
    assert spawners and all(s.cap == 6 for s in spawners)
    assert all(s.templates for s in spawners)
    for spawner in spawners:
        assert {t.enemy_id for t in spawner.templates} >= {e.enemy_id for e in spawner.queue}
    assert session.game.rules.enemy_return_every == 30


def test_v7_fixture_resumes_with_its_returned_wanderer(tmp_path):
    from tidewrack.core.engine.components import Spawner

    envelope = json.loads((FIXTURES / "v7_returns.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    spawners = [s for _, (s,) in session.game.world.query(Spawner)]
    assert all(len(s.queue) == s.cap for s in spawners)


def test_v7_saves_get_gold_and_town_shops_from_their_own_snapshots(tmp_path):
    from tidewrack.core.economy import shops
    from tidewrack.core.engine.components import Enemy, Quest, Shop, Spawner

    envelope = json.loads((FIXTURES / "v7_returns.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    game = session.game
    assert shops.gold(game) == 10
    towns = [loc for loc in game.overworld.locations.values() if loc.kind == "Town"]
    found = [s for _, (s,) in game.world.query(Shop)]
    assert sorted(s.name for s in found) == sorted(["Market", "Smithy", "Tavern"] * len(towns))
    smithy = next(s for s in found if s.buys_gear)
    assert smithy.wares and all(not i.affixes and not i.roll for i in smithy.wares)
    for _, (spawner,) in game.world.query(Spawner):
        assert all(isinstance(e.gold, int) for e in spawner.queue)
        assert all(len(t.gold) == 2 for t in spawner.templates)
    assert all(isinstance(e.gold, int) for _, (e,) in game.world.query(Enemy))
    assert all(q.gold > 0 for _, (q,) in game.world.query(Quest))
    # The player can shop straight away: the town's shops are at its gate or in its rooms.
    assert game.economy.inn_price == 4


def test_v8_fixture_keeps_its_gold_shops_and_purchases(tmp_path):
    from tidewrack.core.economy import shops

    envelope = json.loads((FIXTURES / "v8_economy.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    assert shops.gold(session.game) == 3
    assert "You sell the Miner's Helm to the Smithy for 3 gold." in session.game.log


def test_v8_saves_get_a_satchel_recipes_markets_and_upgrades(tmp_path):
    from tidewrack.core.economy import crafting
    from tidewrack.core.engine.components import Enemy, Item, Quest, Shop, Spawner

    envelope = json.loads((FIXTURES / "v8_economy.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    game = session.game
    assert crafting.held(game) == {}
    assert sorted(crafting.known(game)) == sorted(
        r for r, schema in CONTENT.recipes.items() if schema.known
    )
    towns = [loc for loc in game.overworld.locations.values() if loc.kind == "Town"]
    found = [s for _, (s,) in game.world.query(Shop)]
    assert sum(s.name == "Market" for s in found) == len(towns)
    market = next(s for s in found if s.name == "Market")
    assert market.materials and market.buys_materials
    smithy = next(s for s in found if s.name == "Smithy")
    assert smithy.crafts and "gear.cutlass" in smithy.upgrades
    # Only what's stocked past a shop's cap counts as sold gear; this shelf was full
    # but not over (the Miner's Helm sold back in v8 stays as ordinary stock).
    assert smithy.buyback == []
    assert all(not e.materials for _, (e,) in game.world.query(Enemy))
    assert all(q.recipe is None for _, (q,) in game.world.query(Quest))
    templates = [t for _, (s,) in game.world.query(Spawner) for t in s.templates]
    assert any(t.materials for t in templates)
    # Gear v9 made upgradable is upgradable in old worlds too.
    club = next(i for _, (i,) in game.world.query(Item) if i.gear_id == "gear.driftwood_club")
    assert club.max_upgrade == 2 and club.upgrade_step == {"atk": 1}


def test_v9_fixture_keeps_its_materials_crafts_and_upgrades(tmp_path):
    from tidewrack.core.economy import crafting

    envelope = json.loads((FIXTURES / "v9_crafting.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    game = session.game
    assert {k: v.count for k, v in crafting.held(game).items()} == {
        "material.iron_ore": 1,
        "material.timber": 1,
    }
    names = [i.name for i in game.inventory().pack] + [
        s.item.name for s in game.inventory().slots if s.item
    ]
    assert "Cutlass" in names and "Driftwood Club +1" in names
    assert "The smith makes you a Cutlass for 17 gold." in game.log


def test_an_overfull_v8_smithy_keeps_only_the_newest_sold_gear(tmp_path):
    from tidewrack.core.engine.components import Shop, Stocked

    envelope = json.loads((FIXTURES / "v8_economy.json").read_text(encoding="utf-8"))
    game = envelope["game"]
    shop_id = next(e["id"] for e in game["entities"] if "Shop" in e["components"])
    item = next(
        e["components"]["Item"]
        for e in game["entities"]
        if e["components"].get("Stocked", {}).get("shop") == shop_id
    )
    extra = list(range(game["next_entity_id"], game["next_entity_id"] + 27))
    for entity in extra:  # 27 more on a shelf that holds 4: like selling a lot of loot
        game["entities"].append(
            {"id": entity, "components": {"Item": dict(item), "Stocked": {"shop": shop_id}}}
        )
    game["next_entity_id"] = extra[-1] + 1
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    world = session.game.world
    shop = world.get(shop_id, Shop)
    on_shelf = [e for e, (s,) in world.query(Stocked) if s.shop == shop_id]
    assert shop.buyback == extra[-6:]
    assert len(on_shelf) == shop.cap + 6


def test_v9_saves_get_kitchens_staples_and_a_pantry(tmp_path):
    from tidewrack.core.economy import cooking, crafting
    from tidewrack.core.engine.components import Shop

    envelope = json.loads((FIXTURES / "v9_crafting.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    game = session.game
    assert cooking.held(game) == {} and cooking.fed(game) is None
    assert all(not s.material.ingredient for s in crafting.held(game).values())
    found = [s for _, (s,) in game.world.query(Shop)]
    taverns = [s for s in found if s.inn]
    assert taverns and all(s.cooks and len(s.meals) == 7 for s in taverns)
    assert all(not s.cooks for s in found if not s.inn)
    market = next(s for s in found if s.buys_materials)
    staples = [m.name for m in market.materials if m.ingredient]
    assert staples == ["Salt", "Ship's Biscuit"]


def test_v10_fixture_keeps_its_meals_and_buff(tmp_path):
    from tidewrack.core.economy import cooking

    envelope = json.loads((FIXTURES / "v10_cooking.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    game = session.game
    assert [(m.name, m.count) for m in game.inventory().meals] == [("Kelp Broth", 1)]
    fed = cooking.fed(game)
    assert (
        fed is not None and fed.meal.name == "Mussel Stew" and fed.turns_left == 57
    )  # 3 waits after eating


def test_v10_saves_regrow_their_wild_places(tmp_path):
    from tidewrack.core.engine.components import Grower

    envelope = json.loads((FIXTURES / "v10_cooking.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    game = session.game
    growers = [g for _, (g,) in game.world.query(Grower)]
    wild = [loc for loc in game.overworld.locations.values() if loc.kind != "Town"]
    assert sorted(g.location for g in growers) == sorted(loc.id for loc in wild)
    caves = next(g for g in growers if game.overworld.location(g.location).kind == "Sea Caves")
    assert {e.material.name for e in caves.materials} >= {"Kelp", "Mussels"}


def test_v11_fixture_keeps_its_regrowth(tmp_path):
    from tidewrack.core.engine.components import Grower

    envelope = json.loads((FIXTURES / "v11_regrowth.json").read_text(encoding="utf-8"))
    session = GameSession.open(FileSaveStore(tmp_path), _install(tmp_path, envelope), CONTENT)
    assert len(list(session.game.world.query(Grower))) == 4
    assert session.game.turn == 44


def test_renaming_a_world_saves_a_new_revision_but_not_a_new_play_time(tmp_path):
    store = FileSaveStore(tmp_path)
    session = new_session(store, clock=fake_clock())
    before = session.meta
    session.rename("  The   Drowned  Coast ")
    reopened = GameSession.open(store, before.slot_id, CONTENT)
    assert reopened.meta.name == "The Drowned Coast"  # spaces tidied
    assert reopened.meta.revision == before.revision + 1
    assert reopened.meta.updated_at == before.updated_at  # keeps its place in the list
    session.rename("x" * 100)
    assert len(GameSession.open(store, before.slot_id, CONTENT).meta.name) == 40
    with pytest.raises(ValueError):
        session.rename("   ")

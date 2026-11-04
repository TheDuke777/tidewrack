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

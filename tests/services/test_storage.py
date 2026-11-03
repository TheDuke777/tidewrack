import gzip
import itertools
import json
from pathlib import Path

import pytest

from tidewrack.core.engine.game import Look, Move, Wait
from tidewrack.services.content import load_bundled_content
from tidewrack.services.session import GameSession, next_world_name
from tidewrack.services.storage import FileSaveStore, SaveError
from tidewrack.services.storage.migrations import NewerSaveError, migrate
from tidewrack.services.storage.store import BACKUPS_KEPT

CONTENT = load_bundled_content()
DUNGEON = "dungeon.first_descent"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "saves"


def fake_clock():
    counter = itertools.count()
    return lambda: f"2026-11-03T12:{next(counter):02d}:00+00:00"


def new_session(store, name="World 1", seed=7, clock=None):
    return GameSession.new(
        store, CONTENT, CONTENT.dungeon(DUNGEON), name, seed, clock=clock or fake_clock()
    )


# --- session + autosave ------------------------------------------------------------


def test_new_world_is_saved_immediately(tmp_path):
    store = FileSaveStore(tmp_path)
    session = new_session(store)
    [listing] = store.list_slots()
    assert listing.meta.slot_id == session.meta.slot_id
    assert listing.meta.revision == 1
    assert listing.meta.summary.location == "Wrack Cove"


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
    assert reopened.game.view().location == "The Cliff Stair"


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


@pytest.mark.parametrize("fixture", sorted(FIXTURES.glob("*.json")), ids=lambda p: p.name)
def test_every_released_save_format_still_opens(tmp_path, fixture):
    """Fixture saves from each released schema must open and keep playing (§9)."""
    store = FileSaveStore(tmp_path)
    envelope = json.loads(fixture.read_text(encoding="utf-8"))
    slot_id = envelope["meta"]["slot_id"]
    (tmp_path / f"slot_{slot_id}.json.gz").write_bytes(gzip.compress(json.dumps(envelope).encode()))
    session = GameSession.open(store, slot_id, CONTENT)
    session.perform(Wait())
    assert session.game.turn == envelope["game"]["turn"] + 1


def test_there_is_a_fixture_for_every_schema_version():
    from tidewrack.core.versions import SCHEMA_VERSION

    versions = {json.loads(p.read_text())["schema_version"] for p in FIXTURES.glob("*.json")}
    assert versions == set(range(1, SCHEMA_VERSION + 1))

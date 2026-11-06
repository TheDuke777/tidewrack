"""Autosaves split by place (CLAUDE.md §6): fast, and only what changed is written."""

import gzip
import json

import pytest

from tidewrack.core.engine.game import Attack, Defend, Flee, Move, Travel, Wait
from tidewrack.services.content import load_bundled_content
from tidewrack.services.session import GameSession, StateEncoder, _summary
from tidewrack.services.storage import FileSaveStore

CONTENT = load_bundled_content()


def generated(store, seed=7):
    return GameSession.generate(store, CONTENT, "world.standard", "World 1", seed)


def play(session, turns=40):
    """Wander: move, travel when at a gate, fight whatever turns up."""
    for n in range(turns):
        view = session.game.view()
        if view.combat:
            session.perform(Attack() if n % 3 else Defend())
        elif view.at_gate and view.roads and n % 4 == 0:
            session.perform(Travel(view.roads[n % len(view.roads)].location))
        elif view.exits:
            session.perform(Move(view.exits[n % len(view.exits)].label))
        else:
            session.perform(Wait())


def parts(tmp_path, session):
    return {p.name for p in (tmp_path / f"slot_{session.meta.slot_id}.parts").iterdir()}


def test_the_fast_encoding_is_exactly_the_saved_state(tmp_path):
    session = generated(FileSaveStore(tmp_path))
    encoder = StateEncoder()
    for _ in range(4):
        play(session, 15)
        state, _, commit = encoder.encode(session.game)
        assert state == session.game.to_state().model_dump(mode="json")
        commit()
    view = session.game.view()
    summary = _summary(session.game)
    assert (summary.location, summary.room, summary.turn) == (view.location, view.room, view.turn)
    assert (summary.locations_visited, summary.total_locations) == (
        view.locations_visited,
        view.total_locations,
    )


def test_a_split_save_reopens_identically(tmp_path):
    store = FileSaveStore(tmp_path)
    session = generated(store)
    play(session)
    reopened = GameSession.open(FileSaveStore(tmp_path), session.meta.slot_id, CONTENT)
    assert reopened.game.to_state() == session.game.to_state()
    for command in [Wait(), Wait(), Flee() if session.game.view().combat else Wait()]:
        assert reopened.perform(command) == session.perform(command)


def test_waiting_rewrites_no_place(tmp_path):
    session = generated(FileSaveStore(tmp_path))
    main = tmp_path / f"slot_{session.meta.slot_id}.json.gz"
    before = parts(tmp_path, session)
    assert len(before) > 10  # a world map and a part per place with things in it
    assert len(main.read_bytes()) < 15_000  # the player, quests, codex: not the world

    session.perform(Wait())
    assert parts(tmp_path, session) == before


def test_moving_rewrites_only_the_places_that_changed(tmp_path):
    session = generated(FileSaveStore(tmp_path))
    before = parts(tmp_path, session)
    play(session, 6)
    after = parts(tmp_path, session)
    # Old parts stay while a backup still uses them; new ones are few.
    assert len(after - before) <= 6 * 2


def test_unused_parts_are_cleaned_up_but_backups_keep_theirs(tmp_path):
    store = FileSaveStore(tmp_path)
    session = generated(store)
    play(session, 30)
    folder = tmp_path / f"slot_{session.meta.slot_id}.parts"
    used = set()
    for main in [tmp_path.glob("slot_*.json.gz"), (tmp_path / "backups").glob("*.gz")]:
        for path in main:
            used |= set(json.loads(gzip.decompress(path.read_bytes()))["parts"].values())
    assert {p.name.removesuffix(".json.gz") for p in folder.iterdir()} == used

    store.delete(session.meta.slot_id)
    assert not folder.exists()


def test_a_failed_save_is_written_in_full_next_time(tmp_path):
    class Flaky(FileSaveStore):
        fail = False

        def save(self, slot_id, envelope, changed=None):
            if self.fail:
                raise OSError("disk full")
            super().save(slot_id, envelope, changed)

    store = Flaky(tmp_path)
    session = generated(store)
    store.fail = True
    with pytest.raises(OSError):
        play(session, 3)
    store.fail = False
    session.perform(Wait())
    reopened = GameSession.open(FileSaveStore(tmp_path), session.meta.slot_id, CONTENT)
    assert reopened.game.to_state() == session.game.to_state()

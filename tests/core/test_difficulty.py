"""Difficulty presets (8b): content, rules snapshots, saving, and what they change."""

from dataclasses import fields

import pytest

from tidewrack.core.combat.rules import STANDARD, Rules, scaled
from tidewrack.core.data.loader import ContentError, load_content
from tidewrack.core.data.save import RulesState
from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()


def test_standard_is_the_built_in_rules():
    # Old saves (no difficulty) and Standard worlds must play the same.
    assert CONTENT.difficulties["difficulty.standard"].to_rules() == STANDARD


def test_presets_are_valid_save_snapshots_easiest_first():
    choices = CONTENT.difficulty_choices()
    assert [d.name for d in choices] == ["Easy", "Standard", "Hard"]
    for d in choices:
        RulesState(**d.to_rules().__dict__)  # within every saved field's limits
    easy, standard, hard = (d.to_rules() for d in choices)
    warden = {"atk": 25, "def": 12, "hp": 90}
    assert scaled(warden, easy)["hp"] < scaled(warden, standard)["hp"] < scaled(warden, hard)["hp"]
    assert easy.flee_chance > standard.flee_chance > hard.flee_chance
    assert easy.respawn_hp > standard.respawn_hp > hard.respawn_hp


def test_rules_snapshot_fields_all_saved():
    assert {f.name for f in fields(Rules)} == set(RulesState.model_fields)


def test_enemy_hp_only_changes_hp():
    rules = Rules(enemy_hp=1.5)
    assert scaled({"atk": 10, "def": 4, "hp": 20}, rules) == {"atk": 10, "def": 4, "hp": 30}


def test_a_preset_may_only_set_known_rules():
    files = {
        "difficulties/odd.json": '{"id": "difficulty.odd", "name": "Odd", "description": "x",'
        ' "order": 0, "rules": {"enemy_speed": 2}}'
    }
    with pytest.raises(ContentError, match="unknown rules: enemy_speed"):
        load_content(files)


def test_a_world_keeps_its_difficulty(tmp_path):
    from tidewrack.services.session import GameSession
    from tidewrack.services.storage import FileSaveStore

    store = FileSaveStore(tmp_path / "saves")
    session = GameSession.generate(
        store, CONTENT, "world.standard", "W", 7, difficulty="difficulty.hard"
    )
    assert session.game.rules.difficulty == "Hard"
    assert session.game.rules.enemy_hp == 1.3
    [listing] = store.list_slots()
    assert listing.meta.summary.difficulty == "Hard"
    reopened = GameSession.open(store, session.meta.slot_id, CONTENT)
    assert reopened.game.rules == session.game.rules


def test_codex_shows_foes_as_the_world_scales_them(tmp_path):
    from tidewrack.core.engine.components import Codex, FoeEntry
    from tidewrack.services.session import GameSession
    from tidewrack.services.storage import FileSaveStore

    session = GameSession.generate(
        FileSaveStore(tmp_path / "saves"),
        CONTENT,
        "world.standard",
        "W",
        7,
        difficulty="difficulty.hard",
    )
    game = session.game
    codex = game.world.get(game.player, Codex)
    codex.foes["enemy.x"] = FoeEntry("enemy.x", "X", "beast", "d", {"atk": 5, "def": 1, "hp": 10})
    codex.kills["enemy.x"] = 1
    [foe] = [f for f in game.foes().foes if f.name == "X"]
    assert foe.stats["hp"] == 13

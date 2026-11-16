"""Big packs mustn't make every screen update slow (v0.11.0 lag): cheap keys for
the unread dots match the full views, and one view build looks up your gear once."""

from tidewrack.core.engine.components import Carried, Item
from tidewrack.core.engine.game import Game
from tidewrack.core.procgen.gear_gen import generate_finds
from tidewrack.core.procgen.world_gen import generate_world
from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()
SEED = 20261103


def _game_with_a_big_pack() -> Game:
    world = generate_world(SEED, CONTENT.world("world.standard"), CONTENT.roomsets, CONTENT.regions)
    game = Game(SEED, world, finds=generate_finds(SEED, world, CONTENT))
    for entity, _ in list(game.world.query(Item)):
        if not game.world.has(entity, Carried):
            game.world.add(entity, Carried(game.player))
    return game


def test_cheap_dot_keys_match_the_inventory_view():
    game = _game_with_a_big_pack()
    inventory = game.inventory()
    assert len(inventory.pack) > 20
    assert game.pack_ids() == {item.id for item in inventory.pack}
    assert game.satchel_keys() == (
        {("material", m.id) for m in inventory.materials}
        | {("meal", m.id) for m in inventory.meals}
        | {("recipe", r) for r in inventory.recipes}
    )


def test_one_view_looks_up_your_gear_once(monkeypatch):
    game = _game_with_a_big_pack()
    calls = []
    original = game._equipped
    monkeypatch.setattr(game, "_equipped", lambda: calls.append(1) or original())
    before = game.inventory()
    assert len(before.pack) > 20 and len(calls) <= 2  # not once per item (the sheet adds one)
    assert game._compare_with is None  # and nothing left behind

    calls.clear()
    monkeypatch.setattr(game, "_compare_with", None)
    slow = [game._item_view(i.id, game.world.get(i.id, Item)) for i in before.pack]
    assert [v.comparison for v in slow] == [v.comparison for v in before.pack]  # same answers


def test_cheap_quest_states_match_the_quest_log(tmp_path):
    from tidewrack.core.engine.components import Quest
    from tidewrack.services.session import GameSession
    from tidewrack.services.storage import FileSaveStore

    game = GameSession.generate(FileSaveStore(tmp_path), CONTENT, "world.standard", "W", SEED).game
    quests = [q for _, (q,) in game.world.query(Quest)]
    for quest, state in zip(quests, ("active", "active", "ready", "done"), strict=False):
        quest.state = state
    log = game.quests()
    states = game.quest_states()
    for state, views in (("active", log.active), ("ready", log.ready), ("done", log.done)):
        assert {i for i, s in states.items() if s == state} == {q.id for q in views}
    assert len(log.active) == 2 and len(log.ready) == 1 and len(log.done) == 1


def test_upgrade_and_recipe_lists_only_for_the_shop_asked_for(tmp_path, monkeypatch):
    from tidewrack.services.session import GameSession
    from tidewrack.services.settings import SettingsStore
    from tidewrack.services.storage import FileSaveStore
    from tidewrack.ui.shell import WorldShell

    # Seed 20261103: the start town's Smithy is at the gate, where you begin.
    session = GameSession.generate(FileSaveStore(tmp_path), CONTENT, "world.standard", "W", SEED)
    game = session.game
    smithy = next(s for s in game.view().shops if s.crafts)
    assert smithy.recipes and smithy.upgrades  # the default: every shop's lists
    assert next(s for s in game.view(lists_for=smithy.name).shops if s.crafts).recipes
    lean = next(s for s in game.view(lists_for=False).shops if s.crafts)
    assert lean.crafts and not lean.recipes and not lean.upgrades  # the button still knows

    asked = []
    original = game.view
    monkeypatch.setattr(
        game, "view", lambda lists_for=True: asked.append(lists_for) or original(lists_for)
    )
    shell = WorldShell(
        session,
        SettingsStore(tmp_path / "s.json"),
        on_back=lambda: None,
        confirm=lambda *_: None,
        notify=lambda _: None,
    )
    asked.clear()
    shell.explore.refresh()
    assert asked == [False]  # panel closed: no lists
    shell.explore.open(smithy.name)
    assert asked[-1] == smithy.name  # just the open panel's

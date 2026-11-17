"""Dev-build extras: the Reveal map menu item (dev builds only) and what it does."""

import flet as ft

from tidewrack.core.engine.components import Enemy, Explorer, Fighting, Warden
from tidewrack.services.content import load_bundled_content
from tidewrack.ui import dev

CONTENT = load_bundled_content()


def _session(tmp_path):
    from tidewrack.services.session import GameSession
    from tidewrack.services.storage import FileSaveStore

    return GameSession.generate(
        FileSaveStore(tmp_path / "saves"), CONTENT, "world.standard", "W", 20261103
    )


def _shell(session, tmp_path, toasts=None):
    from tidewrack.services.settings import SettingsStore
    from tidewrack.ui.shell import WorldShell

    return WorldShell(
        session,
        SettingsStore(tmp_path / "s.json"),
        on_back=lambda: None,
        confirm=lambda *_: None,
        notify=(toasts if toasts is not None else []).append,
    )


def _menu_items(shell) -> list[str]:
    def walk(control):
        yield control
        for attr in ("content", "controls"):
            child = getattr(control, attr, None)
            for c in child if isinstance(child, list) else [child]:
                if isinstance(c, ft.Control):
                    yield from walk(c)

    menu = next(c for c in walk(shell.explore.control) if isinstance(c, ft.PopupMenuButton))
    return [item.content for item in menu.items if item.visible is not False]


def test_reveal_map_is_only_in_dev_builds(tmp_path, monkeypatch):
    session = _session(tmp_path)
    assert _menu_items(_shell(session, tmp_path)) == ["Switch world"]
    monkeypatch.setattr(dev, "ENABLED", True)
    assert _menu_items(_shell(session, tmp_path)) == ["Switch world", "Reveal map (dev)"]


def test_reveal_map_shows_everything_opens_every_road_and_is_saved(tmp_path):
    from tidewrack.services.session import GameSession

    session = _session(tmp_path)
    game = session.game
    world = game.overworld
    revision = session.meta.revision
    assert list(game.world.query(Warden))

    assert session.reveal_map()
    explorer = game.world.get(game.player, Explorer)
    assert explorer.locations_visited == set(world.locations)
    assert all(explorer.rooms_visited[i] == set(loc.rooms) for i, loc in world.locations.items())
    assert not list(game.world.query(Warden))
    assert all(r.guard is None for r in game.view().roads)
    view = game.view()
    assert view.locations_visited == len(world.locations)
    assert len(view.world_map.nodes) == len(world.locations) and view.world_map.borders
    assert session.meta.revision == revision + 1

    reopened = GameSession.open(session.store, session.meta.slot_id, CONTENT)
    assert reopened.game.world.get(reopened.game.player, Explorer).locations_visited == set(
        world.locations
    )


def test_reveal_map_waits_until_a_fight_is_over(tmp_path):
    session = _session(tmp_path)
    game = session.game
    enemy = next(e for e, _ in game.world.query(Enemy))
    game.world.add(game.player, Fighting(enemy, retreat_room="a"))
    revision = session.meta.revision
    assert session.reveal_map() is False and session.meta.revision == revision
    assert list(game.world.query(Warden))


def test_hidden_tabs_are_isolated_so_page_updates_skip_them(tmp_path):
    shell = _shell(_session(tmp_path), tmp_path)

    def isolated():
        return [screen.control.is_isolated() for screen, *_ in shell.tabs]

    assert isolated() == [False, True, True, True]  # Explore on screen
    shell.select(2)
    assert isolated() == [True, True, False, True]
    assert [screen.control.visible for screen, *_ in shell.tabs] == [False, False, True, False]
    shell.back()
    assert isolated() == [False, True, True, True]


# --- skip to region (8b) -----------------------------------------------------------


def test_skip_to_region_starts_at_its_town_in_maxed_gear_from_before(tmp_path):
    from tidewrack.core.engine.components import Equipped, Position, Respawn, Wallet
    from tidewrack.core.gear.item import Item
    from tidewrack.core.procgen.head_start import region_gear
    from tidewrack.services.session import GameSession

    session = _session(tmp_path)
    game = session.game
    world = game.overworld
    revision = session.meta.revision
    assert session.skip_to_region(CONTENT, "region.moors")

    position = game.world.get(game.player, Position)
    town = world.location(position.location)
    assert town.town and world.region_of(town.id).id == "region.moors"
    assert position.room == town.start
    assert game.world.get(game.player, Respawn).location == town.id
    # It's the town just over the border from the Fens.
    assert any(world.region_of(n).id == "region.fens" for n in world.neighbours(town.id))

    guarded = {game.overworld.regions[w.region].tier for _, (w,) in game.world.query(Warden)}
    assert guarded == {4}  # only the Highlands' warden is left

    explorer = game.world.get(game.player, Explorer)
    earlier = {i for i, loc in world.locations.items() if world.region_of(i).tier < 3}
    assert earlier <= explorer.locations_visited

    worn = [i for _, (i, _) in game.world.query(Item, Equipped)]
    allowed = set(region_gear(CONTENT, "region.wrack_coast")) | set(
        region_gear(CONTENT, "region.fens")
    )
    assert worn and all(i.upgrade == i.max_upgrade for i in worn)
    assert {i.gear_id for i in worn} <= allowed
    assert "gear.driftwood_club" not in {i.gear_id for i in worn}  # the kit is gone
    assert len(game.pack_ids()) >= 1  # the other weapon setup, to try both
    assert game.world.get(game.player, Wallet).gold >= 300
    assert session.meta.revision == revision + 1

    reopened = GameSession.open(session.store, session.meta.slot_id, CONTENT)
    assert reopened.game.world.get(reopened.game.player, Position).location == town.id


def test_skip_to_region_waits_until_a_fight_is_over(tmp_path):
    session = _session(tmp_path)
    game = session.game
    enemy = next(e for e, _ in game.world.query(Enemy))
    game.world.add(game.player, Fighting(enemy, retreat_room="a"))
    assert session.skip_to_region(CONTENT, "region.fens") is False


def test_best_loadout_prefers_higher_stats_and_keeps_the_other_weapon_setup():
    from tidewrack.core.economy.value_model import stats_value
    from tidewrack.core.gear.stat_pipeline import player_stats
    from tidewrack.core.procgen.head_start import best_loadout, candidates

    base = CONTENT.world("world.standard").player
    items = candidates(CONTENT, ["region.wrack_coast", "region.fens", "region.moors"])
    worn, spare = best_loadout(base, items)
    assert len({i.slot for i in worn}) == len(worn)
    best = stats_value(player_stats(base, worn).total)
    # No single swap from the candidates does better.
    for candidate in items:
        if candidate.two_handed or any(w.two_handed for w in worn):
            continue
        swapped = [candidate if w.slot == candidate.slot else w for w in worn]
        assert stats_value(player_stats(base, swapped).total) <= best
    hands = {i.two_handed for i in worn if i.slot == "main_hand"}
    assert spare and {i.two_handed for i in spare if i.slot == "main_hand"} == {not hands.pop()}

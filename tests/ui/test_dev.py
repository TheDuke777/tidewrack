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
    return [item.content for item in menu.items]


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

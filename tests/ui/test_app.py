import pytest

from tidewrack.services.content import load_bundled_content
from tidewrack.services.session import GameSession
from tidewrack.services.settings import SettingsStore
from tidewrack.services.storage import FileSaveStore
from tidewrack.ui import app as app_module
from tidewrack.ui.app import App

CONTENT = load_bundled_content()


class FakePage:
    def __init__(self):
        self.controls = []
        self.navigation_bar = None

    def update(self):
        pass

    def show_dialog(self, dialog):
        pass


@pytest.fixture
def make_app(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "_open_world", None)  # a cold start
    store = FileSaveStore(tmp_path / "saves")
    settings = SettingsStore(tmp_path / "settings.json")

    def make():
        page = FakePage()
        return page, App(page, store, settings, CONTENT)

    return store, make


def in_world(page) -> bool:
    return page.navigation_bar is not None  # only the world shell has one


def test_cold_start_shows_the_picker(make_app):
    _, make = make_app
    page, app = make()
    app.start()
    assert not in_world(page)


def test_rerun_in_the_same_process_reopens_the_world(make_app):
    """Android rebuilt the window (new system palette); main() runs again."""
    store, make = make_app
    page, app = make()
    app.new_world()
    assert in_world(page)
    page, app = make()
    app.start()
    assert in_world(page)


def test_leaving_the_world_forgets_it(make_app):
    store, make = make_app
    page, app = make()
    app.new_world()
    app.show_picker()
    page, app = make()
    app.start()
    assert not in_world(page)


def test_a_world_that_cant_be_opened_falls_back_to_the_picker(make_app):
    store, make = make_app
    page, app = make()
    session = GameSession.generate(store, CONTENT, "world.standard", "W", 7)
    app.show_game(session)
    store.delete(session.meta.slot_id)
    page, app = make()
    app.start()
    assert not in_world(page)


def walk(control):
    yield control
    for name in ("content", "controls"):
        child = getattr(control, name, None)
        if isinstance(child, list):
            for c in child:
                yield from walk(c)
        elif child is not None and hasattr(child, "__dict__"):
            yield from walk(child)


def test_the_menu_switches_world_and_nothing_up_top_means_back(make_app):
    import flet as ft

    _, make = make_app
    page, app = make()
    app.new_world()
    controls = list(walk(page.controls[0]))
    assert not any(getattr(c, "icon", None) == ft.Icons.ARROW_BACK for c in controls)
    (menu,) = [c for c in controls if isinstance(c, ft.PopupMenuButton)]
    (switch,) = [i for i in menu.items if i.content == "Switch world"]
    switch.on_click(None)
    assert not in_world(page)


def test_unread_keeps_what_was_new_until_you_leave():
    from tidewrack.ui.components.unread import Unread

    class Fake:
        pass

    unread = Unread.__new__(Unread)
    current = {"quests": {"q1"}}
    unread.seen = {"quests": set()}
    unread.fresh = {"quests": set()}
    import tidewrack.ui.components.unread as module

    original = module.keys
    module.keys = lambda game, part: current[part]
    try:
        unread.game = Fake()
        assert unread.new("quests") == {"q1"}
        unread.look("quests")
        assert unread.new("quests") == set() and unread.is_new("quests", "q1")
        current["quests"] = {"q1", "q2"}
        unread.look("quests")  # something else arrived while you looked
        assert unread.is_new("quests", "q1") and unread.is_new("quests", "q2")
        unread.leave("quests")
        assert not unread.is_new("quests", "q1")
    finally:
        module.keys = original


def test_renaming_from_the_world_list(make_app):
    store, make = make_app
    page, app = make()
    session = GameSession.generate(store, CONTENT, "world.standard", "World 1", 7)
    app.rename(session.meta.slot_id, "Saltmarsh")
    assert [s.meta.name for s in store.list_slots()] == ["Saltmarsh"]
    app.rename(session.meta.slot_id, "   ")  # blank: unchanged
    assert [s.meta.name for s in store.list_slots()] == ["Saltmarsh"]
    assert not in_world(page)  # back on the list


def test_back_steps_out_one_level_at_a_time(make_app):
    store, make = make_app
    page, app = make()
    # A fixed seed whose start room has a Smithy (as in test_economy_ui), not
    # new_world's random one: otherwise there may be no shop here to open.
    app.show_game(GameSession.generate(store, CONTENT, "world.standard", "W", 20261103))
    shell = app.shell
    shell.select(2)  # Quests
    assert app.back() is False and shell.current == 0  # → Explore
    shell.explore.open("Smithy")
    assert shell.explore.opened == "Smithy"
    assert app.back() is False and shell.explore.opened is None  # → shop closed
    assert app.back() is False and not in_world(page)  # → the world list
    assert app.back() is True  # on the list: Android's usual back (leave the app)


def test_the_back_gesture_is_caught_on_the_root_view(make_app):
    import asyncio

    import flet as ft

    _, make = make_app
    page, app = make()
    page.views = [ft.View()]
    app.start()
    view = page.views[0]
    assert view.can_pop is False and view.on_confirm_pop is not None
    answers = []

    class Event:
        control = view

    async def confirm_pop(should_pop):
        answers.append(should_pop)

    view.confirm_pop = confirm_pop
    asyncio.run(view.on_confirm_pop(Event()))
    assert answers == [True]  # on the world list
    app.new_world()
    asyncio.run(view.on_confirm_pop(Event()))
    assert answers == [True, False] and not in_world(page)  # left the world, stayed in the app

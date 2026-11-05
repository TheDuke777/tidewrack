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

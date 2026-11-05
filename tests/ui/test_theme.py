import time

import flet as ft

from tidewrack.services.settings import Settings, SettingsStore
from tidewrack.services.system_colours import SystemColours
from tidewrack.ui.theme import Theming, themes

OLD = SystemColours(light={"primary": "#112233"}, dark={"primary": "#445566"})
NEW = SystemColours(light={"primary": "#778899"}, dark={"primary": "#aabbcc"})


def run_now(job):
    job()


class FakePage:
    def __init__(self):
        self.theme = self.dark_theme = None
        self.on_app_lifecycle_state_change = None
        self.updates = 0

    def update(self):
        self.updates += 1


def make(tmp_path, cached, read):
    store = SettingsStore(tmp_path / "settings.json")
    store.save(Settings(log_share=0.3, system_colours=cached))
    page = FakePage()
    return page, store, Theming(page, store, read=lambda: read[0], background=run_now)


def test_no_scheme_means_flets_default_theme():
    assert themes(None) == (None, None)


def test_themes_use_the_scheme_for_each_brightness():
    light, dark = themes(OLD)
    assert light.color_scheme.primary == "#112233"
    assert dark.color_scheme.primary == "#445566"
    assert light.color_scheme_seed == dark.color_scheme_seed == "#112233"


def test_start_applies_the_cache_then_the_fresh_read(tmp_path):
    seen = []
    store = SettingsStore(tmp_path / "settings.json")
    store.save(Settings(log_share=0.3, system_colours=OLD))
    page = FakePage()
    theming = Theming(page, store, read=lambda: seen.append(page.theme) or NEW, background=run_now)
    theming.start()
    assert seen[0].color_scheme.primary == "#112233"  # cached scheme was on first
    assert page.theme.color_scheme.primary == "#778899"
    assert store.load().system_colours == NEW
    assert store.load().log_share == 0.3  # other settings kept
    assert page.updates == 1


def test_unchanged_or_failed_reads_change_nothing(tmp_path):
    read = [OLD]
    page, store, theming = make(tmp_path, OLD, read)
    theming.start()
    assert page.updates == 0
    read[0] = None  # a failed read keeps the cached scheme
    theming.refresh()
    assert page.updates == 0
    assert store.load().system_colours == OLD
    assert page.theme.color_scheme.primary == "#112233"


def test_resuming_rereads(tmp_path):
    read = [OLD]
    page, store, theming = make(tmp_path, OLD, read)
    theming.start()
    read[0] = NEW
    page.on_app_lifecycle_state_change(
        ft.AppLifecycleStateChangeEvent(name="x", control=page, state=ft.AppLifecycleState.HIDE)
    )
    assert page.updates == 0
    page.on_app_lifecycle_state_change(
        ft.AppLifecycleStateChangeEvent(name="x", control=page, state=ft.AppLifecycleState.RESUME)
    )
    assert page.theme.color_scheme.primary == "#778899"
    assert store.load().system_colours == NEW


def test_a_page_still_showing_old_colours_repaints_even_if_the_cache_is_new(tmp_path):
    """After a palette change two refreshes race; the loser must still repaint."""
    read = [NEW]
    page, store, theming = make(tmp_path, OLD, read)
    theming._apply(OLD)  # what start() painted before the other refresh won
    store.save(Settings(system_colours=NEW))  # the other refresh already cached NEW
    theming.refresh()
    assert page.theme.color_scheme.primary == "#778899"
    assert page.updates == 1


def test_refreshes_run_on_a_thread_of_our_own(tmp_path):
    """Not page.run_thread, whose executor Flet kills when the window is rebuilt."""
    store = SettingsStore(tmp_path / "settings.json")
    page = FakePage()
    done = []
    theming = Theming(page, store, read=lambda: done.append(1) or NEW)
    theming.start()
    for _ in range(100):
        if done:
            break
        time.sleep(0.01)
    assert done

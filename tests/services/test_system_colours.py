import dataclasses
import sys
import types

import flet as ft

from tidewrack.services.settings import Settings, SettingsStore
from tidewrack.services.system_colours import (
    ROLES,
    SystemColours,
    read_system_colours,
    resource_names,
    scheme_from,
)


def test_roles_are_flets_colour_scheme_fields():
    assert set(ROLES) == {f.name for f in dataclasses.fields(ft.ColorScheme)}


def test_role_resources_beat_palettes():
    assert resource_names("primary", "light") == [
        "system_primary_light",
        "system_primary",
        "system_accent1_600",
    ]
    assert resource_names("surface_dim", "dark") == [
        "system_surface_dim_dark",
        "system_surface_dim",
    ]


def test_android_14_roles_are_used_directly():
    colours = {"system_primary_light": 0xFF112233, "system_primary_dark": 0xFFAABBCC,
               "system_primary_fixed": 0xFF010203, "system_accent1_600": 0xFF999999}  # fmt: skip
    scheme = scheme_from(colours.get)
    assert scheme.light["primary"] == "#112233"
    assert scheme.dark["primary"] == "#aabbcc"
    assert scheme.light["primary_fixed"] == scheme.dark["primary_fixed"] == "#010203"


def test_android_12_palettes_fill_in():
    colours = {"system_accent1_600": 0xFF336699, "system_accent1_200": 0xFFCCDDEE,
               "system_neutral1_10": 0xFFFAFAFA}  # fmt: skip
    scheme = scheme_from(colours.get)
    assert scheme.light["primary"] == scheme.light["surface_tint"] == "#336699"
    assert scheme.dark["primary"] == "#ccddee"
    assert scheme.light["surface"] == "#fafafa"
    assert "error" not in scheme.light  # left to the seed
    assert scheme.seed == "#336699"


def test_nothing_found_means_no_scheme():
    assert scheme_from({}.get) is None


def test_off_android_is_none(monkeypatch):
    monkeypatch.delenv("FLET_PLATFORM", raising=False)
    assert read_system_colours() is None


def fake_jnius(sdk: int, colours: dict[str, int], fail: bool = False):
    ids = {name: i + 1 for i, name in enumerate(colours)}
    by_id = {i: colours[name] for name, i in ids.items()}

    class Resources:
        def getConfiguration(self):  # noqa: N802
            return "config"

        def getIdentifier(self, name, kind, package):  # noqa: N802 - Java API
            assert (kind, package) == ("color", "android")
            if fail:
                raise RuntimeError("JNI went wrong")
            return ids.get(name, 0)

    class Application:
        def getResources(self):  # noqa: N802
            return Resources()

        def createConfigurationContext(self, configuration):  # noqa: N802
            assert configuration == "config"
            return Application()

        def getColor(self, resource_id):  # noqa: N802
            return by_id[resource_id] - (1 << 32)  # Java ints are signed

    class StaleActivity:
        """After a palette change Flet still holds the first, destroyed activity."""

        def getResources(self):  # noqa: N802
            raise AssertionError("read the application, not the activity")

        getColor = getResources  # noqa: N815

        def getApplicationContext(self):  # noqa: N802
            return Application()

    def autoclass(name):
        if name == "android.os.Build$VERSION":
            return types.SimpleNamespace(SDK_INT=sdk)
        assert name == "Host"
        return types.SimpleNamespace(mActivity=StaleActivity())

    return types.SimpleNamespace(autoclass=autoclass)


def on_android(monkeypatch, jnius):
    monkeypatch.setenv("FLET_PLATFORM", "android")
    monkeypatch.setenv("MAIN_ACTIVITY_HOST_CLASS_NAME", "Host")
    monkeypatch.setitem(sys.modules, "jnius", jnius)


def test_reads_through_pyjnius_on_android(monkeypatch):
    on_android(monkeypatch, fake_jnius(36, {"system_primary_light": 0xFF123456,
                                            "system_primary_dark": 0xFF654321}))  # fmt: skip
    colours = read_system_colours()
    assert colours.light == {"primary": "#123456"}
    assert colours.dark == {"primary": "#654321"}


def test_old_android_and_failures_are_none(monkeypatch):
    on_android(monkeypatch, fake_jnius(30, {"system_primary_light": 0xFF123456}))
    assert read_system_colours() is None
    on_android(monkeypatch, fake_jnius(36, {"system_primary_light": 0xFF123456}, fail=True))
    assert read_system_colours() is None


def test_settings_cache_round_trips(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    cached = SystemColours(light={"primary": "#112233"}, dark={"primary": "#445566"})
    store.save(Settings(system_colours=cached))
    assert store.load().system_colours == cached

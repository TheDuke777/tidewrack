"""Material You: the system colour scheme Android derives from the wallpaper.

Flet has no dynamic-colour API, so on Android this reads the colours through
pyjnius (an Android-only dependency, `[tool.flet.android]` in pyproject.toml).
Android 14+ publishes every Material 3 role (`system_primary_light`, …); 12–13
only the five tonal palettes, mapped onto roles the way Android 12 does. Off
Android, on Android 11 or older, or if anything at all goes wrong, the answer
is None and the app keeps its built-in theme: colours are never worth a crash.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict

# Material 3 roles, named as flet's ColorScheme fields (tests check they match).
ROLES = (
    "primary", "on_primary", "primary_container", "on_primary_container",
    "secondary", "on_secondary", "secondary_container", "on_secondary_container",
    "tertiary", "on_tertiary", "tertiary_container", "on_tertiary_container",
    "error", "on_error", "error_container", "on_error_container",
    "surface", "on_surface", "on_surface_variant", "outline", "outline_variant",
    "shadow", "scrim", "inverse_surface", "on_inverse_surface", "inverse_primary",
    "surface_tint",
    "primary_fixed", "primary_fixed_dim", "on_primary_fixed", "on_primary_fixed_variant",
    "secondary_fixed", "secondary_fixed_dim", "on_secondary_fixed",
    "on_secondary_fixed_variant",
    "tertiary_fixed", "tertiary_fixed_dim", "on_tertiary_fixed", "on_tertiary_fixed_variant",
    "surface_bright", "surface_dim", "surface_container_lowest", "surface_container_low",
    "surface_container", "surface_container_high", "surface_container_highest",
)  # fmt: skip

# Android 12–13 tonal palettes → roles. Resource steps, not M3 tones: _600 is tone 40.
PALETTE_ROLES: dict[str, dict[str, tuple[str, int]]] = {
    "light": {
        "primary": ("accent1", 600), "on_primary": ("accent1", 0),
        "primary_container": ("accent1", 100), "on_primary_container": ("accent1", 900),
        "secondary": ("accent2", 600), "on_secondary": ("accent2", 0),
        "secondary_container": ("accent2", 100), "on_secondary_container": ("accent2", 900),
        "tertiary": ("accent3", 600), "on_tertiary": ("accent3", 0),
        "tertiary_container": ("accent3", 100), "on_tertiary_container": ("accent3", 900),
        "surface": ("neutral1", 10), "on_surface": ("neutral1", 900),
        "on_surface_variant": ("neutral2", 700),
        "outline": ("neutral2", 500), "outline_variant": ("neutral2", 200),
        "inverse_surface": ("neutral1", 800), "on_inverse_surface": ("neutral1", 50),
        "inverse_primary": ("accent1", 200), "surface_tint": ("accent1", 600),
    },
    "dark": {
        "primary": ("accent1", 200), "on_primary": ("accent1", 800),
        "primary_container": ("accent1", 700), "on_primary_container": ("accent1", 100),
        "secondary": ("accent2", 200), "on_secondary": ("accent2", 800),
        "secondary_container": ("accent2", 700), "on_secondary_container": ("accent2", 100),
        "tertiary": ("accent3", 200), "on_tertiary": ("accent3", 800),
        "tertiary_container": ("accent3", 700), "on_tertiary_container": ("accent3", 100),
        "surface": ("neutral1", 900), "on_surface": ("neutral1", 100),
        "on_surface_variant": ("neutral2", 200),
        "outline": ("neutral2", 400), "outline_variant": ("neutral2", 700),
        "inverse_surface": ("neutral1", 100), "on_inverse_surface": ("neutral1", 800),
        "inverse_primary": ("accent1", 600), "surface_tint": ("accent1", 200),
    },
}  # fmt: skip

MIN_SDK = 31  # Android 12, when the system palettes appeared


class SystemColours(BaseModel):
    """Role name → "#rrggbb" for each brightness. Missing roles follow the seed."""

    model_config = ConfigDict(frozen=True)

    light: dict[str, str]
    dark: dict[str, str]

    @property
    def seed(self) -> str:
        """What flet fills unread roles from: the light primary, else any colour."""
        return self.light.get("primary") or next(iter(self.light.values()))


def resource_names(role: str, mode: str) -> list[str]:
    """Android colour resources to try for a role, best first."""
    names = [f"system_{role}_{mode}", f"system_{role}"]
    if role in PALETTE_ROLES[mode]:
        palette, step = PALETTE_ROLES[mode][role]
        names.append(f"system_{palette}_{step}")
    return names


def scheme_from(lookup) -> SystemColours | None:
    """Build both schemes from `lookup(resource name) -> ARGB int | None`."""
    schemes = {}
    for mode in ("light", "dark"):
        scheme = {}
        for role in ROLES:
            for name in resource_names(role, mode):
                argb = lookup(name)
                if argb is not None:
                    scheme[role] = f"#{argb & 0xFFFFFF:06x}"
                    break
        schemes[mode] = scheme
    if not schemes["light"] or not schemes["dark"]:
        return None
    return SystemColours(**schemes)


def read_system_colours() -> SystemColours | None:
    """The wallpaper scheme, or None anywhere it isn't available."""
    if os.environ.get("FLET_PLATFORM") != "android":
        return None
    try:
        from jnius import autoclass  # Android-only dependency

        if autoclass("android.os.Build$VERSION").SDK_INT < MIN_SDK:
            return None
        context = current_context(autoclass)
        resources = context.getResources()
        found: dict[str, int | None] = {}

        def lookup(name: str) -> int | None:
            if name not in found:
                resource_id = resources.getIdentifier(name, "color", "android")
                found[name] = context.getColor(resource_id) if resource_id else None
            return found[name]

        return scheme_from(lookup)
    except Exception:  # noqa: BLE001 - any failure means "use the built-in theme"
        return None


def current_context(autoclass):
    """A context built now, so it carries the palette Android has now.

    Changing the system palette recreates the activity, but Flet's plugin only
    hands Python the first one, and contexts made before the change can keep
    the old colours. A configuration context made from the (long-lived)
    application is created afresh from Android's current resources.
    """
    activity = autoclass(os.environ["MAIN_ACTIVITY_HOST_CLASS_NAME"]).mActivity
    app = activity.getApplicationContext()
    return app.createConfigurationContext(app.getResources().getConfiguration())

"""App version info, readable from a source checkout and from a packaged build.

Packaged apps don't ship pyproject.toml, so release builds generate
``tidewrack/_build_info.py`` first (``python tools/release.py build-info <tag>``).
Running from source falls back to reading pyproject.toml directly.

This is the *app* version (CLAUDE.md §10). Save/content compatibility versions
(``schema_version`` etc., §9) are tracked separately.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


@dataclass(frozen=True)
class BuildInfo:
    version: str  # plain x.y.z (Android versionName)
    build_number: int  # Android versionCode
    tag: str | None  # release tag, e.g. "v0.2.0-beta.1"; None when running from source


def get_build_info() -> BuildInfo:
    try:
        from tidewrack import _build_info  # generated; absent in source checkouts
    except ImportError:
        return _from_pyproject(_PYPROJECT)
    return BuildInfo(_build_info.VERSION, _build_info.BUILD_NUMBER, _build_info.TAG)


def _from_pyproject(path: Path) -> BuildInfo:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return BuildInfo("0.0.0", 0, None)
    return BuildInfo(
        version=data["project"]["version"],
        build_number=int(data["tool"]["flet"]["build_number"]),
        tag=None,
    )


def version_label(info: BuildInfo) -> str:
    """Human-readable version, e.g. ``v0.2.0-beta.1 (build 7)``."""
    if info.tag:
        return f"{info.tag} (build {info.build_number})"
    return f"v{info.version} (build {info.build_number}, dev)"

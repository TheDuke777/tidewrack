"""Upgrade old slot envelopes to the current schema (CLAUDE.md §9, §10).

When the save format changes: bump core.versions.SCHEMA_VERSION to N, add
``MIGRATIONS[N - 1]`` (a pure function from the version N-1 envelope to version
N), and commit a fixture save of the *old* version under tests/fixtures/saves/
so the migration stays tested forever. Never edit a released migration.

The un-migrated file is not lost: the next autosave rotates it into the slot's
backups before writing the upgraded version.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tidewrack.core.versions import SCHEMA_VERSION
from tidewrack.services.storage.store import SaveError

Envelope = dict[str, Any]

# from-version -> function producing the next version's envelope
MIGRATIONS: dict[int, Callable[[Envelope], Envelope]] = {}


class NewerSaveError(SaveError):
    """The save was made by a newer version of the app."""


def migrate(envelope: Envelope) -> Envelope:
    version = envelope.get("schema_version")
    if not isinstance(version, int) or version < 1:
        raise ValueError(f"save has no valid schema_version ({version!r})")
    if version > SCHEMA_VERSION:
        raise NewerSaveError(
            f"This world was saved by a newer version of Tidewrack (save format "
            f"{version}, this app reads up to {SCHEMA_VERSION}). Update the app to open it."
        )
    while version < SCHEMA_VERSION:
        envelope = MIGRATIONS[version](envelope)
        version += 1
        envelope["schema_version"] = version
    return envelope

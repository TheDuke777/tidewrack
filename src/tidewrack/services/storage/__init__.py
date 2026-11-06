"""Local save slots (CLAUDE.md §6).

- :class:`SaveStore` is the interface; :class:`FileSaveStore` writes each slot as
  a gzipped JSON main file plus a part file per place (see store.py) into the
  app's private data directory, rewriting only the places that changed.
- Writes are atomic (temp file + rename), so a save is never half-written even if
  Android kills the app mid-write, and the previous few revisions of each slot
  are kept as backups that loading falls back to if the main file is unreadable.
- A slot file is an *envelope*: format marker, versions, slot metadata (enough to
  list slots without loading games), and the game state. Migrations upgrade old
  envelopes; see migrations.py.
"""

from tidewrack.services.storage.store import (
    FileSaveStore,
    LoadedSlot,
    SaveError,
    SaveStore,
    SlotListing,
    SlotMeta,
    SlotSummary,
    data_dir,
    saves_dir,
)

__all__ = [
    "FileSaveStore",
    "LoadedSlot",
    "SaveError",
    "SaveStore",
    "SlotListing",
    "SlotMeta",
    "SlotSummary",
    "data_dir",
    "saves_dir",
]

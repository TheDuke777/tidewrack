"""Data-compatibility versions carried by every save/share payload (CLAUDE.md §9).

Separate from the app version. Bump SCHEMA_VERSION when the save format changes
(and add a migration in services/storage/migrations.py); bump GENERATOR_VERSION
when the same seed would produce different results (RNG or generation changes).
"""

SCHEMA_VERSION = 1
GENERATOR_VERSION = 1

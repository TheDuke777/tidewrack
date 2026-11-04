"""Data-compatibility versions carried by every save/share payload (CLAUDE.md §9).

Separate from the app version. Bump SCHEMA_VERSION when the save format changes
(and add a migration in services/storage/migrations.py); bump GENERATOR_VERSION
when the same seed would produce different results (RNG or generation changes).
"""

# 2: dungeon nodes may carry map positions (`pos`)
# 3: a save holds a world of locations (each with rooms) instead of one dungeon
SCHEMA_VERSION = 3
# 2: worlds of locations; per-roomset layouts
GENERATOR_VERSION = 2

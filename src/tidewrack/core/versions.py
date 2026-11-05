"""Data-compatibility versions carried by every save/share payload (CLAUDE.md §9).

Separate from the app version. Bump SCHEMA_VERSION when the save format changes
(and add a migration in services/storage/migrations.py); bump GENERATOR_VERSION
when the same seed would produce different results (RNG or generation changes).
"""

# 2: dungeon nodes may carry map positions (`pos`)
# 3: a save holds a world of locations (each with rooms) instead of one dungeon
# 4: gear (player Stats; Item, Carried and Equipped components)
# 5: combat (Health, Codex, Respawn on the player; Enemy, Fighting, Spawner;
#    combat/encounter RNG streams and the world's Rules in GameState)
# 6: quests (Quest, QuestItem, Clue components; Bounty on wanted enemies)
# 7: enemies return (Spawner cap + templates; respawn RNG stream; return Rules)
# 8: the economy (Wallet on the player; Shop and Stocked components; gold on
#    Enemy, EnemyTemplate and Quest; shop RNG stream and EconomyRules in GameState)
SCHEMA_VERSION = 8
# 2: worlds of locations; per-roomset layouts
# 3: new worlds also get a starting kit and gear finds (procgen/gear_gen.py)
# 4: new worlds also get enemies, placed and wandering (procgen/enemy_gen.py)
# 5: generated items record their set's chip colour
# 6: new worlds also get quests: notice boards, clues, bounties (procgen/quest_gen.py)
# 7: spawners also carry enemy templates (with pre-rolled loot) for returning enemies
# 8: enemies and quests also roll gold; new worlds also get shops (procgen/shop_gen.py)
GENERATOR_VERSION = 8

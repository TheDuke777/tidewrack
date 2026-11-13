# CLAUDE.md — Tidewrack: Project Context & Architecture (v3)

Orientation file for an AI coding assistant (or future-you) working in this repo. It is a **no-code** architecture reference: constraints, directory layout, subsystem responsibilities, feature specs, conventions, risks, and build order. Implementation lives in `src/`.

---

## 1. What this project is

**Tidewrack** is a **text-based, procedurally generated roguelike RPG** in Python + Flet. Android-first, with a possible web build. No tile grid, no line-of-sight, no pathfinding — the world is graphs and data, presented as prose plus a schematic point-crawl map.

### World structure
**World → Locations → Rooms.** A **world** (one per save slot; `Overworld` in code, to avoid clashing with the ECS `World`) is a graph of **locations** joined by two-way roads. A location is a town, forest, mine, sea cave, dungeon… with its own graph of **rooms**, where events happen (description, look, later combat, shops, foraging). The player travels between locations only from a location's **gate rooms** (town gate, cave mouth, forest edge). Two fog-of-war maps: the area map (rooms here) and the world map (locations; discovered places are named, as if signposted).

### Hard constraints (non-negotiable)
- **Fully offline gameplay.** The only network use is optional cloud-save sync. No multiplayer, no leaderboards, no live-ops, no server code of our own.
- **No ads. No in-app purchases. No premium currency.** One in-game currency (gold). No energy timers, no dark patterns.
- **No telemetry by default.** Anything beyond sync (e.g. crash reports) must be opt-in and listed in Settings.
- **Players never need to leave the app to learn the game.** Everything is discoverable in-app: tutorial, codex, searchable help.

### Design pillars
1. **Procgen everything** — worlds, quests, factions, lore, names, pets. Generated from systems + data.
2. **Systems over content** — ECS-style composition; no deep inheritance trees.
3. **Ascension/prestige loop** — runs end, meta-progression persists, difficulty and achievements scale with prestige.
4. **Deterministic, seeded runs** — same seed + same generator version = same world.
5. **Legibility** — schematic map, obvious gear comparison, self-documenting codex.
6. **Portable core** — game logic is pure Python with no UI/IO imports, so it runs on mobile, desktop, and (if pursued) in-browser via Pyodide.

---

## 2. Platform strategy

| Target | Approach | Notes |
|---|---|---|
| Android (primary) | `flet build apk` (Flutter-based), delivered via GitHub Releases + Komi Store (§10) | Touch-first, portrait-first layouts; responsive controls. **iOS is not targeted for now** (no way to build for it); nothing in the design should block it later |
| Desktop (dev + bonus) | `flet run` / `flet build` | Fast dev loop with hot reload |
| Web (optional) | **Static** Flet build (Pyodide, Python runs in-browser) | Not the server-hosted mode — keeps "no server of our own" true |

**Rules that keep web possible without committing to it:**
- `core/` imports nothing from `ui/` or `services/`, and does no file/network I/O.
- All persistence goes through a `SaveStore` interface; all sync goes through a `CloudProvider` interface. Platform-specific backends plug in behind them.
- Dependencies in `core/` must be pure-Python or available in Pyodide — verify before adding (see Spikes).
- Worldgen must be fast or chunked/async: the static web build is single-threaded and long CPU work freezes the UI.

---

## 3. Tech stack

| Concern | Choice | Notes |
|---|---|---|
| UI | **Flet** (Material Design 3) | Light/dark/system. **Material You** on Android 12+ (`ui/theme.py`): Flet has no dynamic-colour API, so `services/system_colours.py` reads Android's `system_<role>_light/_dark` colour resources (tonal palettes on 12–13) through **pyjnius**, an Android-only dependency (`[tool.flet.android] dependencies`). Read via a fresh configuration context of the application (a palette change recreates the activity and Flet keeps handing Python the first one); cached in `Settings.system_colours`, applied at launch, refreshed on resume and whenever `main()` reruns. Off Android or on any failure: Flet's default theme |
| Map rendering | Flet `canvas` (`ui/map_canvas.py`) | Point-crawl diagram with fog of war, for both the area and the world map; tap a ringed neighbour to go there (tapping a road neighbour away from a gate toasts `MapNode.blocked`, the reason). Gate rooms are rounded squares; world-map labels start with a kind glyph (`KIND_GLYPHS`; add one per new roomset name, a test checks) and end with ✓ (every room visited), ◆ (an active quest leads there) and ⚔ (a warden bars the road there); region names are drawn behind the world map (faint when zoomed in; at or below `REGION_ZOOMED_OUT` larger, clearer, kept on the map, and labels steer around them); area-map rooms get badges for items left lying (✦) and a seen bounty (◆). Marks only ever show what the player has seen. **Level of detail (8a beta 3):** labels are placed by `label_rank` (you; tappable, quest and guarded places, always labelled; towns; visited; the rest), only for places near the screen, and a lesser label more than `DROP_OVERLAP` covered is left out, so zooming in reveals names. A tap whose nearby places would do different things zooms in `TAP_ZOOM`× around it instead. Pinch-zoom/pan is our own `Viewport` (spreads the map out instead of magnifying dots and labels), not Flet's `InteractiveViewer`. Maps open at `FOCUS_ZOOM` centred on you; each map kind (`zoom_key`: area, world) keeps the zoom you leave it at across moves, travel and canvas resizes. The legend hides with a map button (`Settings.legend_open`); the map's buttons sit on tinted backs (`BUTTON_FILL`, 90% secondary container) with an outline edge (light mode's secondary container is too close to the map's background) so they don't read as map symbols |
| World structure | Hand-rolled (`core/procgen/grid.py`, `location_gen.py`, `world_gen.py`) | One grid-based spanning tree + loops layout for both rooms and the overworld; gives map positions directly and stays deterministic. Chosen over `networkx` (layouts need numpy, ~2 MB, little benefit at 10–60 nodes) |
| Overworld regions | *Later, if they add something:* `scipy.spatial.Voronoi` | Not needed for the grid overworld; heavy compiled dependency (check pypi.flet.dev, and Pyodide if web is pursued) |
| Biomes | *Later:* `opensimplex` | Coherent noise → biome per region |
| ECS | In-house (`core/engine/ecs.py`) | Instance-based, insertion-ordered `World`. Chosen over `esper` 3.x, whose state is module-global (bad for tests, multiple slots, save/load) |
| Names/lore | `markovify` (+ `Faker` stopgap) | Late polish pass |
| Dice | `d20` | Dice-notation rolls |
| Validation | `pydantic` **==2.13.4** | All content + save + import payloads. Exact pin: APK builds install binary wheels only, and Flet's Android index (pypi.flet.dev) has cp314 arm64 `pydantic-core` 2.46.4 (pydantic 2.13.4) but not 2.14.x's. Check the index before bumping, and do the same for any new compiled dependency |
| Local persistence | JSON(+gzip) slot files; `sqlite3` optional | Behind `SaveStore`; browser backend if web |
| Auth | Flet built-in OAuth (Google first; GitHub/Microsoft via same mechanism) | See Spikes — secret handling and webview policy |
| Cloud storage | **Per-provider app-private storage** (Google Drive `appDataFolder` first) | Thin REST client, no heavy SDK; see §6 |
| Release & distribution | GitHub Actions + `flet build apk` → GitHub Releases → **Komi Store** on-device updates | Version bumping + tagging scripted; see §10 |

Not used: `tcod` FOV/pathfinding/renderer (tile-grid problems we don't have).

---

## 4. Architecture layers

```
┌──────────────────────────────────────────────┐
│ UI (Flet, MD3)                               │
│ screens · components · theme · map canvas    │
└───────────────┬──────────────────────────────┘
                │ view-models / commands
┌───────────────▼──────────────────────────────┐
│ Services (platform adapters, behind          │
│ interfaces)                                  │
│ storage · cloud sync · auth · share/import · │
│ settings                                     │
└───────────────┬──────────────────────────────┘
                │ plain data (pydantic models)
┌───────────────▼──────────────────────────────┐
│ CORE — pure Python, no UI/IO                 │
│ engine (ECS, event bus, turn loop)           │
│ procgen · gear (stat pipeline + compare)     │
│ economy (value model, shops, crafting,       │
│   cooking) · progression (prestige,          │
│   achievements, difficulty) · codex + help   │
│ data (schemas, loader) · rng                 │
└───────────────┬──────────────────────────────┘
                │ loads
┌───────────────▼──────────────────────────────┐
│ content/ — JSON/YAML + Markdown              │
│ monsters, items, recipes, shops, pets,       │
│ factions, quests, achievements, modifiers,   │
│ lore, help articles, tutorial world          │
└──────────────────────────────────────────────┘
```

**Event bus** (`core/engine/events.py`) is the spine: the engine emits typed events (`EnemyKilled`, `ItemCrafted`, `RoomDiscovered`, `LocationEntered`, `QuestCompleted`, `PetBonded`, `GoldSpent`, …). Achievements, codex discovery, quest tracking, and tutorial hints are all **subscribers** — they never reach into engine internals.

---

## 5. Directory layout

```
tidewrack/
├── CLAUDE.md
├── README.md
├── LICENSE                          # MIT
├── CHANGELOG.md                     # "Unreleased" section promoted on release
├── pyproject.toml                   # version + build_number live here
├── .github/
│   ├── actions/build-cache/         # restore/save Flutter, NDK, Gradle caches (§10)
│   └── workflows/
│       ├── ci.yml                   # tests, lint, content validation, quick sims
│       ├── release.yml              # tag → signed APK → GitHub Release → ntfy
│       └── warm-build-cache.yml     # Mon/Thu on main: fills + refreshes build caches
├── tools/
│   └── release.py                   # bump version/build_number, changelog, tag, push
├── art/                             # source artwork (not bundled into the APK)
├── src/content/                     # All game content as data, <kind>/<name>.json
│                                    #   (under src/ because flet build only bundles src/)
│   ├── worlds/                      # world recipes: regions (coast first) + places in each
│   ├── regions/                     # biomes (8a): tier, names, town + roomset weights, warden
│   ├── roomsets/                    # location kinds (town, forest, mine, sea caves): names,
│   │                                #   size, layout shape, room archetypes, gate room
│   ├── dungeons/                    # hand-authored locations (first_descent → tutorial later)
│   ├── gear/                        # gear definitions: slot, base stats, rolls, upgrades, set
│   ├── affixes/                     # prefixes/suffixes found gear may roll ("Keen", "of the Gull")
│   ├── gearsets/                    # set bonuses by pieces worn
│   ├── enemies/                     # beasts, people, spirits: stats, rolls, loot table
│   ├── consumables/                 # (later; the loader only allows flat <kind>/<name>.json,
│   ├── materials/                   #   so no items/ parent dir) hides, ore, timber, … (7b);
│   │                                #   cooking ingredients later (7c)
│   ├── recipes/                     # crafting recipes (7b): makes, affix, materials, known
│   ├── meals/                       # meals (7c): ingredients, buff (stats, regen), turns, sold
│   ├── shops/                       # shop archetypes, stock rules
│   ├── pets/
│   ├── factions/
│   ├── quests/                      # one template per quest type (bounty, cull, explore,
│   │                                #   recover): titles, summaries, clues, epithets, items
│   ├── events/
│   ├── modifiers/                   # run/world modifiers
│   ├── achievements/
│   ├── lore/
│   ├── corpora/                     # markovify training text
│   ├── help/                        # Markdown articles (searchable)
│   └── tutorial/                    # fixed tutorial world + step script
├── src/main.py                      # Flet entry point
├── src/assets/                      # bundled: icon.png, icon_android.png, logo
├── src/tidewrack/
│   ├── version.py                   # app version for the UI (reads _build_info.py,
│   │                                #   generated in CI; else pyproject)
│   ├── core/                        # PURE PYTHON — no UI/IO imports
│   │   ├── engine/                  # ecs.py, components.py, events.py,
│   │   │                            #   game.py (commands, turn loop, view model)
│   │   ├── world/                   # location.py (rooms + exits + gates),
│   │   │                            #   overworld.py (locations + roads)
│   │   ├── procgen/                 # grid.py (shared layout), location_gen.py,
│   │   │                            #   world_gen.py (+ world_hash), gear_gen.py (kit +
│   │   │                            #   finds), enemy_gen.py (placed + wanderer queues),
│   │   │                            #   quest_gen.py (boards, clues, bounties, rewards),
│   │   │                            #   shop_gen.py (town shops: room or gate, stock),
│   │   │                            #   material_gen.py (gathering, drops, recipes);
│   │   │                            #   later: biomes, names, factions, pets, lore
│   │   ├── gear/                    # stats.py (STATS), item.py (Item snapshot, SLOTS),
│   │   │                            #   stat_pipeline.py, compare.py
│   │   ├── combat/                  # rules.py (Rules snapshot, damage), fight.py (rounds,
│   │   │                            #   encounters, defeat, regen), returns.py (wanderers
│   │   │                            #   coming back)
│   │   ├── quests/                  # quests.py (accept, turn in, progress subscribers)
│   │   ├── economy/                 # value_model.py (value, prices, EconomyRules),
│   │   │                            #   shops.py (buy, sell, inn, restock, buy-back),
│   │   │                            #   crafting.py (satchel, markets, craft, upgrade),
│   │   │                            #   cooking.py (kitchens, meals, buffs)
│   │   ├── progression/             # prestige.py, achievements.py, difficulty.py
│   │   ├── codex/                   # foes.py (Foes: reveal by kills), items.py (materials,
│   │   │                            #   ingredients, recipes, meals; v0.10.2); later
│   │   │                            #   lore/quest-log models, help index + search, glossary
│   │   ├── data/                    # schemas.py (pydantic → runtime models);
│   │   │                            #   loader.py (pure: {path: text} → Content);
│   │   │                            #   save.py (GameState schema + component codec)
│   │   ├── versions.py              # SCHEMA_VERSION, GENERATOR_VERSION (§9)
│   │   └── rng.py                   # own xoshiro256** stream; derive() substreams
│   ├── services/                    # platform adapters behind interfaces
│   │   ├── content/                 # reads bundled src/content files → core loader
│   │   ├── storage/                 # SaveStore interface + FileSaveStore (store.py),
│   │   │                            #   migrations.py; browser backend later
│   │   ├── session.py               # GameSession: a Game bound to a slot, autosaves
│   │   ├── system_colours.py        # Material You: Android wallpaper scheme via pyjnius
│   │   ├── cloud/                   # CloudProvider interface; google_drive/; sync_engine.py;
│   │   │                            #   conflict.py  (onedrive/ later, same interface)
│   │   ├── auth/                    # OAuth wrappers, token storage
│   │   ├── share/                   # world/save export + import codec, validation
│   │   └── settings/                # Settings model + SettingsStore (app-wide settings.json
│   │                                #   beside saves/; UI prefs such as the log split)
│   └── ui/
│       ├── app.py                   # slot picker ⇄ open world; confirm dialogs
│       ├── shell.py                 # open world: Material 3 navigation bar over tabs
│       │                            #   (Explore, Inventory, Quests, Codex); add tabs here
│       ├── theme.py                 # MD3 theming: Material You (Theming), later seed
│       │                            #   colour + colorblind-safe palettes
│       ├── components/              # card (the one card style, surface_container fill: use it, never bare ft.Card), gear_compare_card, quest_card, meal_card, pack_list
│       │                            #   (filters/sort/select, shared by Inventory + shops),
│       │                            #   folds (collapsible cards), unread (dots), stat_delta, …
│       ├── map_canvas.py            # point-crawl renderer + fog of war + tap-to-move
│       └── screens/                 # sign_in, slot_picker, game, map, inventory, shop,
│                                    #   crafting, cooking, pets, achievements, codex,
│                                    #   quest_log, help, settings, tutorial
├── sim/                             # headless harnesses (on pytest's pythonpath)
│   ├── difficulty_sim.py            # (step 8)
│   └── economy_sim.py               # gold income vs prices, arbitrage + top-tier lint
└── tests/
    ├── core/                        # golden-seed tests, compare tests, economy lint
    ├── services/                    # storage/session tests, sync/conflict, import fuzz
    ├── sim/                         # quick sim passes for CI
    ├── fixtures/saves/              # one save per released schema_version — never delete
    └── content/                     # schema validation of every content file
```

---

## 6. Accounts, save slots, and cloud sync

### Identity vs storage
- **Sign-in is identity; storage is per-provider.** Google sign-in → Google Drive `appDataFolder` (hidden, app-private, user-owned, no backend for us to run or pay for). Other SSOs (e.g. Microsoft → OneDrive app folder) are added later as additional `CloudProvider` implementations. An SSO with no suitable storage = local-only + manual export.
- Playing without signing in is always allowed (local slots only). Signing in later uploads existing slots.
- Use thin REST calls for Drive/OneDrive rather than large Google SDKs (smaller, more portable).

### Data model
- **Account-level:** settings (theme, sync prefs, etc.) + cloud manifest.
- **World slot (self-contained):** world snapshot, player, prestige, achievements, codex discoveries, pets, quests, RNG state, schema + content versions. Each slot is one main file (`slot_<uuid>.json.gz`) plus its part files (§6 local implementation).
- `manifest.json` lists slots with `name`, `updated_at`, `revision`, `device_id`, `content_hash`.

### Sync rules
- **Offline-first:** local files are the source of truth; sync is background and failure-tolerant.
- Each slot syncs independently.
- Track `last_synced_revision` per slot. If **only one side changed** → fast-forward. If **both changed** → conflict.
- **Never silently overwrite.** Conflict dialog: *Keep this device / Keep cloud / Keep both (duplicate slot)*, showing playtime, prestige, last-played for each side.
- Keep rolling local backups (last N autosaves per slot) and one prior cloud revision where the provider allows.
- Autosave on meaningful events (node change, combat end, shop/craft transaction), not just on exit — mobile apps get killed.

### Local implementation (step 3)
- Slots live in `$FLET_APP_STORAGE_DATA/saves/` (the app's private dir, kept across updates; `flet run` maps it to `.flet/storage/data`). One main file per slot, `slot_<uuid hex>.json.gz`: an **envelope** of `format`, `schema_version`, `generator_version`, `content_version` (content hash), `meta` (name, timestamps, `revision`, picker summary) and `game` (a `GameState`). **Split saves (8a beta 2):** `FileSaveStore` writes the main file with the player and anything not tied to a place (quests, codex, pack), plus `parts` naming one part file per place (`slot_<id>.parts/<sha256>.json.gz`: entities with a `Position` there, its `Spawner`/`Grower`, its shops' `Stocked` wares) and one for the world map. Parts are content-named and never rewritten; replacing the main file is the commit, and parts no main file or backup lists are deleted. `SaveStore.save(..., changed)` takes the entity ids changed since the store's last save of the slot (None = write all); `GameSession`'s `StateEncoder` keeps each entity's encoding with a deep copy of its components and re-encodes only those that no longer compare equal (a test pins its output to `Game.to_state()`), committing only once the write succeeded. Loading reassembles the envelope (entities sorted by id = creation order), so migrations and old whole-file slots are unaffected; envelopes that don't look current are written whole.
- `GameSession` autosaves after **every** command that produced events. Writes are atomic (temp + fsync + rename); the previous **3** revisions are copied to `saves/backups/` first, and loading falls back to the newest readable backup (the picker flags it).
- Locally the slot list comes from scanning slot files (no local manifest to drift); `manifest.json` is for cloud sync.
- A `GameState` **snapshots the whole world** (every location and room, generated up front at world creation) and every entity, so saves never depend on current content files (§9). A standard world is ~35 KB gzipped at 21 places (8a beta 2); at 28 places (8a beta 3) a slot is ~90 KB on disk across its files and takes ~0.3 s to generate and first save. Before the split an autosave took ~48 ms on desktop at 14 places (~70 ms at 21), mostly encoding entities; now ~7.6 ms at 21 places (a Wait rewrites only the ~4 KB main file), ~11 ms at 28, and the slot summary is read directly instead of from `Game.view()`. Check autosave time on a phone.

---

## 7. World sharing (import/export)

Two distinct operations (don't conflate them):

| | **Share World** | **Backup Save** |
|---|---|---|
| Contents | World snapshot (+ seed, generator + content versions); **no player progress** | Entire slot incl. progress |
| Purpose | Friend plays the same world fresh | Move/restore a save outside cloud |
| On import | Creates a **new** slot | Creates a **new** slot (never overwrites) |

- Share payload **includes the generated snapshot**, not just the seed — otherwise any generator tweak silently changes shared worlds. Optionally also expose a short **seed code** for quick text sharing.
- Delivery: OS share sheet / file picker / clipboard text (and QR for seed codes). Verify Flet support per platform.
- **Import safety:** data-only JSON (never pickle/eval); size limits; pydantic validation; schema + content-version checks with a clear error ("made with a newer version"); unknown content IDs are rejected or sandboxed, never executed.

---

## 8. Feature specs

### 8.1 Pets (discoverable companions)
- **Discovery:** biome events, rare encounters, faction quests, eggs/tames via items. Procgen picks species/traits from pet templates. Appears in codex as ??? until found.
- **Roles:** Fighter (assist/defend), Scout (reveals adjacent map nodes, reduces ambush), Forager (bonus ingredients/materials), Hauler (carry capacity), Support (heal/buff).
- **Bond:** grows through use and feeding. **Pet food is a cooking recipe category** — ties cooking into pets.
- **Limits:** 1 active pet (2nd slot unlocked via achievement/prestige). Pet contribution is power-budgeted so pets aid but never replace the player. Pets are **downed, not permanently killed.**
- **Rarity & persistence (decided):** pets are **rare finds** and **persist across prestige**. Because they're permanent, balance comes from the power budget (pet strength capped per prestige tier), not from resetting them. A **soft-pity** rule raises discovery odds after each qualifying run that ends without a find, so rarity never becomes pure bad luck. Duplicate finds convert into bond/pet food instead of being wasted.
- **ECS:** `Companion`, `PetAbility`, `Bond` components; a roster screen manages owned pets.

### 8.2 Achievements with prestige-scaling tiers
- Data-driven definitions: `id, name, description, hint, category, trigger (event type + filter + counter), scope (lifetime | run), tiers[], rewards, hidden`.
- **Tiers:** thresholds follow a formula (`base × growth^tier`); higher tiers **unlock as prestige rank rises**, so achievements stay meaningful after ascension.
- **Rewards:** titles/cosmetics, QoL (stash slots, codex hints), unlocks (pets, recipes, shop stock), and small **capped** permanent bonuses. All permanent power is budgeted into the difficulty formula and covered by the sim.
- UI: progress bars, next-tier preview, non-blocking unlock toasts. "Hidden" achievements still show a hint — no forum-hunting.

### 8.3 Settings screen
- **Appearance:** light/dark/system, MD3 seed color, font scale, high-contrast, colorblind-safe palette, reduce motion.
- **Cloud:** account (sign in/out), sync now, auto-sync on/off, Wi-Fi only, last synced, per-slot sync status, delete cloud data.
- **Data:** share world, backup save, import, restore from backup, storage usage.
- **Gameplay:** text speed, auto-advance, combat-log verbosity, confirm-destructive-actions (drop already always confirms via `App.confirm`; sell will too), tooltips/hints on-off.
- **Tutorial:** replay onboarding, reset contextual hints.
- **Sound/haptics** (if added), **About** (version, licenses, privacy statement).

### 8.4 Gear comparison (base **and** total)
- **Single stat pipeline** (`core/gear/stat_pipeline.py`): `base (def + roll) → upgrades → enchants/affixes → set bonuses → total`. Both comparisons use this same code, so they can't disagree.
- `compare(candidate, equipped, player)` is a pure function returning, per stat: base Δ, total Δ, and the resulting player-level before/after.
- **UI (`gear_compare_card`, used everywhere gear appears — loot, shop, inventory, crafting preview):** both base and total Δ visible by default per stat row; player-impact summary ("ATK 42 → 47, DEF 30 → 28"); verdict chip **Better / Worse / Mixed**.
- **Never color alone:** every delta pairs color with ▲/▼/＝ and a +/− sign.
- **Better upgraded (v0.10.1):** `Comparison.upgraded_verdict` weighs the candidate fully upgraded against what it replaces fully upgraded; `better_upgraded` (verdict not better, upgraded verdict better) draws a "⤒ Better upgraded" chip beside the set chip and a note naming what it beats.
- Edge cases: two-handed vs dual slots, multi-slot gear (compare against the slot it would replace), set bonuses gained/lost, unmet requirements flagged, effect-text diff (new/lost effects), "at max upgrade" potential line, unknown/cursed stats.
- **Built (step 5):** stats are ATK/DEF/HP (`core/gear/stats.py`; a new stat is one entry there plus content). Six slots (main hand, off hand, head, body, feet, trinket); a two-hander fills both hands, and an off-hand item replaces an equipped two-hander. Items are **snapshots** (`Item` holds its definition, roll, affixes and set bonuses), so saves don't depend on content. New worlds get the recipe's `kit` (equipped) and **finds** placed at world creation from roomset `finds` (`procgen/gear_gen.py`, its own `gear` substream, never in gate rooms). Upgrade levels are stored and shown ("fully upgraded" line) but nothing raises them until crafting (step 7). **Not yet:** unidentified/cursed gear (no identification yet); add it to `compare` when that lands. Level requirements are out: there are no levels (§13).

### 8.4b Combat (built in step 6a)
- **Enemies, not monsters:** content kind `enemies/` (`enemy.<id>`) with a `category` (beast, person, spirit); people can be enemies (wreckers, smugglers; later factions). Snapshots (`Enemy`) with pre-rolled loot, so saves don't need content.
- **Encounters:** roomset `enemies` tables place enemies at world creation (never in gate rooms) and roll each location's **wanderer queue** into a `Spawner` (`procgen/enemy_gen.py`, its own `enemies` substream). Entering a room with an enemy, or a wanderer roll on the saved `encounter_rng` (never in gates, towns, or while fleeing), starts a fight.
- **Enemies return (step 6c, `core/combat/returns.py`):** every `Rules.enemy_return_every` turns each `Spawner` under its `cap` regains one wanderer, rolled on the saved `respawn_rng` from its `templates` (`EnemyTemplate` snapshots made at world creation on a `returns.<location>` substream: stats, roll ranges, a few pre-rolled loot pieces). Loot chance is the kind's times `Rules.return_loot_factor`. Only wanderers return; cleared rooms stay clear. Saves from before v7 get templates built from the enemy snapshots left in same-kind locations (never from content).
- **Rounds** (`core/combat/fight.py`): you act first (Attack, Defend, Flee), then the enemy strikes back. Damage `max(1, ATK − DEF + d(0..⌈ATK/3⌉))`; Defend multiplies damage taken; Flee may fail (free blow) and returns you to the room you came from. Only Look is allowed mid-fight.
- **Health** is stored as damage taken (`Health`), so max HP follows gear; taking gear off never knocks you out. Regen out of fights every few turns heals `regen_fraction` of max HP (min `regen_amount`), so recovery time stays flat as HP grows; a full rest is a paid night at a town's inn (step 7a). **Defeat** wakes you at the last town's gate (`Respawn`) with part of your HP; the enemy stays at full strength.
- **Difficulty (decided, not built):** per world, chosen at creation and fixed. Rule knobs live in the `Rules` snapshot saved in `GameState` (`flee_chance`, regen, `respawn_hp`, `enemy_strength` applied at fight time, `defend_factor`); generation knobs (placement density, wanderer queues) are fixed by nature. Every world is Standard until the picker lands with the difficulty sim (step 8).
- **Codex → Foes** (`core/codex/foes.py`): an entry on first meeting; stats after 1 defeat, drops after 3; grouped by category. Every entry says where its kind is found (`FoeView.found_in`, from `Game._found_in`: place kinds holding it placed, wandering or as a returning template, by region; undiscovered regions read "places you haven't found yet"; wardens say the road they guard). Every Codex level collapses (section → group).
- **Codex → Materials, Ingredients, Recipes, Meals** (v0.10.2, `core/codex/items.py`, save schema v13): `Codex.materials` (`MaterialEntry`: a `Material` snapshot + `looted_from` enemy ids) and `Codex.meals` (`MealRecipe` snapshots) are filled by subscribers: `MaterialsGained` (loot carries `enemy_id`), `RecipeLearned` and `GameStarted` (what known recipes need), `RoomEntered` into a shop's room (a market's wares; a cooking tavern's menu and its ingredients). Recipes are `Recipes.known`. `Game.codex()` → `CodexView`: each material says where it's gathered (`Grower`s + lying spots, via `items.where`, which `_found_in` shares), dropped by (named once looted from it or its drops are known at `DROPS_AT`; else "foes you've yet to learn about"), sold at (markets by region), uses (known recipes, seen meals, upgrades for carried gear) and is grouped by its lowest-tier source region ("Further afield" if that's undiscovered); recipes say how many are still out there (pages + quest rewards). Unread keys are `(kind, id)` (`items.keys`, cheap); sections start collapsed unless they hold something new, with "New" chips on section and group headings.
- **Gear set chips:** each `gearsets/*.json` has a `color` (one of `SET_COLORS`), snapshotted into `GearSet.color`; `ui/components/set_chip.py` draws it beside the verdict chip (name always written; older items without a colour use `LEGACY_COLORS` — Drowned Watch → teal — else a colour picked from the set id). **Two-handers can complete every set** (user rule): a set's biggest bonus must be reachable without the off hand, counting a main-hand piece only if it's two-handed (`tests/content/test_content.py`); so off-hand pieces are extras at most, and 5-piece sets (a possible later change, needing a rebalance) would use head, body, feet, trinket + a 2h weapon.

### 8.4c Quests (built in step 6b)
- **Templates, not quests, are content:** `quests/<type>.json` (`quest.<type>`, one per type) holds titles, summaries and clue texts with placeholders (`QUEST_PLACEHOLDERS` per type), bounty `epithets` per enemy category and `strength`, cull `counts`, recover `items`. The world recipe's `quests` sets `per_board`, `found` and `reward_affix_chance`.
- **Generated at world creation** (`procgen/quest_gen.py`, its own `quests` substream: one sub-substream per board, one for found quests). Each town's **gate room** is its notice board (no extra room, so `world_hash` is untouched); found quests are a `Clue` in a non-gate room outside towns. Bounties (`Enemy` + `Bounty`, stats × `strength`, named "<epithet> <kind>") and recover items (`QuestItem`) go in free non-gate rooms (no other enemy). Culls only target kinds with a world supply (placed + wanderer queues) of at least 2×N. Rewards come from the target location's `finds` pool at the **highest roll**, with an affix at `reward_affix_chance`.
- **Rules** (`core/quests/quests.py`): `Quest` snapshots on their own entities; states posted/hidden → active → ready → done. Accept at that quest's own board; turn in at **any** town's board (both free actions; rejected mid-fight). A bounty beaten or an item recovered counts even before accepting; culls count kills only after accepting; explore is checked against `Explorer.rooms_visited`. Accepting (or finding) a quest discovers its target location on the world map. No abandon and no cap on active quests yet.
- **Codex:** a bounty's `Bounty.kind_name`/`kind_stats` are what the Foes codex records, so a named enemy never replaces its kind's entry.
- **UI:** a Notice board button on Explore at a town gate opens the board as a panel (compact reward line + verdict, Accept / Turn in, a toast naming the reward); a Quests tab (Ready, Active, Done; collapsible; full reward comparison cards).
- **Gold and abandoning (step 7a):** templates have a `gold` range; turning in pays it with the item. An active quest can be abandoned anywhere (free; the Quests tab asks first): a board quest goes back up as posted on its board, a found one on the board of the last town visited (`Respawn`); a cull's progress resets, a beaten bounty or found item stays achieved.
- **Later:** NPC/faction quest givers (step 13), quest chains.

### 8.5 Codex, help, and onboarding
- **Codex tabs:** Bestiary, Quest Log, Lore, Items & Recipes, Pets, Factions & Regions, Modifiers, Achievements. Every content definition has a stable ID; entries show as ??? until discovered, then **fill in progressively** (e.g. kill count reveals drop table/weaknesses).
- **Codex is generated from the same content data the game runs on**, so docs can't drift from reality. Formula text and stat definitions are pulled from actual constants.
- **Help:** Markdown articles in `content/help/` + auto-generated reference pages, with a **search** over help + codex (start with simple token/prefix scoring built at startup; no heavy dependency). Glossary terms are tappable anywhere in game text. Contextual **"?"** buttons on each screen deep-link to the relevant article.
- **Onboarding:** first run launches a skippable guided tutorial in a fixed, hand-authored mini-world covering map reading, travel, combat, gear comparison, shopping, crafting/cooking, saving. After that, **just-in-time hints** fire the first time each mechanic appears (tracked in `seen_hints`). Replayable from Settings/Help.

### 8.6 Economy: shops vs crafting vs cooking
Each system owns a distinct role so none makes the others pointless:

| System | Role | Gets what | Limits |
|---|---|---|---|
| **Shops** | Reliability & convenience | Basic gear tiers, staple consumables, raw materials, ingredients | Limited/rotating stock by region + faction rep; never sells top-tier gear or advanced recipes |
| **Crafting** | Customization & power | Upgrades, enchants, targeted gear; consumes materials from exploration | Needs recipes (discovered) + materials + sometimes stations |
| **Cooking** | Situational/temporary buffs, pet food, sustain | Biome-themed meals from foraged/bought ingredients | Buffs are shorter/more specific than shop potions; ingredient freshness/region-gated |
| **Loot/quests** | Rare finds, recipes, one-offs | Top-tier drops, recipe unlocks | RNG + progression gated |

**Balance rules, enforced mechanically:**
1. Every item has one internal **`value`** (budget). Shop buy price, craft cost, and sell price are all *derived* from it by formula.
2. Buying a craftable item costs more than gathering its materials (a "convenience tax").
3. Sell-back is a fraction of value (e.g. 25–40%) so buy→sell loops can't print money.
4. Top-tier outputs are never purchasable.
5. `sim/economy_sim.py` + a content lint **detect arbitrage loops** (buy→craft→sell profit) and "shop strictly dominates crafting" cases before they ship.
6. Gold sources/sinks scale with prestige via the same difficulty model.

**Built (step 7a):**
- **Value** (`core/economy/value_model.py`): stats at `STAT_VALUES` gold a point (`core/gear/stats.py`; a new stat needs one), plus a quarter of what remaining upgrades would add, ×1.2 in a set, at least 1. Prices are worked out when shown, never stored: buy = value × `buy_factor`, sell = value × `sell_factor` (capped below buy). These and `inn_price`, `restock_every` are the world's `EconomyRules`, a snapshot in `GameState` like `Rules`.
- **Gold:** one `Wallet` on the player; the recipe's `gold` to start. Enemies carry a rolled `gold` (content `gold` range; beasts none), bounties × `strength`, returning wanderers roll it from their template. Every gain/spend emits `GoldGained`/`GoldSpent` (not narrated; for achievements).
- **Shops** (`shops/<name>.json`, listed by roomset `shops`): each town gets one of each, in the first room whose name ends with the shop's `room` noun, else at the gate (`procgen/shop_gen.py`, its own `shops` substream, `shops_hash`). A `Shop` entity has a `Position`; wares for sale are Items with `Stocked`. Stock is plain copies (no affix, rolls in the lower half), so rewards and best finds always beat it (rule 4, linted). Shops restock one ware every `restock_every` turns up to `cap` from pre-rolled `wares` on the saved `shop_rng`. Gear you sell goes on the shop's buy-back shelf (`Shop.buyback`, only the newest `EconomyRules.buyback` stay; it doesn't count towards `cap`). Buy/Sell are free; Rest at an inn costs a turn and `inn_price`. **UI:** a board or shop is one button in the room that opens a full-screen panel like a fight (`GameScreen.opened`, UI state only; moving or a fight closes it); the Smithy panel has Buy/Sell tabs (`GameScreen.shop_tab`, back to Buy on each open), and the Inventory tab sells too. Both sell lists are a `PackList` sharing one `PackChoices` (filters + sort) per open world; Buy tabs are a `PackList` (no select mode, sorted by buy price) sharing a second one. Tavern food comes in 7c.
- **Sim/lint:** `sim/economy_sim.py` totals a world's income (start, enemy, quest gold, selling everything) against its shops' stock, and flags arbitrage and top-roll shop items; `tests/sim/` runs a quick pass, `tests/core/test_economy.py` the content lint. Standard worlds (7a): about 380 gold of income against about 100 of first stock, so gold piled up until crafting.

**Built (step 7b):**
- **Materials** (`materials/<name>.json`, `material.<name>`: name, description, `value`) are counts, not items: a `Material` snapshot in `MaterialStack`s, held in the player's `Materials` satchel. Sources: enemy `materials` drops (rolled with the enemy at creation, and from `EnemyTemplate.materials` for returning ones; the codex lists them with gear drops), roomset `gathering` (`MaterialStack` + `Position` in non-gate rooms outside towns, gathered on entering the room; `procgen/material_gen.py`, its own `gathering` substream, `gathering_hash`), and every town's **Market** (`shops/market.json`: `materials` it always sells, `buys_materials`). Market price = value × `buy_factor` × `material_markup`; it pays value × `sell_factor` (capped below).
- **Crafting** (`core/economy/crafting.py`) needs a shop that `crafts` (the Smithy; a third **Craft** tab). Upgrades: gear `upgrade_materials` (per level, × the level reached) are snapshotted into each crafting Smithy's `Shop.upgrades` (gear id → stacks), so items need no new fields; fee = value one level adds × `upgrade_fee` × level. Most gear is upgradable now (weapons to +3, the rest +2). Recipes (`recipes/<name>.json`, `recipe.<name>`: `makes`, optional `affix`, `materials`, `known`) are `Recipe` snapshots (the `Item` they make, best roll + affix, plus materials) in the player's `Recipes`; fee = made item's value × `craft_fee`. `known` recipes are taught at world creation; each other one turns up once per world (`recipes` substream, `recipes_hash`): as a quest's extra reward (`Quest.recipe`, at the world recipe's `quests.recipe_chance`) or a `RecipePage` in a wild non-gate room, learned on entering. All crafting actions are free. UI: a crafting Smithy has Buy / Sell / Upgrade / Craft tabs (no tab icons at four); Upgrade and Craft are `PackList`s sharing a third `PackChoices` ("Price" = fee), and a "Hide what I can't make" switch (`GameScreen.craftable_only`, UI state) hides upgrades and recipes short of materials; the Inventory tab has Equipped / Pack / Satchel tabs (`InventoryScreen.tab`). v0.8.1: gear and quest cards collapse to their top row + a one-line summary (`collapsed`/`on_toggle` on `gear_compare_card` and `quest_card`; actions and details such as material costs stay). `ui/components/folds.py` (`Folds`) tracks each list's collapsed cards; per-list defaults (`DEFAULTS`: long lists collapsed, equipped/ground expanded) can be changed with "Expand all / Collapse all", remembered in `Settings.collapsed` (Settings screen toggles come in step 10).
- **Sim/lint:** income now includes materials (about 480 a standard world); the sim also reports crafting fees. The lint flags any craft or upgrade that sells for more than its fee plus its materials' sale value, and any smithy-sold gear whose cheapest copy costs no more than crafting it (rule 2).

**Built (step 7c):**
- **Ingredients** are materials with `ingredient: true` (same satchel, same gathering/drops/Market plumbing): kelp, mussels, mushrooms, wild herbs, black truffle (rare) in roomset `gathering`; boar, crab and eel meat from beasts; salt and ship's biscuit at every Market. **Meals** (`meals/<name>.json`, `meal.<name>`: `ingredients`, buff `stats` and/or `regen` (extra HP per regen tick), `turns`, `sold`) are `Meal` snapshots whose `value` is their ingredients'. A Tavern that `cooks` holds every meal as a `MealRecipe` (`Shop.meals`, snapshotted at creation); Cook costs the ingredients + fee (value × `cook_fee`), and `sold` meals can be bought ready-made (value × `buy_factor` × `meal_markup`). Meals can't be sold.
- **Eating** (`core/economy/cooking.py`) is free, any time out of a fight: the meal leaves the player's `Meals` and becomes `WellFed` (one at a time; a new one replaces it). `cooking.meal_system` ticks it down each turn; at zero it wears off (health clamped, never a knock-out). The buff is a `StatSource` in the stat sheet and is included in gear comparisons; `regen` adds to `fight.regen_system`. UI: Tavern panel with Rest, a "Well fed" line and Menu / Cook tabs (the hide switch covers Cook); Satchel tab with Meals (Eat; replacing a meal asks first), Ingredients, Materials; the status row ends with "Fed: <meal> (<turns>)".
- **Regrowth (v0.8.2):** each wild location gets a `Grower` at creation (`procgen/material_gen.generate_growers`: its roomset's gathering table; `cap` ≈ non-gate rooms × chance, min 2; no RNG). `crafting.regrow_system` adds one spot per location every `EconomyRules.regrow_every` (25) turns while under the cap, in an empty non-gate room other than the player's, rolled on the saved `gather_rng`. The economy sim still counts only the starting gathering.
- **Unread dots (v0.8.2, `ui/components/unread.py`):** a dot always means "a new thing you'll find when you look" (user rule; the one exception is a quest ready to turn in, which stays until handed in). Per-part key sets (quests, codex entries, pack items, satchel kinds) are compared with what was there when you last looked (UI state; "seen" starts as everything present when the world opens). Dots: Quests (ready, or new), Codex (a new foe only, not more learned about one), Inventory (new pack/satchel) on the nav bar, and Pack/Satchel inner tabs; shop tabs dot Upgrade (affordable upgrade for worn gear), Craft and Cook (makeable) only for what's newly doable since you last looked at that tab (`GameScreen._new_doable`). No dot for a meal running out. `GameSession.listeners` lets the shell refresh dots after every command. Dots clear on arrival (on the tab that holds the new thing): `Unread.look` clears the dot but keeps those keys, so the cards behind it show a "New" chip (`new_chip`; quests, Codex foes, pack, satchel materials, meals, recipes) until `Unread.leave` on switching tabs (v0.9.0). Shop tabs do the same for newly doable upgrades, recipes and meals (`GameScreen._doable_fresh`, cleared on switching tab or opening/closing a panel). The shell tracks the tab on screen itself (`WorldShell._shown`): Flet sets `selected_index` before `on_change`. Flet only draws `badge` on icon and text controls, so dots are `dot_icon` (an `ft.Icon` with a badge) or `dot_label` (text with a badge, padded so the dot clears it) — never on destinations or segments directly.
- **Lint:** a sold meal costs more than cooking it (rule 2), and a meal's power (stat value + 3 per regen point, × turns/60) is at most `MEAL_POWER_PER_VALUE` (4) × its ingredient value, so harder meals can be stronger but never runaway.

### 8.7 Prestige pacing ("not too fast, not too slow")
Goal: the first prestige feels earned within a few sessions, later prestiges never feel like a grind wall, and every prestige brings something new.

**Levers**
1. **Milestone-gated, not timer-gated.** Ascension unlocks when the player clears a defined milestone (e.g. the current tier's final boss). Being *able* to ascend is never forced.
2. **Reward scales with progress, with diminishing returns** (e.g. prestige currency ∝ progress^0.5), so ascending early is viable and pushing a bit further is rewarding, without punishing either choice.
3. **Target time bands (starting hypotheses — tune via sim + playtests):** first prestige ≈ 3–4 hours of total play (roughly 6–10 sessions); later prestiges stay within ≈ 2–5 hours each, with a hard ceiling around 6 hours. Meta-power gains should roughly offset rising difficulty so the band holds. All constants live in data, not code.
4. **Every prestige unlocks something new** — regions, modifiers, recipes, pet slots, achievement tiers — so it's progress, not just bigger numbers.
5. **Soft adaptive assist:** after repeated deaths at the same tier, quietly nudge difficulty/drops. Capped, and switchable off in Settings.
6. **Mobile session fit:** meaningful progress in 5–10 minute sessions; natural checkpoints; autosave.

**Validation:** `sim/difficulty_sim.py` runs three bot skill profiles (casual / typical / optimal) and reports median and p90 time-to-prestige, deaths per prestige, and the gold curve. The check fails if casual p90 exceeds the ceiling or optimal play prestiges absurdly fast relative to typical. With no telemetry, the sim plus manual playtests are the only feedback loop; add a local-only **run summary** screen for players and for you.

---

## 9. Versioning & compatibility (critical because of sharing + cloud)

- **Stable content IDs, forever.** Never rename; deprecate with a replacement mapping.
- Every save/share payload carries: `schema_version`, `content_version`, `generator_version`.
- Worlds are **snapshotted**, not regenerated on load, so generator changes don't alter existing saves.
- `services/storage/migrations.py` upgrades old saves (`MIGRATIONS[n]`: envelope v`n` → v`n+1`); `tests/services/test_storage.py` opens and plays every fixture in `tests/fixtures/saves/` (one per released schema). Newer-than-supported saves are refused with a clear message. Component class names are part of the save format (`components.COMPONENTS`): renaming one needs a migration.
- Golden-seed tests: seed X + generator version Y must produce a stable world hash (`tests/core/test_procgen.py`, via `world_hash`). New worlds come from `generate_world(seed, recipe, roomsets)`, which uses the seed's `worldgen` substream; the overworld layout, location kinds, location names and each location (`location.<id>`) get their own substreams, and inside a location layout and naming are separate, so content edits to names don't reshape worlds. Gear finds come from the seed's separate `gear` substream (one sub-substream per location), pinned by their own golden hash (`finds_hash`), so they never reshape a world. Enemies come from the separate `enemies` substream (`enemies_hash`), quests from the separate `quests` substream (`quests_hash`), shops from the separate `shops` substream (`shops_hash`), gathering from `gathering` (`gathering_hash`) and found recipes from `recipes` (`recipes_hash`). Session entry point: `GameSession.generate(store, content, recipe_id, name, seed)` builds the world, kit, finds, enemies, quests, shops, gathering and recipes together.
- Every location is generated **at world creation**, never lazily on first visit, so an update can't change places a player hasn't reached yet.
- `tests/services/test_storage.py` also requires a fixture save for **every** schema version up to the current one.

---

## 10. Build, release & distribution

**Goal:** one scripted path from "done" to "updated on my phone" — bump version, tag, push, build a signed APK, publish a GitHub Release, and let **Komi Store** (an app store for GitHub releases that tracks installed apps and checks for new releases) deliver it.

### Version sources of truth
- `pyproject.toml` → `[project].version` = user-facing semver `x.y.z` (Flet `--build-version`, Android `versionName`).
- `pyproject.toml` → `[tool.flet].build_number` = integer (Android `versionCode`). **Strictly increases every release; never reused.**
- Git tag `vX.Y.Z` (pre-releases: `vX.Y.Z-beta.N`) = the release trigger and what Komi Store sees.
- App version is **separate** from `schema_version` / `content_version` / `generator_version` (§9), which describe data compatibility. Settings → About shows all of them.
- Flet's build version is plain `x.y.z`, so a beta tag builds as `x.y.z` with a higher build number; the tag + GitHub "pre-release" flag carry the beta-ness. Verified with Komi Store (Spike 7): betas are ignored unless its pre-release toggle is on, and the final `x.y.z` installs over its betas.
- `release.py` bumps from the **last final tag**: `patch --pre` repeatedly → `-beta.1`, `-beta.2`…; the same part without `--pre` promotes to the final release, whose CHANGELOG section folds in its betas' notes. It refuses an empty "Unreleased" section (except when promoting betas).
- Packaged apps don't ship `pyproject.toml`, so `release.yml` runs `release.py build-info <tag>` to write `src/tidewrack/_build_info.py` (gitignored) for the in-app version label.

### Release flow
1. Work merges to `main`; `ci.yml` runs lint, `core/` import-lint, golden-seed tests, migration tests, content validation, import fuzz tests, and quick sims.
2. Locally: `python tools/release.py patch|minor|major` (add `--pre` for a beta, `--dry-run` to preview). It refuses on a dirty tree, a non-`main` branch, or failing tests; then bumps `version` and `build_number`, promotes the CHANGELOG's "Unreleased" section, commits `release: vX.Y.Z`, tags, and pushes commit + tag.
3. The tag triggers `release.yml`: verify tag == pyproject version → run tests → restore the keystore from secrets → `flet build apk` → write a SHA-256 file → create the GitHub Release (marked pre-release if the tag has a suffix) with notes from the CHANGELOG → attach the APK + checksum → send an ntfy notification to the self-hosted server (on success, tapping it opens the app in Komi Store via `githubstore://repo/<owner>/<repo>`, with "Open in Komi Store" and "View release" buttons; on failure or cancel it opens the run logs; skipped if `NTFY_URL` is absent). It refuses to publish a debug-signed APK. Uses the built-in `GITHUB_TOKEN` with `contents: write`.
4. Phone: Komi Store's background check finds the release, notifies, and installs over the existing app (its update interval and pre-release inclusion are configurable per its settings).
5. First launch after an update: if a schema migration is needed, **snapshot every slot first**, then migrate.

Releases are **CI-built** (reproducible; the keystore never sits on a dev machine's disk during builds). A local `flet build apk` + `gh release create` fallback uses the same version files.

### Build cache
- `flet build apk` downloads Flutter, the NDK/CMake and Gradle deps every run; the `build-cache` action restores them (~6¾ → ~4¾ min). Keys follow the pinned `flet-cli` + its Flutter version, so they only change when Flet is upgraded.
- **Tag runs can only read caches saved on `main`**, so `release.yml` only restores; `warm-build-cache.yml` (Mon/Thu + manual) saves them, keeps them inside GitHub's 7-day eviction window, and smoke-tests an unsigned build of `main`. After bumping `flet-cli`, run it manually (`gh workflow run warm-build-cache.yml`).
- Only NDKs the build adds are cached (staged in `~/android-sdk-extra`, symlinked back), not the runner's preinstalled ones.
- Pinning `flet-cli` (pyproject `build` group) also pins the APK's bundled Python (highest version allowed by `requires-python`).

### Secrets (GitHub Actions)
`ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_PASSWORD` (same as the store password for PKCS12), `ANDROID_KEY_ALIAS` (`tidewrack`), `NTFY_URL` (full topic URL, `https://<server>/<topic>`), `NTFY_TOKEN` (access token with write access to that topic).

### Signing & identity (permanent decisions)
- **One release keystore**, created once, backed up in two places (password manager + offline copy), stored in GitHub as a base64 secret with its passwords as separate secrets. Never committed. Losing it means everyone must uninstall to update (cloud saves and backups soften this, but avoid it).
- **Bundle ID chosen now and never changed** (`tech.dukedigital.tidewrack`); a different ID is a different app to Android.
- **Dev builds use a different ID** (`tech.dukedigital.tidewrack.dev`) so they install side-by-side and don't confuse Komi Store's tracking.
- Create the keystore and fix the bundle ID **before** registering any Google OAuth credentials (Google may tie Android credentials to package name + signing fingerprint).

### Asset conventions
- **One APK per release** with a consistent name pattern (e.g. `tidewrack-<version>-arm64-v8a.apk`) plus a `.sha256`. Komi Store can pin the specific asset variant it installed, so don't change the architecture/naming scheme later.
- The repo is **public** (secrets stay in Actions). Private-repo support in Komi Store is unverified.
- **App icon:** `src/assets/icon.png` (transparent art, used for splash/desktop/web) and `src/assets/icon_android.png` (same art padded to ~60% of the canvas, used as-is for Android so launcher masks don't clip it). `icon_background` and the splash colours are black. Flet does **not** pad a generic `icon.png` for Android adaptive icons; preview with `flet_platform_assets.render_icons` before shipping new art.

### Rules
- **Roll forward, never back.** A bad release is fixed by a higher version + build number; never reuse or delete-and-republish a build number.
- Never ship a build that can't read the previous release's save schema (§9 migration tests enforce this).

---

## 11. Conventions

- **All randomness via `core/rng.py`** — no bare `random` anywhere else (a test enforces it). RNG state is saved. It's our own xoshiro256** so results don't depend on the Python version (CI runs 3.12, the APK bundles 3.14); changing its output means bumping `generator_version`. Give each subsystem its own `rng.derive("name")` substream so one system's draws never shift another's.
- **Turn loop delivery order:** a command's events (and subscribers' follow-ups) are delivered first, then per-turn systems run, then `TurnEnded`. The UI only calls `Game.perform(command)` and reads `Game.view()`.
- **Content is data, not code.** New monster/item/pet/recipe = new data file unless behavior truly diverges.
- **Loading content:** `core/data/loader.py` is pure (takes `{relative path: text}`), so it never reads files; `services/content` does the reading. A new content kind = a schema in `schemas.py` + an entry in `loader.KINDS`. Schemas reject unknown keys, and all problems are reported together with file paths; `tests/content/` validates every bundled file in CI. The app shows load errors on screen instead of crashing.
- **`core/` is pure.** No UI/IO imports, clock or system randomness; enforced by `tests/core/test_purity.py`.
- **Never use `page.run_thread`** (Flet 1.0.5): when Android rebuilds the window (e.g. a new system palette), Flet shuts its shared executor down and keeps using it, so jobs are silently dropped. Start a `threading.Thread` (see `ui/theme.py`). After such a rebuild `main()` runs again in the same process; `App.start` reopens the world that was open.
- **Subscribe, don't reach in.** New cross-cutting features (achievements, tutorial hints, codex) hook the event bus.
- **Difficulty and economy are validated by simulation**, not by feel.
- **Accessibility is default:** never color-only signaling; scalable text; large touch targets.

---

## 12. Risks — spike these before building on them

1. **Mobile Google OAuth.** Flet's built-in OAuth supports Google and works on mobile via an in-app web browser, but its documented setup uses a client secret, which would ship inside the app. Confirm PKCE/no-secret flow is possible; and confirm Google accepts the in-app browser flow (Google has restricted OAuth in embedded webviews — verify on a real device). Fallback: Firebase Auth, or a minimal token-exchange function.
2. **Drive `appDataFolder` from Python on-device** — read/write/list with a thin REST client; test token refresh and offline→online transitions.
3. ✅ **Done (v0.3.0).** **Canvas map performance** — a 60-room map with fog of war ran with no lag on a Galaxy S24 Ultra. Caveat: that's not a low-end phone; recheck on one if players report lag. Generating 60 rooms takes ~8 ms on desktop.
4. **Pyodide dependency check** (only if web is pursued) — verify `scipy`, `pydantic`, `markovify`, `opensimplex`; time worldgen in-browser.
5. **Share/import plumbing** — file picker, share sheet, clipboard, QR on mobile through Flet.
6. **Search quality/perf** of the in-app help index on mobile.
7. ✅ **Done (v0.0.1–v0.0.3).** **End-to-end Komi Store update cycle.** Install v0.0.1 via Komi Store, publish v0.0.2 from CI, and confirm detection, in-place update, and how tag / versionName / build-number comparisons behave (including the pre-release toggle and asset-variant pinning).
8. ✅ **Done** — keystore created and backed up in two places; bundle ID fixed. **Signing-identity lock-in.** Keystore and bundle ID are permanent; changing either breaks in-place updates. Create and back them up before any OAuth client registration.

---

## 13. Decisions

**Settled**
1. **Meta-progression and achievements are per world slot.**
2. **Pets persist across prestige** (rare finds; balanced by a power cap and soft pity — §8.1).
3. **iOS is not targeted for now.** Android first; revisit later (if added, check Apple's rules for apps that offer third-party sign-in).
4. **Prestige pacing** targets a middle path — neither fast nor slow (§8.7).
5. **Distribution** via GitHub Releases + Komi Store (§10).
6. **CI-built releases** (§10).
7. **Public repo**, **MIT** licensed.
8. **arm64-only APK**, fixed from the first release (`[tool.flet.android] target_arch`).
9. **No XP or character levels** (decided at step 7). Power comes from gear, crafting upgrades, cooking buffs, pets and prestige; gear requirements stay out.
10. **Shops live in themed town rooms with a gate fallback** (Smithy, Tavern; Market in 7b), so every town has one of each and layouts don't change.
11. **Content lives in `src/content/`** (bundled by `flet build`). Files are `<kind>/<name>.json`; each holds the ID `<prefix>.<name>` (e.g. `dungeons/first_descent.json` → `dungeon.first_descent`).

12. **Prestige = a new world in the same slot** (decided at step 8). Keeps prestige rank, achievements, pets and codex knowledge; resets gear, gold, materials, quests and the map. **Ascending needs an in-story reason** (user requirement): work out the lore with 8c.
13. **Regions are clusters on the one world map** (decided at step 8): nearby locations share a region/biome, deeper regions are tougher, and region names show when zoomed out. No extra world → region map level.
14. **Difficulty = a picker at world creation + prestige tier** (decided at step 8): Easy / Standard / Hard is fixed per world (§8.4b); prestige tier stacks on top; the difficulty sim checks every combination against the §8.7 bands.

**Still open**
1. Other SSOs at launch or later? Recommended: Google only at launch; the `CloudProvider` interface makes others additive.
2. Do shared worlds carry modifiers/difficulty settings? Recommended: yes, as world params.

---

## 14. Build order (MVP-first)

0. ✅ **Done (v0.0.3).** **Pipeline first.** Repo, `pyproject.toml`, bundle ID, release keystore, `ci.yml`, `release.yml`, `tools/release.py`, and a hello-world Flet app that shows its version — shipped end-to-end through GitHub Release → Komi Store → phone, with one real update cycle. (Spikes 7–8.)
1. ✅ **Done (v0.1.0).** **Core skeleton:** ECS + event bus + turn loop + seeded RNG + one hand-authored dungeon. Import-lint test for `core/` purity.
2. ✅ **Done (v0.1.1).** **Data layer:** pydantic schemas + content loader + content validation tests.
3. ✅ **Done (v0.2.0).** **Local persistence:** `SaveStore`, multiple local slots, autosave, schema versioning, slot picker UI.
4. ✅ **Done (v0.3.0).** **World graph + map:** hand-rolled seeded generation, canvas point-crawl, fog of war. (Spike 3.)
   - ✅ **Done (v0.3.0).** **4b. World → locations → rooms:** overworld of locations (towns, forests, mines, sea caves) joined by roads, travel from gate rooms, area + world maps, save schema v3 with migration; plus pinch-zoom/pan maps, a scrolling game screen and a collapsible, resizable log (first app-wide setting).
5. ✅ **Done (v0.4.0).** **Gear:** stat pipeline + compare + `gear_compare_card` + inventory/equip. ATK/DEF/HP, six slots, starting kit + seeded finds, take/drop/equip/unequip, inventory tab with pack filters, bulk drop and drop confirmation, save schema v4 with migration, generator v3. Also: Material 3 navigation bar (`ui/shell.py`), gate and kind markers on the maps.
6. **Combat + quests + codex discovery**, in two parts:
   - ✅ **Done (v0.5.0).** **6a. Combat + Foes codex:** round-by-round fights, placed + wandering enemies (beasts, people, spirits), loot, health/regen/rest, defeat → last town, `Rules` snapshot for future difficulty, Codex tab. Save schema v5, generator v5 (items record their set's chip colour). The explore screen's bottom row now shows only turn/rooms/places; a fight hides the map; gear actions refused mid-fight toast their reason; Codex sections and groups are collapsible (`ExpansionTile`, state kept per world while open). Pack sorting (name/ATK/DEF/HP/verdict, either direction; now `components/pack_list.sort_pack`, which also sorts by sale price) applies after the filters.
   - ✅ **Done (v0.6.0).** **6b. Quests + quest log:** notice boards at town gates, found clues, bounty/cull/explore/recover, gear rewards, Quests tab; world-map ✓/◆ and area-map ✦/◆ marks. Save schema v6 (new components only; old worlds have no quests), generator v6.
   - ✅ **Done (v0.6.1).** **6c. Enemies return:** wanderer queues refill slowly (one per location every 30 turns up to the starting size; rate and loot factor in `Rules`; rolled from a saved stream and enemy templates snapshotted into each `Spawner`), so late culls stay possible and worlds don't empty out. Save schema v7 (migration builds templates from snapshots), generator v7. v0.6.2: world-map taps away from a gate say where you can leave from.
7. **Economy**, in three parts (decided at the start of step 7):
   - ✅ **Done (v0.7.0).** **7a. Gold, value model, shops** (betas 1–4 added full-screen board/shop panels, Smithy Buy/Sell tabs with filters and sort): `Wallet`, enemy/quest gold, Smithy + Tavern in every town, buy/sell (bulk sell in the Inventory's select mode), paid inn rest (replaces free town rest), restocking, quest abandoning, area-map ¤ mark, economy sim + lint. Save schema v8 (migration gives old worlds gold and shops from their own snapshots), generator v8.
   - ✅ **Done (v0.8.0).** **7b. Materials + crafting** (betas 2–3 added Inventory tabs and Smithy Upgrade/Craft tabs with filters and a hide switch): materials (enemy drops, gathering, Market), Smithy Craft tab with upgrades and recipes (4 known, 6 found as pages or quest rewards), buy-back shelf (last 6 sold), crafting lint (rule 2 + no craft/upgrade profit loops). Save schema v9 (migration: satchel, starting recipes, Markets, upgrade tables, gear made upgradable, overfull shelves trimmed), generator v9.
   - ✅ **Done (v0.8.2).** **7c. Cooking** (beta.2 added regrowth, unread dots and a collapsible Satchel; beta.3 fixes made dots mean "new" only): ingredients (gathered, beast drops, Market staples), Tavern kitchens (Menu + Cook), 7 meals incl. two multi-stat ones, one buff at a time for N turns (stats or regen), meal lint (rule 2 + power budget). Save schema v10 (migration: pantry, kitchens, staples, `ingredient` on materials), generator v10; v11 adds gathering regrowth (`Grower`, migration gives every wild place one), generator v11.
   - ✅ **Done (v0.9.1).** **UI patch** (v0.9.0–v0.9.1 betas): Material You on Android 12+ (pyjnius; window rebuilds reopen the open world); "New" chips behind cleared dots; the Tidewrack logo on the world picker; a menu button (Switch world, later Settings/Help) replacing the top-left back arrow; coins for prices and rewards (`ui/components/coins.py`: `coins(text)` draws each "N gold" as N + `PAID`, `purse(n)` your total with the same coin tinted gold (one icon only, so nobody reads it as a second currency); toasts, dialogs and the log keep the word; tests read labels with `label_of`); brightness-aware greens/golds (`theme.good()`, `theme.gold()`). v0.9.1: Android's back gesture is caught on the root view (`can_pop=False` + `on_confirm_pop`, `App.back`): another tab → Explore, an open panel → closed, then the world list; on the list `confirm_pop(True)` leaves the app. Also world renaming (`GameSession.rename`: new revision, same `updated_at`), the log's latest-action lines in bold under a divider (`Game.log_total`, not saved), and an instant log jump on opening (`auto_scroll_animation=0`; new lines keep Flet's glide).
8. **Prestige + difficulty + achievements**, in four parts (decided at the start of step 8; §13 settled 12–14):
   - **8a. Bigger world** (decided at the start of step 8; betas 1–2 ✅ done in v0.10.0 and v0.10.1): a standard world is **~28 places in 4 regions** (~7 each, ~400 rooms), clustered on the one world map, from the coast inward: **Wrack Coast** (tier 1: today's harbours, sea caves, forest, mine) → **Fens** (tier 2: stilt villages, peat bogs, reed mazes) → **Moors** (tier 3: hill farms, barrows, standing stones) → **Highlands** (tier 4: crag forts, pine passes, deep mines, a drowned king's hall). Each region brings its own place kinds, towns, enemies, materials, ingredients and gear. **A region warden** (a boss at the gate of the border place) guards every road into the next region; beating it opens the region (the last warden is the natural 8c milestone). Saves grow ~4×, so autosave is split by location. Big-map handling: level-of-detail labels, region names zoomed out. **Sub-locations** ride along (enterable mansions, towers… as nested locations with a parent room instead of roads, some generated hidden until a quest reveals them). Planned as betas: (1) regions, wardens, coast + **Fens** (14 places); (2) **Moors** + autosave split by location (14 places already doubled autosave to ~67 ms on desktop); (3) **Highlands** (28 places) + big-map handling; (4) sub-locations.
     - **Built (8a beta 1):** `regions/<name>.json` (`region.<name>`: biome `name`, `tier`, world `names`, `town` roomset for its first place, `roomsets` weights, `warden` enemy, `crossing` text); world recipes list `regions` (coast first, tiers rising, every later one with a warden; linted). `grid.grow_regions` grows each region as a cluster from beside the deepest part of the one before (northward), with loops only inside a region, so exactly one road joins neighbours (retries on a fresh substream, then a bigger grid, if a region boxes itself in). `Overworld.regions` (`Region`: id, name, kind, tier), `Location.region` and `Location.town` (towns are flagged, no longer found by the kind name "Town"; roomset `town: true`). `Overworld.borders()` = roads into a deeper region. **Wardens** (`procgen/enemy_gen.generate_wardens`, own `wardens` substream, `wardens_hash`): an `Enemy` + `Warden(region, road, crossing)` at the near side's gate; never ambushes (`fight.encounter` skips it), `Travel` along its road calls `fight.challenge` (`WayBarred`, then a normal fight; fleeing keeps you at the gate), beating it emits `RegionOpened`. Quests: boards target their own region; `found` quests are per region. UI: `RoadView.guard/region` ("· into The Sallow Fens (the Reed Warden bars the way)"), `MapNode.guarded` (⚔ in labels), `MapView.regions` (`RegionMark`s, drawn faint behind the world map when there are 2+ regions), "You cross into …" in the log. Save schema v12 (migration: one Wrack Coast region, `town` from the kind), generator v12.
     - **Built (8a beta 2, v0.10.1):** the **Moors** (tier 3, 7 places, 21 in a standard world): `hill_farm` town (Fold Gate; Smithy/Tavern/Market; `moor_smithy`, `moor_market` with oatmeal), `heath`, `barrow_downs` ("Barrows"), `standing_stones`; foes moor wolf, feral ram, moor adder, highwayman, barrow wight, black dog; the **Barrow Warden** (atk 19, def 9, hp 70) on "the drove road" from the Fens. Gear hanger, barrow blade, stone maul (2h), hide targe, wolfskin hood, drover's coat, hobnail boots, hagstone; materials wool, wolf pelt, adder skin, flint, grave silver; ingredients mutton, bilberries, heather honey, oatmeal; found recipes stone maul, drover's coat, hobnail boots, hagstone; meals Drover's Hotpot and Honey Oatcakes (sold). Map glyphs ⚘ Heath, ∩ Barrows, Π Standing Stones; Hill Farm is ⌂ and listed as Town (`LEGEND_NAMES`). Autosave split by place (§6). Generator v13; save schema unchanged (v12). Beta 3: every region gets one place of each of its non-town roomsets before weighted draws (`world_gen._kinds`, shuffled), generator v14. v0.10.1 also shipped: maps open zoomed in and keep each map's zoom, a hideable legend, outlined/tinted map buttons, a tighter status row, the "Better upgraded" chip (§8.4) and where-found lines in the Codex (§8.4b).
     - **Playtest calibration (v0.10.1):** the Reed Warden felt right; the Barrow Warden was *barely* beaten without meals in mixed Fens + coast gear (worn for the Drowned Watch bonus); the coast and Fens are far too easy, while the Moors (nearly dying until you have Moors gear, bounties hit hard) is the target feel. Feed this into 8b. User wish for later content: 2–3 gear sets per region plus legendary sets needing materials from every region.
     - ✅ **Done (v0.10.2).** **A fuller Codex** (§8.4b; playtested in beta 1: meals all appear at the first tavern, droppers named only once looted or drops known, sections start closed — all confirmed by the user), before the Highlands (user: the world is big enough that it's hard to keep track of). New sections for materials, ingredients, recipes and meals, per §8.5: entries appear on discovery and fill in (where each comes from: places that gather it, foes that drop it, markets that sell it; what uses it: recipes, upgrades, meals; meal buffs), driven by event subscribers; a new entry gets an unread dot, more learned about an existing one doesn't. Then 8a beta 3 (Highlands, 28 places, big-map handling) as v0.11.0 betas.
     - **Built (8a beta 3, v0.11.0 betas):** the **Highlands** (tier 4, 7 places, 28 in a standard world, ~380 rooms): `crag_fort` town (Fort Gate; `crag_smithy`, Tavern, `crag_market` with barley), `pine_pass`, `deep_mine`, `drowned_hall` (a drowned king's hall in a loch; the drowned king is unused lore for 8c's story). Foes wildcat, golden eagle, cave bear, reiver, knocker, kelpie, drowned thane; the **Crag Warden** (atk 25, def 12, hp 90) on "the high pass" from the Moors. Gear broadsword, thane's sword, claymore (2h), studded targe, steel bonnet, feathered bonnet, bearskin cloak, mail byrnie, hill brogues, cairngorm brooch; the second gear set, **Crag Guard** (indigo: bonnet, byrnie, brogues; 2: +1 ATK +2 DEF, 3: +8 HP). Materials coal, silver ore, pine resin, bear pelt, eagle feather, sinew, river pearl, drowned gold; ingredients bear meat, trout, cloudberries, pine nuts, barley; found recipes claymore, mail byrnie, hill brogues, cairngorm brooch; meals Bear Stew, Trout and Bannock (sold), Cloudberry Cranachan (uses Moors oatmeal and honey). Glyphs ⌂ Crag Fort (Town), Λ Pine Pass, ⚒ Deep Mine (legend: Mine), ♛ Drowned Hall. **Calibrated by a fight Monte Carlo** (maxed best-in-slot loadouts, the real `damage()`): maxed Moors gear loses ~4–22% HP per Highlands foe (maxed Fens vs the Moors: 2–10%), and beats the Crag Warden ~91% of the time at ~75% HP lost, ~38% with a Drover's Hotpot (maxed Fens vs the Barrow Warden: 55%, 25% fed): a real test with meals as the edge. Big-map handling in `map_canvas` (§3). Generator v15; save schema unchanged (v13); existing worlds keep three regions. Next: beta 4, sub-locations.
   - **8b. Difficulty:** Easy/Standard/Hard picker at creation, tier scaling (enemies, rewards, **meal buffs** so cooking stays worthwhile), `sim/difficulty_sim.py` against the §8.7 bands (count regrowth in the economy sim too).
   - **8c. Prestige:** milestone, ascension into a new world in the same slot, what carries over, the in-story reason for ascending.
   - **8d. Achievements** with prestige-scaling tiers (§8.2).
   - **Unplaced** (fit in where they suit): gathering quests ("bring N of a material"); more gear sets (2–3 per region, legendary cross-region sets). The Settings About section and status-row toggle wait for step 10.
9. **Pets** (rarity, soft pity, persistence).
10. **Settings screen, onboarding tutorial, searchable help** (write help articles as mechanics land).
11. **Share/import.**
12. **Cloud sync** (Spikes 1–2 done earlier; implement after the local flow is solid).
13. **Factions/events + Markov lore polish, and a real story (user requirement).** Each world needs an immersive, generated story that's worth reading: right now you can rush through without reading anything. Story should drive play (factions, events, quest chains with stakes, places and NPCs that matter), not sit beside it as flavour text.
14. **Web build** (if desired) — only after the core is proven portable.

# CLAUDE.md — Tidewrack: Project Context & Architecture (v3)

Orientation file for an AI coding assistant (or future-you) working in this repo. It is a **no-code** architecture reference: constraints, directory layout, subsystem responsibilities, feature specs, conventions, risks, and build order. Implementation lives in `src/`.

---

## 1. What this project is

**Tidewrack** is a **text-based, procedurally generated roguelike RPG** in Python + Flet. Android-first, with a possible web build. No tile grid, no line-of-sight, no pathfinding — the world is graphs and data, presented as prose plus a schematic point-crawl map.

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
| UI | **Flet** (Material Design 3) | Theming via MD3 seed color; light/dark/system |
| Map rendering | Flet `canvas` | Draws the networkx world graph as a point-crawl diagram |
| World structure | `networkx` | Dungeons and overworld as weighted graphs |
| Overworld regions | `scipy.spatial.Voronoi` | Verify Pyodide availability if web is pursued |
| Biomes | `opensimplex` | Coherent noise → biome per region |
| ECS | In-house (`core/engine/ecs.py`) | Instance-based, insertion-ordered `World`. Chosen over `esper` 3.x, whose state is module-global (bad for tests, multiple slots, save/load) |
| Names/lore | `markovify` (+ `Faker` stopgap) | Late polish pass |
| Dice | `d20` | Dice-notation rolls |
| Validation | `pydantic` | All content + save + import payloads |
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

**Event bus** (`core/engine/events.py`) is the spine: the engine emits typed events (`EnemyKilled`, `ItemCrafted`, `NodeDiscovered`, `QuestCompleted`, `PetBonded`, `GoldSpent`, …). Achievements, codex discovery, quest tracking, and tutorial hints are all **subscribers** — they never reach into engine internals.

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
│       ├── release.yml              # tag → signed APK → GitHub Release → Pushover
│       └── warm-build-cache.yml     # Mon/Thu on main: fills + refreshes build caches
├── tools/
│   └── release.py                   # bump version/build_number, changelog, tag, push
├── art/                             # source artwork (not bundled into the APK)
├── content/                         # All game content as data
│                                    #   ⚠ Flet only bundles src/ — move under src/
│                                    #   (or change [tool.flet.app]) before step 2
│   ├── monsters/
│   ├── items/
│   │   ├── gear/
│   │   ├── consumables/
│   │   └── materials/               # incl. cooking ingredients
│   ├── recipes/
│   │   ├── crafting/
│   │   └── cooking/
│   ├── shops/                       # shop archetypes, stock rules
│   ├── pets/
│   ├── factions/
│   ├── quests/
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
│   │   ├── world/                   # dungeon.py (point-crawl map model);
│   │   │                            #   first_descent.py (hand-authored, → content/ in step 2)
│   │   ├── procgen/                 # world_graph, biomes, names, quests, factions, pets, lore
│   │   ├── gear/                    # stat_pipeline.py, compare.py
│   │   ├── economy/                 # value_model.py, shops.py, crafting.py, cooking.py
│   │   ├── progression/             # prestige.py, achievements.py, difficulty.py
│   │   ├── codex/                   # discovery tracker, bestiary/lore/quest-log models,
│   │   │                            #   help index + search, glossary
│   │   ├── data/                    # schemas.py (pydantic), loader.py
│   │   └── rng.py                   # own xoshiro256** stream; derive() substreams
│   ├── services/                    # platform adapters behind interfaces
│   │   ├── storage/                 # SaveStore interface; file backend; browser backend
│   │   ├── cloud/                   # CloudProvider interface; google_drive/; sync_engine.py;
│   │   │                            #   conflict.py  (onedrive/ later, same interface)
│   │   ├── auth/                    # OAuth wrappers, token storage
│   │   ├── share/                   # world/save export + import codec, validation
│   │   └── settings/                # settings model + persistence
│   └── ui/
│       ├── app.py                   # routing / navigation shell
│       ├── theme.py                 # MD3 theming, palettes (incl. colorblind-safe)
│       ├── components/              # gear_compare_card, stat_delta, tier_progress, toast, …
│       ├── map_canvas.py            # point-crawl renderer + fog of war
│       └── screens/                 # sign_in, slot_picker, game, map, inventory, shop,
│                                    #   crafting, cooking, pets, achievements, codex,
│                                    #   quest_log, help, settings, tutorial
├── sim/                             # headless harnesses
│   ├── difficulty_sim.py
│   └── economy_sim.py               # arbitrage + shop-vs-craft balance checks
└── tests/
    ├── core/                        # golden-seed tests, compare tests, economy lint
    ├── services/                    # sync/conflict tests, import fuzz tests
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
- **World slot (self-contained):** world snapshot, player, prestige, achievements, codex discoveries, pets, quests, RNG state, schema + content versions. Each slot is one file (`slot_<uuid>.json.gz`).
- `manifest.json` lists slots with `name`, `updated_at`, `revision`, `device_id`, `content_hash`.

### Sync rules
- **Offline-first:** local files are the source of truth; sync is background and failure-tolerant.
- Each slot syncs independently.
- Track `last_synced_revision` per slot. If **only one side changed** → fast-forward. If **both changed** → conflict.
- **Never silently overwrite.** Conflict dialog: *Keep this device / Keep cloud / Keep both (duplicate slot)*, showing playtime, prestige, last-played for each side.
- Keep rolling local backups (last N autosaves per slot) and one prior cloud revision where the provider allows.
- Autosave on meaningful events (node change, combat end, shop/craft transaction), not just on exit — mobile apps get killed.

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
- **Gameplay:** text speed, auto-advance, combat-log verbosity, confirm-destructive-actions, tooltips/hints on-off.
- **Tutorial:** replay onboarding, reset contextual hints.
- **Sound/haptics** (if added), **About** (version, licenses, privacy statement).

### 8.4 Gear comparison (base **and** total)
- **Single stat pipeline** (`core/gear/stat_pipeline.py`): `base (def + roll) → upgrades → enchants/affixes → set bonuses → total`. Both comparisons use this same code, so they can't disagree.
- `compare(candidate, equipped, player)` is a pure function returning, per stat: base Δ, total Δ, and the resulting player-level before/after.
- **UI (`gear_compare_card`, used everywhere gear appears — loot, shop, inventory, crafting preview):** both base and total Δ visible by default per stat row; player-impact summary ("ATK 42 → 47, DEF 30 → 28"); verdict chip **Better / Worse / Mixed**.
- **Never color alone:** every delta pairs color with ▲/▼/＝ and a +/− sign.
- Edge cases: two-handed vs dual slots, multi-slot gear (compare against the slot it would replace), set bonuses gained/lost, unmet requirements flagged, effect-text diff (new/lost effects), "at max upgrade" potential line, unknown/cursed stats.

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
- `services/storage/migrations/` upgrades old saves; migration tests run against fixture saves from every released schema.
- Golden-seed tests: seed X + generator version Y must produce a stable world hash.

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
3. The tag triggers `release.yml`: verify tag == pyproject version → run tests → restore the keystore from secrets → `flet build apk` → write a SHA-256 file → create the GitHub Release (marked pre-release if the tag has a suffix) with notes from the CHANGELOG → attach the APK + checksum → send a Pushover notification (success links the release, failure links the logs; skipped if the `PUSHOVER_*` secrets are absent). It refuses to publish a debug-signed APK. Uses the built-in `GITHUB_TOKEN` with `contents: write`.
4. Phone: Komi Store's background check finds the release, notifies, and installs over the existing app (its update interval and pre-release inclusion are configurable per its settings).
5. First launch after an update: if a schema migration is needed, **snapshot every slot first**, then migrate.

Releases are **CI-built** (reproducible; the keystore never sits on a dev machine's disk during builds). A local `flet build apk` + `gh release create` fallback uses the same version files.

### Build cache
- `flet build apk` downloads Flutter, the NDK/CMake and Gradle deps every run; the `build-cache` action restores them (~6¾ → ~4¾ min). Keys follow the pinned `flet-cli` + its Flutter version, so they only change when Flet is upgraded.
- **Tag runs can only read caches saved on `main`**, so `release.yml` only restores; `warm-build-cache.yml` (Mon/Thu + manual) saves them, keeps them inside GitHub's 7-day eviction window, and smoke-tests an unsigned build of `main`. After bumping `flet-cli`, run it manually (`gh workflow run warm-build-cache.yml`).
- Only NDKs the build adds are cached (staged in `~/android-sdk-extra`, symlinked back), not the runner's preinstalled ones.
- Pinning `flet-cli` (pyproject `build` group) also pins the APK's bundled Python (highest version allowed by `requires-python`).

### Secrets (GitHub Actions)
`ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_PASSWORD` (same as the store password for PKCS12), `ANDROID_KEY_ALIAS` (`tidewrack`), `PUSHOVER_APP_TOKEN`, `PUSHOVER_USER_KEY`.

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
- **`core/` is pure.** No UI/IO imports, clock or system randomness; enforced by `tests/core/test_purity.py`.
- **Subscribe, don't reach in.** New cross-cutting features (achievements, tutorial hints, codex) hook the event bus.
- **Difficulty and economy are validated by simulation**, not by feel.
- **Accessibility is default:** never color-only signaling; scalable text; large touch targets.

---

## 12. Risks — spike these before building on them

1. **Mobile Google OAuth.** Flet's built-in OAuth supports Google and works on mobile via an in-app web browser, but its documented setup uses a client secret, which would ship inside the app. Confirm PKCE/no-secret flow is possible; and confirm Google accepts the in-app browser flow (Google has restricted OAuth in embedded webviews — verify on a real device). Fallback: Firebase Auth, or a minimal token-exchange function.
2. **Drive `appDataFolder` from Python on-device** — read/write/list with a thin REST client; test token refresh and offline→online transitions.
3. **Canvas map performance** — render/update a ~60-node graph with fog of war on a low-end phone.
4. **Pyodide dependency check** (only if web is pursued) — verify `networkx`, `scipy`, `pydantic`, `markovify`, `opensimplex`; time worldgen in-browser.
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

**Still open**
1. Other SSOs at launch or later? Recommended: Google only at launch; the `CloudProvider` interface makes others additive.
2. Do shared worlds carry modifiers/difficulty settings? Recommended: yes, as world params.
3. Where `content/` lives so it's bundled (see §5 note). Recommended: under `src/` (e.g. `src/content/`), decided at the start of step 2.

---

## 14. Build order (MVP-first)

0. ✅ **Done (v0.0.3).** **Pipeline first.** Repo, `pyproject.toml`, bundle ID, release keystore, `ci.yml`, `release.yml`, `tools/release.py`, and a hello-world Flet app that shows its version — shipped end-to-end through GitHub Release → Komi Store → phone, with one real update cycle. (Spikes 7–8.)
1. **Core skeleton:** ECS + event bus + turn loop + seeded RNG + one hand-authored dungeon. Import-lint test for `core/` purity.
2. **Data layer:** pydantic schemas + content loader + content validation tests.
3. **Local persistence:** `SaveStore`, multiple local slots, autosave, schema versioning, slot picker UI.
4. **World graph + map:** networkx generation, canvas point-crawl, fog of war. (Spike 3.)
5. **Gear:** stat pipeline + compare + `gear_compare_card` + inventory/equip.
6. **Combat + quests + codex discovery** (bestiary/quest log first).
7. **Economy:** value model, shops, crafting, cooking + economy sim/lint.
8. **Prestige + difficulty + achievements** (tier scaling) + difficulty sim against the §8.7 pacing bands.
9. **Pets** (rarity, soft pity, persistence).
10. **Settings screen, onboarding tutorial, searchable help** (write help articles as mechanics land).
11. **Share/import.**
12. **Cloud sync** (Spikes 1–2 done earlier; implement after the local flow is solid).
13. **Factions/events + Markov lore polish.**
14. **Web build** (if desired) — only after the core is proven portable.

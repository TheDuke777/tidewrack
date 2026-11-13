# Tidewrack

A text-based, procedurally generated roguelike RPG for Android, built in Python + Flet.

> **This is an unabashedly vibe-coded project.** It's an experiment in building a
> complete app mostly by directing an AI coding assistant. The design, code, and
> docs are AI-written under human direction. Expect rough edges, and don't take
> anything here as a model of best practice. It's a hobby experiment, not a product.

## Concept

Every world is generated from systems and data: a map of towns, forests, mines and caves joined by roads, each with its own rooms to explore — and later quests, factions, lore, and companions. Runs end, but progress carries forward through an ascension/prestige loop with scaling difficulty and scaling achievements. There's no tile grid — the game is read and chosen — but a schematic map keeps the world easy to understand without drawing your own.

## Principles

- **Offline-first.** The whole game works without a connection. Cloud sync is optional.
- **No ads, no in-app purchases, no premium currency.** One in-game currency, earned by playing.
- **No multiplayer.** Share worlds with friends as files or codes — no servers involved.
- **Your data stays yours.** Cloud saves live in your own cloud account's private app folder. No telemetry by default.
- **No outside guides needed.** Tutorial, codex, and searchable help are built in.

## Planned features

- **Cloud sync** of your worlds across devices, with optional Google sign-in
- **World sharing** — export/import worlds (and full save backups) between friends
- **Discoverable pets** with roles (fighter, scout, forager, hauler, support) and a bond system
- **Achievements with scaling tiers** that grow as you prestige
- **Gear comparison** showing base and total stat differences — plus the effect on your character — at a glance
- **Crafting, cooking, and shops** designed to complement rather than replace each other
- **Codex** (bestiary, quest log, lore, modifiers, recipes, pets) that fills in as you discover things
- **Onboarding tutorial and searchable in-app help**
- **Settings** for theme, accessibility, cloud sync, import/export, and gameplay options
- **Material Design 3** UI; Android first, with desktop and a possible web build (iOS isn't currently planned)

## Status

Early and playable as an explorer: generate a world, walk its rooms, and travel between its locations on two fog-of-war maps (pinch to zoom, tap to move). Worlds save automatically into multiple local slots, with backups. Gear is in: find it in rooms, compare it against what you have on, and equip it across six slots. Fight beasts, people and spirits round by round, and track what you've learned about them in the Codex; wandering enemies slowly come back. Take quests from town notice boards (or find them in the wild) for gear and gold. Spend gold at each town's smithy and on a bed at its tavern, and sell what you don't need. Gather materials and ingredients from beasts, wild places (they grow back) and markets, then upgrade your gear or craft new pieces at a smithy from recipes you know or find, and cook meals at a tavern for buffs that last a while. Dots on the tabs point out anything new. Worlds now span three regions (the coast, the Fens and the Moors, 21 places), each tougher than the last and guarded by a warden you must beat to cross into it. Next up: a fuller Codex (materials, ingredients, recipes and meals), the Highlands, then difficulty, prestige and achievements; pets, settings, help and a real story come after.

Release pipeline is live (signed APKs via GitHub Releases + Komi Store). See [`CLAUDE.md`](./CLAUDE.md) for the full architecture, feature specs, risks, and build order.

## Tech stack

Python · Flet · pydantic, with a small in-house ECS and seeded generators (no NumPy/SciPy). Later: markovify (names/lore), opensimplex (biomes).

## Install & updates

Releases are published as signed APKs on this repo's GitHub Releases page. The easiest way to install and stay current is [Komi Store](https://github.com/kurikomi-labs/komi-store), which tracks GitHub releases and updates apps for you. You can also download the APK directly.

## Development

Requires Python 3.12+.

```bash
python -m venv env_tidewrack && source env_tidewrack/bin/activate
pip install --upgrade pip
pip install flet --group dev --group ci
flet run                      # desktop dev loop with hot reload
pytest -q && ruff check .     # what CI runs
```

Releases are cut with `python tools/release.py patch|minor|major` (`--pre` for a beta,
`--dry-run` to preview); pushing the tag builds and publishes the signed APK. See
[`CLAUDE.md`](./CLAUDE.md) §10 for the full build and release process.

## License

[MIT](./LICENSE).

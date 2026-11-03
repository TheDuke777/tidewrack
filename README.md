# Tidewrack

A text-based, procedurally generated roguelike RPG for Android, built in Python + Flet.

## Concept

Every world is generated from systems and data: dungeons, quests, factions, lore, and companions. Runs end, but progress carries forward through an ascension/prestige loop with scaling difficulty and scaling achievements. There's no tile grid — the game is read and chosen — but a schematic map keeps the world easy to understand without drawing your own.

## Principles

- **Offline-first.** The whole game works without a connection. Cloud sync is optional.
- **No ads, no in-app purchases, no premium currency.** One in-game currency, earned by playing.
- **No multiplayer.** Share worlds with friends as files or codes — no servers involved.
- **Your data stays yours.** Cloud saves live in your own cloud account's private app folder. No telemetry by default.
- **No outside guides needed.** Tutorial, codex, and searchable help are built in.

## Planned features

- **Multiple worlds / save slots** with optional Google sign-in and cloud sync across devices
- **World sharing** — export/import worlds (and full save backups) between friends
- **Point-crawl map** with fog of war, drawn automatically
- **Discoverable pets** with roles (fighter, scout, forager, hauler, support) and a bond system
- **Achievements with scaling tiers** that grow as you prestige
- **Gear comparison** showing base and total stat differences — plus the effect on your character — at a glance
- **Crafting, cooking, and shops** designed to complement rather than replace each other
- **Codex** (bestiary, quest log, lore, modifiers, recipes, pets) that fills in as you discover things
- **Onboarding tutorial and searchable in-app help**
- **Settings** for theme, accessibility, cloud sync, import/export, and gameplay options
- **Material Design 3** UI; Android first, with desktop and a possible web build (iOS isn't currently planned)

## Status

Early design/architecture phase. See [`CLAUDE.md`](./CLAUDE.md) for the full architecture, feature specs, risks, and build order.

## Tech stack

Python · Flet · networkx · scipy · opensimplex · esper (ECS) · markovify · pydantic

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

TBD

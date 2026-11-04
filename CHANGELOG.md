# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0-beta.2] - 2026-11-03

### Added
- Worlds are now made of places: each new world has 8 locations (towns,
  forests, mines and sea caves) joined by roads, and every location has its
  own rooms to explore. You start in a harbour town.
- Travel between locations from their gate rooms (the town gate, the cave
  mouth, the forest edge, the mine head).
- A world map alongside the area map: switch between them with the buttons at
  the top. Places you know of are named; at a gate, tap a ringed place to
  travel there.
- Each kind of place is shaped differently: towns are compact with many
  shortcuts, mines are long and winding, forests sprawl.

### Changed
- Existing worlds open as a single location with no roads out of it.

### Removed
- The temporary "Map test world (60 rooms)" button.

## [0.3.0-beta.1] - 2026-11-03

### Added
- Every new world is a freshly generated dungeon: 14 sea-cave rooms with their
  own names, descriptions and layout, different every time.
- A map of the rooms you know, with unexplored rooms shown hollow and your
  position ringed. Tap a neighbouring room to walk there, or hide the map with
  the map button.
- A temporary "Map test world (60 rooms)" button for checking map performance.

### Changed
- Exits are now named by compass direction ("Go north") in generated worlds.

## [0.2.0] - 2026-11-03

### Added
- Saved worlds: start several worlds and pick one to continue from the new
  world list. Progress saves automatically after every action, so closing the
  app (or Android closing it) never loses anything.
- Delete a world from the list (with confirmation).
- If a save file is ever damaged, the world is restored from one of its recent
  backups.

### Changed
- "New run" is replaced by "New world" on the world list; the game screen has a
  back button to return to it.

## [0.1.1] - 2026-11-03

### Changed
- Game data now comes from content files that are validated when the app starts;
  if they ever fail to load, the app explains why instead of showing a blank screen.

## [0.1.0] - 2026-11-03

### Added
- First playable slice: explore "The First Descent", a hand-authored seven-room
  dungeon. Move between rooms, look around, wait, and start a new run; rooms you
  have visited show by name on their exits.
- Game core: seeded random number generator, entity-component store, event bus,
  and turn loop.

## [0.0.3] - 2026-11-03

- Testing pre-release builds.

## [0.0.3-beta.1] - 2026-11-03

- Testing pre-release builds.

## [0.0.2] - 2026-11-03

### Added
- Tidewrack app icon and splash screen, and the logo on the home screen.

## [0.0.1] - 2026-11-02

### Added
- Hello-world app screen showing the app version and build number.
- Release pipeline: CI checks, tag-triggered signed APK builds published to
  GitHub Releases, and `tools/release.py` for version bumps and tagging.

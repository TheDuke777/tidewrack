# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Quests. Each town's gate has a notice board with a few quests to accept:
  - **Bounty:** hunt down a named, tougher enemy.
  - **Cull:** defeat a number of one kind of enemy.
  - **Explore:** visit every room of a place.
  - **Recover:** find a lost item and bring it back.
- Some quests aren't on any board. Find a torn notice or an unsent letter out in
  the world and the quest starts on the spot.
- Finished quests are turned in at any town's notice board for a reward: a
  piece of gear better than an ordinary find. Its comparison card shows before
  you accept.
- A Quests tab lists what's ready to turn in, what's active and what's done.
- World map: places you've fully explored show ✓, and places an active quest
  sends you to show ◆.
- Area map: rooms where you've left items lying show ✦, and a bounty you've
  seen but not yet beaten shows ◆.

### Note
- Worlds made before this version have no quests. Start a new world to get
  them.

## [0.5.0] - 2026-11-04

### Fixed
- Drowned Watch pieces found before 0.5.0-beta.3 now wear the same teal set
  chip as newer ones, instead of indigo.

### Added
- Sort your pack by name, ATK, DEF, HP or verdict, best first or worst first
  (A to Z or Z to A for names). Sorting works on whatever your filters show.
- Combat. Enemies wait in the rooms of caves, forests and mines, and others
  wander and may come upon you. Fights go round by round: Attack, Defend (take
  less damage from the next blow) or Flee (back the way you came; it doesn't
  always work).
- Not every enemy is a beast: wreckers prowl the forests and smugglers hide in
  the sea caves, alongside crabs, eels, boars, wisps, rats, spiders and the
  drowned.
- Beaten enemies sometimes drop gear.
- Health. You slowly recover outside fights, and Rest in a town to heal fully.
  If you're beaten, you wake at the edge of the last town you visited.
- A Codex tab with Foes: everyone and everything you've fought, grouped as
  beasts, people and spirits. Beat them to learn their strength, then what they
  drop.

### Changed
- A fight now takes over the Explore screen: the map hides until it's over, so
  you can't miss that one has started.
- Trying to change gear mid-fight now tells you why you can't.
- Every level of the Codex folds away: the Foes section and each group in it
  (Beasts, People, Spirits).
- Gear sets show as coloured chips beside the Better/Worse verdict, so matching
  pieces stand out.
- Recovering outside fights now heals a share of your maximum HP (5% every
  three turns, at least 1), so it keeps pace as your health grows.
- The line under the Explore screen now shows only your progress (turn, rooms,
  places). Your stats are on the Inventory tab.
- Worlds made with earlier versions open at full health, but have no enemies.
  Start a new world to fight.

## [0.5.0-beta.4] - 2026-11-04

### Added
- Sort your pack by name, ATK, DEF, HP or verdict, best first or worst first
  (A to Z or Z to A for names). Sorting works on whatever your filters show.

## [0.5.0-beta.3] - 2026-11-04

### Changed
- A fight now takes over the Explore screen: the map hides until it's over, so
  you can't miss that one has started.
- Trying to change gear mid-fight now tells you why you can't.
- Every level of the Codex folds away: the Foes section and each group in it
  (Beasts, People, Spirits).
- Gear sets show as coloured chips beside the Better/Worse verdict, so matching
  pieces stand out.

## [0.5.0-beta.2] - 2026-11-04

### Changed
- Recovering outside fights now heals a share of your maximum HP (5% every
  three turns, at least 1), so it keeps pace as your health grows.

## [0.5.0-beta.1] - 2026-11-04

### Added
- Combat. Enemies wait in the rooms of caves, forests and mines, and others
  wander and may come upon you. Fights go round by round: Attack, Defend (take
  less damage from the next blow) or Flee (back the way you came; it doesn't
  always work).
- Not every enemy is a beast: wreckers prowl the forests and smugglers hide in
  the sea caves, alongside crabs, eels, boars, wisps, rats, spiders and the
  drowned.
- Beaten enemies sometimes drop gear.
- Health. You slowly recover outside fights, and Rest in a town to heal fully.
  If you're beaten, you wake at the edge of the last town you visited.
- A Codex tab with Foes: everyone and everything you've fought, grouped as
  beasts, people and spirits. Beat them to learn their strength, then what they
  drop.

### Changed
- The line under the Explore screen now shows only your progress (turn, rooms,
  places). Your stats are on the Inventory tab.
- Worlds made with earlier versions open at full health, but have no enemies.
  Start a new world to fight.

## [0.4.0] - 2026-11-04

### Added
- A navigation bar at the bottom switches between Explore and Inventory.
- Filter your pack by slot, affix or set, and select several items to drop at
  once (filter first, then "Select all shown").
- Gate rooms, where roads leave from, show as squares on the area map. On the
  world map, each place's name starts with a symbol for its kind (⌂ Town,
  ≈ Sea Caves, ♣ Forest, ⚒ Mine), with a key below the map.
- Gear. You start with a Driftwood Club and a Patched Coat, and every new world
  has gear lying in its rooms: cutlasses, harpoons, bucklers, lanterns, helms,
  boots and charms, some with a twist such as "Keen" or "of the Gull".
- Six equipment slots (main hand, off hand, head, body, feet, trinket).
  Two-handed weapons take both hands.
- Your stats (ATK, DEF and HP) show at the bottom of the game screen.
- Every piece of gear shows how it compares with what you have on: a Better,
  Worse or Mixed verdict, the change to each stat (both the item's own stats
  and with its bonuses), what your stats would become, what it would replace,
  and what it could reach fully upgraded. Changes are marked with ▲, ▼ or ＝
  and a sign, never by colour alone.
- Take, Take & equip, Equip, Take off and Drop. The new inventory shows your
  stats, what adds up to them, your six slots and your pack.
- The Drowned Watch set: wear two or three pieces for extra DEF and HP.

### Changed
- Dropping gear asks first.
- Worlds made with earlier versions open with the starting stats and no gear;
  their rooms have nothing to find. Start a new world to find gear.

## [0.4.0-beta.2] - 2026-11-04

### Added
- A navigation bar at the bottom switches between Explore and Inventory.
- Filter your pack by slot, affix or set, and select several items to drop at
  once (filter first, then "Select all shown").
- Gate rooms, where roads leave from, show as squares on the area map. On the
  world map, each place's name starts with a symbol for its kind (⌂ Town,
  ≈ Sea Caves, ♣ Forest, ⚒ Mine), with a key below the map.

### Changed
- Dropping gear asks first.

## [0.4.0-beta.1] - 2026-11-04

### Added
- Gear. You start with a Driftwood Club and a Patched Coat, and every new world
  has gear lying in its rooms: cutlasses, harpoons, bucklers, lanterns, helms,
  boots and charms, some with a twist such as "Keen" or "of the Gull".
- Six equipment slots (main hand, off hand, head, body, feet, trinket).
  Two-handed weapons take both hands.
- Your stats (ATK, DEF and HP) show at the bottom of the game screen.
- Every piece of gear shows how it compares with what you have on: a Better,
  Worse or Mixed verdict, the change to each stat (both the item's own stats
  and with its bonuses), what your stats would become, what it would replace,
  and what it could reach fully upgraded. Changes are marked with ▲, ▼ or ＝
  and a sign, never by colour alone.
- Take, Take & equip, Equip, Take off and Drop. The new inventory shows your
  stats, what adds up to them, your six slots and your pack.
- The Drowned Watch set: wear two or three pieces for extra DEF and HP.

### Changed
- Worlds made with earlier versions open with the starting stats and no gear;
  their rooms have nothing to find. Start a new world to find gear.

## [0.3.1-beta.1] - 2026-11-04

### Changed
- Release notifications now come from a self-hosted ntfy server instead of
  Pushover. Tapping a release notification opens Tidewrack in Komi Store, with
  buttons for Komi Store and the GitHub release; failed runs open the logs.

## [0.3.0] - 2026-11-04

### Added
- Pinch to zoom and drag to pan either map. The map follows you as you walk,
  "centre on me" jumps back to where you are, and "show the whole map" zooms
  back out.
- Tap the Log bar to hide or show the log, or drag it to resize it (drag it
  all the way down to hide it). While hidden, the bar shows the newest line.
  This choice is remembered for every world.
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
- Every new world is freshly generated, with its own names, descriptions and
  layout, different every time.
- A map of the rooms you know, with unexplored rooms shown hollow and your
  position ringed. Tap a neighbouring room to walk there.

### Changed
- The map stays put while the room text and buttons scroll beneath it; the log
  scrolls on its own below them.
- Place names on the world map move above or beside their dot when they would
  otherwise run into another place or a road.
- Existing worlds open as a single location with no roads out of it.
- Exits are now named by compass direction ("Go north") in generated worlds.

## [0.3.0-beta.3] - 2026-11-03

### Added
- Pinch to zoom and drag to pan either map. The map follows you as you walk,
  "centre on me" jumps back to where you are, and "show the whole map" zooms
  back out.
- Tap the Log bar to hide or show the log, or drag it to resize it (drag it
  all the way down to hide it). While hidden, the bar shows the newest line.
  This choice is remembered for every world.

### Changed
- The map stays put while the room text and buttons scroll beneath it; the log
  scrolls on its own below them.
- Place names on the world map move above or beside their dot when they would
  otherwise run into another place or a road.

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

## [0.3.0-beta.1] - 2026-11-03

### Added
- Every new world is freshly generated, with its own names, descriptions and
  layout, different every time.
- A map of the rooms you know, with unexplored rooms shown hollow and your
  position ringed. Tap a neighbouring room to walk there.

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

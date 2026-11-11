# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Codex foe entries say where they're found: the kinds of place, by region
  (regions you haven't found yet stay unnamed). Wardens say which road they
  guard.

### Changed
- Every region in a new world has at least one place of each of its kinds,
  so no kind's gear, foes or materials are ever missing from a world (one
  world had no sea caves, and so no Sealskin Boots).

## [0.10.1-beta.2] - 2026-11-11

### Added
- A "Better upgraded" chip on gear that's worse than what you have on now
  but would beat it once both are fully upgraded, so you know it's the one
  to put materials into. Expanded cards say what it beats.
- The map's legend can be hidden with a button on the map; the app
  remembers your choice.

### Changed
- Maps open zoomed in on you instead of showing the whole map, and keep
  your zoom when you move or travel (the area map and world map each keep
  their own). The whole-map button still shows everything.
- Less empty space around the Turn · Rooms · Places line under the log.

## [0.10.1-beta.1] - 2026-11-06

### Added
- The Moors: beyond the Fens, a third region of hill farms, heaths, barrows
  and standing stones, with its own foes (moor wolves, feral rams, adders,
  highwaymen, barrow wights, black dogs), gear, materials, ingredients,
  recipes and two new meals. Tougher again than the Fens.
- The Barrow Warden holds the drove road from the Fens into the Moors.
- New worlds have 21 places.

### Changed
- Saving after each action is much faster (about a sixth of the time on a
  computer, and it no longer grows with the size of the world): only the
  places that changed are written.

## [0.10.0] - 2026-11-06

### Changed
- The world map's legend lists stilt villages under Town instead of giving
  them their own entry.
- Worlds have 14 places (7 per region) instead of 8. Notice boards only
  send you around their own region, and each region has its own found
  quests.
- Older worlds open as they were: all coast, no wardens.

### Fixed
- Dragging or pinching a zoomed-in map is smoother: place names stay put
  until you let go, and what's off screen isn't drawn.
- Cards (gear, quests, meals, materials, foes, worlds, fights) no longer
  blend into the background with some wallpaper colours: they're filled a
  shade further from the page.

### Added
- Regions: new worlds now have two, the coast and, inland, the Fens. Each
  is a cluster of places on the world map, its name written faintly across
  them, and only one road leads from one region into the next.
- The Fens: stilt villages, peat bogs, reed mazes and meres, with their own
  foes (bog toads, fen pike, fen raiders, marsh lights, bog walkers), gear,
  materials, ingredients, recipes and two new meals. Tougher than the coast.
- Wardens: the Reed Warden stands at the gate on the road into the Fens.
  It never attacks first; taking that road challenges it, and the way stays
  open once it's beaten. Roads it bars show ⚔ on the world map.
- The log says when you cross into a new region.

## [0.10.0-beta.3] - 2026-11-06

### Changed
- The world map's legend lists stilt villages under Town instead of giving
  them their own entry.

### Fixed
- Dragging or pinching a zoomed-in map is smoother: place names stay put
  until you let go, and what's off screen isn't drawn.

## [0.10.0-beta.2] - 2026-11-05

### Fixed
- Cards (gear, quests, meals, materials, foes, worlds, fights) no longer
  blend into the background with some wallpaper colours: they're filled a
  shade further from the page.

## [0.10.0-beta.1] - 2026-11-05

### Added
- Regions: new worlds now have two, the coast and, inland, the Fens. Each
  is a cluster of places on the world map, its name written faintly across
  them, and only one road leads from one region into the next.
- The Fens: stilt villages, peat bogs, reed mazes and meres, with their own
  foes (bog toads, fen pike, fen raiders, marsh lights, bog walkers), gear,
  materials, ingredients, recipes and two new meals. Tougher than the coast.
- Wardens: the Reed Warden stands at the gate on the road into the Fens.
  It never attacks first; taking that road challenges it, and the way stays
  open once it's beaten. Roads it bars show ⚔ on the world map.
- The log says when you cross into a new region.

### Changed
- Worlds have 14 places (7 per region) instead of 8. Notice boards only
  send you around their own region, and each region has its own found
  quests.
- Older worlds open as they were: all coast, no wardens.

## [0.9.1] - 2026-11-05

### Added
- Rename a world from the world list (the pencil beside delete).
- "New" chips in the Smithy and Tavern too: upgrades, recipes and meals
  that just became possible say "New" until you switch tab.
- The log marks what your latest action did: those lines are bold, under a
  thin divider, until your next action.

### Changed
- Android's back gesture steps out one level at a time: from another tab
  to Explore, then out of an open shop or notice board, then to the world
  list. On the world list it leaves the app as before.
- Opening the log (or a world) shows its newest lines straight away instead
  of slowly scrolling down from the top. New lines still glide in.

## [0.9.1-beta.1] - 2026-11-05

### Added
- Rename a world from the world list (the pencil beside delete).
- "New" chips in the Smithy and Tavern too: upgrades, recipes and meals
  that just became possible say "New" until you switch tab.
- The log marks what your latest action did: those lines are bold, under a
  thin divider, until your next action.

### Changed
- Android's back gesture steps out one level at a time: from another tab
  to Explore, then out of an open shop or notice board, then to the world
  list. On the world list it leaves the app as before.
- Opening the log (or a world) shows its newest lines straight away instead
  of slowly scrolling down from the top. New lines still glide in.

## [0.9.0] - 2026-11-05

### Changed
- Your gold total in the Inventory uses the same coin as prices (tinted
  gold) instead of a money bag, so it doesn't look like a second currency.
- The top-left back arrow in a world is now a menu with "Switch world", so
  leaving a shop or notice board no longer drops you at the world list by
  mistake. Settings and Help will live in this menu too.
- Prices and rewards show a coin instead of the word "gold" (Buy · 12 ◉),
  and your total in the Inventory has a gold money bag. Messages and the
  log still say "gold"; screen readers say it everywhere.
- "▲ Better" and stat gains use a darker green on light themes and a
  lighter one on dark themes, so they're easy to read on both.

### Fixed
- "New" chips now go away when you leave the tab on the navigation bar
  (they stayed on new quests, for example).
- v0.9.0-beta.1 showed an error on launch ("'Event' object has no
  attribute 'brightness'"); switching between light and dark works again.
- When Android rebuilds the app's window (for example after a new system
  colour palette), you stay in the world you had open instead of landing back
  on the world list.

### Added
- Material You: on Android 12 and later the app takes its colours from your
  wallpaper, in light and dark. It picks up a new palette when you come back
  to the app (on Samsung, once you've applied it in the system settings).
- The Tidewrack logo on the world list.
- "New" chips: when a dot clears because you opened a tab, the cards it was
  about (new quests, Codex foes, pack items, satchel materials, meals and
  recipes) say "New" until you leave that tab.

## [0.9.0-beta.3] - 2026-11-05

### Changed
- Your gold total in the Inventory uses the same coin as prices (tinted
  gold) instead of a money bag, so it doesn't look like a second currency.

### Fixed
- "New" chips now go away when you leave the tab on the navigation bar
  (they stayed on new quests, for example).

## [0.9.0-beta.2] - 2026-11-05

### Fixed
- v0.9.0-beta.1 showed an error on launch ("'Event' object has no
  attribute 'brightness'"); switching between light and dark works again.

## [0.9.0-beta.1] - 2026-11-05

### Added
- Material You: on Android 12 and later the app takes its colours from your
  wallpaper, in light and dark. It picks up a new palette when you come back
  to the app (on Samsung, once you've applied it in the system settings).
- The Tidewrack logo on the world list.
- "New" chips: when a dot clears because you opened a tab, the cards it was
  about (new quests, Codex foes, pack items, satchel materials, meals and
  recipes) say "New" until you leave that tab.

### Changed
- The top-left back arrow in a world is now a menu with "Switch world", so
  leaving a shop or notice board no longer drops you at the world list by
  mistake. Settings and Help will live in this menu too.
- Prices and rewards show a coin instead of the word "gold" (Buy · 12 ◉),
  and your total in the Inventory has a gold money bag. Messages and the
  log still say "gold"; screen readers say it everywhere.
- "▲ Better" and stat gains use a darker green on light themes and a
  lighter one on dark themes, so they're easy to read on both.

### Fixed
- When Android rebuilds the app's window (for example after a new system
  colour palette), you stay in the world you had open instead of landing back
  on the world list.

## [0.8.2] - 2026-11-05

### Changed
- A dot now always means something new to find. The Smithy and Tavern tabs
  dot only for what's newly doable since you last looked there, and clear
  once you've looked (they used to come back every time). There's no dot any
  more for a meal running low, or for learning more about a foe already in
  the Codex.
- The Satchel tab's Meals, Ingredients, Materials and Recipes are
  collapsible sections with counts.
- Sea caves have more to gather (kelp and mussels were too scarce).
- The Satchel tab lists Meals, Ingredients and Materials separately.
- Worlds from earlier versions get tavern kitchens and the market's new
  staples. They have no ingredients lying about, so buy or cook from what
  beasts drop from now on.

### Fixed
- Dots on the Smithy's tabs no longer push its tab labels out of line.

### Added
- Gathering spots grow back. Every so often each wild place regrows a spot
  in an empty room (never the one you're in), up to about as many as it
  started with, so materials and ingredients don't run out. Worlds from
  earlier versions regrow too.
- Unread dots:
  - Quests: a quest is ready to turn in, or one has been added since you
    last looked.
  - Codex: you've met a new foe or learned more about one.
  - Inventory: new gear in your pack, a new kind of material or meal, a new
    recipe, or your meal has 10 turns or fewer left. The Pack and Satchel
    tabs get their own dots.
  - Smithy and Tavern tabs: an upgrade you can afford for gear you have on,
    or something you can craft or cook right now.
- Cooking. Every tavern has a kitchen with two tabs: a Menu of ready meals,
  and Cook, where you make any of seven meals from ingredients for a small
  fee (cheaper than buying).
- Ingredients: kelp, mussels, mushrooms, wild herbs and a rare black truffle
  in the wild; boar, crab and eel meat from beasts; salt and ship's biscuit
  at every market. They share the satchel with crafting materials.
- Meals keep until you eat them, any time outside a fight. Each gives a buff
  for a number of turns: more ATK, DEF or HP, faster healing, or several at
  once for the harder ones (Smoked Eel Supper, Harbour Feast). One meal at a
  time; eating another replaces it (it asks first).
- What you've eaten shows on the Satchel tab, in your stats, and at the end of
  the status row ("Fed: Mussel Stew (57)").

## [0.8.2-beta.2] - 2026-11-05

### Added
- Gathering spots grow back. Every so often each wild place regrows a spot
  in an empty room (never the one you're in), up to about as many as it
  started with, so materials and ingredients don't run out. Worlds from
  earlier versions regrow too.
- Unread dots:
  - Quests: a quest is ready to turn in, or one has been added since you
    last looked.
  - Codex: you've met a new foe or learned more about one.
  - Inventory: new gear in your pack, a new kind of material or meal, a new
    recipe, or your meal has 10 turns or fewer left. The Pack and Satchel
    tabs get their own dots.
  - Smithy and Tavern tabs: an upgrade you can afford for gear you have on,
    or something you can craft or cook right now.

### Changed
- The Satchel tab's Meals, Ingredients, Materials and Recipes are
  collapsible sections with counts.
- Sea caves have more to gather (kelp and mussels were too scarce).

## [0.8.2-beta.1] - 2026-11-05

### Added
- Cooking. Every tavern has a kitchen with two tabs: a Menu of ready meals,
  and Cook, where you make any of seven meals from ingredients for a small
  fee (cheaper than buying).
- Ingredients: kelp, mussels, mushrooms, wild herbs and a rare black truffle
  in the wild; boar, crab and eel meat from beasts; salt and ship's biscuit
  at every market. They share the satchel with crafting materials.
- Meals keep until you eat them, any time outside a fight. Each gives a buff
  for a number of turns: more ATK, DEF or HP, faster healing, or several at
  once for the harder ones (Smoked Eel Supper, Harbour Feast). One meal at a
  time; eating another replaces it (it asks first).
- What you've eaten shows on the Satchel tab, in your stats, and at the end of
  the status row ("Fed: Mussel Stew (57)").

### Changed
- The Satchel tab lists Meals, Ingredients and Materials separately.
- Worlds from earlier versions get tavern kitchens and the market's new
  staples. They have no ingredients lying about, so buy or cook from what
  beasts drop from now on.

## [0.8.1] - 2026-11-05

### Fixed
- A collapsed card's stat line now counts set bonuses (it shows what happens
  to your stats, like the open card's "You" column), and says when you'd gain
  or lose a set bonus.

### Changed
- Gear cards are laid out so the name and its details aren't squeezed into a
  narrow column: name, verdict and arrow on top, then the set and the
  slot/upgrade line across the full width.

### Added
- Gear and quest cards can be collapsed to their top row and a one-line
  summary: what the gear changes (e.g. "DEF ▲ +1  HP ▲ +3"), or a quest's
  progress and reward. Its buttons stay. Tap a card's top row or its arrow
  to open or fold it.
- Shop lists, your pack and the quest log start collapsed; what you have on
  and gear lying in a room start open. "Expand all" / "Collapse all" by each
  list changes how it starts, and the app remembers that.

## [0.8.1-beta.2] - 2026-11-05

### Fixed
- A collapsed card's stat line now counts set bonuses (it shows what happens
  to your stats, like the open card's "You" column), and says when you'd gain
  or lose a set bonus.

### Changed
- Gear cards are laid out so the name and its details aren't squeezed into a
  narrow column: name, verdict and arrow on top, then the set and the
  slot/upgrade line across the full width.

## [0.8.1-beta.1] - 2026-11-05

### Added
- Gear and quest cards can be collapsed to their top row and a one-line
  summary: what the gear changes (e.g. "DEF ▲ +1  HP ▲ +3"), or a quest's
  progress and reward. Its buttons stay. Tap a card's top row or its arrow
  to open or fold it.
- Shop lists, your pack and the quest log start collapsed; what you have on
  and gear lying in a room start open. "Expand all" / "Collapse all" by each
  list changes how it starts, and the app remembers that.

## [0.8.0] - 2026-11-05

### Changed
- The smithy's crafting is split into Upgrade and Craft tabs, each with
  counts and the same filters and sorting as your pack ("Price" sorts by the
  fee). Both share one set of filters, and the switch to hide what you can't
  make covers both.
- The Inventory tab is split into Equipped, Pack and Satchel tabs under your
  stats, each with a count.
- Gear you sell stays on the smithy's shelf to buy back, but only the last 6
  pieces; older ones are gone. Shelves from earlier versions are cleared down
  the same way.
- Gear is worth a bit more (and costs a bit more in shops) when it can still
  be upgraded.
- Worlds from earlier versions get markets, crafting and the four starting
  recipes, and their gear becomes upgradable. They have nothing new to gather
  or find, but enemies that come back drop materials.

### Added
- The Craft tab has a switch to hide recipes you don't have the materials
  for. It stays as you left it while the world is open.
- Materials: hides, shells, ore, timber, sailcloth and rarer finds. Beasts drop
  them at last, people and spirits drop some too, and wild places have them
  lying about: walking into the room gathers them. They go in a satchel shown
  on the Inventory tab.
- Markets. Every town has one, selling common materials and buying any back.
- Crafting at the smithy, on a new Craft tab:
  - Upgrades: most gear can now be upgraded (+1, +2, +3 on weapons) for
    materials and a fee that grows with each level.
  - Recipes: make a specific piece of gear at its best roll. You start knowing
    four; more turn up as pages out in the world and as extra quest rewards,
    including one that makes affixed gear.
- The cards show what each craft or upgrade needs and what you have, with
  short materials marked "✗ short".

## [0.8.0-beta.3] - 2026-11-05

### Changed
- The smithy's crafting is split into Upgrade and Craft tabs, each with
  counts and the same filters and sorting as your pack ("Price" sorts by the
  fee). Both share one set of filters, and the switch to hide what you can't
  make covers both.

## [0.8.0-beta.2] - 2026-11-04

### Added
- The Craft tab has a switch to hide recipes you don't have the materials
  for. It stays as you left it while the world is open.

### Changed
- The Inventory tab is split into Equipped, Pack and Satchel tabs under your
  stats, each with a count.

## [0.8.0-beta.1] - 2026-11-04

### Added
- Materials: hides, shells, ore, timber, sailcloth and rarer finds. Beasts drop
  them at last, people and spirits drop some too, and wild places have them
  lying about: walking into the room gathers them. They go in a satchel shown
  on the Inventory tab.
- Markets. Every town has one, selling common materials and buying any back.
- Crafting at the smithy, on a new Craft tab:
  - Upgrades: most gear can now be upgraded (+1, +2, +3 on weapons) for
    materials and a fee that grows with each level.
  - Recipes: make a specific piece of gear at its best roll. You start knowing
    four; more turn up as pages out in the world and as extra quest rewards,
    including one that makes affixed gear.
- The cards show what each craft or upgrade needs and what you have, with
  short materials marked "✗ short".

### Changed
- Gear you sell stays on the smithy's shelf to buy back, but only the last 6
  pieces; older ones are gone. Shelves from earlier versions are cleared down
  the same way.
- Gear is worth a bit more (and costs a bit more in shops) when it can still
  be upgraded.
- Worlds from earlier versions get markets, crafting and the four starting
  recipes, and their gear becomes upgradable. They have nothing new to gather
  or find, but enemies that come back drop materials.

## [0.7.0] - 2026-11-04

### Added
- The smithy's Buy tab can be filtered and sorted too, including by price.
  It keeps its own choices, separate from your pack's.
- The smithy's sell list has the same filters, sorting and select mode as
  your pack on the Inventory tab, so you can sell several items at once.
  Filters and sorting carry over between the two.
- Sorting your pack by sale price.
- Gold. People you defeat (wreckers, smugglers, the odd drowned sailor) carry
  some, quests pay gold as well as their gear reward, and every new world
  starts you with 10.
- Shops. Every town has a Smithy that sells plain gear and buys yours, and a
  Tavern with beds. Each shop is in a room named for it, or at the town gate
  if the town hasn't got one. Every item for sale shows the usual comparison
  card and its price. Smithies slowly restock, and gear you sell goes on their
  shelves.
- Selling, inside the smithy or from the Inventory tab while you're there (one
  item at a time, or several at once in select mode). Selling always asks
  first.
- Abandoning quests from the Quests tab. A quest from a notice board goes
  back up on its board; a quest you found goes up on the board of the last
  town you visited. A cull's count starts again.
- Area map: rooms with a shop or inn show ¤.

### Changed
- The smithy has Buy and Sell tabs, so a shelf full of gear you've sold
  doesn't bury your pack (or the other way round). It opens on Buy.
- Shop and notice board headings fit better on a phone: no second back arrow
  (the one at the top goes back to your worlds), and your gold is shorter.
- Notice boards and shops show in the room as one button each. Tapping one
  opens it over the whole screen, like a fight, until you leave it.
- Resting to full health in town is no longer free: it's a night at a tavern,
  for 4 gold. Waiting anywhere still heals slowly.
- Worlds from earlier versions get gold and shops too. You start with 10 gold,
  enemies and unfinished quests carry gold, and every town gets a Smithy and a
  Tavern. The Smithy stocks plain copies of gear already in that world.

## [0.7.0-beta.4] - 2026-11-04

### Added
- The smithy's Buy tab can be filtered and sorted too, including by price.
  It keeps its own choices, separate from your pack's.

## [0.7.0-beta.3] - 2026-11-04

### Changed
- The smithy has Buy and Sell tabs, so a shelf full of gear you've sold
  doesn't bury your pack (or the other way round). It opens on Buy.
- Shop and notice board headings fit better on a phone: no second back arrow
  (the one at the top goes back to your worlds), and your gold is shorter.

## [0.7.0-beta.2] - 2026-11-04

### Added
- The smithy's sell list has the same filters, sorting and select mode as
  your pack on the Inventory tab, so you can sell several items at once.
  Filters and sorting carry over between the two.
- Sorting your pack by sale price.

## [0.7.0-beta.1] - 2026-11-04

### Added
- Gold. People you defeat (wreckers, smugglers, the odd drowned sailor) carry
  some, quests pay gold as well as their gear reward, and every new world
  starts you with 10.
- Shops. Every town has a Smithy that sells plain gear and buys yours, and a
  Tavern with beds. Each shop is in a room named for it, or at the town gate
  if the town hasn't got one. Every item for sale shows the usual comparison
  card and its price. Smithies slowly restock, and gear you sell goes on their
  shelves.
- Selling, inside the smithy or from the Inventory tab while you're there (one
  item at a time, or several at once in select mode). Selling always asks
  first.
- Abandoning quests from the Quests tab. A quest from a notice board goes
  back up on its board; a quest you found goes up on the board of the last
  town you visited. A cull's count starts again.
- Area map: rooms with a shop or inn show ¤.

### Changed
- Notice boards and shops show in the room as one button each. Tapping one
  opens it over the whole screen, like a fight, until you leave it.
- Resting to full health in town is no longer free: it's a night at a tavern,
  for 4 gold. Waiting anywhere still heals slowly.
- Worlds from earlier versions get gold and shops too. You start with 10 gold,
  enemies and unfinished quests carry gold, and every town gets a Smithy and a
  Tavern. The Smithy stocks plain copies of gear already in that world.

## [0.6.2] - 2026-11-04

### Added
- Tapping another place on the world map when you're not at a gate now tells
  you where you can leave from, instead of doing nothing.

## [0.6.1] - 2026-11-04

### Added
- Enemies come back. Every 30 turns, each cave, forest and mine gains one
  wandering enemy, up to as many as it started with. Rooms you've cleared stay
  clear, but there's always something out there to hunt, so a cull quest taken
  late can still be finished.
- Returning enemies can drop gear, at half their kind's usual chance.

### Changed
- Worlds from earlier versions get returning wanderers too, made from the
  enemies still left in them. A kind of place where none are left anywhere in
  the world stays clear.

## [0.6.0] - 2026-11-04

### Fixed
- Turning in a quest really does clear it from the notice board now. Showing
  the reward toast stopped the rest of the screen from updating; any toast now
  updates the whole screen.
- Turning in a quest now clears it from the notice board straight away, instead
  of only after another tap.

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

## [0.6.0-beta.3] - 2026-11-04

### Fixed
- Turning in a quest really does clear it from the notice board now. Showing
  the reward toast stopped the rest of the screen from updating; any toast now
  updates the whole screen.

## [0.6.0-beta.2] - 2026-11-04

### Fixed
- Turning in a quest now clears it from the notice board straight away, instead
  of only after another tap.

## [0.6.0-beta.1] - 2026-11-04

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

"""Enemies coming back (CLAUDE.md §14 step 6c).

Every `Rules.enemy_return_every` turns, each location's wanderer queue
(`Spawner.queue`) regains one enemy, up to its `cap`, rolled from the location's
`templates` on the saved respawn stream. Rooms you've cleared stay clear; only
wanderers return, so there's always something left to hunt (late cull quests).
Returning enemies may drop one of their template's pre-rolled loot pieces, at
their kind's chance times `Rules.return_loot_factor`.

Everything comes from the save (templates are snapshots), so a shared world
plays the same for the same actions, on any app version.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from tidewrack.core.engine.components import Enemy, EnemyTemplate, Spawner
from tidewrack.core.gear.stats import STATS
from tidewrack.core.rng import Rng

if TYPE_CHECKING:
    from tidewrack.core.engine.game import Game


def from_template(rng: Rng, template: EnemyTemplate, loot_factor: float) -> Enemy:
    stats = dict(template.stats)
    for stat in STATS:
        if stat in template.rolls:
            low, high = template.rolls[stat]
            stats[stat] = stats.get(stat, 0) + rng.randint(low, high)
    loot = []
    if template.loot and rng.chance(template.loot_chance * loot_factor):
        loot.append(copy.deepcopy(rng.choice(template.loot)))
    low, high = template.gold
    gold = rng.randint(low, high) if high else 0
    return Enemy(
        enemy_id=template.enemy_id,
        name=template.name,
        category=template.category,
        description=template.description,
        stats=stats,
        drops=list(template.drops),
        loot=loot,
        gold=gold,
    )


def returns_system(game: Game) -> None:
    """Per turn: on every Nth turn, each location under its cap regains a wanderer."""
    if game.turn % game.rules.enemy_return_every:
        return
    for _, (spawner,) in game.world.query(Spawner):
        if spawner.templates and len(spawner.queue) < spawner.cap:
            templates = spawner.templates
            template = game.respawn_rng.weighted_choice(templates, [t.weight for t in templates])
            spawner.queue.append(
                from_template(game.respawn_rng, template, game.rules.return_loot_factor)
            )

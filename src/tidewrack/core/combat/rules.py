"""Combat and recovery rules, and the formulas that use them.

Every number a fight depends on lives in `Rules`, a snapshot saved with each
world. A world's difficulty (content `difficulties/`, chosen when the world is
made and fixed afterwards) is just a different snapshot: its name plus the
fields it overrides.
Changing a formula here changes fights in existing worlds, so treat it like any
other balance change and check it against the difficulty sim once that exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

from tidewrack.core.rng import Rng


@dataclass(frozen=True)
class Rules:
    flee_chance: float = 0.6  # chance a Flee succeeds
    regen_every: int = 3  # out of a fight, recover some HP every this many turns:
    regen_fraction: float = 0.05  # this share of max HP (so bigger health bars keep pace),
    regen_amount: int = 1  # but never less than this many HP
    respawn_hp: float = 0.5  # fraction of max HP you wake with after a defeat
    enemy_strength: float = 1.0  # multiplies enemy ATK, DEF and HP when a fight starts
    enemy_hp: float = 1.0  # and HP again: longer fights, without ATK − DEF's cliff
    enemy_atk: float = 1.0  # and ATK again (tides, 8c): small steps, it's cliffy
    defend_factor: float = 0.5  # damage taken while defending is multiplied by this
    enemy_return_every: int = 30  # turns between each location regaining a wanderer
    return_loot_factor: float = 0.5  # returning enemies' loot chance, times their kind's
    difficulty: str = "Standard"  # the name of the preset these came from (8b)


STANDARD = Rules()


def damage(rng: Rng, atk: int, defence: int, defending: bool, rules: Rules) -> int:
    """One blow: ATK − DEF plus up to a third of ATK, at least 1 (also when defending)."""
    hit = max(1, atk - defence + rng.randint(0, ceil(atk / 3)))
    if defending:
        hit = max(1, int(hit * rules.defend_factor))
    return hit


def regen(max_hp: int, rules: Rules) -> int:
    """HP recovered per regen tick: a share of max HP, at least regen_amount."""
    return max(rules.regen_amount, floor(max_hp * rules.regen_fraction))


def scaled(stats: dict[str, int], rules: Rules) -> dict[str, int]:
    """An enemy's stats under these rules (at least 1 HP)."""
    result = {s: round(v * rules.enemy_strength) for s, v in stats.items()}
    if "atk" in stats and rules.enemy_atk != 1.0:
        result["atk"] = round(stats["atk"] * rules.enemy_strength * rules.enemy_atk)
    hp = stats.get("hp", 1) * rules.enemy_strength * rules.enemy_hp
    result["hp"] = max(1, round(hp))
    return result

"""Upgrade old slot envelopes to the current schema (CLAUDE.md §9, §10).

When the save format changes: bump core.versions.SCHEMA_VERSION to N, add
``MIGRATIONS[N - 1]`` (a pure function from the version N-1 envelope to version
N), and commit a fixture save of the *old* version under tests/fixtures/saves/
so the migration stays tested forever. Never edit a released migration.

The un-migrated file is not lost: the next autosave rotates it into the slot's
backups before writing the upgraded version.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from tidewrack.core.versions import SCHEMA_VERSION
from tidewrack.services.storage.store import SaveError

Envelope = dict[str, Any]


def _v1_to_v2(envelope: Envelope) -> Envelope:
    # v2 only added optional map positions to dungeon nodes; v1 maps have none.
    return envelope


def _v2_to_v3(envelope: Envelope) -> Envelope:
    # v3 nests rooms inside locations inside a world. An old save's single dungeon
    # becomes a world with one location (and no roads out of it).
    game, location_id = envelope["game"], "loc_00"
    dungeon = game.pop("dungeon")
    game["world"] = {
        "start": location_id,
        "locations": [
            {
                "id": location_id,
                "name": dungeon["name"],
                "kind": "Sea Caves" if dungeon["id"] == "dungeon.generated" else "Dungeon",
                "start": dungeon["start"],
                "gates": [dungeon["start"]],
                "rooms": dungeon["nodes"],
            }
        ],
    }
    for entity in game["entities"]:
        components = entity["components"]
        if "Position" in components:
            components["Position"] = {
                "location": location_id,
                "room": components["Position"]["node"],
            }
        if "Explorer" in components:
            old = components["Explorer"]
            components["Explorer"] = {
                "locations_visited": [location_id],
                "locations_discovered": [location_id],
                "rooms_visited": {location_id: old["visited"]},
                "rooms_discovered": {location_id: old["discovered"]},
            }
    old = envelope["meta"]["summary"]
    envelope["meta"]["summary"] = {
        "location": old["dungeon_name"],
        "room": old["location"],
        "turn": old["turn"],
        "locations_visited": 1,
        "total_locations": 1,
    }
    return envelope


def _v3_to_v4(envelope: Envelope) -> Envelope:
    # v4 adds gear: the player gets base stats (the values new worlds started with
    # in v4, written out here so later content changes can't alter this migration)
    # and carries nothing. Old worlds have no finds; their rooms stay empty.
    for entity in envelope["game"]["entities"]:
        components = entity["components"]
        if "Player" in components:
            components["Stats"] = {"base": {"atk": 2, "def": 1, "hp": 20}}
    return envelope


def _v4_to_v5(envelope: Envelope) -> Envelope:
    # v5 adds combat: the player gets full health, an empty codex and a place to
    # wake after a defeat (the world's start, a town in generated worlds). Old
    # worlds have no enemies or wanderers, and keep the Standard rules and
    # seed-derived combat streams that GameState defaults to.
    game = envelope["game"]
    for entity in game["entities"]:
        components = entity["components"]
        if "Player" in components:
            components["Health"] = {"damage": 0}
            components["Codex"] = {"foes": {}, "kills": {}}
            components["Respawn"] = {"location": game["world"]["start"]}
    return envelope


def _v5_to_v6(envelope: Envelope) -> Envelope:
    # v6 adds quests as new components only (Quest, QuestItem, Clue, Bounty), so
    # older worlds load as they are: they just have no notice-board quests.
    return envelope


MIGRATED_CAP = 6  # the wanderer queue size every world had before v7
MIGRATED_LOOT_CHANCE = 0.25  # a typical kind's loot chance (the save doesn't record it)
MIGRATED_LOOT_PIECES = 3


def _v6_to_v7(envelope: Envelope) -> Envelope:
    # v7 lets wanderers return. Every Spawner gets a cap and templates, built only
    # from enemy snapshots already in the save (never content): the enemies left
    # in locations of the same kind, placed or still queued, bounties excluded.
    # A kind of place with no enemy left anywhere gets no templates and stays clear.
    game = envelope["game"]
    kinds = {loc["id"]: loc["kind"] for loc in game["world"]["locations"]}
    seen: dict[str, list[dict]] = {}  # location kind -> enemy snapshots
    for entity in game["entities"]:
        components = entity["components"]
        if "Enemy" in components and "Position" in components and "Bounty" not in components:
            kind = kinds.get(components["Position"]["location"])
            seen.setdefault(kind, []).append(components["Enemy"])
        if "Spawner" in components:
            kind = kinds.get(components["Spawner"]["location"])
            seen.setdefault(kind, []).extend(components["Spawner"]["queue"])
    for entity in game["entities"]:
        spawner = entity["components"].get("Spawner")
        if spawner is not None:
            spawner["cap"] = MIGRATED_CAP
            spawner["templates"] = _templates(seen.get(kinds.get(spawner["location"]), []))
    return envelope


def _templates(enemies: list[dict]) -> list[dict]:
    by_kind: dict[str, list[dict]] = {}
    for enemy in enemies:
        by_kind.setdefault(enemy["enemy_id"], []).append(enemy)
    templates = []
    for enemy_id, copies in sorted(by_kind.items()):
        first = copies[0]
        loot = [item for e in copies for item in e["loot"]][:MIGRATED_LOOT_PIECES]
        templates.append(
            {
                "enemy_id": enemy_id,
                "name": first["name"],
                "category": first["category"],
                "description": first["description"],
                "stats": dict(first["stats"]),
                "rolls": {},
                "drops": list(first["drops"]),
                "loot_chance": MIGRATED_LOOT_CHANCE if loot else 0.0,
                "loot": loot,
                "weight": float(len(copies)),
            }
        )
    return templates


# What v8 gave every world, written out so later content changes can't alter this
# migration: starting gold, gold carried by each enemy category, quest gold.
MIGRATED_START_GOLD = 10
MIGRATED_ENEMY_GOLD = {"person": [2, 6], "spirit": [0, 2]}  # anything else carries none
MIGRATED_QUEST_GOLD = {"bounty": 16, "cull": 11, "explore": 11, "recover": 13}
MIGRATED_SMITHY_STOCK = 4
MIGRATED_SHOPS = (  # (shop_id, name, room noun, buys gear, inn)
    ("shop.smithy", "Smithy", "Smithy", True, False),
    ("shop.tavern", "Tavern", "Tavern", False, True),
)


def _v7_to_v8(envelope: Envelope) -> Envelope:
    # v8 adds the economy. The player gets starting gold; enemies, templates and
    # quests get gold by category or kind; every town gets a Smithy and a Tavern,
    # in rooms named for them or at the gate. The Smithy stocks plain copies (no
    # affixes or rolls) of gear already in the save (returning enemies' loot),
    # never content, so a world with none has an empty Smithy that still buys.
    game = envelope["game"]
    entities = game["entities"]
    loot: dict[str, dict] = {}
    for entity in entities:
        components = entity["components"]
        if "Player" in components:
            components["Wallet"] = {"gold": MIGRATED_START_GOLD}
        if "Enemy" in components:
            components["Enemy"]["gold"] = _enemy_gold(components["Enemy"])
        if "Quest" in components:
            components["Quest"]["gold"] = MIGRATED_QUEST_GOLD.get(components["Quest"]["kind"], 0)
        if "Spawner" in components:
            for enemy in components["Spawner"]["queue"]:
                enemy["gold"] = _enemy_gold(enemy)
            for template in components["Spawner"]["templates"]:
                template["gold"] = list(MIGRATED_ENEMY_GOLD.get(template["category"], [0, 0]))
                for item in template["loot"]:
                    loot.setdefault(item["gear_id"], item)
    plain = [{**item, "roll": {}, "upgrade": 0, "affixes": []} for _, item in sorted(loot.items())]

    next_id = game["next_entity_id"]
    for location in game["world"]["locations"]:
        if location["kind"] != "Town":
            continue
        for shop_id, name, noun, buys_gear, inn in MIGRATED_SHOPS:
            wares = plain if buys_gear else []
            shop_entity = next_id
            entities.append(
                {
                    "id": shop_entity,
                    "components": {
                        "Shop": {
                            "shop_id": shop_id,
                            "name": name,
                            "buys_gear": buys_gear,
                            "inn": inn,
                            "cap": MIGRATED_SMITHY_STOCK if wares else 0,
                            "wares": [dict(w) for w in wares],
                        },
                        "Position": {
                            "location": location["id"],
                            "room": _room_named(location, noun),
                        },
                    },
                }
            )
            next_id += 1
            for item in wares[:MIGRATED_SMITHY_STOCK]:
                entities.append(
                    {
                        "id": next_id,
                        "components": {"Item": dict(item), "Stocked": {"shop": shop_entity}},
                    }
                )
                next_id += 1
    game["next_entity_id"] = next_id
    return envelope


def _enemy_gold(enemy: dict) -> int:
    low, high = MIGRATED_ENEMY_GOLD.get(enemy["category"], [0, 0])
    return (low + high) // 2


def _room_named(location: dict, noun: str) -> str:
    pattern = re.compile(rf"(^|\s){re.escape(noun)}(\s[IVXLC]+)?$")
    for room in location["rooms"]:
        if room["id"] not in location["gates"] and pattern.search(room["name"]):
            return room["id"]
    return location["start"]


# What v9 gave every world, written out so later content changes can't alter this
# migration: materials, gear upgrade levels, enemy drops, starting recipes and the
# Market's goods.
MIGRATED_MATERIALS = {  # id -> (name, description, value)
    "material.crab_shell": ("Crab Shell", "Plates of shell, harder than they look.", 2),
    "material.driftwood": (
        "Driftwood",
        "Sea-bleached wood, light and hard. Good for hafts and frames.",
        1,
    ),
    "material.eel_skin": ("Eel Skin", "Supple, slick and waterproof.", 4),
    "material.hide": ("Hide", "A rough hide, scraped and salted.", 2),
    "material.iron_ore": (
        "Iron Ore",
        "Rust-red lumps from the old workings. A smith can make something of it.",
        2,
    ),
    "material.sailcloth": ("Sailcloth", "Tarred canvas, cut from wrecks and old sails.", 2),
    "material.spider_silk": (
        "Spider Silk",
        "Grey cord from the tunnel spiders' webs, strong as wire.",
        3,
    ),
    "material.timber": ("Seasoned Timber", "Straight, dry lengths of forest wood.", 2),
    "material.wisp_essence": ("Wisp Essence", "A faint cold light caught in a stoppered vial.", 6),
}
MIGRATED_UPGRADES = {  # gear id -> (max_upgrade, upgrade_step, materials per level)
    "gear.boathook": (2, {"atk": 1}, {"material.iron_ore": 1, "material.timber": 1}),
    "gear.buckler": (2, {"def": 1}, {"material.timber": 1, "material.iron_ore": 1}),
    "gear.cutlass": (3, {"atk": 1}, {"material.iron_ore": 2}),
    "gear.driftwood_club": (2, {"atk": 1}, {"material.timber": 1}),
    "gear.harpoon": (3, {"atk": 1}, {"material.iron_ore": 2}),
    "gear.miners_helm": (2, {"def": 1}, {"material.iron_ore": 1, "material.hide": 1}),
    "gear.oilskin_hood": (2, {"def": 1}, {"material.sailcloth": 2}),
    "gear.patched_coat": (2, {"def": 1}, {"material.hide": 1, "material.sailcloth": 1}),
    "gear.pick": (2, {"atk": 1}, {"material.iron_ore": 2}),
    "gear.sealskin_boots": (2, {"def": 1}, {"material.hide": 1, "material.eel_skin": 1}),
    "gear.storm_lantern": (2, {"hp": 2}, {"material.iron_ore": 1, "material.spider_silk": 1}),
    "gear.watchmans_coat": (2, {"def": 1}, {"material.hide": 2}),
    "gear.whalebone_charm": (2, {"hp": 2}, {"material.crab_shell": 2}),
}
MIGRATED_DROPS = {  # enemy id -> [(material, chance, low, high)]
    "enemy.cave_rat": [("material.hide", 0.3, 1, 1)],
    "enemy.conger_eel": [("material.eel_skin", 0.7, 1, 1)],
    "enemy.drowned_sailor": [("material.sailcloth", 0.5, 1, 2)],
    "enemy.shore_crab": [("material.crab_shell", 0.8, 1, 2)],
    "enemy.smuggler": [("material.sailcloth", 0.5, 1, 2)],
    "enemy.tunnel_spider": [("material.spider_silk", 0.7, 1, 2)],
    "enemy.wailing_wisp": [("material.wisp_essence", 0.5, 1, 1)],
    "enemy.wild_boar": [("material.hide", 0.8, 1, 2)],
    "enemy.wrecker": [("material.sailcloth", 0.4, 1, 2), ("material.iron_ore", 0.2, 1, 1)],
}
MIGRATED_RECIPES = [  # (recipe id, the Item it makes, materials)
    (
        "recipe.buckler",
        {
            "gear_id": "gear.buckler",
            "name": "Buckler",
            "slot": "off_hand",
            "two_handed": False,
            "base": {"def": 2},
            "roll": {"def": 1},
            "upgrade": 0,
            "max_upgrade": 2,
            "upgrade_step": {"def": 1},
            "affixes": [],
            "effects": [],
            "gear_set": None,
        },
        {"material.timber": 3, "material.iron_ore": 1},
    ),
    (
        "recipe.cutlass",
        {
            "gear_id": "gear.cutlass",
            "name": "Cutlass",
            "slot": "main_hand",
            "two_handed": False,
            "base": {"atk": 4},
            "roll": {"atk": 2},
            "upgrade": 0,
            "max_upgrade": 3,
            "upgrade_step": {"atk": 1},
            "affixes": [],
            "effects": [],
            "gear_set": None,
        },
        {"material.iron_ore": 3, "material.timber": 1},
    ),
    (
        "recipe.miners_helm",
        {
            "gear_id": "gear.miners_helm",
            "name": "Miner's Helm",
            "slot": "head",
            "two_handed": False,
            "base": {"def": 1, "hp": 2},
            "roll": {"hp": 2},
            "upgrade": 0,
            "max_upgrade": 2,
            "upgrade_step": {"def": 1},
            "affixes": [],
            "effects": [],
            "gear_set": None,
        },
        {"material.iron_ore": 2, "material.hide": 1},
    ),
    (
        "recipe.storm_lantern",
        {
            "gear_id": "gear.storm_lantern",
            "name": "Storm Lantern",
            "slot": "off_hand",
            "two_handed": False,
            "base": {"hp": 3},
            "roll": {"hp": 2},
            "upgrade": 0,
            "max_upgrade": 2,
            "upgrade_step": {"hp": 2},
            "affixes": [],
            "effects": [],
            "gear_set": None,
        },
        {"material.iron_ore": 2, "material.sailcloth": 1},
    ),
]
MIGRATED_MARKET = [
    "material.driftwood",
    "material.timber",
    "material.iron_ore",
    "material.sailcloth",
]
MIGRATED_BUYBACK = 6  # sold gear a smithy keeps (the newest)


def _v8_to_v9(envelope: Envelope) -> Envelope:
    # v9 adds materials and crafting. The player gets an empty satchel and the
    # starting recipes; enemies get no materials (they're rolled at creation) but
    # returning enemies' templates get their kind's drops; quests get no recipe.
    # Gear anywhere in the save that v9 made upgradable becomes upgradable (if it
    # wasn't), smithies learn upgrades and get a buy-back shelf (anything stocked
    # past the shop's cap counts as sold gear; only the newest few stay), and every
    # town gets a Market. Old worlds have nothing to gather and no recipe pages.
    game = envelope["game"]
    entities = game["entities"]
    _upgradable(game)
    removed: set[int] = set()
    stocked: dict[int, list[int]] = {}
    for entity in entities:
        components = entity["components"]
        if "Player" in components:
            components["Materials"] = {"held": {}}
            components["Recipes"] = {
                "known": {
                    rid: {
                        "recipe_id": rid,
                        "name": _display_name(item),
                        "makes": dict(item),
                        "materials": _stacks(needs),
                    }
                    for rid, item, needs in MIGRATED_RECIPES
                }
            }
        if "Enemy" in components:
            components["Enemy"]["materials"] = []
        if "Quest" in components:
            components["Quest"]["recipe"] = None
        if "Spawner" in components:
            for enemy in components["Spawner"]["queue"]:
                enemy["materials"] = []
            for template in components["Spawner"]["templates"]:
                template["materials"] = [
                    {"material": _material(m), "chance": chance, "low": low, "high": high}
                    for m, chance, low, high in MIGRATED_DROPS.get(template["enemy_id"], [])
                ]
        if "Stocked" in components:
            stocked.setdefault(components["Stocked"]["shop"], []).append(entity["id"])
    for entity in entities:
        shop = entity["components"].get("Shop")
        if shop is None:
            continue
        crafts = shop["shop_id"] == "shop.smithy"
        on_shelf = sorted(stocked.get(entity["id"], []))
        sold = on_shelf[shop["cap"] :]
        removed.update(sold[:-MIGRATED_BUYBACK] if MIGRATED_BUYBACK else sold)
        shop.update(
            buyback=sold[-MIGRATED_BUYBACK:] if MIGRATED_BUYBACK else [],
            materials=[],
            buys_materials=False,
            crafts=crafts,
            upgrades={g: _stacks(m) for g, (_, _, m) in MIGRATED_UPGRADES.items()}
            if crafts
            else {},
        )
    game["entities"] = entities = [e for e in entities if e["id"] not in removed]

    next_id = game["next_entity_id"]
    for location in game["world"]["locations"]:
        if location["kind"] != "Town":
            continue
        entities.append(
            {
                "id": next_id,
                "components": {
                    "Shop": {
                        "shop_id": "shop.market",
                        "name": "Market",
                        "buys_gear": False,
                        "inn": False,
                        "cap": 0,
                        "wares": [],
                        "buyback": [],
                        "materials": [_material(m) for m in MIGRATED_MARKET],
                        "buys_materials": True,
                        "crafts": False,
                        "upgrades": {},
                    },
                    "Position": {
                        "location": location["id"],
                        "room": _room_named(location, "Market"),
                    },
                },
            }
        )
        next_id += 1
    game["next_entity_id"] = next_id
    return envelope


def _material(material_id: str) -> dict:
    name, description, value = MIGRATED_MATERIALS[material_id]
    return {"material_id": material_id, "name": name, "description": description, "value": value}


def _stacks(needs: dict[str, int]) -> list[dict]:
    return [{"material": _material(m), "count": n} for m, n in needs.items()]


def _display_name(item: dict) -> str:
    prefixes = [a["name"] for a in item["affixes"] if a["prefix"]]
    suffixes = [a["name"] for a in item["affixes"] if not a["prefix"]]
    return " ".join([*prefixes, item["name"], *suffixes])


def _upgradable(value: Any) -> None:
    """Every Item snapshot anywhere in `value` that v9 made upgradable, if it wasn't."""
    if isinstance(value, dict):
        upgrade = MIGRATED_UPGRADES.get(value.get("gear_id"))
        if upgrade is not None and "max_upgrade" in value and not value["max_upgrade"]:
            value["max_upgrade"], value["upgrade_step"] = upgrade[0], dict(upgrade[1])
        for child in value.values():
            _upgradable(child)
    elif isinstance(value, list):
        for child in value:
            _upgradable(child)


# What v10 gave every world, written out so later content changes can't alter this
# migration: ingredients, the tavern's meals and the Market's new staples.
MIGRATED_INGREDIENTS = {  # id -> (name, description, value)
    "material.black_truffle": (
        "Black Truffle",
        "A knobbly black lump that smells of earth and money. Rare.",
        4,
    ),
    "material.boar_meat": ("Boar Meat", "A dark, heavy cut, already going stiff.", 2),
    "material.crab_meat": ("Crab Meat", "Sweet white meat picked from the shell.", 2),
    "material.eel_meat": ("Eel Meat", "Oily grey-white flesh. Smoked, it keeps for weeks.", 3),
    "material.kelp": ("Kelp", "Long brown ribbons of it, salty and rubbery. Better in a broth.", 1),
    "material.mushrooms": (
        "Mushrooms",
        "Pale caps from damp, dark places. The safe kind, probably.",
        1,
    ),
    "material.mussels": ("Mussels", "Blue-black shells prised off the rocks, still closed.", 1),
    "material.salt": ("Salt", "Coarse grey sea salt in a twist of cloth.", 1),
    "material.ships_biscuit": (
        "Ship's Biscuit",
        "Hard enough to break teeth; soften it in something first.",
        1,
    ),
    "material.wild_herbs": (
        "Wild Herbs",
        "Thyme, sorrel and something peppery, bundled with grass.",
        2,
    ),
}
MIGRATED_MEALS = [  # the Meal snapshot, its ingredients, sold ready-made
    (
        {
            "meal_id": "meal.boar_roast",
            "name": "Boar Roast",
            "description": "Charred outside, pink within, rubbed with herbs. You feel like hitting something.",  # noqa: E501
            "stats": {"atk": 2},
            "regen": 0,
            "turns": 60,
            "value": 6,
        },
        {"material.boar_meat": 2, "material.wild_herbs": 1},
        False,
    ),
    (
        {
            "meal_id": "meal.crab_cakes",
            "name": "Crab Cakes",
            "description": "Crab meat bound with crushed biscuit and fried. Filling enough for two.",  # noqa: E501
            "stats": {"hp": 6},
            "regen": 0,
            "turns": 60,
            "value": 5,
        },
        {"material.crab_meat": 2, "material.ships_biscuit": 1},
        False,
    ),
    (
        {
            "meal_id": "meal.harbour_feast",
            "name": "Harbour Feast",
            "description": "Roast boar, crab, a shaving of truffle and biscuit to mop it up. You could walk all day on it.",  # noqa: E501
            "stats": {"atk": 2, "def": 1, "hp": 8},
            "regen": 1,
            "turns": 90,
            "value": 13,
        },
        {
            "material.boar_meat": 2,
            "material.crab_meat": 2,
            "material.black_truffle": 1,
            "material.ships_biscuit": 1,
        },
        False,
    ),
    (
        {
            "meal_id": "meal.kelp_broth",
            "name": "Kelp Broth",
            "description": "A thin green broth that warms you through. You heal faster for a while.",  # noqa: E501
            "stats": {},
            "regen": 2,
            "turns": 60,
            "value": 3,
        },
        {"material.kelp": 2, "material.salt": 1},
        True,
    ),
    (
        {
            "meal_id": "meal.mushroom_pie",
            "name": "Mushroom Pie",
            "description": "A heavy pie with a biscuit crust. Not exciting, but it lasts.",
            "stats": {"atk": 1, "def": 1},
            "regen": 0,
            "turns": 90,
            "value": 4,
        },
        {"material.mushrooms": 3, "material.ships_biscuit": 1},
        False,
    ),
    (
        {
            "meal_id": "meal.mussel_stew",
            "name": "Mussel Stew",
            "description": "Mussels steamed open in their own juice. It sits well; blows seem to matter less.",  # noqa: E501
            "stats": {"def": 2},
            "regen": 0,
            "turns": 60,
            "value": 4,
        },
        {"material.mussels": 3, "material.salt": 1},
        True,
    ),
    (
        {
            "meal_id": "meal.smoked_eel_supper",
            "name": "Smoked Eel Supper",
            "description": "Eel smoked over driftwood, with herbs and coarse salt. Steadies the hand and the nerve.",  # noqa: E501
            "stats": {"atk": 2, "def": 2},
            "regen": 0,
            "turns": 60,
            "value": 9,
        },
        {"material.eel_meat": 2, "material.wild_herbs": 1, "material.salt": 1},
        False,
    ),
]
MIGRATED_MARKET_STAPLES = ["material.salt", "material.ships_biscuit"]


def _v9_to_v10(envelope: Envelope) -> Envelope:
    # v10 adds cooking. Every material snapshot gets `ingredient` (none were then);
    # the player gets an empty pantry (Meals); every shop gets `cooks` and `meals`,
    # and taverns cook every v10 meal; markets also sell salt and ship's biscuit.
    # Old worlds have no ingredients lying about, and their beasts drop none.
    game = envelope["game"]
    _not_ingredients(game)
    for entity in game["entities"]:
        components = entity["components"]
        if "Player" in components:
            components["Meals"] = {"held": {}}
        shop = components.get("Shop")
        if shop is None:
            continue
        cooks = bool(shop["inn"])
        shop["cooks"] = cooks
        shop["meals"] = (
            [
                {"meal": dict(meal), "ingredients": _ingredients(needs), "sold": sold}
                for meal, needs, sold in MIGRATED_MEALS
            ]
            if cooks
            else []
        )
        if shop["buys_materials"]:
            shop["materials"] += [_ingredient(m) for m in MIGRATED_MARKET_STAPLES]
    return envelope


def _ingredient(material_id: str) -> dict:
    name, description, value = MIGRATED_INGREDIENTS[material_id]
    return {
        "material_id": material_id,
        "name": name,
        "description": description,
        "value": value,
        "ingredient": True,
    }


def _ingredients(needs: dict[str, int]) -> list[dict]:
    return [{"material": _ingredient(m), "count": n} for m, n in needs.items()]


def _not_ingredients(value: Any) -> None:
    """Every Material snapshot in `value`: v9 had only crafting materials."""
    if isinstance(value, dict):
        if "material_id" in value and "ingredient" not in value:
            value["ingredient"] = False
        for child in value.values():
            _not_ingredients(child)
    elif isinstance(value, list):
        for child in value:
            _not_ingredients(child)


# from-version -> function producing the next version's envelope
MIGRATIONS: dict[int, Callable[[Envelope], Envelope]] = {
    1: _v1_to_v2,
    2: _v2_to_v3,
    3: _v3_to_v4,
    4: _v4_to_v5,
    5: _v5_to_v6,
    6: _v6_to_v7,
    7: _v7_to_v8,
    8: _v8_to_v9,
    9: _v9_to_v10,
}


class NewerSaveError(SaveError):
    """The save was made by a newer version of the app."""


def migrate(envelope: Envelope) -> Envelope:
    version = envelope.get("schema_version")
    if not isinstance(version, int) or version < 1:
        raise ValueError(f"save has no valid schema_version ({version!r})")
    if version > SCHEMA_VERSION:
        raise NewerSaveError(
            f"This world was saved by a newer version of Tidewrack (save format "
            f"{version}, this app reads up to {SCHEMA_VERSION}). Update the app to open it."
        )
    while version < SCHEMA_VERSION:
        envelope = MIGRATIONS[version](envelope)
        version += 1
        envelope["schema_version"] = version
    return envelope

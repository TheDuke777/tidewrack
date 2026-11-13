"""Content validation: every bundled file must load (CLAUDE.md §14 step 2), and
the loader must reject the mistakes content authors are likely to make."""

import copy
import json

import pytest

from tidewrack.core.data.loader import ContentError, content_hash, load_content
from tidewrack.services.content import CONTENT_ROOT, read_content_files

BUNDLED = read_content_files()


def test_bundled_content_is_valid():
    content = load_content(BUNDLED)  # raises ContentError listing every problem
    assert "dungeon.first_descent" in content.dungeons
    assert len(content.dungeon("dungeon.first_descent").rooms) == 7


def test_content_lives_where_flet_bundles_it():
    # flet build only packages src/ ([tool.flet.app] path).
    assert CONTENT_ROOT.parent.name == "src" and CONTENT_ROOT.is_dir()


def test_content_hash_is_stable_and_sensitive():
    assert content_hash(BUNDLED) == content_hash(dict(reversed(BUNDLED.items())))
    changed = dict(
        BUNDLED, **{"dungeons/first_descent.json": BUNDLED["dungeons/first_descent.json"] + " "}
    )
    assert content_hash(changed) != content_hash(BUNDLED)


# --- rejections ------------------------------------------------------------------

DUNGEON = json.loads(BUNDLED["dungeons/first_descent.json"])


def _problems(files: dict[str, str]) -> list[str]:
    with pytest.raises(ContentError) as e:
        load_content(files)
    return e.value.problems


def _dungeon_problems(mutate) -> list[str]:
    data = copy.deepcopy(DUNGEON)
    mutate(data)
    return _problems({"dungeons/first_descent.json": json.dumps(data)})


def test_rejects_unknown_keys():
    problems = _dungeon_problems(lambda d: d["rooms"][0].update(descripton="typo"))
    assert any("rooms.0.descripton" in p and "Extra inputs" in p for p in problems)


def test_rejects_missing_fields():
    problems = _dungeon_problems(lambda d: d["rooms"][0].pop("name"))
    assert any("rooms.0.name" in p and "required" in p for p in problems)


def test_rejects_dangling_exit():
    problems = _dungeon_problems(lambda d: d["rooms"][0]["exits"][0].update(to="nowhere"))
    assert any("unknown room 'nowhere'" in p for p in problems)


def test_rejects_unreachable_room():
    def strand_shrine(d):
        stair = next(n for n in d["rooms"] if n["id"] == "cliff_stair")
        stair["exits"] = [e for e in stair["exits"] if e["to"] != "tide_shrine"]

    assert any("tide_shrine: unreachable" in p for p in _dungeon_problems(strand_shrine))


def test_rejects_duplicate_room_ids():
    problems = _dungeon_problems(lambda d: d["rooms"].append(copy.deepcopy(d["rooms"][0])))
    assert any("duplicate room ids: wrack_cove" in p for p in problems)


def test_rejects_bad_ids():
    assert any(
        "rooms.0.id" in p
        for p in _dungeon_problems(lambda d: d["rooms"][0].update(id="Wrack Cove"))
    )
    assert any(
        p.startswith("dungeons/first_descent.json: id:")
        for p in _dungeon_problems(lambda d: d.update(id="first_descent"))
    )


def test_id_must_match_file_name():
    problems = _problems({"dungeons/other.json": BUNDLED["dungeons/first_descent.json"]})
    assert problems == [
        "dungeons/other.json: id is 'dungeon.first_descent' but this file must hold 'dungeon.other'"
    ]


def test_reports_every_problem_with_its_path():
    problems = _problems(
        {
            "dungeons/broken.json": "{not json",
            "monsters/rat.json": "{}",
            "dungeons/notes.txt": "",
            "dungeons/first_descent.json": BUNDLED["dungeons/first_descent.json"],
        }
    )
    assert [p.split(":")[0] for p in problems] == [
        "dungeons/broken.json",
        "dungeons/notes.txt",
        "monsters/rat.json",
    ]


def test_regions_must_name_existing_roomsets():
    region = json.loads(BUNDLED["regions/fens.json"])
    region["roomsets"]["roomset.lava_tubes"] = 1.0
    problems = _problems(dict(BUNDLED, **{"regions/fens.json": json.dumps(region)}))
    assert problems == ["regions/fens.json: unknown roomset 'roomset.lava_tubes'"]


def test_world_recipes_must_name_existing_regions():
    recipe = json.loads(BUNDLED["worlds/standard.json"])
    recipe["regions"].append({"region": "region.lava_fields", "locations": 5})
    problems = _problems(dict(BUNDLED, **{"worlds/standard.json": json.dumps(recipe)}))
    assert problems == ["worlds/standard.json: unknown region 'region.lava_fields'"]


def test_regions_go_inland_and_deeper_ones_have_wardens():
    recipe = json.loads(BUNDLED["worlds/standard.json"])
    recipe["regions"].reverse()
    problems = _problems(dict(BUNDLED, **{"worlds/standard.json": json.dumps(recipe)}))
    assert (
        "worlds/standard.json: regions must be listed coast first, each a higher tier" in problems
    )
    assert "worlds/standard.json: the first region can't have a warden" in problems
    assert "worlds/standard.json: region.wrack_coast needs a warden to guard the way in" in problems


def test_a_regions_first_place_must_be_a_town():
    region = json.loads(BUNDLED["regions/fens.json"])
    region["town"] = "roomset.peat_bog"
    problems = _problems(dict(BUNDLED, **{"regions/fens.json": json.dumps(region)}))
    assert problems == ["regions/fens.json: roomset.peat_bog isn't a town"]


def test_roomset_sizes_must_make_sense():
    roomset = json.loads(BUNDLED["roomsets/old_mine.json"])
    roomset["size"] = [9, 4]
    problems = _problems(dict(BUNDLED, **{"roomsets/old_mine.json": json.dumps(roomset)}))
    assert any("roomsets/old_mine.json" in p and "size must satisfy" in p for p in problems)


# --- gear --------------------------------------------------------------------------


def _edited(path: str, mutate) -> list[str]:
    data = json.loads(BUNDLED[path])
    mutate(data)
    return _problems(dict(BUNDLED, **{path: json.dumps(data)}))


def test_every_gear_set_can_be_completed_with_a_two_handed_weapon():
    """A two-hander fills both hands, so off-hand pieces (and one-handed main-hand
    pieces) are out of reach for its wielder: a set's biggest bonus must be
    reachable from the other slots alone (user rule; holds if sets grow to 5)."""
    content = load_content(BUNDLED)
    for set_id, gear_set in content.gearsets.items():
        pieces = [g for g in content.gear.values() if g.set == set_id]
        slots = {
            g.slot
            for g in pieces
            if g.slot != "off_hand" and (g.slot != "main_hand" or g.two_handed)
        }
        most = max(b.pieces for b in gear_set.bonuses)
        assert len(slots) >= most, f"{set_id}: a two-hander can wear {len(slots)} of {most}"


def test_bundled_gear_loads():
    content = load_content(BUNDLED)
    assert content.world("world.standard").kit == ["gear.driftwood_club", "gear.patched_coat"]
    assert content.gear["gear.harpoon"].two_handed
    assert content.gearsets["gearset.drowned_watch"].bonuses[0].pieces == 2


def test_gear_rejects_unknown_stats_and_slots():
    problems = _edited("gear/cutlass.json", lambda d: d.update(base={"str": 3}, slot="hand"))
    assert any("gear/cutlass.json: slot:" in p for p in problems)
    assert any("gear/cutlass.json: base:" in p and "unknown stats ['str']" in p for p in problems)
    problems = _edited("gear/cutlass.json", lambda d: d.update(rolls={"luck": [0, 1]}))
    assert any("unknown stats ['luck']" in p for p in problems)


def test_gear_rejects_inconsistent_definitions():
    problems = _edited("gear/buckler.json", lambda d: d.update(two_handed=True))
    assert any("two-handed gear must have slot main_hand" in p for p in problems)
    problems = _edited("gear/cutlass.json", lambda d: d.update(rolls={"atk": [3, 1]}))
    assert any("min 3 above max 1" in p for p in problems)
    problems = _edited("gear/cutlass.json", lambda d: d.update(upgrade_step={}))
    assert any("needs a non-zero upgrade_step" in p for p in problems)


def test_gear_references_must_exist():
    assert _edited("worlds/standard.json", lambda d: d["kit"].append("gear.trident")) == [
        "worlds/standard.json: unknown gear 'gear.trident'"
    ]
    assert _edited(
        "roomsets/old_mine.json", lambda d: d["finds"]["gear"].update({"gear.drill": 1})
    ) == ["roomsets/old_mine.json: unknown gear 'gear.drill'"]
    assert _edited("gear/cutlass.json", lambda d: d.update(set="gearset.pirate")) == [
        "gear/cutlass.json: unknown gear set 'gearset.pirate'"
    ]


def test_kit_cant_fill_a_slot_twice():
    problems = _edited("worlds/standard.json", lambda d: d["kit"].append("gear.harpoon"))
    assert problems == ["worlds/standard.json: kit has more than one item for a slot"]


def test_roomset_names_must_be_unique():
    problems = _edited("roomsets/old_mine.json", lambda d: d.update(name="Town"))
    assert problems == ["roomsets/old_mine.json: name 'Town' is also used by roomset.harbour_town"]


# --- enemies -----------------------------------------------------------------------


def test_bundled_enemies_include_people():
    content = load_content(BUNDLED)
    categories = {e.category for e in content.enemies.values()}
    assert {"beast", "person", "spirit"} <= categories


def test_enemies_reject_bad_definitions():
    problems = _edited("enemies/shore_crab.json", lambda d: d.update(category="monster"))
    assert any("enemies/shore_crab.json: category:" in p for p in problems)
    problems = _edited("enemies/shore_crab.json", lambda d: d["stats"].update(hp=0))
    assert any("at least 1 hp" in p for p in problems)
    problems = _edited("enemies/shore_crab.json", lambda d: d["stats"].update(luck=2))
    assert any("unknown stats ['luck']" in p for p in problems)


def test_enemy_references_must_exist():
    assert _edited(
        "enemies/shore_crab.json", lambda d: d["loot"]["gear"].update({"gear.anchor": 1})
    ) == ["enemies/shore_crab.json: unknown gear 'gear.anchor'"]
    assert _edited(
        "roomsets/old_mine.json", lambda d: d["enemies"]["pool"].update({"enemy.dragon": 1})
    ) == ["roomsets/old_mine.json: unknown enemy 'enemy.dragon'"]


# --- quests ------------------------------------------------------------------------


def test_bundled_quests_cover_every_type():
    content = load_content(BUNDLED)
    assert {q.type for q in content.quests.values()} == {"bounty", "cull", "explore", "recover"}
    assert load_content(BUNDLED).worlds["world.standard"].quests.per_board == 3


def test_quests_reject_bad_templates():
    problems = _edited("quests/cull.json", lambda d: d["titles"].append("Slay the {dragon}"))
    assert any("uses ['dragon']; cull quests may use" in p for p in problems)
    problems = _edited("quests/bounty.json", lambda d: d["epithets"].pop("spirit"))
    assert any("bounty epithets are needed" in p for p in problems)
    problems = _edited("quests/recover.json", lambda d: d.update(items=[]))
    assert any("recover quests need at least one item" in p for p in problems)
    problems = _edited("quests/cull.json", lambda d: d.update(counts=[5, 2]))
    assert any("counts must satisfy" in p for p in problems)


def test_each_quest_type_has_one_template():
    data = json.loads(BUNDLED["quests/explore.json"])
    data["id"] = "quest.explore_again"
    problems = _problems(dict(BUNDLED, **{"quests/explore_again.json": json.dumps(data)}))
    assert problems == [
        "quests/explore_again.json: another file (quests/explore.json) already defines "
        "explore quests"
    ]

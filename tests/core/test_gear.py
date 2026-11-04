"""Stat pipeline and gear comparison (CLAUDE.md §8.4)."""

from dataclasses import replace

from tidewrack.core.gear.compare import compare, format_stats
from tidewrack.core.gear.item import Affix, GearSet, Item, SetBonus, slots_taken
from tidewrack.core.gear.stat_pipeline import (
    active_set_bonuses,
    at_max_upgrade,
    item_base,
    item_total,
    item_upgraded,
    player_stats,
)

BASE = {"atk": 2, "def": 1, "hp": 20}
WATCH = GearSet(
    "gearset.watch",
    "Drowned Watch",
    [SetBonus(2, {"def": 2}, ["Breathe underwater."]), SetBonus(3, {"hp": 5})],
)


def gear(name, slot, two_handed=False, gear_set=None, effects=(), **stats):
    return Item(
        gear_id=f"gear.{name.lower().replace(' ', '_')}",
        name=name,
        slot=slot,
        two_handed=two_handed,
        base=stats,
        gear_set=gear_set,
        effects=list(effects),
    )


CLUB = gear("Club", "main_hand", atk=2)
SHIELD = gear("Buckler", "off_hand", **{"def": 2})
HARPOON = gear("Harpoon", "main_hand", two_handed=True, atk=7)
HOOD = gear("Hood", "head", gear_set=WATCH, **{"def": 1})
COAT = gear("Coat", "body", gear_set=WATCH, **{"def": 2})
BOOTS = gear("Boots", "feet", gear_set=WATCH, **{"def": 1})


def stats_of(comparison):
    return {r.stat: (r.base_delta, r.total_delta, r.before, r.after) for r in comparison.rows}


# --- pipeline ----------------------------------------------------------------------


def test_each_stage_builds_on_the_last():
    cutlass = Item(
        gear_id="gear.cutlass",
        name="Cutlass",
        slot="main_hand",
        base={"atk": 4},
        roll={"atk": 1},
        upgrade=2,
        max_upgrade=3,
        upgrade_step={"atk": 1, "def": 1},
        affixes=[Affix("affix.barnacled", "Barnacled", True, {"atk": -1, "def": 2})],
    )
    assert item_base(cutlass) == {"atk": 5, "def": 0, "hp": 0}
    assert item_upgraded(cutlass) == {"atk": 7, "def": 2, "hp": 0}
    assert item_total(cutlass) == {"atk": 6, "def": 4, "hp": 0}
    assert cutlass.display_name == "Barnacled Cutlass +2"
    assert item_total(at_max_upgrade(cutlass)) == {"atk": 7, "def": 5, "hp": 0}
    assert at_max_upgrade(replace(cutlass, upgrade=3)) is None


def test_set_bonuses_need_enough_pieces():
    assert active_set_bonuses([HOOD]) == []
    assert [b.pieces for _, b in active_set_bonuses([HOOD, COAT])] == [2]
    assert [b.pieces for _, b in active_set_bonuses([HOOD, COAT, BOOTS])] == [2, 3]
    sheet = player_stats(BASE, [HOOD, COAT, BOOTS])
    assert sheet.total == {"atk": 2, "def": 1 + 4 + 2, "hp": 25}
    assert [s.label for s in sheet.sources] == [
        "Base",
        "Hood",
        "Coat",
        "Boots",
        "Drowned Watch (2 pieces)",
        "Drowned Watch (3 pieces)",
    ]


def test_two_handers_take_both_hands():
    assert slots_taken(HARPOON) == ("main_hand", "off_hand")
    assert slots_taken(CLUB) == ("main_hand",)


# --- compare -----------------------------------------------------------------------


def test_same_slot_swap_reports_base_total_and_player_change():
    keen = replace(gear("Cutlass", "main_hand", atk=4), roll={"atk": 1})
    keen.affixes = [Affix("affix.keen", "Keen", True, {"atk": 1})]
    result = compare(keen, [CLUB, SHIELD], BASE)
    assert result.replaces == ("Club",)
    assert stats_of(result)["atk"] == (3, 4, 4, 8)  # base 5 vs 2; total 6 vs 2
    assert stats_of(result)["def"] == (0, 0, 3, 3)
    assert result.verdict == "better"


def test_an_empty_slot_replaces_nothing():
    result = compare(HOOD, [CLUB], BASE)
    assert result.replaces == () and result.verdict == "better"


def test_a_two_hander_replaces_main_and_off_hand():
    result = compare(HARPOON, [CLUB, SHIELD], BASE)
    assert result.replaces == ("Club", "Buckler")
    assert stats_of(result)["atk"] == (5, 5, 4, 9)
    assert stats_of(result)["def"] == (-2, -2, 3, 1)
    assert result.verdict == "mixed"
    assert result.slot == "Both hands"


def test_an_off_hand_item_replaces_an_equipped_two_hander():
    result = compare(SHIELD, [HARPOON], BASE)
    assert result.replaces == ("Harpoon",)
    assert stats_of(result)["atk"] == (-7, -7, 9, 2)
    assert result.verdict == "mixed"


def test_comparing_an_equipped_item_changes_nothing():
    result = compare(CLUB, [CLUB, SHIELD], BASE)
    assert result.equipped and result.replaces == () and result.verdict == "same"
    assert all(r.base_delta == r.total_delta == r.change == 0 for r in result.rows)


def test_set_bonuses_gained_and_lost_count_toward_the_player():
    gained = compare(BOOTS, [HOOD, COAT], BASE)
    assert gained.sets_gained == ("Drowned Watch (3 pieces): HP +5",)
    assert stats_of(gained)["hp"] == (0, 0, 20, 25)  # the item gives no HP; the set does

    plain_hood = gear("Iron Helm", "head", **{"def": 2})
    lost = compare(plain_hood, [HOOD, COAT], BASE)
    assert lost.sets_lost == ("Drowned Watch (2 pieces): DEF +2; Breathe underwater.",)
    assert lost.effects_lost == ("Breathe underwater.",)
    assert stats_of(lost)["def"] == (1, 1, 6, 5)  # +1 from the helm, −2 from the set
    assert lost.verdict == "worse"


def test_effect_text_diff():
    lantern = gear("Lantern", "off_hand", effects=["Lights dark places."], hp=3)
    result = compare(lantern, [CLUB, SHIELD], BASE)
    assert result.effects_gained == ("Lights dark places.",)
    assert result.effects_lost == ()


def test_at_max_upgrade_line():
    cutlass = replace(gear("Cutlass", "main_hand", atk=4), max_upgrade=3, upgrade_step={"atk": 1})
    assert compare(cutlass, [CLUB], BASE).at_max == {"atk": 9, "def": 1, "hp": 20}
    assert compare(CLUB, [CLUB], BASE).at_max is None


def test_verdicts():
    assert compare(gear("Twig", "main_hand", atk=1), [CLUB], BASE).verdict == "worse"
    assert compare(gear("Copy", "main_hand", atk=2), [CLUB], BASE).verdict == "same"


def test_format_stats_uses_signs_and_skips_zeros():
    assert format_stats({"atk": -1, "def": 2}) == "ATK −1, DEF +2"
    assert format_stats({}) == ""

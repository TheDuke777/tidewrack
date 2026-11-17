"""Quick difficulty sim for CI (sim/difficulty_sim.py, CLAUDE.md §8.7)."""

import difficulty_sim as sim
import pytest

from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()


@pytest.fixture(scope="module")
def rows():
    return sim.simulate(CONTENT, fights=300)


def regions(rows):
    return list(dict.fromkeys(r.region for r in rows))


def test_ordinary_foes_are_always_beaten(rows):
    # The bot never flees or defends: an ordinary foe of a region must still
    # fall to the gear you'd arrive in (the coast: the starting kit), on Hard too.
    for region in regions(rows):
        for difficulty in ("Easy", "Standard", "Hard"):
            s = sim.summary(rows, region, "arriving", difficulty)
            assert s["median foe"].win >= 0.99, (region, difficulty)


def test_wardens_are_a_test_with_a_meal_as_the_edge(rows):
    for region in regions(rows):
        for difficulty in ("Easy", "Standard", "Hard"):
            s = sim.summary(rows, region, "arriving", difficulty)
            if "warden" not in s:
                continue
            assert s["warden fed"].win >= 0.95, (region, difficulty)  # a meal gets you through
            assert s["warden fed"].hp_lost < s["warden"].hp_lost, (region, difficulty)
        assert (
            sim.summary(rows, region, "arriving", "Standard").get("warden", sim.Odds(1, 0, 0)).win
            >= 0.8
        ), region


def test_a_geared_region_is_comfortable(rows):
    for region in regions(rows):
        s = sim.summary(rows, region, "geared", "Standard")
        assert s["worst foe"].hp_lost <= 0.1, region
        assert s["bounty"].win >= 0.95, region


def test_harder_presets_cost_more_health(rows):
    for region in regions(rows):
        for gear in ("arriving", "geared"):
            lost = [
                sim.summary(rows, region, gear, d)["worst foe"].hp_lost
                for d in ("Easy", "Standard", "Hard")
            ]
            assert lost == sorted(lost), (region, gear, lost)


def test_meals_unlock_with_their_ingredients():
    tiers = sim.material_tiers(CONTENT)
    for meal in CONTENT.meals.values():
        assert sim.meal_tier(meal, tiers) is not None, meal.id  # every meal can be cooked
    coast = {m.id for m in sim.meals_by(CONTENT, 1)}
    assert "meal.bear_stew" not in coast and "meal.boar_roast" in coast


def test_every_region_after_the_coast_bites_on_arrival(rows):
    # 8b retune (playtests: the Moors felt right, the coast and Fens too easy).
    # Arriving in maxed gear from the region before, on Standard: its worst foe
    # hurts and its warden costs about half your health unfed, without being a
    # coin flip.
    for region in regions(rows)[1:]:
        s = sim.summary(rows, region, "arriving", "Standard")
        assert s["worst foe"].hp_lost >= 0.08, region
        assert 0.4 <= s["warden"].hp_lost <= 0.85, region


def test_bounties_stay_fair_once_geared(rows):
    # Bounties are "come back when you've geared up here" fights (user, 2026-11-16):
    # hard on arrival, under about half your health once geared.
    for region in regions(rows):
        assert sim.summary(rows, region, "geared", "Standard")["bounty"].hp_lost <= 0.55, region


def test_each_region_cooks_its_own_best_meal():
    # 8b meals: a region's own meals beat everything cookable before it, for the
    # fights they're for (its hardest bounty and the next warden), by a margin.
    for edge in sim.meal_edges(CONTENT, fights=300)[1:]:
        assert edge.own_lost <= 0.9 * edge.earlier_lost, edge

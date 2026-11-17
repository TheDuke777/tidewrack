"""Quick economy sim for CI (sim/economy_sim.py, CLAUDE.md §8.6)."""

import economy_sim

from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()


def test_no_arbitrage_and_no_top_tier_gear_for_sale():
    assert economy_sim.lint_content(CONTENT) == []
    for seed in range(15):
        assert economy_sim.simulate(seed, CONTENT).problems == []


def test_a_world_pays_enough_to_buy_from_its_shops():
    # Loose bounds until the step-8 sim: a world pays more than its shops' first
    # stock costs, and the start gold buys at least a night at the inn.
    reports = [economy_sim.simulate(seed, CONTENT) for seed in range(15)]
    assert all(r.income > r.stock_cost for r in reports)
    assert CONTENT.world("world.standard").gold >= 4


def test_regrowth_is_a_trickle():
    # Even picking every spot the moment it grows, regrowth (v0.8.2) pays well
    # under a tenth of what a world holds at the start, per 100 turns.
    for seed in range(5):
        r = economy_sim.simulate(seed, CONTENT)
        assert 0 < r.regrowth <= 0.1 * r.income, (seed, r.regrowth, r.income)

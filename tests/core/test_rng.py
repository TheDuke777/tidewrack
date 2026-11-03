import json

import pytest

from tidewrack.core.rng import Rng, splitmix64


def _rng_with_state(s: list[int]) -> Rng:
    rng = Rng(0)
    rng._s = list(s)
    return rng


def test_xoshiro256starstar_reference_vector():
    # Published reference output for state {1, 2, 3, 4}.
    rng = _rng_with_state([1, 2, 3, 4])
    assert [rng.next_u64() for _ in range(3)] == [11520, 0, 1509978240]


def test_splitmix64_reference_vector():
    assert splitmix64(0)[0] == 0xE220A8397B1DCDAF


def test_golden_seed():
    # If this changes, every seeded world changes: bump generator_version (§9).
    rng = Rng(42)
    assert [rng.randint(1, 100) for _ in range(8)] == [43, 3, 10, 94, 77, 85, 55, 8]


def test_same_seed_same_stream():
    a, b = Rng(123), Rng(123)
    assert [a.next_u64() for _ in range(50)] == [b.next_u64() for _ in range(50)]
    assert Rng(124).next_u64() != Rng(123).next_u64()


def test_state_round_trips_through_json():
    rng = Rng(7)
    for _ in range(10):
        rng.next_u64()
    restored = Rng.from_state(json.loads(json.dumps(rng.get_state())))
    assert [restored.next_u64() for _ in range(20)] == [rng.next_u64() for _ in range(20)]


def test_invalid_state_rejected():
    with pytest.raises(ValueError):
        Rng.from_state({"seed": 1, "s": [0, 0, 0, 0]})


def test_derive_is_independent_of_parent_draws():
    parent = Rng(99)
    before = parent.derive("loot").next_u64()
    for _ in range(100):
        parent.next_u64()
    assert parent.derive("loot").next_u64() == before
    assert parent.derive("loot").next_u64() != parent.derive("ambient").next_u64()


def test_helpers_stay_in_range():
    rng = Rng(5)
    assert all(1 <= rng.randint(1, 6) <= 6 for _ in range(1000))
    assert all(0.0 <= rng.random() < 1.0 for _ in range(1000))
    assert {rng.randint(1, 6) for _ in range(1000)} == {1, 2, 3, 4, 5, 6}
    with pytest.raises(ValueError):
        rng.randint(3, 2)
    with pytest.raises(IndexError):
        rng.choice([])


def test_shuffle_is_a_seeded_permutation():
    items = list(range(20))
    a, b = items.copy(), items.copy()
    Rng(1).shuffle(a)
    Rng(1).shuffle(b)
    assert a == b and sorted(a) == items and a != items


def test_weighted_choice_respects_zero_weights():
    rng = Rng(3)
    picks = {rng.weighted_choice(["a", "b", "c"], [1, 0, 3]) for _ in range(500)}
    assert picks == {"a", "c"}

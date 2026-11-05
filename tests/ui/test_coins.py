from pathlib import Path

import flet as ft

from tidewrack.ui import theme
from tidewrack.ui.components.coins import COIN, PURSE, coins, label_of, purse


def test_each_gold_amount_becomes_a_number_and_a_labelled_coin():
    row = coins("Sell all 3 · 12 gold")
    assert [type(c) for c in row.controls] == [ft.Text, ft.Icon]
    assert row.controls[0].value == "Sell all 3 · 12"
    assert row.controls[1].icon == COIN and row.controls[1].semantics_label == "gold"
    assert label_of(row) == "Sell all 3 · 12 gold"  # what tests and screen readers get


def test_text_around_and_between_amounts_is_kept():
    row = coins("Reward: Charm + 8 gold + the Kelp Broth recipe")
    assert [c.value for c in row.controls if isinstance(c, ft.Text)] == [
        "Reward: Charm + 8",
        " + the Kelp Broth recipe",
    ]
    assert len(coins("Tavern · beds 4 gold · kitchen").controls) == 3


def test_no_amount_is_just_the_text():
    row = coins("Leave")
    assert [c.value for c in row.controls] == ["Leave"]
    assert label_of("plain") == "plain" and label_of(None) == ""


def test_the_purse_is_tinted_gold_for_the_brightness(monkeypatch):
    monkeypatch.setattr(theme, "_dark", False)
    bag, amount = purse(42).controls
    assert bag.src == PURSE and bag.color == ft.Colors.AMBER_800 and amount.value == "42"
    assert label_of(purse(42)) == "42 gold"
    monkeypatch.setattr(theme, "_dark", True)
    assert purse(42).controls[0].color == ft.Colors.AMBER_300


def test_the_purse_art_is_bundled():
    assert (Path(__file__).parents[2] / "src" / "assets" / PURSE).is_file()

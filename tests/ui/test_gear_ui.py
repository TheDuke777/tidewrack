import flet as ft

from tidewrack.core.engine.game import Game
from tidewrack.core.gear.compare import Comparison, StatRow
from tidewrack.core.procgen.gear_gen import generate_kit, make_item
from tidewrack.core.world.overworld import Overworld
from tidewrack.services.content import load_bundled_content
from tidewrack.ui.components.gear_compare_card import gear_compare_card, impact_line, subtitle
from tidewrack.ui.components.stat_delta import delta_label

CONTENT = load_bundled_content()
RECIPE = CONTENT.world("world.standard")
FIRST_DESCENT = CONTENT.dungeon("dungeon.first_descent")


def _game() -> Game:
    world = Overworld(FIRST_DESCENT.id, {FIRST_DESCENT.id: FIRST_DESCENT})
    harpoon = make_item(CONTENT.gear["gear.harpoon"], CONTENT.gearsets)
    return Game(
        1,
        world,
        RECIPE.player,
        generate_kit(RECIPE, CONTENT),
        [(FIRST_DESCENT.id, "wrack_cove", harpoon)],
    )


def _texts(control) -> list[str]:
    """Every Text value in a control tree."""
    found = []

    def walk(c):
        if isinstance(c, ft.Text) and c.value:
            found.append(c.value)
        for attr in ("content", "controls"):
            child = getattr(c, attr, None)
            for x in child if isinstance(child, list) else [child]:
                if isinstance(x, ft.Control):
                    walk(x)

    walk(control)
    return found


def test_deltas_always_carry_a_symbol_and_sign():
    assert delta_label(3) == "▲ +3"
    assert delta_label(-2) == "▼ −2"
    assert delta_label(0) == "＝ 0"


def test_card_shows_verdict_replacement_and_both_deltas():
    harpoon = _game().view().items_here[0]
    texts = _texts(gear_compare_card(harpoon))
    assert "Harpoon" in texts and "◆ Mixed" not in texts and "▲ Better" in texts
    assert subtitle(harpoon) == "Both hands · upgrade +0/3 · replaces Driftwood Club"
    # ATK row: base and total both +5 (7 vs the club's 2); the player goes 4 → 9.
    assert texts.count("▲ +5") == 2 and "4 → 9" in texts
    assert any(t.startswith("Fully upgraded, you'd have ATK 12") for t in texts)
    assert impact_line(harpoon.comparison) == "ATK 4 → 9 · DEF 2 · HP 20"


def test_impact_line_lists_every_stat():
    rows = (StatRow("atk", 1, 1, 4, 5), StatRow("def", -1, -1, 3, 2), StatRow("hp", 0, 0, 20, 20))
    comparison = Comparison("X", "Main hand", False, (), rows, "mixed", (), (), (), (), None)
    assert impact_line(comparison) == "ATK 4 → 5 · DEF 3 → 2 · HP 20"


def test_screens_build(tmp_path):
    from tidewrack.services.session import GameSession
    from tidewrack.services.settings import SettingsStore
    from tidewrack.services.storage import FileSaveStore
    from tidewrack.ui.screens.game import GameScreen
    from tidewrack.ui.screens.inventory import InventoryScreen

    session = GameSession.generate(
        FileSaveStore(tmp_path / "saves"), CONTENT, "world.standard", "W", 20261103
    )
    screen = GameScreen(
        session, SettingsStore(tmp_path / "s.json"), on_back=lambda: None, on_inventory=lambda: None
    )
    assert screen.status.value.startswith("ATK 4 DEF 2 HP 20 · Turn 0")
    inventory = InventoryScreen(session, on_back=lambda: None)
    texts = _texts(inventory.control)
    assert "ATK 4   DEF 2   HP 20" in texts and "Head: empty" in texts
    assert "Your pack is empty." in texts

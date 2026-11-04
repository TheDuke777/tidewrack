import flet as ft

from tidewrack.core.engine.components import Codex, Enemy
from tidewrack.core.engine.game import Attack, Defend, Flee, Game, Move
from tidewrack.core.world.overworld import Overworld
from tidewrack.services.content import load_bundled_content
from tidewrack.ui.components.combat_panel import combat_panel
from tidewrack.ui.screens.codex import UNKNOWN, foe_lines

CONTENT = load_bundled_content()
FIRST_DESCENT = CONTENT.dungeon("dungeon.first_descent")
WORLD = Overworld(FIRST_DESCENT.id, {FIRST_DESCENT.id: FIRST_DESCENT})


def _fighting() -> Game:
    smuggler = Enemy(
        "enemy.smuggler", "Smuggler", "person", "Knife drawn.", {"atk": 5, "def": 3, "hp": 14}
    )
    game = Game(1, WORLD, enemies=[(FIRST_DESCENT.id, "cliff_stair", smuggler)])
    game.perform(Move("Descend the cliff stair"))
    return game


def _walk(control):
    yield control
    for attr in ("content", "controls"):
        child = getattr(control, attr, None)
        for x in child if isinstance(child, list) else [child]:
            if isinstance(x, ft.Control):
                yield from _walk(x)


def test_combat_panel_shows_hp_as_text_and_sends_commands():
    game = _fighting()
    sent = []
    panel = combat_panel(game.view(), sent.append)
    texts = [c.value for c in _walk(panel) if isinstance(c, ft.Text)]
    assert "Fighting: Smuggler" in texts and "Person · ATK 5 · DEF 3" in texts
    assert "Smuggler: HP 14/14" in texts and "You: HP 20/20" in texts
    buttons = [
        c
        for c in _walk(panel)
        if isinstance(c, ft.FilledButton | ft.OutlinedButton | ft.TextButton)
    ]
    for button in buttons:
        button.on_click(None)
    assert sent == [Attack(), Defend(), Flee()]


def test_codex_lines_hide_what_isnt_known_yet():
    game = _fighting()
    [foe] = game.foes().foes
    assert foe_lines(foe) == [
        "Defeated: 0",
        f"Strength: {UNKNOWN}",
        f"Drops: {UNKNOWN}",
        "Defeat one to learn its strength.",
    ]
    game.world.get(game.player, Codex).kills["enemy.smuggler"] = 3
    [foe] = game.foes().foes
    assert foe_lines(foe)[1:3] == ["Strength: ATK 5 · DEF 3 · HP 14", "Drops: nothing"]

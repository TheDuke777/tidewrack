import flet as ft

from tidewrack.core.engine.components import Codex, Enemy
from tidewrack.core.engine.game import Attack, Defend, Equip, Flee, Game, Move
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
        "Found in: Dungeon",
        "Defeat one to learn its strength.",
    ]
    game.world.get(game.player, Codex).kills["enemy.smuggler"] = 3
    [foe] = game.foes().foes
    assert foe_lines(foe)[1:3] == ["Strength: ATK 5 · DEF 3 · HP 14", "Drops: nothing"]


def _shell_in_a_fight(tmp_path):
    from tidewrack.core.engine.components import Carried
    from tidewrack.core.procgen.gear_gen import make_item
    from tidewrack.services.session import GameSession
    from tidewrack.services.settings import SettingsStore
    from tidewrack.services.storage import FileSaveStore
    from tidewrack.ui.shell import WorldShell

    smuggler = Enemy(
        "enemy.smuggler", "Smuggler", "person", "Knife.", {"atk": 1, "def": 0, "hp": 50}
    )
    world = Overworld(FIRST_DESCENT.id, {FIRST_DESCENT.id: FIRST_DESCENT})
    session = GameSession.new(
        FileSaveStore(tmp_path / "saves"),
        CONTENT,
        world,
        "W",
        1,
        enemies=[(FIRST_DESCENT.id, "cliff_stair", smuggler)],
    )
    boots = make_item(CONTENT.gear["gear.sealskin_boots"], CONTENT.gearsets)
    session.game.world.create(boots, Carried(session.game.player))
    toasts = []
    shell = WorldShell(
        session,
        SettingsStore(tmp_path / "s.json"),
        on_back=lambda: None,
        confirm=lambda *a: None,
        notify=toasts.append,
    )
    shell.explore.act(Move("Descend the cliff stair"))
    return session, shell, toasts


def test_a_fight_takes_over_the_explore_screen(tmp_path):
    _, shell, _ = _shell_in_a_fight(tmp_path)
    explore = shell.explore
    assert not explore.map.control.visible and not explore.map_choice.visible
    assert explore.combat.controls and not explore.exits.visible
    explore.act(Flee())  # may or may not get away; either way the screen follows
    fighting = explore.session.game.view().combat is not None
    assert explore.map.control.visible == (not fighting)


def test_gear_actions_mid_fight_explain_themselves(tmp_path):
    session, shell, toasts = _shell_in_a_fight(tmp_path)
    shell.select(1)
    [boots] = session.game.inventory().pack
    shell.inventory.act(Equip(boots.id))
    assert toasts == ["You're fighting the Smuggler!"]


def test_codex_sections_collapse_at_every_level_and_remember(tmp_path):
    session, shell, _ = _shell_in_a_fight(tmp_path)
    shell.select(3)
    foes, *others = shell.codex.sections.controls
    titles = [_title(s) for s in shell.codex.sections.controls]
    assert titles[0] == "Foes (1)"
    assert [t.split(" (")[0] for t in titles[1:]] == [
        "Materials",
        "Ingredients",
        "Recipes",
        "Meals",
    ]
    assert isinstance(foes, ft.ExpansionTile) and foes.expanded  # it holds a new foe
    assert not any(s.expanded for s in others)  # nothing new: a list of contents
    [people] = foes.controls
    assert isinstance(people, ft.ExpansionTile) and _title(people) == "People (1)"

    class Changed:
        data = False

    people.on_change(Changed())
    shell.codex.refresh()
    foes = shell.codex.sections.controls[0]
    assert foes.expanded and not foes.controls[0].expanded


def _title(tile: ft.ExpansionTile) -> str:
    return tile.title.controls[0].value  # beside it, maybe a "New" chip


def test_set_items_wear_their_set_chip():
    from tidewrack.core.procgen.gear_gen import make_item
    from tidewrack.ui.components.gear_compare_card import chips
    from tidewrack.ui.components.set_chip import PALETTE, set_color

    hood = make_item(CONTENT.gear["gear.oilskin_hood"], CONTENT.gearsets)
    game = Game(1, WORLD, finds=[(FIRST_DESCENT.id, "wrack_cove", hood)])
    [view] = game.view().items_here
    assert (view.gear_set, view.gear_set_color) == ("Drowned Watch", "teal")
    texts = [c.value for chip in chips(view) for c in _walk(chip) if isinstance(c, ft.Text)]
    assert texts == ["▲ Better", "Drowned Watch set"]
    assert set_color("gearset.drowned_watch", "teal") == PALETTE["teal"]
    assert set_color("gearset.old", None) == set_color("gearset.old", None)  # older saves
    assert set_color("gearset.drowned_watch", None) == PALETTE["teal"]  # matches new pieces

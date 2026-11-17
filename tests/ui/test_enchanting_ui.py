"""The Enchanter's panel and dialog (v0.13.0)."""

import flet as ft

from tidewrack.core.economy import crafting
from tidewrack.core.engine.components import MaterialStack, Position, Shop, Wallet
from tidewrack.core.procgen.material_gen import make_material
from tidewrack.services.content import load_bundled_content
from tidewrack.ui.components.coins import label_of

CONTENT = load_bundled_content()


def _shell_at_the_enchanter(tmp_path, toasts):
    from tidewrack.services.session import GameSession
    from tidewrack.services.settings import SettingsStore
    from tidewrack.services.storage import FileSaveStore
    from tidewrack.ui.shell import WorldShell

    session = GameSession.generate(
        FileSaveStore(tmp_path / "saves"), CONTENT, "world.standard", "W", 20261103
    )
    game = session.game
    here = game.world.get(game.player, Position)
    at = next(
        p
        for _, (s, p) in game.world.query(Shop, Position)
        if s.enchants and p.location == here.location
    )
    here.room = at.room
    for name, count in (("iron_ore", 2), ("wisp_essence", 1)):
        crafting.add(
            game,
            MaterialStack(make_material(CONTENT.materials[f"material.{name}"]), count),
            "bought",
        )
    game.world.get(game.player, Wallet).gold = 50
    shell = WorldShell(
        session,
        SettingsStore(tmp_path / "s.json"),
        on_back=lambda: None,
        confirm=lambda *_: None,
        notify=toasts.append,
    )
    return session, shell


def _buttons(control, text):
    out = []

    def walk(c):
        if isinstance(c, (ft.FilledTonalButton, ft.FilledButton)) and c.content == text:
            out.append(c)
        for attr in ("content", "controls"):
            child = getattr(c, attr, None)
            for x in child if isinstance(child, list) else [child]:
                if isinstance(x, ft.Control):
                    walk(x)

    walk(control)
    return out


def test_the_enchanter_enchants_a_piece_you_choose(tmp_path):
    toasts: list[str] = []
    session, shell = _shell_at_the_enchanter(tmp_path, toasts)
    screen = shell.explore
    screen.refresh()
    labels = [label_of(b.content) for b in screen.entrances.controls]
    assert any(text.startswith("Tide-Priest · enchants") for text in labels)
    screen.open("Tide-Priest")
    [first, *_] = _buttons(screen.shops, "Enchant…")
    first.on_click(None)
    dialog = screen._enchant_dialog
    assert dialog.scrollable  # sized to its content
    radios = {}

    def walk(c):
        if isinstance(c, ft.Radio):
            radios[c.label] = c
        for attr in ("content", "controls"):
            child = getattr(c, attr, None)
            for x in child if isinstance(child, list) else [child]:
                if isinstance(x, ft.Control):
                    walk(x)

    walk(dialog.content)
    assert not radios["Baneful I"].disabled  # you have its materials
    assert radios["of the Leech I"].disabled  # you don't
    group = next(c for c in dialog.content.controls if isinstance(c, ft.RadioGroup))
    group.value = radios["Baneful I"].value
    group.on_change(None)
    go = dialog.actions[-1]
    assert not go.disabled
    go.on_click(None)
    assert toasts and toasts[-1].startswith("It's now a Baneful ")
    assert session.game.sheet().effects == {"bane": 1}

"""The notice board on Explore, the Quests tab and quest marks on the maps."""

import flet as ft

from tidewrack.core.engine.components import Quest
from tidewrack.core.engine.game import AcceptQuest, MapNode, Move
from tidewrack.services.content import load_bundled_content
from tidewrack.ui.map_canvas import badges, label
from tidewrack.ui.screens.quests import EMPTY

CONTENT = load_bundled_content()


def _shell(tmp_path):
    from tidewrack.services.session import GameSession
    from tidewrack.services.settings import SettingsStore
    from tidewrack.services.storage import FileSaveStore
    from tidewrack.ui.shell import WorldShell

    session = GameSession.generate(
        FileSaveStore(tmp_path / "saves"), CONTENT, "world.standard", "W", 20261103
    )
    toasts: list[str] = []
    shell = WorldShell(
        session,
        SettingsStore(tmp_path / "s.json"),
        on_back=lambda: None,
        confirm=lambda *a: None,
        notify=toasts.append,
    )
    return session, shell, toasts


def _walk(control):
    yield control
    for attr in ("content", "controls"):
        child = getattr(control, attr, None)
        for x in child if isinstance(child, list) else [child]:
            if isinstance(x, ft.Control):
                yield from _walk(x)


def _texts(control) -> list[str]:
    return [c.value for c in _walk(control) if isinstance(c, ft.Text) and c.value]


def _buttons(control, text: str) -> list[ft.Control]:
    return [
        c
        for c in _walk(control)
        if isinstance(c, ft.FilledButton | ft.FilledTonalButton) and c.content == text
    ]


def test_the_board_shows_at_the_town_gate_and_accepting_moves_a_quest_to_the_log(tmp_path):
    session, shell, _ = _shell(tmp_path)
    board = shell.explore.board
    assert board.visible and "Notice board" in _texts(board)
    accepts = _buttons(board, "Accept")
    assert len(accepts) == 3

    shell.select(2)
    assert _texts(shell.quests.control) == ["Quests", EMPTY]

    accepts[0].on_click(None)
    assert len(_buttons(shell.explore.board, "Accept")) == 2
    shell.select(2)
    [active] = shell.quests.sections.controls
    assert isinstance(active, ft.ExpansionTile) and active.title.value == "Active (1)"
    assert "Reward" in _texts(active)  # the full comparison card


def test_turning_in_toasts_the_reward(tmp_path):
    session, shell, toasts = _shell(tmp_path)
    game = session.game
    quest_id = game.view().board[0].id
    shell.explore.act(AcceptQuest(quest_id))
    quest = next(q for _, (q,) in game.world.query(Quest) if q.quest_id == quest_id)
    quest.state = "ready"  # as if done
    shell.explore.refresh()
    [turn_in] = _buttons(shell.explore.board, "Turn in")
    turn_in.on_click(None)
    assert toasts == [f"{quest.reward.display_name} added to your pack."]
    shell.select(2)
    [done] = shell.quests.sections.controls
    assert done.title.value == "Done (1)" and not done.expanded  # folded by default


def test_the_board_hides_away_from_the_gate(tmp_path):
    session, shell, _ = _shell(tmp_path)
    first_exit = session.game.view().exits[0].label
    shell.explore.act(Move(first_exit))
    assert shell.explore.board.controls == []


def test_map_marks():
    assert label("Saltmere", "Town") == "⌂ Saltmere"
    assert label("Mistwood", "Forest", quest=True, charted=True) == "♣ Mistwood ✓ ◆"
    node = MapNode("r", 0.5, 0.5, "visited", "Hall", None, items=True, quest=True)
    assert badges(node) == "✦◆"
    assert badges(MapNode("r", 0.5, 0.5, "visited", "Hall", None)) == ""


def test_toasts_push_the_whole_page():
    # show_dialog updates only the dialog layer, which also turns off Flet's update
    # of the page after the handler; the toast must push everything else itself, or
    # a turned-in quest stays on the board.
    from tidewrack.ui.app import App

    class FakePage:
        def __init__(self):
            self.calls = []

        def show_dialog(self, dialog):
            self.calls.append("dialog")

        def update(self):
            self.calls.append("update")

    page = FakePage()
    App(page, None, None, CONTENT)._notify("Reward Charm added to your pack.")
    assert page.calls == ["dialog", "update"]

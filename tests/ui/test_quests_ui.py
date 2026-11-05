"""The notice board on Explore, the Quests tab and quest marks on the maps."""

import flet as ft

from tidewrack.core.engine.components import Quest
from tidewrack.core.engine.game import AcceptQuest, MapNode, Move
from tidewrack.services.content import load_bundled_content
from tidewrack.ui.components.coins import label_of
from tidewrack.ui.map_canvas import badges, label
from tidewrack.ui.screens.game import BOARD
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
    """Text values, plus the sentence behind each coins()/purse() row."""
    return [
        label_of(c)
        for c in _walk(control)
        if (isinstance(c, ft.Text) and c.value)
        or (isinstance(c, ft.Row) and isinstance(c.data, str))
    ]


def _buttons(control, text: str) -> list[ft.Control]:
    return [
        c
        for c in _walk(control)
        if isinstance(c, ft.FilledButton | ft.FilledTonalButton) and label_of(c.content) == text
    ]


def test_the_board_shows_at_the_town_gate_and_accepting_moves_a_quest_to_the_log(tmp_path):
    session, shell, _ = _shell(tmp_path)
    explore = shell.explore
    [entrance] = [
        b
        for b in _walk(explore.entrances)
        if str(getattr(b, "content", "")).startswith("Notice board · ")
    ]
    assert label_of(entrance.content) == "Notice board · 3 posted" and explore.board.controls == []
    entrance.on_click(None)  # opens the board, which takes over the screen
    board = explore.board
    assert "Notice board" in _texts(explore.panel_heading)
    assert not explore.map.control.visible and not explore.exits.visible
    accepts = _buttons(board, "Accept")
    assert len(accepts) == 3

    shell.select(2)
    assert _texts(shell.quests.control) == ["Quests", EMPTY]

    accepts[0].on_click(None)
    assert len(_buttons(shell.explore.board, "Accept")) == 2  # still open
    shell.select(2)
    [active] = shell.quests.sections.controls
    assert isinstance(active, ft.ExpansionTile) and active.title.value == "Active (1)"
    assert not any(t.startswith("Reward (and ") for t in _texts(active))  # collapsed
    shell.quests.folds.toggle(session.game.quests().active[0].id)
    [active] = shell.quests.sections.controls
    assert any(t.startswith("Reward (and ") for t in _texts(active))  # the full card
    assert [
        b
        for b in _walk(active)
        if isinstance(b, ft.TextButton) and label_of(b.content) == "Abandon"
    ]


def test_turning_in_toasts_the_reward(tmp_path):
    session, shell, toasts = _shell(tmp_path)
    game = session.game
    quest_id = game.view().board[0].id
    shell.explore.act(AcceptQuest(quest_id))
    quest = next(q for _, (q,) in game.world.query(Quest) if q.quest_id == quest_id)
    quest.state = "ready"  # as if done
    shell.explore.open(BOARD)
    [turn_in] = _buttons(shell.explore.board, "Turn in")
    turn_in.on_click(None)
    assert toasts == [f"{quest.reward.display_name} added to your pack, and {quest.gold} gold."]
    shell.select(2)
    [done] = shell.quests.sections.controls
    assert done.title.value == "Done (1)" and not done.expanded  # folded by default


def test_the_board_hides_away_from_the_gate(tmp_path):
    session, shell, _ = _shell(tmp_path)
    explore = shell.explore
    explore.open(BOARD)
    first_exit = session.game.view().exits[0].label
    explore.act(Move(first_exit))  # anything that moves you closes it
    assert explore.opened is None and explore.board.controls == []
    assert explore.exits.visible
    assert not [
        b for b in explore.entrances.controls if label_of(b.content).startswith("Notice board")
    ]


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

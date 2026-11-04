"""Quests: notice boards, found clues, progress and rewards (CLAUDE.md §14 step 6b)."""

from collections import deque

from tidewrack.core.data.save import GameState
from tidewrack.core.engine.components import (
    Bounty,
    Clue,
    Codex,
    Enemy,
    Explorer,
    Position,
    Quest,
    QuestItem,
)
from tidewrack.core.engine.events import (
    ActionRejected,
    EnemyKilled,
    QuestCompleted,
    QuestProgress,
    QuestReady,
)
from tidewrack.core.engine.game import (
    AcceptQuest,
    Attack,
    Game,
    Move,
    Travel,
    TurnInQuest,
    Wait,
)
from tidewrack.core.gear.item import Item
from tidewrack.core.procgen.world_gen import generate_world
from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()
WORLD = generate_world(7, CONTENT.world("world.standard"), CONTENT.roomsets)
TOWN = WORLD.location(WORLD.start)  # loc_00, its gate is the start room
CAVES = WORLD.location("loc_02")  # a road from the town
STRONG = {"atk": 60, "def": 30, "hp": 100}


def charm(name="Reward Charm") -> Item:
    return Item(gear_id="gear.whalebone_charm", name=name, slot="trinket", base={"hp": 4})


def quest(quest_id="q.1", kind="recover", **fields) -> Quest:
    defaults = dict(
        title=f"Quest {quest_id}",
        summary="Do the thing.",
        reward=charm(),
        board=TOWN.id,
        location=CAVES.id,
    )
    return Quest(quest_id=quest_id, kind=kind, **{**defaults, **fields})


def crab(name="Shore Crab", **stats) -> Enemy:
    return Enemy(
        enemy_id="enemy.shore_crab",
        name=name,
        category="beast",
        description="A big crab.",
        stats={"atk": 3, "def": 2, "hp": 8, **stats},
    )


def game_with(*quests, player=None, enemies=(), bounties=(), things=()) -> Game:
    return Game(
        7,
        WORLD,
        player or {"atk": 4, "def": 2, "hp": 20},
        enemies=enemies,
        quests=quests,
        bounties=bounties,
        quest_things=things,
    )


def walk_to(game: Game, location, room: str) -> list:
    """Move through `location` (which the player is in) to `room`; all events."""
    here = game.world.get(game.player, Position)
    prev = {here.room: None}
    queue = deque([here.room])
    while queue:
        node = queue.popleft()
        for e in location.room(node).exits:
            if e.to not in prev:
                prev[e.to] = (node, e.label)
                queue.append(e.to)
    labels, node = [], room
    while prev[node]:
        node, label = prev[node]
        labels.append(label)
    events = []
    for label in reversed(labels):
        events += game.perform(Move(label)).events
    return events


def far_room(location) -> str:
    return next(r for r in reversed(list(location.rooms)) if r not in location.gates)


def state(game: Game, quest_id="q.1") -> Quest:
    return next(q for _, (q,) in game.world.query(Quest) if q.quest_id == quest_id)


def rejected(result):
    return [e.reason for e in result.events if isinstance(e, ActionRejected)]


# --- boards ------------------------------------------------------------------------


def test_the_board_posts_quests_and_accepting_puts_them_in_the_log():
    game = game_with(quest(), quest("q.2", board="loc_99"))
    view = game.view()
    assert [q.id for q in view.board] == ["q.1"]  # only this town's notices
    assert view.board[0].source == f"Posted at {TOWN.name}"
    assert "A notice board by the gate has 1 notice pinned to it." in game.log
    assert game.quests().active == ()

    result = game.perform(AcceptQuest("q.1"))
    assert not result.took_turn and not rejected(result)
    assert [q.id for q in game.quests().active] == ["q.1"]
    assert game.view().board == ()
    assert CAVES.id in game.world.get(game.player, Explorer).locations_discovered
    assert rejected(game.perform(AcceptQuest("q.1"))) == ["That notice isn't on this board."]


def test_boards_are_only_at_town_gates():
    game = game_with(quest())
    game.perform(Move(TOWN.room(TOWN.start).exits[0].label))
    assert game.view().board is None
    assert rejected(game.perform(AcceptQuest("q.1"))) == [
        "Quests are taken from a town's notice board."
    ]
    assert rejected(game.perform(TurnInQuest("q.1"))) == [
        "Quests are turned in at a town's notice board."
    ]


def test_quests_cant_be_taken_mid_fight():
    room = TOWN.room(TOWN.start).exits[0].to
    game = game_with(quest(), enemies=[(TOWN.id, room, crab())])
    game.perform(Move(TOWN.room(TOWN.start).exits[0].label))
    assert game.view().combat is not None
    assert rejected(game.perform(AcceptQuest("q.1"))) == ["You're fighting the Shore Crab!"]


# --- recover -----------------------------------------------------------------------


def test_recover_counts_before_accepting_and_rewards_on_turn_in():
    room = far_room(CAVES)
    item = QuestItem("q.1", "Brass Sextant", "Green with verdigris.")
    game = game_with(quest(target="Brass Sextant"), things=[(CAVES.id, room, item)])
    game.perform(Travel(CAVES.id))
    walk_to(game, CAVES, room)
    assert "You find the Brass Sextant. Green with verdigris." in game.log
    assert state(game).achieved and state(game).state == "posted"
    assert rejected(game.perform(TurnInQuest("q.1"))) == [
        "Quests are turned in at a town's notice board."
    ]
    walk_to(game, CAVES, CAVES.start)
    game.perform(Travel(TOWN.id))
    assert "q.1" in [q.id for q in game.view().board]
    events = game.perform(AcceptQuest("q.1")).events
    assert any(isinstance(e, QuestReady) for e in events)
    assert [q.progress for q in game.quests().ready] == ["Brass Sextant: found"]

    events = game.perform(TurnInQuest("q.1")).events
    assert [e.reward for e in events if isinstance(e, QuestCompleted)] == ["Reward Charm"]
    assert [q.id for q in game.quests().done] == ["q.1"]
    assert "Reward Charm" in [i.name for i in game.inventory().pack]
    assert rejected(game.perform(TurnInQuest("q.1"))) == ["That quest isn't finished yet."]


# --- bounty ------------------------------------------------------------------------


def test_beating_a_bounty_readies_its_quest_and_the_codex_records_its_kind():
    room = far_room(CAVES)
    boss = crab("Scarred Shore Crab", hp=12)
    bounty = Bounty("q.1", "Shore Crab", {"atk": 3, "def": 2, "hp": 8})
    game = game_with(quest(kind="bounty"), player=STRONG, bounties=[(CAVES.id, room, boss, bounty)])
    game.perform(AcceptQuest("q.1"))
    game.perform(Travel(CAVES.id))
    walk_to(game, CAVES, room)
    assert game.view().combat.name == "Scarred Shore Crab"
    [foe] = game.foes().foes
    assert foe.name == "Shore Crab"
    assert game.world.get(game.player, Codex).foes["enemy.shore_crab"].stats["hp"] == 8
    events = game.perform(Attack()).events
    assert [e.bounty for e in events if isinstance(e, EnemyKilled)] == ["q.1"]
    assert any(isinstance(e, QuestReady) for e in events)
    assert game.quests().ready[0].progress == "Beaten"


def test_a_seen_bounty_is_marked_on_the_area_map():
    room = CAVES.room(CAVES.start).exits[0].to
    bounty = Bounty("q.1", "Shore Crab", {})
    game = game_with(
        quest(kind="bounty"),
        player={"atk": 1, "def": 50, "hp": 100},
        bounties=[(CAVES.id, room, crab(atk=1, hp=500), bounty)],
    )
    game.perform(AcceptQuest("q.1"))
    game.perform(Travel(CAVES.id))
    game.perform(Move(CAVES.room(CAVES.start).exits[0].label))
    node = next(n for n in game.view().map.nodes if n.id == room)
    assert node.quest


# --- cull --------------------------------------------------------------------------


def test_culls_count_only_after_accepting():
    rooms = [r for r in CAVES.rooms if r not in CAVES.gates][:3]
    game = game_with(
        quest(kind="cull", enemy_id="enemy.shore_crab", target="Shore Crabs", needed=2),
        player=STRONG,
        enemies=[(CAVES.id, r, crab()) for r in rooms],
    )
    game.perform(Travel(CAVES.id))
    walk_to(game, CAVES, rooms[0])
    game.perform(Attack())  # before accepting: doesn't count
    walk_to(game, CAVES, CAVES.start)
    game.perform(Travel(TOWN.id))
    game.perform(AcceptQuest("q.1"))
    assert game.quests().active[0].progress == "0/2 Shore Crabs defeated"
    game.perform(Travel(CAVES.id))
    walk_to(game, CAVES, rooms[1])
    events = game.perform(Attack()).events
    assert [(e.progress, e.needed) for e in events if isinstance(e, QuestProgress)] == [(1, 2)]
    walk_to(game, CAVES, rooms[2])
    events = game.perform(Attack()).events
    assert any(isinstance(e, QuestReady) for e in events)


# --- explore -----------------------------------------------------------------------


def test_explore_is_ready_once_every_room_is_visited_and_charted_on_the_world_map():
    game = game_with(quest(kind="explore", needed=len(CAVES.rooms)))
    game.perform(AcceptQuest("q.1"))
    world_node = next(n for n in game.view().world_map.nodes if n.id == CAVES.id)
    assert world_node.quest and not world_node.charted
    game.perform(Travel(CAVES.id))
    ready = []
    for room in CAVES.rooms:
        ready += [e for e in walk_to(game, CAVES, room) if isinstance(e, QuestReady)]
    assert len(ready) == 1
    assert game.quests().ready[0].progress == f"{len(CAVES.rooms)}/{len(CAVES.rooms)} rooms visited"
    world_node = next(n for n in game.view().world_map.nodes if n.id == CAVES.id)
    assert world_node.charted and not world_node.quest  # ready, not active


# --- found quests ------------------------------------------------------------------


def test_a_found_clue_starts_its_quest():
    room = CAVES.room(CAVES.start).exits[0].to
    clue = Clue("q.1", "A torn notice flaps on a nail.")
    found = quest(kind="explore", needed=99, board=None, source="found", state="hidden")
    game = game_with(found, things=[(CAVES.id, room, clue)])
    assert game.view().board == ()  # found quests aren't posted
    game.perform(Travel(CAVES.id))
    game.perform(Move(CAVES.room(CAVES.start).exits[0].label))
    assert game.log[-2:] == ["A torn notice flaps on a nail.", "New quest: Quest q.1."]
    [view] = game.quests().active
    assert view.source == f"Found in {CAVES.name}"
    assert not list(game.world.query(Clue))


# --- maps and saving ---------------------------------------------------------------


def test_visited_rooms_with_items_left_in_them_are_marked():
    game = game_with()
    exit_ = TOWN.room(TOWN.start).exits[0]
    game.perform(Move(exit_.label))
    game.world.create(charm(), Position(TOWN.id, exit_.to))
    marked = {n.id for n in game.view().map.nodes if n.items}
    assert marked == {exit_.to}


def test_quests_survive_a_save_round_trip():
    room = far_room(CAVES)
    item = QuestItem("q.1", "Brass Sextant", "Green.")
    found = quest("q.2", kind="explore", needed=99, board=None, source="found", state="hidden")
    game = game_with(
        quest(target="Brass Sextant"),
        found,
        things=[
            (CAVES.id, room, item),
            (CAVES.id, CAVES.room(CAVES.start).exits[0].to, Clue("q.2", "X")),
        ],
    )
    game.perform(AcceptQuest("q.1"))
    restored = Game.from_state(GameState.model_validate_json(game.to_state().model_dump_json()))
    assert restored.view() == game.view() and restored.quests() == game.quests()
    for command in [Travel(CAVES.id), Wait(), Travel(TOWN.id)]:
        assert restored.perform(command) == game.perform(command)
    assert restored.to_state() == game.to_state()

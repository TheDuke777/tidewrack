"""Quests: notice boards, found clues, progress and turning in (CLAUDE.md §8.4c).

Functions over a Game, like core.combat.fight: Game.perform calls `accept` and
`turn_in`, and its event bus calls the subscribers. Quests are made at world
creation (core/procgen/quest_gen.py) and live as Quest components.

A bounty beaten or an item recovered counts even before you accept the quest
(accepting then makes it ready at once); culls count only kills after you
accept; explore quests are checked against the rooms you've visited. Every
quest is turned in at any town's notice board (a town's gate room).

An active quest can be abandoned anywhere: a board quest goes back up on its
own board, a found one on the board of the last town you visited; a cull's
count starts again. A bounty beaten or an item already found stays achieved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tidewrack.core.combat.fight import TOWN
from tidewrack.core.economy import crafting, shops
from tidewrack.core.engine.components import (
    Carried,
    Clue,
    Explorer,
    Position,
    Quest,
    QuestItem,
    Respawn,
)
from tidewrack.core.engine.events import (
    ActionRejected,
    EnemyKilled,
    LocationDiscovered,
    QuestAbandoned,
    QuestAccepted,
    QuestCompleted,
    QuestFound,
    QuestItemFound,
    QuestProgress,
    QuestReady,
    RoomEntered,
)

if TYPE_CHECKING:
    from tidewrack.core.engine.game import Game

KIND_LABELS = {"bounty": "Bounty", "cull": "Cull", "explore": "Explore", "recover": "Recover"}


def all_quests(game: Game) -> list[Quest]:
    return [quest for _, (quest,) in game.world.query(Quest)]


def find(game: Game, quest_id: str) -> Quest | None:
    return next((q for q in all_quests(game) if q.quest_id == quest_id), None)


def board_here(game: Game) -> str | None:
    """The town whose notice board the player is standing at, if any."""
    location, room = game.here()
    if location.kind == TOWN and room.id in location.gates:
        return location.id
    return None


def charted(game: Game, location_id: str) -> int:
    """Rooms of a location the player has visited."""
    explorer = game.world.get(game.player, Explorer)
    return len(explorer.rooms_visited.get(location_id, set()))


def is_done(game: Game, quest: Quest) -> bool:
    match quest.kind:
        case "cull":
            return quest.progress >= quest.needed
        case "explore":
            return quest.location is not None and charted(game, quest.location) >= quest.needed
        case _:
            return quest.achieved


def progress_text(game: Game, quest: Quest) -> str:
    match quest.kind:
        case "bounty":
            return "Beaten" if quest.achieved else "Still at large"
        case "cull":
            return f"{min(quest.progress, quest.needed)}/{quest.needed} {quest.target} defeated"
        case "explore":
            visited = charted(game, quest.location) if quest.location else 0
            return f"{min(visited, quest.needed)}/{quest.needed} rooms visited"
        case _:
            return f"{quest.target}: {'found' if quest.achieved else 'not found yet'}"


def _check(game: Game, quest: Quest) -> None:
    if quest.state == "active" and is_done(game, quest):
        quest.state = "ready"
        game.bus.emit(QuestReady(quest.quest_id, quest.title))


def _discover(game: Game, location_id: str | None) -> None:
    """Being told where a quest leads puts the place on your world map."""
    explorer = game.world.get(game.player, Explorer)
    if location_id is not None and location_id not in explorer.locations_discovered:
        explorer.locations_discovered.add(location_id)
        game.bus.emit(LocationDiscovered(location_id))


# --- commands ----------------------------------------------------------------------


def accept(game: Game, quest_id: str) -> None:
    quest = find(game, quest_id)
    board = board_here(game)
    if board is None:
        game.bus.emit(ActionRejected("Quests are taken from a town's notice board."))
    elif quest is None or quest.state != "posted" or quest.board != board:
        game.bus.emit(ActionRejected("That notice isn't on this board."))
    else:
        quest.state = "active"
        game.bus.emit(QuestAccepted(quest.quest_id, quest.title))
        _discover(game, quest.location)
        _check(game, quest)


def turn_in(game: Game, quest_id: str) -> None:
    quest = find(game, quest_id)
    if board_here(game) is None:
        game.bus.emit(ActionRejected("Quests are turned in at a town's notice board."))
    elif quest is None or quest.state != "ready":
        game.bus.emit(ActionRejected("That quest isn't finished yet."))
    else:
        quest.state = "done"
        game.world.create(quest.reward, Carried(game.player))
        game.bus.emit(
            QuestCompleted(quest.quest_id, quest.title, quest.reward.display_name, quest.gold)
        )
        shops.gain(game, quest.gold, "quest")
        if quest.recipe is not None:
            crafting.learn(game, quest.recipe, "quest")


def abandon(game: Game, quest_id: str) -> None:
    quest = find(game, quest_id)
    if quest is None or quest.state != "active":
        game.bus.emit(ActionRejected("You can only give up a quest you're still working on."))
        return
    if quest.board is None:  # a found quest: leave word at the last town you visited
        quest.board = game.world.get(game.player, Respawn).location
    quest.state = "posted"
    quest.progress = 0
    game.bus.emit(QuestAbandoned(quest.quest_id, quest.title, quest.board))


# --- subscribers -------------------------------------------------------------------


def on_room_entered(game: Game, event: RoomEntered) -> None:
    """Pick up clues and quest items lying here; check explore quests."""
    if event.entity != game.player:
        return
    here = (event.location, event.room)
    for entity, (clue, position) in game.world.query(Clue, Position):
        if (position.location, position.room) != here:
            continue
        game.world.destroy(entity)
        quest = find(game, clue.quest_id)
        if quest is not None and quest.state == "hidden":
            quest.state = "active"
            quest.found_in = event.location
            game.bus.emit(QuestFound(quest.quest_id, quest.title, clue.text))
            _discover(game, quest.location)
            _check(game, quest)
    for entity, (item, position) in game.world.query(QuestItem, Position):
        if (position.location, position.room) != here:
            continue
        game.world.destroy(entity)
        quest = find(game, item.quest_id)
        if quest is not None:
            quest.achieved = True
            game.bus.emit(QuestItemFound(quest.quest_id, item.name, item.description))
            _check(game, quest)
    for quest in all_quests(game):
        if quest.kind == "explore" and quest.location == event.location:
            _check(game, quest)


def on_enemy_killed(game: Game, event: EnemyKilled) -> None:
    for quest in all_quests(game):
        if event.bounty is not None and quest.quest_id == event.bounty:
            quest.achieved = True
            _check(game, quest)
        elif quest.kind == "cull" and quest.state == "active" and quest.enemy_id == event.enemy_id:
            quest.progress += 1
            if quest.progress <= quest.needed:
                game.bus.emit(
                    QuestProgress(quest.quest_id, quest.title, quest.progress, quest.needed)
                )
            _check(game, quest)

"""The game session: world state, the turn loop, and a view model for the UI.

The UI only ever calls :meth:`Game.perform` with a command and reads
:meth:`Game.view`; it never touches the ECS world directly (CLAUDE.md §4).

Turn loop, delivered in phases so each sees the previous one's consequences:
1. the command is validated and applied; its events (and whatever subscribers
   emit in response, e.g. NodeDiscovered) are delivered;
2. if it took a turn: the counter advances and each per-turn system runs in
   order, and their events are delivered;
3. ``TurnEnded`` is delivered last.
Subscribers (exploration, narration, later achievements/codex) therefore see
every event in a deterministic order.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from tidewrack.core.engine.components import Explorer, Name, Player, Position, Scenery
from tidewrack.core.engine.ecs import World
from tidewrack.core.engine.events import (
    ActionRejected,
    AmbientNoticed,
    Event,
    EventBus,
    GameStarted,
    LookedAround,
    NodeDiscovered,
    NodeEntered,
    TurnEnded,
    Waited,
)
from tidewrack.core.rng import Rng
from tidewrack.core.world.dungeon import DungeonMap

AMBIENT_CHANCE = 0.35  # per turn, when the current node has ambient lines
LOG_LIMIT = 200


# --- commands ----------------------------------------------------------------------


@dataclass(frozen=True)
class Move:
    exit_label: str


@dataclass(frozen=True)
class Look:
    """Free action: describe the scenery here."""


@dataclass(frozen=True)
class Wait:
    """Spend a turn doing nothing."""


Command = Move | Look | Wait


# --- results and view model --------------------------------------------------------


@dataclass(frozen=True)
class TurnResult:
    took_turn: bool
    events: tuple[Event, ...]


@dataclass(frozen=True)
class ExitView:
    label: str
    destination: str | None  # node name once visited; None while unexplored


@dataclass(frozen=True)
class GameView:
    dungeon_name: str
    location: str
    description: str
    exits: tuple[ExitView, ...]
    log: tuple[str, ...]
    turn: int
    seed: int
    visited: int
    total_nodes: int


# --- the game ----------------------------------------------------------------------


class Game:
    def __init__(self, seed: int, dungeon: DungeonMap) -> None:
        self.seed = seed
        self.dungeon = dungeon
        self.rng = Rng(seed)
        self.ambient_rng = self.rng.derive("ambient")
        self.world = World()
        self.bus = EventBus()
        self.turn = 0
        self.log: list[str] = []

        # Per-turn systems, run in this order after every turn-taking command.
        self.systems: list[Callable[[Game], None]] = [ambience_system]

        # Subscription order is delivery order: exploration updates state before
        # the narrator describes it.
        self.bus.subscribe(NodeEntered, self._explore)
        self.bus.subscribe(Event, self._narrate)

        self.player = self.world.create(Player(), Name("You"), Position(dungeon.start), Explorer())
        for node in dungeon.nodes.values():
            for text in node.features:
                self.world.create(Scenery(text), Position(node.id))

        self.bus.emit(GameStarted(seed, dungeon.id))
        self.bus.emit(NodeEntered(self.player, dungeon.start, None, first_visit=True))
        self.bus.flush()

    # --- turn loop -------------------------------------------------------------------

    def perform(self, command: Command) -> TurnResult:
        position = self.world.get(self.player, Position)
        took_turn = False

        match command:
            case Move(exit_label=label):
                exit_ = self.dungeon.exit(position.node, label)
                if exit_ is None:
                    self.bus.emit(ActionRejected("You can't go that way."))
                else:
                    explorer = self.world.get(self.player, Explorer)
                    origin, position.node = position.node, exit_.to
                    self.bus.emit(
                        NodeEntered(
                            self.player,
                            exit_.to,
                            origin,
                            first_visit=exit_.to not in explorer.visited,
                        )
                    )
                    took_turn = True
            case Look():
                self.bus.emit(LookedAround(position.node))
            case Wait():
                self.bus.emit(Waited(position.node))
                took_turn = True
            case _:
                raise TypeError(f"unknown command: {command!r}")

        events = self.bus.flush()
        if took_turn:
            self.turn += 1
            for system in self.systems:
                system(self)
            events += self.bus.flush()
            self.bus.emit(TurnEnded(self.turn))
            events += self.bus.flush()
        return TurnResult(took_turn, tuple(events))

    # --- view model ------------------------------------------------------------------

    def view(self) -> GameView:
        here = self.dungeon.node(self.world.get(self.player, Position).node)
        explorer = self.world.get(self.player, Explorer)
        exits = tuple(
            ExitView(e.label, self.dungeon.node(e.to).name if e.to in explorer.visited else None)
            for e in here.exits
        )
        return GameView(
            dungeon_name=self.dungeon.name,
            location=here.name,
            description=here.description,
            exits=exits,
            log=tuple(self.log),
            turn=self.turn,
            seed=self.seed,
            visited=len(explorer.visited),
            total_nodes=len(self.dungeon.nodes),
        )

    # --- subscribers -----------------------------------------------------------------

    def _explore(self, event: NodeEntered) -> None:
        explorer = self.world.try_get(event.entity, Explorer)
        if explorer is None:
            return
        explorer.visited.add(event.node_id)
        explorer.discovered.add(event.node_id)
        for neighbour in self.dungeon.neighbours(event.node_id):
            if neighbour not in explorer.discovered:
                explorer.discovered.add(neighbour)
                self.bus.emit(NodeDiscovered(neighbour))

    def _narrate(self, event: Event) -> None:
        match event:
            case GameStarted():
                self._say(f"— {self.dungeon.name} —")
            case NodeEntered(entity=entity, node_id=node_id, from_node=origin, first_visit=first):
                if entity == self.player:
                    name = self.dungeon.node(node_id).name
                    if origin is None:
                        self._say(f"You stand at {name}.")
                    else:
                        self._say(
                            f"You make your way to {name}." if first else f"You return to {name}."
                        )
            case LookedAround(node_id=node_id):
                scenery = [
                    s.text for _, (s, p) in self.world.query(Scenery, Position) if p.node == node_id
                ]
                for text in scenery or ["Nothing else here catches your eye."]:
                    self._say(text)
            case Waited():
                self._say("Time passes.")
            case AmbientNoticed(text=text):
                self._say(text)
            case ActionRejected(reason=reason):
                self._say(reason)

    def _say(self, line: str) -> None:
        self.log.append(line)
        del self.log[:-LOG_LIMIT]


# --- systems -----------------------------------------------------------------------


def ambience_system(game: Game) -> None:
    """Sometimes play a flavour line for where the player is."""
    node = game.dungeon.node(game.world.get(game.player, Position).node)
    if node.ambient and game.ambient_rng.chance(AMBIENT_CHANCE):
        game.bus.emit(AmbientNoticed(node.id, game.ambient_rng.choice(node.ambient)))

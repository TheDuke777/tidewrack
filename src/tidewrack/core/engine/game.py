"""The game session: world state, the turn loop, and a view model for the UI.

The UI only ever calls :meth:`Game.perform` with a command and reads
:meth:`Game.view`; it never touches the ECS world directly (CLAUDE.md §4).

Turn loop, delivered in phases so each sees the previous one's consequences:
1. the command is validated and applied; its events (and whatever subscribers
   emit in response, e.g. RoomDiscovered) are delivered;
2. if it took a turn: the counter advances and each per-turn system runs in
   order, and their events are delivered;
3. ``TurnEnded`` is delivered last.
Subscribers (exploration, narration, later achievements/codex) therefore see
every event in a deterministic order.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from tidewrack.core.data.save import (
    EntityState,
    GameState,
    RngState,
    decode_component,
    encode_component,
)
from tidewrack.core.data.schemas import OverworldSchema
from tidewrack.core.engine.components import Explorer, Name, Player, Position, Scenery
from tidewrack.core.engine.ecs import World
from tidewrack.core.engine.events import (
    ActionRejected,
    AmbientNoticed,
    Event,
    EventBus,
    GameStarted,
    LocationDiscovered,
    LocationEntered,
    LookedAround,
    RoomDiscovered,
    RoomEntered,
    TurnEnded,
    Waited,
)
from tidewrack.core.rng import Rng
from tidewrack.core.world.location import Location, Room
from tidewrack.core.world.overworld import Overworld

AMBIENT_CHANCE = 0.35  # per turn, when the current room has ambient lines
LOG_LIMIT = 200


# --- commands ----------------------------------------------------------------------


@dataclass(frozen=True)
class Move:
    """Take an exit to another room of this location."""

    exit_label: str


@dataclass(frozen=True)
class Travel:
    """Take the road to a neighbouring location (only from a gate room)."""

    location: str


@dataclass(frozen=True)
class Look:
    """Free action: describe the scenery here."""


@dataclass(frozen=True)
class Wait:
    """Spend a turn doing nothing."""


Command = Move | Travel | Look | Wait


# --- results and view model --------------------------------------------------------


@dataclass(frozen=True)
class TurnResult:
    took_turn: bool
    events: tuple[Event, ...]


@dataclass(frozen=True)
class ExitView:
    label: str
    destination: str | None  # room name once visited; None while unexplored


@dataclass(frozen=True)
class RoadView:
    location: str  # id, for Travel(location)
    name: str
    kind: str
    visited: bool


@dataclass(frozen=True)
class MapNode:
    id: str
    x: float
    y: float
    state: Literal["current", "visited", "seen"]  # "seen": known but not yet visited
    name: str | None  # None while the player doesn't know it
    command: Command | None  # set when one step away: perform it to go there


@dataclass(frozen=True)
class MapView:
    """A fog-of-war map: only nodes the player knows, only paths they've seen."""

    nodes: tuple[MapNode, ...]
    edges: tuple[tuple[str, str], ...]
    size: int  # nodes in the whole map, known or not (for scaling)


@dataclass(frozen=True)
class GameView:
    location: str  # the location's name
    kind: str  # "Town", "Sea Caves", …
    room: str
    description: str
    exits: tuple[ExitView, ...]
    at_gate: bool  # roads can be taken from here
    gates: tuple[str, ...]  # names of this location's gate rooms
    roads: tuple[RoadView, ...]  # this location's neighbours (usable when at_gate)
    log: tuple[str, ...]
    turn: int
    seed: int
    rooms_visited: int
    total_rooms: int
    locations_visited: int
    total_locations: int
    map: MapView | None  # rooms of this location; None if it has no map positions
    world_map: MapView | None  # locations; None if the world has no map positions


# --- the game ----------------------------------------------------------------------


class Game:
    def __init__(self, seed: int, world: Overworld) -> None:
        """Start a new run in `world`."""
        self._setup(seed, world)
        start = world.location(world.start)
        self.player = self.world.create(
            Player(), Name("You"), Position(start.id, start.start), Explorer()
        )
        for location in world.locations.values():
            for room in location.rooms.values():
                for text in room.features:
                    self.world.create(Scenery(text), Position(location.id, room.id))

        self.bus.emit(GameStarted(seed))
        self.bus.emit(LocationEntered(self.player, start.id, None, first_visit=True))
        self.bus.emit(RoomEntered(self.player, start.id, start.start, None, first_visit=True))
        self.bus.flush()

    def _setup(
        self, seed: int, overworld: Overworld, snapshot: OverworldSchema | None = None
    ) -> None:
        """Runtime wiring shared by new and loaded games."""
        self.seed = seed
        self.overworld = overworld
        # The world never changes during play, so it's snapshotted for saving once.
        self._snapshot = snapshot or OverworldSchema.from_overworld(overworld)
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
        self.bus.subscribe(LocationEntered, self._explore_location)
        self.bus.subscribe(RoomEntered, self._explore_room)
        self.bus.subscribe(Event, self._narrate)

    # --- saving ----------------------------------------------------------------------

    def to_state(self) -> GameState:
        next_id, entities = self.world.snapshot()
        return GameState(
            seed=self.seed,
            turn=self.turn,
            log=list(self.log),
            world=self._snapshot,
            rng=RngState(**self.rng.get_state()),
            ambient_rng=RngState(**self.ambient_rng.get_state()),
            next_entity_id=next_id,
            entities=[
                EntityState(id=e, components=dict(encode_component(c) for c in components))
                for e, components in entities.items()
            ],
        )

    @classmethod
    def from_state(cls, state: GameState) -> Game:
        """Resume a saved game exactly where it stopped (RNG streams included)."""
        game = cls.__new__(cls)
        game._setup(state.seed, state.world.to_overworld(), state.world)
        game.rng = Rng.from_state(state.rng.model_dump())
        game.ambient_rng = Rng.from_state(state.ambient_rng.model_dump())
        game.turn = state.turn
        game.log = list(state.log)
        game.world = World.restore(
            state.next_entity_id,
            {
                e.id: tuple(decode_component(n, f) for n, f in e.components.items())
                for e in state.entities
            },
        )
        game.player = game.world.single(Player)[0]
        for entity, (position,) in game.world.query(Position):
            location = game.overworld.locations.get(position.location)
            if location is None or position.room not in location.rooms:
                raise ValueError(
                    f"entity {entity} is at unknown room {position.location}/{position.room}"
                )
        return game

    # --- turn loop -------------------------------------------------------------------

    def perform(self, command: Command) -> TurnResult:
        position = self.world.get(self.player, Position)
        location = self.overworld.location(position.location)
        took_turn = False

        match command:
            case Move(exit_label=label):
                exit_ = location.exit(position.room, label)
                if exit_ is None:
                    self.bus.emit(ActionRejected("You can't go that way."))
                else:
                    origin, position.room = position.room, exit_.to
                    self.bus.emit(
                        RoomEntered(
                            self.player,
                            location.id,
                            exit_.to,
                            origin,
                            first_visit=exit_.to
                            not in self._explorer().rooms_visited.get(location.id, set()),
                        )
                    )
                    took_turn = True
            case Travel(location=destination_id):
                if position.room not in location.gates:
                    gates = " or ".join(location.room(g).name for g in location.gates)
                    self.bus.emit(
                        ActionRejected(f"You can only leave {location.name} from {gates}.")
                    )
                elif destination_id not in location.roads:
                    self.bus.emit(ActionRejected("No road leads there from here."))
                else:
                    destination = self.overworld.location(destination_id)
                    position.location, position.room = destination.id, destination.start
                    explorer = self._explorer()
                    self.bus.emit(
                        LocationEntered(
                            self.player,
                            destination.id,
                            location.id,
                            first_visit=destination.id not in explorer.locations_visited,
                        )
                    )
                    self.bus.emit(
                        RoomEntered(
                            self.player,
                            destination.id,
                            destination.start,
                            None,
                            first_visit=destination.start
                            not in explorer.rooms_visited.get(destination.id, set()),
                        )
                    )
                    took_turn = True
            case Look():
                self.bus.emit(LookedAround(location.id, position.room))
            case Wait():
                self.bus.emit(Waited(location.id, position.room))
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

    def _explorer(self) -> Explorer:
        return self.world.get(self.player, Explorer)

    def here(self) -> tuple[Location, Room]:
        position = self.world.get(self.player, Position)
        location = self.overworld.location(position.location)
        return location, location.room(position.room)

    # --- view model ------------------------------------------------------------------

    def view(self) -> GameView:
        location, room = self.here()
        explorer = self._explorer()
        rooms_visited = explorer.rooms_visited.get(location.id, set())
        at_gate = room.id in location.gates
        exits = tuple(
            ExitView(e.label, location.room(e.to).name if e.to in rooms_visited else None)
            for e in room.exits
        )
        roads = tuple(
            RoadView(
                location=to,
                name=self.overworld.location(to).name,
                kind=self.overworld.location(to).kind,
                visited=to in explorer.locations_visited,
            )
            for to in location.roads
        )
        room_map = world_map = None
        if location.has_map:
            room_map = _fog_map(
                nodes=[(r.id, r.pos, r.name) for r in location.rooms.values()],
                neighbours=location.neighbours,
                here=room.id,
                visited=rooms_visited,
                discovered=explorer.rooms_discovered.get(location.id, set()),
                commands={e.to: Move(e.label) for e in room.exits},
                names_on_discovery=False,
            )
        if self.overworld.has_map:
            world_map = _fog_map(
                nodes=[(loc.id, loc.pos, loc.name) for loc in self.overworld.locations.values()],
                neighbours=self.overworld.neighbours,
                here=location.id,
                visited=explorer.locations_visited,
                discovered=explorer.locations_discovered,
                commands={to: Travel(to) for to in location.roads} if at_gate else {},
                names_on_discovery=True,  # signposts name the places a road leads
            )
        return GameView(
            location=location.name,
            kind=location.kind,
            room=room.name,
            description=room.description,
            exits=exits,
            at_gate=at_gate,
            gates=tuple(location.room(g).name for g in location.gates),
            roads=roads,
            log=tuple(self.log),
            turn=self.turn,
            seed=self.seed,
            rooms_visited=len(rooms_visited),
            total_rooms=len(location.rooms),
            locations_visited=len(explorer.locations_visited),
            total_locations=len(self.overworld.locations),
            map=room_map,
            world_map=world_map,
        )

    # --- subscribers -----------------------------------------------------------------

    def _explore_location(self, event: LocationEntered) -> None:
        explorer = self.world.try_get(event.entity, Explorer)
        if explorer is None:
            return
        explorer.locations_visited.add(event.location)
        explorer.locations_discovered.add(event.location)
        for neighbour in self.overworld.neighbours(event.location):
            if neighbour not in explorer.locations_discovered:
                explorer.locations_discovered.add(neighbour)
                self.bus.emit(LocationDiscovered(neighbour))

    def _explore_room(self, event: RoomEntered) -> None:
        explorer = self.world.try_get(event.entity, Explorer)
        if explorer is None:
            return
        visited = explorer.rooms_visited.setdefault(event.location, set())
        discovered = explorer.rooms_discovered.setdefault(event.location, set())
        visited.add(event.room)
        discovered.add(event.room)
        for neighbour in self.overworld.location(event.location).neighbours(event.room):
            if neighbour not in discovered:
                discovered.add(neighbour)
                self.bus.emit(RoomDiscovered(event.location, neighbour))

    def _narrate(self, event: Event) -> None:
        match event:
            case LocationEntered(entity=entity, location=location_id, from_location=origin):
                if entity == self.player:
                    location = self.overworld.location(location_id)
                    if origin is not None:
                        self._say(f"You take the road to {location.name}.")
                    self._say(f"— {location.name} · {location.kind} —")
            case RoomEntered(
                entity=entity,
                location=location_id,
                room=room_id,
                from_room=origin,
                first_visit=first,
            ):
                if entity == self.player:
                    name = self.overworld.location(location_id).room(room_id).name
                    if origin is None:
                        self._say(f"You stand at {name}.")
                    else:
                        self._say(
                            f"You make your way to {name}." if first else f"You return to {name}."
                        )
            case LookedAround(location=location_id, room=room_id):
                scenery = [
                    s.text
                    for _, (s, p) in self.world.query(Scenery, Position)
                    if (p.location, p.room) == (location_id, room_id)
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


# --- maps --------------------------------------------------------------------------


def _fog_map(
    nodes: list[tuple[str, tuple[float, float] | None, str]],
    neighbours: Callable[[str], list[str]],
    here: str,
    visited: set[str],
    discovered: set[str],
    commands: dict[str, Command],
    names_on_discovery: bool,
) -> MapView:
    """Only what the player knows: discovered nodes, and paths out of visited ones."""
    shown = []
    for node_id, pos, name in nodes:  # map order, so output is stable
        if node_id not in discovered:
            continue
        state = "current" if node_id == here else "visited" if node_id in visited else "seen"
        x, y = pos  # type: ignore[misc]  # callers check has_map
        shown.append(
            MapNode(
                id=node_id,
                x=x,
                y=y,
                state=state,
                name=name if names_on_discovery or node_id in visited else None,
                command=commands.get(node_id),
            )
        )
    edges = sorted({tuple(sorted((a, b))) for a in visited for b in neighbours(a)})
    return MapView(nodes=tuple(shown), edges=tuple(edges), size=len(nodes))  # type: ignore[arg-type]


# --- systems -----------------------------------------------------------------------


def ambience_system(game: Game) -> None:
    """Sometimes play a flavour line for where the player is."""
    location, room = game.here()
    if room.ambient and game.ambient_rng.chance(AMBIENT_CHANCE):
        game.bus.emit(AmbientNoticed(location.id, room.id, game.ambient_rng.choice(room.ambient)))

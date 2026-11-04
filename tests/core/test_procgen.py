import pytest

from tidewrack.core.engine.events import LocationDiscovered, LocationEntered
from tidewrack.core.engine.game import Game, Move, Travel
from tidewrack.core.procgen.enemy_gen import enemies_hash, generate_enemies
from tidewrack.core.procgen.gear_gen import finds_hash, generate_finds, generate_kit
from tidewrack.core.procgen.grid import DIRECTIONS
from tidewrack.core.procgen.location_gen import generate_location
from tidewrack.core.procgen.world_gen import generate_world, world_hash
from tidewrack.core.rng import Rng
from tidewrack.core.versions import GENERATOR_VERSION
from tidewrack.core.world.overworld import Overworld
from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()
RECIPE = CONTENT.world("world.standard")
ROOMSETS = CONTENT.roomsets
SEA_CAVES = ROOMSETS["roomset.sea_caves"]


def new_world(seed: int) -> Overworld:
    return generate_world(seed, RECIPE, ROOMSETS)


def test_golden_world():
    # If this fails, the same seed now builds a different world: if that's intended,
    # bump core.versions.GENERATOR_VERSION and update the hash (§9).
    assert GENERATOR_VERSION == 4
    assert world_hash(new_world(20261103)) == GOLDEN_STANDARD


def test_golden_finds():
    # Same rule for the gear lying about a world (procgen/gear_gen.py).
    assert GENERATOR_VERSION == 4
    world = new_world(20261103)
    assert finds_hash(generate_finds(20261103, world, CONTENT)) == GOLDEN_FINDS


def test_golden_enemies():
    # Same rule for enemies, placed and wandering (procgen/enemy_gen.py).
    assert GENERATOR_VERSION == 4
    world = new_world(20261103)
    assert enemies_hash(*generate_enemies(20261103, world, CONTENT)) == GOLDEN_ENEMIES


GOLDEN_STANDARD = "85dcbb3f1e5e3749f402a569df178414074f47f99394e20867aead837bd63e9f"
GOLDEN_ENEMIES = "d6a93d9319360c3cc50ab54e09d7a9d22ef0676bb92270276ced28f7c9ea3976"
GOLDEN_FINDS = "ff12eed26353d043cc262fc20305260710ca8fab607e476cfcf5317ad36ec9e0"


# --- worlds ------------------------------------------------------------------------


def test_many_seeds_produce_valid_connected_worlds():
    for seed in range(40):
        world = new_world(seed)
        assert world.problems() == []  # roads two-way, rooms valid, everything reachable
        assert len(world.locations) == RECIPE.locations
        assert world.has_map and all(loc.has_map for loc in world.locations.values())
        names = [loc.name for loc in world.locations.values()]
        assert len(set(names)) == len(names), "location names must be unique"
        assert world.location(world.start).kind == "Town"


def test_locations_follow_their_roomset():
    for location in new_world(7).locations.values():
        roomset = next(r for r in ROOMSETS.values() if r.name == location.kind)
        low, high = roomset.size
        assert low <= len(location.rooms) <= high
        assert location.gates == (location.start,)
        assert location.room(location.start).name == f"The {roomset.entrance.noun}"


def test_same_seed_same_world_and_seeds_differ():
    assert new_world(5) == new_world(5)
    assert world_hash(new_world(5)) != world_hash(new_world(6))


def test_kinds_are_drawn_by_weight():
    kinds = [loc.kind for seed in range(30) for loc in list(new_world(seed).locations.values())[1:]]
    assert {"Sea Caves", "Forest", "Mine", "Town"} == set(kinds)


# --- locations ---------------------------------------------------------------------


@pytest.mark.parametrize("size", [2, 7, 14, 30, 60])
def test_many_seeds_produce_valid_connected_locations(size):
    for seed in range(40):
        location = generate_location(Rng(seed), SEA_CAVES, size)
        assert location.problems() == []
        assert len(location.rooms) == size
        assert location.has_map
        names = [r.name for r in location.rooms.values()]
        assert len(set(names)) == size, "room names must be unique"


def test_layout_rules():
    location = generate_location(Rng(7), SEA_CAVES, 30)
    start = location.room(location.start)
    assert start.name == "The Cave Mouth"
    assert start.pos[1] > 0.8  # entrance on the south edge
    labels = {f"Go {d}" for d in DIRECTIONS.values()}
    for room in location.rooms.values():
        assert {e.label for e in room.exits} <= labels
        assert all(0 <= v <= 1 for v in room.pos)
        for exit_ in room.exits:  # every path is two-way
            assert any(e.to == room.id for e in location.room(exit_.to).exits)


def test_naming_does_not_change_layout():
    # Layout and names use separate substreams: renaming content keeps shapes.
    a = generate_location(Rng(1), SEA_CAVES, 20)
    renamed = SEA_CAVES.model_copy(update={"adjectives": ["Odd"] + SEA_CAVES.adjectives})
    b = generate_location(Rng(1), renamed, 20)
    assert [(r.id, r.pos, r.exits) for r in a.rooms.values()] == [
        (r.id, r.pos, r.exits) for r in b.rooms.values()
    ]


def test_layouts_differ_by_kind():
    # Towns are compact and loopy; mines are long, branching and rarely loop.
    def loops(roomset_id: str) -> float:
        roomset, total = ROOMSETS[roomset_id], 0
        for seed in range(30):
            location = generate_location(Rng(seed), roomset, 12)
            edges = sum(len(r.exits) for r in location.rooms.values()) // 2
            total += edges - (len(location.rooms) - 1)  # extra edges beyond a tree
        return total / 30

    assert loops("roomset.harbour_town") > 2 * loops("roomset.old_mine")


def test_rejects_tiny_locations():
    with pytest.raises(ValueError):
        generate_location(Rng(1), SEA_CAVES, 1)


# --- travel ------------------------------------------------------------------------


def _walk_to(game: Game, room_id: str) -> None:
    """Move room by room to `room_id` (breadth-first over the current location)."""
    location, here = game.here()
    previous = {here.id: None}
    todo = [here.id]
    while todo:
        current = todo.pop(0)
        for e in location.room(current).exits:
            if e.to not in previous:
                previous[e.to] = (current, e.label)
                todo.append(e.to)
    labels, node = [], room_id
    while previous[node]:
        node, label = previous[node]
        labels.append(label)
    for label in reversed(labels):
        assert game.perform(Move(label)).took_turn


def test_travel_only_from_a_gate_along_a_road():
    world = new_world(11)
    game = Game(11, world)
    start = world.location(world.start)
    road = start.roads[0]

    game.perform(Move(start.room(start.start).exits[0].label))
    result = game.perform(Travel(road))
    assert not result.took_turn
    assert game.log[-1] == f"You can only leave {start.name} from The Town Gate."

    _walk_to(game, start.start)
    stranger = next(i for i in world.locations if i not in start.roads and i != start.id)
    assert not game.perform(Travel(stranger)).took_turn
    assert game.log[-1] == "No road leads there from here."

    result = game.perform(Travel(road))
    assert result.took_turn
    destination = world.location(road)
    assert game.view().location == destination.name
    assert game.view().room == destination.room(destination.start).name
    entered = next(e for e in result.events if isinstance(e, LocationEntered))
    assert (entered.from_location, entered.first_visit) == (start.id, True)
    newly_known = {e.location for e in result.events if isinstance(e, LocationDiscovered)}
    assert newly_known == set(destination.roads) - {start.id, *start.roads}
    assert f"You take the road to {destination.name}." in game.log


def test_rooms_are_remembered_per_location():
    world = new_world(11)
    game = Game(11, world)
    start = world.location(world.start)
    game.perform(Move(start.room(start.start).exits[0].label))
    _walk_to(game, start.start)
    game.perform(Travel(start.roads[0]))
    game.perform(Travel(start.id))
    view = game.view()
    assert view.room == "The Town Gate"
    assert (view.rooms_visited, view.locations_visited) == (2, 2)  # gate + first room


# --- fog-of-war maps ---------------------------------------------------------------


def test_room_map_shows_only_what_is_known():
    world = new_world(11)
    game = Game(11, world)
    location = world.location(world.start)
    start = location.room(location.start)
    view = game.view().map

    assert view.size == len(location.rooms)
    assert {n.id for n in view.nodes} == {start.id, *(e.to for e in start.exits)}
    states = {n.id: n.state for n in view.nodes}
    assert states.pop(start.id) == "current"
    assert set(states.values()) == {"seen"}
    assert all(n.name is None for n in view.nodes if n.state == "seen")
    assert set(view.edges) == {tuple(sorted((start.id, e.to))) for e in start.exits}
    steps = {n.id: n.command for n in view.nodes if n.command}
    assert steps == {e.to: Move(e.label) for e in start.exits}

    first = start.exits[0]
    game.perform(Move(first.label))
    after = {n.id: n for n in game.view().map.nodes}
    assert after[start.id].state == "visited" and after[start.id].name == start.name
    assert after[first.to].state == "current"


def test_world_map_names_known_places_and_travels_only_from_gates():
    world = new_world(11)
    game = Game(11, world)
    start = world.location(world.start)
    view = game.view().world_map

    assert view.size == len(world.locations)
    assert {n.id for n in view.nodes} == {start.id, *start.roads}
    assert all(n.name == world.location(n.id).name for n in view.nodes)  # signposts
    assert {n.id: n.command for n in view.nodes if n.command} == {r: Travel(r) for r in start.roads}

    game.perform(Move(start.room(start.start).exits[0].label))
    assert not any(n.command for n in game.view().world_map.nodes)  # away from the gate


def test_maps_are_none_without_positions():
    location = CONTENT.dungeon("dungeon.first_descent")
    unmapped = type(location)(
        **{
            **location.__dict__,
            "rooms": {k: type(r)(**{**r.__dict__, "pos": None}) for k, r in location.rooms.items()},
        }
    )
    view = Game(1, Overworld(unmapped.id, {unmapped.id: unmapped})).view()
    assert view.map is None and view.world_map is None
    world = Overworld(location.id, {location.id: location})
    assert Game(1, world).view().map is not None


# --- gear --------------------------------------------------------------------------


def test_finds_are_valid_deterministic_and_never_at_gates():
    total = 0
    for seed in range(20):
        world = new_world(seed)
        finds = generate_finds(seed, world, CONTENT)
        assert finds == generate_finds(seed, world, CONTENT)
        total += len(finds)
        for find in finds:
            location = world.location(find.location)
            assert find.room in location.rooms and find.room not in location.gates
            roomset = next(r for r in ROOMSETS.values() if r.name == location.kind)
            assert find.item.gear_id in roomset.finds.gear
            gear = CONTENT.gear[find.item.gear_id]
            for stat, value in find.item.roll.items():
                low, high = gear.rolls[stat]
                assert low <= value <= high
            for affix in find.item.affixes:
                assert gear.slot in CONTENT.affixes[affix.id].slots
    assert total > 20 * 5  # every world has something to find


def test_finds_dont_change_the_world():
    # Finds use their own substream: placing them never reshapes a world.
    assert world_hash(new_world(20261103)) == GOLDEN_STANDARD


def test_kit_is_plain():
    kit = generate_kit(RECIPE, CONTENT)
    assert [i.gear_id for i in kit] == RECIPE.kit
    assert all(not i.affixes and i.upgrade == 0 for i in kit)


# --- enemies -----------------------------------------------------------------------


def test_enemies_are_valid_deterministic_and_never_at_gates_or_in_towns():
    placed_total = 0
    for seed in range(20):
        world = new_world(seed)
        placed, spawners = generate_enemies(seed, world, CONTENT)
        assert (placed, spawners) == generate_enemies(seed, world, CONTENT)
        placed_total += len(placed)
        for p in placed:
            location = world.location(p.location)
            assert p.room in location.rooms and p.room not in location.gates
            assert location.kind != "Town"
            roomset = next(r for r in ROOMSETS.values() if r.name == location.kind)
            assert p.enemy.enemy_id in roomset.enemies.pool
        for spawner in spawners:
            location = world.location(spawner.location)
            assert location.kind != "Town" and len(spawner.queue) == 6
    assert placed_total > 20 * 5


def test_enemies_dont_change_the_world_or_its_finds():
    assert world_hash(new_world(20261103)) == GOLDEN_STANDARD
    world = new_world(20261103)
    assert finds_hash(generate_finds(20261103, world, CONTENT)) == GOLDEN_FINDS

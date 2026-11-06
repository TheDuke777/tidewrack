from tidewrack.ui.map_canvas import _label_size, _overlap, place_labels

# Roughly the world map from a v0.4 phone screenshot, where "The Undertow Deep"
# (drawn below its dot) ran into the path and the dot beneath it.
POINTS = {
    "cragmouth": (230, 215),
    "undertow": (228, 162),
    "gloamholt": (297, 215),
    "gullet": (140, 236),
}
NAMES = {
    "cragmouth": "Cragmouth",
    "undertow": "The Undertow Deep",
    "gloamholt": "Gloamholt",
    "gullet": "The Gullet Caves",
}
EDGES = (("cragmouth", "undertow"), ("cragmouth", "gloamholt"), ("cragmouth", "gullet"))
RADIUS = 10


def _box(node_id, spot):
    w, h = _label_size(NAMES[node_id])
    x, y = spot
    return (x - w / 2, y, x + w / 2, y + h)


def test_labels_avoid_dots_paths_and_each_other():
    spots = place_labels(POINTS, NAMES, EDGES, RADIUS, 355, 278)
    boxes = {i: _box(i, s) for i, s in spots.items()}
    pad = RADIUS + 6
    for node_id, box in boxes.items():
        for x, y in POINTS.values():
            assert _overlap(box, (x - pad, y - pad, x + pad, y + pad)) == 0, node_id
        for other, other_box in boxes.items():
            if other != node_id:
                assert _overlap(box, other_box) == 0, (node_id, other)
    assert spots["undertow"][1] < POINTS["undertow"][1]  # moved above its dot


def test_labels_prefer_below_when_there_is_room():
    spots = place_labels({"a": (100, 100)}, {"a": "Saltmere"}, (), RADIUS, 300, 300)
    assert spots["a"] == (100, 100 + RADIUS + 7)


def test_labels_stay_on_the_map():
    spots = place_labels({"a": (100, 290)}, {"a": "Saltmere"}, (), RADIUS, 300, 300)
    assert spots["a"][1] < 290  # no room below the bottom edge


# --- zoom and pan ------------------------------------------------------------------

SIZE = (300.0, 200.0)


def test_viewport_keeps_the_pinched_point_under_the_fingers():
    from tidewrack.ui.map_canvas import Viewport

    v = Viewport()
    v.place(anchor=(150, 100), screen=(150, 100), zoom=2, size=SIZE)
    assert v.to_screen((150, 100)) == (150, 100)
    assert v.to_content(v.to_screen((80, 40))) == (80, 40)


def test_viewport_never_shows_past_the_map_edges_or_beyond_its_zoom_range():
    from tidewrack.ui.map_canvas import MAX_ZOOM, Viewport

    v = Viewport()
    v.place(anchor=(0, 0), screen=(250, 180), zoom=2, size=SIZE)  # drag the corner inwards
    assert (v.ox, v.oy) == (0, 0)
    v.place(anchor=(300, 200), screen=(0, 0), zoom=2, size=SIZE)
    assert v.to_screen((300, 200)) == SIZE  # far corner pinned to the far edge
    v.place(anchor=(0, 0), screen=(0, 0), zoom=99, size=SIZE)
    assert v.zoom == MAX_ZOOM
    v.place(anchor=(0, 0), screen=(0, 0), zoom=0.1, size=SIZE)
    assert (v.zoom, v.ox, v.oy) == (1, 0, 0)


def test_centre_on_and_follow():
    from tidewrack.ui.map_canvas import FOLLOW_MARGIN, Viewport

    v = Viewport()
    v.centre_on((100, 100), SIZE, zoom=2)
    assert v.to_screen((100, 100)) == (150, 100)
    assert v.shows((100, 100), SIZE, FOLLOW_MARGIN)
    assert not v.shows((280, 20), SIZE, FOLLOW_MARGIN)


def test_gates_and_kinds_are_marked():
    from tidewrack.core.engine.game import Game
    from tidewrack.core.procgen.world_gen import generate_world
    from tidewrack.services.content import load_bundled_content
    from tidewrack.ui.map_canvas import kinds_legend, label

    content = load_bundled_content()
    world = generate_world(
        20261103, content.world("world.standard"), content.roomsets, content.regions
    )
    view = Game(20261103, world).view()
    assert [n.gate for n in view.map.nodes if n.state == "current"] == [True]  # you start at a gate
    assert all(n.kind is None for n in view.map.nodes)
    assert {n.kind for n in view.world_map.nodes} <= {"Town", "Sea Caves", "Forest", "Mine"}
    assert not any(n.gate for n in view.world_map.nodes)
    assert kinds_legend(view.world_map).startswith("⌂ Town")
    assert label("Saltmere", "Town") == "⌂ Saltmere" and label("Hold", None) == "Hold"


def test_tapping_a_place_away_from_a_gate_says_why_you_cant_go():
    from types import SimpleNamespace

    from tidewrack.core.engine.game import Game, Move
    from tidewrack.core.procgen.world_gen import generate_world
    from tidewrack.services.content import load_bundled_content
    from tidewrack.ui.map_canvas import MapCanvas

    content = load_bundled_content()
    world = generate_world(7, content.world("world.standard"), content.roomsets, content.regions)
    town = world.location(world.start)
    game = Game(7, world)
    at_gate = {n.id: n for n in game.view().world_map.nodes}
    assert all(at_gate[r].blocked is None and at_gate[r].command for r in town.roads)

    game.perform(Move(town.room(town.start).exits[0].label))
    nodes = {n.id: n for n in game.view().world_map.nodes}
    reason = f"You can only leave {town.name} from {town.room(town.start).name}."
    assert all(nodes[r].blocked == reason and nodes[r].command is None for r in town.roads)
    assert nodes[town.id].blocked is None  # where you are

    commands, told = [], []
    canvas = MapCanvas(on_command=commands.append, on_blocked=told.append)
    canvas.show(game.view().world_map, "", key="world", labels=True)
    x, y = canvas._points[town.roads[0]]
    canvas._tapped(SimpleNamespace(local_position=SimpleNamespace(x=x, y=y)))
    assert told == [reason] and commands == []


def test_every_place_kind_has_a_glyph():
    from tidewrack.services.content import load_bundled_content
    from tidewrack.ui.map_canvas import KIND_GLYPHS

    content = load_bundled_content()
    assert {r.name for r in content.roomsets.values()} <= set(KIND_GLYPHS)


def test_region_names_and_guarded_roads_on_the_world_map():
    from tidewrack.core.engine.components import Position, Warden
    from tidewrack.core.engine.events import LocationEntered
    from tidewrack.core.engine.game import Game
    from tidewrack.core.procgen.enemy_gen import generate_wardens
    from tidewrack.core.procgen.world_gen import generate_world
    from tidewrack.services.content import load_bundled_content
    from tidewrack.ui.map_canvas import MapCanvas, label

    content = load_bundled_content()
    world = generate_world(7, content.world("world.standard"), content.roomsets, content.regions)
    game = Game(7, world, wardens=generate_wardens(7, world, content))
    coast, fens = (r.name for r in world.regions.values())
    assert [m.name for m in game.view().world_map.regions] == [coast]  # the Fens aren't known yet

    [(near, far)] = world.borders()
    position = game.world.get(game.player, Position)
    position.location, position.room = near, world.location(near).start
    game.bus.emit(LocationEntered(game.player, near, None, first_visit=True))
    game.bus.flush()
    view = game.view()
    assert [m.name for m in view.world_map.regions] == [coast, fens]
    beyond = next(n for n in view.world_map.nodes if n.id == far)
    assert beyond.guarded and label("Thornea", "Stilt Village", guarded=True) == "⌂ Thornea ⚔"

    canvas = MapCanvas(on_command=lambda _: None)
    canvas.show(view.world_map, "", "world", labels=True)
    texts = [s.value for s in canvas.canvas.shapes if hasattr(s, "value") and s.value]
    assert coast.upper() in texts and fens.upper() in texts

    for entity, _ in list(game.world.query(Warden)):
        game.world.destroy(entity)
    assert not next(n for n in game.view().world_map.nodes if n.id == far).guarded

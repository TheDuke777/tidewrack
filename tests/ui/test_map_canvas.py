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
    coast, fens, moors, highlands = (r.name for r in world.regions.values())
    assert [m.name for m in game.view().world_map.regions] == [coast]  # the Fens aren't known yet

    near, far = next(b for b in world.borders() if world.location(b[1]).region == "region.fens")
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
    assert moors.upper() not in texts and highlands.upper() not in texts  # not seen yet

    for entity, (warden,) in list(game.world.query(Warden)):
        if warden.road == far:
            game.world.destroy(entity)
    assert not next(n for n in game.view().world_map.nodes if n.id == far).guarded


def test_the_legend_lists_stilt_villages_as_towns():
    from tidewrack.core.engine.game import MapNode, MapView
    from tidewrack.ui.map_canvas import kinds_legend

    def node(i, kind):
        return MapNode(i, 0.5, 0.5, "visited", f"Place {i}", None, kind=kind)

    view = MapView((node("a", "Town"), node("b", "Peat Bog"), node("c", "Stilt Village")), (), 3)
    assert kinds_legend(view) == "⌂ Town   ∴ Peat Bog"


def test_drags_reuse_label_spots_and_skip_what_is_off_screen():
    from tidewrack.core.engine.game import MapNode, MapView
    from tidewrack.ui.map_canvas import MapCanvas

    nodes = tuple(
        MapNode(f"n{i}", x, 0.5, "visited", f"Place {i}", None, kind="Town")
        for i, x in enumerate((0.05, 0.5, 0.95))
    )
    canvas = MapCanvas(on_command=lambda _: None)
    canvas.width, canvas.height = 400, 260
    canvas.show(MapView(nodes, (("n0", "n1"), ("n1", "n2")), 3), "", "w", labels=True)
    whole = len(canvas.canvas.shapes)
    canvas.viewport.place((200, 130), (200, 130), 4.0, (400, 260))  # only the middle shows
    canvas._gesture = (4.0, (200, 130))
    offsets = dict(canvas._label_offsets)
    canvas._draw()
    assert canvas._label_offsets == offsets  # not placed again mid-gesture
    assert len(canvas.canvas.shapes) < whole
    texts = [s.value for s in canvas.canvas.shapes if getattr(s, "value", None)]
    assert texts == ["⌂ Place 1"]


def _map(n=9):
    from tidewrack.core.engine.game import MapNode, MapView

    nodes = tuple(
        MapNode(f"n{i}", (i % 3) / 2, (i // 3) / 2, "current" if i == 4 else "visited", "P", None)
        for i in range(n)
    )
    return MapView(nodes, (), n)


def test_area_maps_open_whole_world_maps_zoomed_in_and_each_keeps_your_zoom():
    from tidewrack.ui.map_canvas import FOCUS_ZOOM, MapCanvas

    canvas = MapCanvas(on_command=lambda _: None)
    canvas.show(_map(), "", key=("area", "a"), zoom_key="area")
    assert canvas.viewport.zoom == 1.0  # a place: the whole of it (v0.11.2)
    canvas.show(_map(), "", key=("world", "a"), zoom_key="world")
    assert canvas.viewport.zoom == FOCUS_ZOOM  # the world: zoomed in on you

    canvas.show(_map(), "", key=("area", "a"), zoom_key="area")
    canvas.viewport.place((0, 0), (0, 0), 3.0, canvas._size)  # you pinch in
    canvas.show(_map(), "", key=("area", "a"), zoom_key="area")  # a move: same place
    assert canvas.viewport.zoom == 3.0
    canvas.show(_map(), "", key=("area", "b"), zoom_key="area")  # travel: a new place
    assert canvas.viewport.zoom == 3.0
    canvas.show(_map(), "", key=("world", "b"), zoom_key="world")  # the world map: its own
    assert canvas.viewport.zoom == FOCUS_ZOOM

    from types import SimpleNamespace

    canvas._resized(SimpleNamespace(width=380, height=240))  # the layout settling
    assert canvas.viewport.zoom == FOCUS_ZOOM
    canvas._fit()
    canvas.show(_map(), "", key=("area", "c"), zoom_key="area")
    canvas.show(_map(), "", key=("world", "c"), zoom_key="world")
    assert canvas.viewport.zoom == 1.0  # you asked for the whole world map: it stays


def test_your_zoom_for_each_map_outlasts_the_app(tmp_path):
    from types import SimpleNamespace

    from tidewrack.services.settings import SettingsStore
    from tidewrack.ui.map_canvas import MAX_ZOOM, MapCanvas

    saved = []
    canvas = MapCanvas(on_command=lambda _: None, on_zoom=lambda k, z: saved.append((k, z)))
    canvas.show(_map(), "", key=("world", "a"), zoom_key="world")
    canvas._gesture_started(SimpleNamespace(local_focal_point=SimpleNamespace(x=100, y=100)))
    canvas._gesture_moved(
        SimpleNamespace(local_focal_point=SimpleNamespace(x=100, y=100), scale=1.5)
    )
    canvas._gesture_ended(SimpleNamespace())
    assert saved == [("world", 3.0)]  # told once the pinch ends
    canvas._gesture_started(SimpleNamespace(local_focal_point=SimpleNamespace(x=100, y=100)))
    canvas._gesture_ended(SimpleNamespace())
    assert saved == [("world", 3.0)]  # no change, nothing saved

    # A later session starts from what was saved (out-of-range values clamped).
    reopened = MapCanvas(on_command=lambda _: None, zooms={"world": 3.0, "area": 99})
    reopened.show(_map(), "", key=("world", "a"), zoom_key="world")
    assert reopened.viewport.zoom == 3.0
    reopened.show(_map(), "", key=("area", "a"), zoom_key="area")
    assert reopened.viewport.zoom == MAX_ZOOM

    # The Explore screen keeps them in settings beside the other map preferences.
    store = SettingsStore(tmp_path / "s.json")
    from tidewrack.ui.screens.game import GameScreen

    screen = GameScreen.__new__(GameScreen)
    screen.settings = store
    screen._save_zoom("area", 1.5)
    screen._save_zoom("world", 2.5)
    assert store.load().map_zooms == {"area": 1.5, "world": 2.5}


def test_the_legend_can_be_hidden_and_says_so():
    from tidewrack.ui.map_canvas import MapCanvas

    told = []
    canvas = MapCanvas(on_command=lambda _: None, legend_open=False, on_legend=told.append)
    assert not canvas.legend.visible and not canvas.legend_button.selected
    canvas._toggle_legend()
    assert canvas.legend.visible and canvas.legend_button.selected and told == [True]


def test_map_buttons_have_tinted_backs():
    from tidewrack.ui.map_canvas import BUTTON_FILL, MapCanvas

    canvas = MapCanvas(on_command=lambda _: None)
    assert canvas.legend_button.bgcolor == BUTTON_FILL
    assert canvas.fit_button.bgcolor == BUTTON_FILL
    assert canvas.legend_button.style.side.width == 1  # an edge, for light mode


# --- big maps (8a beta 3) ----------------------------------------------------------


def test_lesser_labels_are_left_out_rather_than_piled_up():
    points = {"a": (100, 100), "b": (104, 102)}
    names = {"a": "Saltmere", "b": "Gullhaven"}
    assert set(place_labels(points, names, (), RADIUS, 300, 300)) == {"a", "b"}
    # Obstacles (zoomed-out region names) leave a lesser label nowhere to go...
    wall = [(0, 0, 300, 300)]
    assert set(place_labels(points, names, (), RADIUS, 300, 300, keep={"a"}, obstacles=wall)) == {
        "a"
    }
    # ...but kept labels are never dropped, however crowded.
    both = place_labels(points, names, (), RADIUS, 300, 300, keep={"a", "b"}, obstacles=wall)
    assert set(both) == {"a", "b"}


def _whole_world():
    from tidewrack.core.engine.components import Explorer
    from tidewrack.core.engine.game import Game
    from tidewrack.core.procgen.world_gen import generate_world
    from tidewrack.services.content import load_bundled_content

    content = load_bundled_content()
    world = generate_world(
        20261103, content.world("world.standard"), content.roomsets, content.regions
    )
    game = Game(20261103, world)
    explorer = game.world.get(game.player, Explorer)
    explorer.locations_discovered |= set(world.locations)
    explorer.locations_visited |= set(world.locations)
    return game.view().world_map


def _drawn(canvas):
    texts = [s for s in canvas.canvas.shapes if getattr(s, "value", None)]
    return [s for s in texts if not s.value.isupper()], [s for s in texts if s.value.isupper()]


def test_a_crowded_world_map_labels_what_matters_and_more_when_zoomed_in():
    from tidewrack.ui.map_canvas import (
        LABEL_WIDTH,
        MAP_HEIGHT,
        TOP_INSET,
        MapCanvas,
        Viewport,
        label,
        label_rank,
    )

    view = _whole_world()
    assert len(view.nodes) == 28
    canvas = MapCanvas(on_command=lambda _: None)
    canvas.width, canvas.height = 360, MAP_HEIGHT
    canvas.show(view, "", "world", labels=True)

    def labels_at(zoom):
        canvas.viewport = Viewport()
        canvas.viewport.centre_on(canvas._current(), canvas._size, zoom)
        canvas._draw()
        return {s.value for s in _drawn(canvas)[0]}

    whole = labels_at(1.0)
    assert len(whole) < len(view.nodes)  # not every name fits the whole map
    must = [n for n in view.nodes if label_rank(n) <= 1]
    assert must and all(label(n.name, n.kind, n.quest, n.charted, n.guarded) in whole for n in must)
    zoomed = labels_at(2.0)
    # Zoomed in, every place on screen is named, except perhaps right against an
    # edge or under the map's buttons, where a label may have nowhere to go.
    inside = [
        n
        for n in view.nodes
        if LABEL_WIDTH / 2 <= canvas._points[n.id][0] <= canvas.width - LABEL_WIDTH / 2
        and TOP_INSET <= canvas._points[n.id][1] <= canvas.height  # not under the buttons
    ]
    assert len(inside) >= 4
    assert all(label(n.name, n.kind, n.quest, n.charted, n.guarded) in zoomed for n in inside)


def test_region_names_are_large_zoomed_out_and_stay_on_the_map():
    from tidewrack.ui.map_canvas import (
        MAP_HEIGHT,
        REGION_SIZE,
        REGION_SIZE_OUT,
        MapCanvas,
        Viewport,
        _region_width,
    )

    canvas = MapCanvas(on_command=lambda _: None)
    canvas.width, canvas.height = 360, MAP_HEIGHT
    canvas.show(_whole_world(), "", "world", labels=True)
    canvas.viewport = Viewport()
    canvas._draw()
    _, regions = _drawn(canvas)
    assert len(regions) == 4 and {r.style.size for r in regions} == {REGION_SIZE_OUT}
    for r in regions:
        half = _region_width(r.value) / 2
        assert half <= r.x <= canvas.width - half
    canvas.viewport.centre_on(canvas._current(), canvas._size, 2.0)
    canvas._draw()
    assert {r.style.size for r in _drawn(canvas)[1]} == {REGION_SIZE}


def test_a_tap_between_places_zooms_in_instead_of_guessing():
    from types import SimpleNamespace

    from tidewrack.core.engine.game import MapNode, MapView, Travel
    from tidewrack.ui.map_canvas import TAP_ZOOM, MapCanvas

    def tap(canvas, x, y):
        canvas._tapped(SimpleNamespace(local_position=SimpleNamespace(x=x, y=y)))

    nodes = (
        MapNode("a", 0.50, 0.5, "seen", "A", Travel("a")),
        MapNode("b", 0.56, 0.5, "seen", "B", Travel("b")),
        MapNode("c", 0.10, 0.1, "seen", "C", Travel("c")),
    )
    commands = []
    canvas = MapCanvas(on_command=commands.append)
    canvas.width, canvas.height = 400, 260
    canvas.show(MapView(nodes, (), 3), "", "w", labels=True)
    assert canvas.viewport.zoom == 1.0
    (ax, ay), (bx, _) = canvas._points["a"], canvas._points["b"]
    tap(canvas, (ax + bx) / 2, ay)
    assert commands == [] and canvas.viewport.zoom == TAP_ZOOM  # spread out under your finger
    assert abs(canvas._points["a"][0] - canvas._points["b"][0]) > abs(ax - bx)
    tap(canvas, *canvas._points["a"])  # now far enough apart to tell
    assert commands == [Travel("a")]


def test_a_tap_near_places_you_cant_go_to_still_zooms_in():
    from types import SimpleNamespace

    from tidewrack.core.engine.game import MapNode, MapView, Travel
    from tidewrack.ui.map_canvas import TAP_ZOOM, MapCanvas

    nodes = (
        MapNode("a", 0.50, 0.5, "seen", "A", Travel("a")),  # next door
        MapNode("b", 0.56, 0.5, "visited", "B", None),  # not reachable from here
    )
    commands = []
    canvas = MapCanvas(on_command=commands.append)
    canvas.width, canvas.height = 400, 260
    canvas.show(MapView(nodes, (), 2), "", "w", labels=True)
    (ax, ay), (bx, _) = canvas._points["a"], canvas._points["b"]
    canvas._tapped(SimpleNamespace(local_position=SimpleNamespace(x=(ax + bx) / 2, y=ay)))
    assert commands == [] and canvas.viewport.zoom == TAP_ZOOM
    x, y = canvas._points["b"]  # zoomed: a clear tap on a place you can't go does nothing
    canvas._tapped(SimpleNamespace(local_position=SimpleNamespace(x=x, y=y)))
    assert commands == [] and canvas.viewport.zoom == TAP_ZOOM


def test_walking_to_another_room_switches_from_the_world_map_to_this_place(tmp_path):
    from tidewrack.core.engine.game import Move
    from tidewrack.services.content import load_bundled_content
    from tidewrack.services.session import GameSession
    from tidewrack.services.settings import SettingsStore
    from tidewrack.services.storage import FileSaveStore
    from tidewrack.ui.shell import WorldShell

    session = GameSession.generate(
        FileSaveStore(tmp_path / "saves"),
        load_bundled_content(),
        "world.standard",
        "W",
        20261103,
    )
    shell = WorldShell(
        session,
        SettingsStore(tmp_path / "s.json"),
        on_back=lambda: None,
        confirm=lambda *_: None,
        notify=lambda _: None,
    )
    screen = shell.explore
    screen.map_choice.selected = ["world"]
    screen.refresh()
    town = session.game.overworld.location(session.game.overworld.start)
    screen.act(Move(town.room(town.start).exits[0].label))
    assert screen.map_choice.selected == ["area"]


def test_region_borders_are_one_dashed_path_behind_the_places():
    import flet.canvas as cv

    from tidewrack.ui.map_canvas import BORDER_DASH, MAP_HEIGHT, MapCanvas, Viewport

    view = _whole_world()
    assert view.borders
    canvas = MapCanvas(on_command=lambda _: None)
    canvas.width, canvas.height = 360, MAP_HEIGHT
    canvas.show(view, "", "world", labels=True)
    canvas.viewport = Viewport()
    canvas._draw()
    paths = [s for s in canvas.canvas.shapes if isinstance(s, cv.Path)]
    assert len(paths) == 1 and paths[0].paint.stroke_dash_pattern == BORDER_DASH
    first_dot = next(i for i, s in enumerate(canvas.canvas.shapes) if isinstance(s, cv.Circle))
    assert canvas.canvas.shapes.index(paths[0]) < first_dot  # drawn underneath


def test_map_only_events_send_just_the_map_not_the_whole_page(monkeypatch):
    from types import SimpleNamespace

    import flet as ft

    from tidewrack.core.engine.game import MapNode, MapView, Travel
    from tidewrack.ui import map_canvas
    from tidewrack.ui.map_canvas import MapCanvas

    disabled, updated, commands = [], [], []
    monkeypatch.setattr(ft.Column, "page", property(lambda self: object()))  # "on a page"
    monkeypatch.setattr(ft.context, "disable_auto_update", lambda: disabled.append(1))
    canvas = MapCanvas(on_command=commands.append)
    monkeypatch.setattr(canvas.control, "update", lambda: updated.append(1))
    nodes = (
        MapNode("a", 0.2, 0.5, "current", "A", None),
        MapNode("b", 0.8, 0.5, "seen", "B", Travel("b")),
    )
    clock = [100.0]
    monkeypatch.setattr(map_canvas.time, "monotonic", lambda: clock[0])
    canvas.show(MapView(nodes, (), 2), "", "w", labels=True)

    def point(x, y):
        return SimpleNamespace(x=x, y=y)

    canvas._gesture_started(SimpleNamespace(local_focal_point=point(50, 50)))
    assert (len(disabled), len(updated)) == (1, 0)  # nothing to send yet
    clock[0] += 1
    canvas._gesture_moved(SimpleNamespace(local_focal_point=point(60, 50), scale=1.5))
    assert (len(disabled), len(updated)) == (2, 1)  # redrawn: the map alone is sent
    canvas._gesture_moved(SimpleNamespace(local_focal_point=point(61, 50), scale=1.5))
    assert (len(disabled), len(updated)) == (3, 1)  # too soon to redraw: nothing sent
    canvas._gesture_ended(SimpleNamespace())
    assert (len(disabled), len(updated)) == (4, 2)

    disabled.clear()
    x, y = canvas._points["b"]
    canvas._tapped(SimpleNamespace(local_position=point(x, y)))
    assert commands == [Travel("b")] and disabled == []  # a move updates the whole page


def test_a_place_map_fills_the_canvas_with_its_rooms():
    from tidewrack.core.engine.components import Explorer
    from tidewrack.core.engine.game import Game
    from tidewrack.core.procgen.world_gen import generate_world
    from tidewrack.services.content import load_bundled_content
    from tidewrack.ui.map_canvas import MAP_HEIGHT, PAD, TOP_INSET, MapCanvas, Viewport

    content = load_bundled_content()
    world = generate_world(
        20261103, content.world("world.standard"), content.roomsets, content.regions
    )
    game = Game(20261103, world)
    here = world.location(world.start)
    explorer = game.world.get(game.player, Explorer)
    explorer.rooms_discovered[here.id] = set(here.rooms)  # every room known
    view = game.view().map
    xs = [r.pos[0] for r in here.rooms.values()]
    ys = [r.pos[1] for r in here.rooms.values()]
    assert view.bounds == (min(xs), min(ys), max(xs), max(ys))

    canvas = MapCanvas(on_command=lambda _: None)
    canvas.width, canvas.height = 360, MAP_HEIGHT
    canvas.show(view, "", "area", zoom_key="area")
    canvas.viewport = Viewport()
    canvas._draw()
    px = [canvas._points[n.id][0] for n in view.nodes]
    py = [canvas._points[n.id][1] for n in view.nodes]
    assert (round(min(px)), round(max(px))) == (PAD, 360 - PAD)  # edge to edge
    assert (round(min(py)), round(max(py))) == (TOP_INSET, MAP_HEIGHT - PAD)
    assert world.has_map and view.bounds != (0.0, 0.0, 1.0, 1.0)
    assert game.view().world_map.bounds == (0.0, 0.0, 1.0, 1.0)  # the world: its grid

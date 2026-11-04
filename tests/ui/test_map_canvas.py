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

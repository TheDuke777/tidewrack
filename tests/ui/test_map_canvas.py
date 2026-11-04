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

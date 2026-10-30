"""Painting rooms: colours in words, the paint fields as stored, and each room's paint
on its own side of the walls it shares."""

from app.services.vr_geometry_service import WALL_T, build_geometry_from_rooms
from app.services.vr_paint import apply_paint, clean_paint, paint_color

HALL_AND_BEDROOM = {
    "entry": "Hall",
    "rects": [
        {"room": "Hall", "x": 0, "z": 0, "length": 10, "width": 12},
        {"room": "Bedroom", "x": 10, "z": 0, "length": 12, "width": 12},
    ],
}


def _rooms(hall: dict | None = None, bedroom: dict | None = None) -> list[dict]:
    return [
        {"name": "Hall", "dimensions": {"height": 9}, "connects_to": ["Bedroom"], **(hall or {})},
        {"name": "Bedroom", "dimensions": {"height": 9}, **(bedroom or {})},
    ]


def _quads(geometry: dict, room_id: int) -> dict[str, list[tuple[float, float, float]]]:
    """World-space corners of a room's paint, by colour (r, g, b as text)."""
    piece = next(p for p in geometry["paint"]["pieces"] if p["room"] == room_id)
    at = piece["position"]
    out: dict[str, list] = {}
    for group in geometry["paint"]["meshes"][piece["mesh"]]["groups"]:
        pos = group["positions"]
        key = "{r},{g},{b}".format(**group["color"])
        out[key] = [(pos[i] + at["x"], pos[i + 1] + at["y"], pos[i + 2] + at["z"]) for i in range(0, len(pos), 3)]
    return out


def test_paint_colours_from_words():
    assert paint_color("sage green") == "#a7b59a"
    assert paint_color("Navy Blue") == "#24344d"
    assert paint_color("off-white") == "#eeebe2"
    assert paint_color("#ABC") == "#aabbcc"
    assert paint_color("a7b59a") == "#a7b59a"
    # A colour with no paint name of its own is lightened or darkened.
    assert paint_color("light purple") not in (None, paint_color("purple"))
    assert paint_color("plaid") is None
    assert paint_color(None) is None


def test_clean_paint_keeps_usable_fields_as_hex():
    room = clean_paint({
        "name": "Den", "wall_color": "sage", "ceiling_color": "nonsense",
        "accent_wall": {"side": "rear", "color": "navy"},
    })
    assert room == {"name": "Den", "wall_color": "#a7b59a", "accent_wall": {"side": "back", "color": "#24344d"}}
    assert "accent_wall" not in clean_paint({"name": "Den", "accent_wall": {"side": "up", "color": "red"}})


def test_apply_paint_changes_only_the_named_rooms_and_fields():
    rooms = _rooms(bedroom={"wall_color": "#ffffff", "ceiling_color": "#eeeeee"})
    out, changed = apply_paint(rooms, {"bedroom": {"wall_color": "sage green", "ceiling_color": None}, "Attic": {}})
    assert changed == ["Bedroom"]
    assert out[0] is rooms[0]
    assert out[1]["wall_color"] == "#a7b59a" and "ceiling_color" not in out[1]
    assert apply_paint(rooms, {"Hall": {"wall_color": "plaid"}})[1] == []


def test_adjacent_rooms_are_painted_on_their_own_side_of_the_shared_wall():
    g = build_geometry_from_rooms(rooms_ft=_rooms({"wall_color": "white"}, {"wall_color": "sage green"}),
                                  layout=HALL_AND_BEDROOM)
    hall, bedroom = g["rooms"]
    assert hall["paint"]["walls"] == "#f4f4f0" and bedroom["paint"]["walls"] == "#a7b59a"
    shared_x = hall["bounds"]["x1"]
    assert shared_x == bedroom["bounds"]["x0"]

    def on_shared_wall(quads):
        return [p for pts in quads.values() for p in pts if abs(abs(p[0] - shared_x) - WALL_T) < 0.01]

    hall_side = on_shared_wall(_quads(g, hall["id"]))
    bed_side = on_shared_wall(_quads(g, bedroom["id"]))
    assert hall_side and bed_side
    assert all(p[0] < shared_x for p in hall_side)
    assert all(p[0] > shared_x for p in bed_side)


def test_accent_wall_and_ceiling_and_unpainted_rooms():
    g = build_geometry_from_rooms(rooms_ft=_rooms(bedroom={
        "accent_wall": {"side": "back", "color": "navy"}, "ceiling_color": "warm white",
    }), layout=HALL_AND_BEDROOM)
    hall, bedroom = g["rooms"]
    assert hall["paint"] is None
    assert [p["room"] for p in g["paint"]["pieces"]] == [bedroom["id"]]
    quads = _quads(g, bedroom["id"])
    assert len(quads) == 2  # no wall colour: only the accent wall and the ceiling
    navy = next(pts for key, pts in quads.items() if key.startswith("0.141"))
    back = bedroom["bounds"]["z1"]
    assert all(abs(p[2] - (back - WALL_T - 0.004)) < 0.002 for p in navy)
    ceiling = next(pts for key, pts in quads.items() if not key.startswith("0.141"))
    assert len({round(p[1], 3) for p in ceiling}) == 1


def test_no_paint_means_no_paint_entry():
    g = build_geometry_from_rooms(rooms_ft=_rooms(), layout=HALL_AND_BEDROOM)
    assert g["paint"] is None


def test_paint_on_an_upper_floor_is_lifted_with_it():
    layout = {"entry": "Hall", "rects": HALL_AND_BEDROOM["rects"] + [
        {"room": "Loft", "x": 0, "z": 0, "length": 22, "width": 12, "level": 1},
    ]}
    rooms = _rooms() + [{"name": "Loft", "dimensions": {"height": 8}, "wall_color": "blush"}]
    g = build_geometry_from_rooms(rooms_ft=rooms, layout=layout)
    loft = next(r for r in g["rooms"] if r["name"] == "Loft")
    ys = [p[1] for pts in _quads(g, loft["id"]).values() for p in pts]
    floor_y = next(lv["y"] for lv in g["levels"] if lv["level"] == 1)
    assert min(ys) >= floor_y - 0.01 and floor_y > 2

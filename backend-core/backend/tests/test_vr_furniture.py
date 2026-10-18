"""Furniture: cleaning the plan's description and placing pieces in rooms (no network calls)."""

import math

import pytest

from app.services import vr_furniture as vf
from app.services.example_floor_plans import EXAMPLE_STRUCTURE
from app.services.vr_geometry_service import build_geometry_from_rooms

# One 14 x 12 ft room: a doorway in the middle of its left wall, a window in the back.
ROOM = {"id": 1, "name": "Living Room", "bounds": {"x0": 0.0, "x1": 4.2672, "z0": 0.0, "z1": 3.6576}}
DOOR = {"axis": "z", "line": 0.0, "lo": 1.37, "hi": 2.29, "bottom": 0.0, "top": 2.03}
WINDOW = {"axis": "x", "line": 3.6576, "lo": 1.52, "hi": 2.74, "bottom": 0.914, "top": 2.13}


def _build(items, room=ROOM, openings=(DOOR, WINDOW), models=None, auto=None):
    spec = {"rooms": {room["name"]: items}}
    if auto is not None:
        spec["auto"] = auto
    out, notes = vf.build_furniture(vf.furniture_spec(spec), [room], list(openings), models)
    return out, notes


def _boxes(out):
    """Plan bounds of every piece (rugs left out: things stand on them)."""
    boxes = []
    for p in out["pieces"] + out["models"]:
        if p["type"] == "rug":
            continue
        xs, zs = [c[0] for c in p["outline"]], [c[1] for c in p["outline"]]
        boxes.append((p["type"], min(xs), max(xs), min(zs), max(zs)))
    return boxes


# --- Words --------------------------------------------------------------------------

@pytest.mark.parametrize("text, room, piece", [
    ("navy velvet couch", "", "sofa"),
    ("Queen bed", "", "bed"),
    ("L-shaped sofa", "", "sectional"),
    ("a table", "dining", "dining table"),
    ("a table", "living", "coffee table"),
    ("chair", "office", "office chair"),
    ("chair", "", "armchair"),
    ("sink", "kitchen", "counter"),
    ("sink", "bathroom", "vanity"),
    ("fridge", "", "refrigerator"),
    ("fiddle leaf fig", "", "potted plant"),
    ("spaceship", "", None),
])
def test_find_piece(text, room, piece):
    assert vf.find_piece(text, room) == piece


@pytest.mark.parametrize("name, kind", [
    ("Primary Bedroom", "primary"), ("Hall Bathroom", "bathroom"), ("Primary Closet", "storage"),
    ("Kitchen", "kitchen"), ("Breakfast Nook", "dining"), ("Hallway", "hall"), ("Family Room", "living"),
    ("Powder Room", "powder"), ("Kids Bedroom", "kids"), ("Entry Foyer", "entry"),
])
def test_room_kind(name, kind):
    assert vf.room_kind(name) == kind


def test_spec_cleans_what_the_ai_sends():
    spec = vf.furniture_spec({
        "auto": "true",
        "rooms": {
            "Dining Room": [{"type": "round dining table", "chairs": 4, "material": "walnut"}],
            "Primary Bedroom": [{"type": "bed", "name": "king bed with a tufted headboard", "color": "navy"}],
            "Office": ["desk", {"type": "a time machine", "width": 3}],
            "Garage": "not a list",
        },
    })
    assert spec["auto"] is True
    table = spec["rooms"]["Dining Room"][0]
    assert table == {"type": "round table", "wood": vf.WOODS["walnut"], "seats": 4}
    bed = spec["rooms"]["Primary Bedroom"][0]
    assert bed["size"] == "king" and bed["color"] == "#24344d"
    assert spec["rooms"]["Office"] == [
        {"type": "desk"}, {"type": "custom", "name": "a time machine", "width": 3.0},
    ]
    assert "Garage" not in spec["rooms"]


def test_spec_takes_a_list_of_items_naming_their_rooms():
    spec = vf.furniture_spec([{"room": "Den", "type": "sofa"}, {"type": "lamp"}])
    assert spec == {"rooms": {"Den": [{"type": "sofa"}]}}
    assert vf.furniture_spec("nonsense") is None


def test_merge_replaces_only_the_rooms_it_lists():
    current = {"auto": True, "rooms": {"Den": [{"type": "sofa"}], "Office": [{"type": "desk"}]}}
    merged = vf.merge_furniture(current, {"rooms": {"den": [{"type": "piano"}], "Kitchen": []}})
    assert merged == {"auto": True, "rooms": {"Office": [{"type": "desk"}], "den": [{"type": "piano"}], "Kitchen": []}}
    assert vf.merge_furniture(current, {"auto": False})["auto"] is False


def test_rename_and_prune_follow_the_rooms():
    spec = {"rooms": {"Den": [{"type": "sofa"}], "Office": [{"type": "desk"}]}}
    renamed = vf.rename_furniture_rooms(spec, {"den": "Family Room"})
    assert set(renamed["rooms"]) == {"Family Room", "Office"}
    assert vf.prune_furniture(renamed, ["family room"]) == {"rooms": {"Family Room": [{"type": "sofa"}]}}
    assert vf.prune_furniture(renamed, []) is None


# --- Placing ------------------------------------------------------------------------

def test_pieces_stay_inside_the_room_clear_of_each_other_and_the_doorway():
    out, notes = _build([
        {"type": "sofa"}, {"type": "coffee table"}, {"type": "armchair"}, {"type": "tv stand"},
        {"type": "bookshelf"}, {"type": "rug"}, {"type": "floor lamp"},
    ])
    assert notes == []
    boxes = _boxes(out)
    inner = (ROOM["bounds"]["x0"] + 0.1, ROOM["bounds"]["x1"] - 0.1, ROOM["bounds"]["z0"] + 0.1, ROOM["bounds"]["z1"] - 0.1)
    for kind, x0, x1, z0, z1 in boxes:
        assert inner[0] - 1e-3 <= x0 and x1 <= inner[1] + 1e-3 and inner[2] - 1e-3 <= z0 and z1 <= inner[3] + 1e-3, kind
        # Nothing in front of the doorway on the left wall.
        assert not (x0 < 0.1 + 0.9 and DOOR["lo"] - 0.1 < z1 and z0 < DOOR["hi"] + 0.1), kind
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            overlap = a[1] < b[2] - 1e-3 and b[1] < a[2] - 1e-3 and a[3] < b[4] - 1e-3 and b[3] < a[4] - 1e-3
            assert not overlap, (a[0], b[0])


def test_tall_pieces_keep_clear_of_windows_low_ones_may_stand_under_them():
    # Only the back wall is free: a sofa fits under the window, a bookshelf does not.
    narrow = {"id": 1, "name": "Den", "bounds": {"x0": 0.0, "x1": 2.6, "z0": 0.0, "z1": 3.0}}
    window = {**WINDOW, "line": 3.0, "lo": 0.3, "hi": 2.3}
    sofa, _ = _build([{"type": "loveseat", "place": "back"}], narrow, [window])
    assert sofa["pieces"][0]["yaw"] == 180.0  # its back to the back wall, facing the street
    shelf, notes = _build([{"type": "bookshelf", "place": "back"}], narrow, [window])
    assert shelf["pieces"][0]["position"]["z"] < 2.5  # moved to another wall
    assert notes == []


def test_dining_table_comes_with_chairs_facing_it():
    out, notes = _build([{"type": "dining table", "seats": 6}], {**ROOM, "name": "Dining Room"})
    assert notes == []
    chairs = [p for p in out["pieces"] if p["type"] == "dining chair"]
    table = next(p for p in out["pieces"] if p["type"] == "dining table")
    assert len(chairs) == 6
    # All six chairs share one mesh.
    assert len({c["mesh"] for c in chairs}) == 1
    for chair in chairs:
        dx = table["position"]["x"] - chair["position"]["x"]
        dz = table["position"]["z"] - chair["position"]["z"]
        yaw = math.radians(chair["yaw"])
        front = (-math.sin(yaw), math.cos(yaw))  # where its front (+z) points
        assert front[0] * dx + front[1] * dz > 0


def test_too_many_chairs_for_the_room_are_dropped_with_a_note():
    small = {"id": 1, "name": "Dining Nook", "bounds": {"x0": 0.0, "x1": 2.6, "z0": 0.0, "z1": 2.6}}
    out, notes = _build([{"type": "dining table", "seats": 10}], small, [])
    chairs = [p for p in out["pieces"] if p["type"] == "dining chair"]
    assert len(chairs) < 10
    assert notes and "chairs fit" in notes[0]


def test_nightstands_stand_beside_the_bed():
    bedroom = {"id": 1, "name": "Guest Bedroom", "bounds": {"x0": 0.0, "x1": 4.0, "z0": 0.0, "z1": 3.8}}
    out, notes = _build([{"type": "bed", "size": "queen"}, {"type": "nightstand"}, {"type": "nightstand"}],
                        bedroom, [])
    assert notes == []
    bed = next(p for p in out["pieces"] if p["type"] == "bed")
    stands = [p for p in out["pieces"] if p["type"] == "nightstand"]
    assert len(stands) == 2
    for stand in stands:
        assert stand["yaw"] == bed["yaw"]
        gap = math.hypot(stand["position"]["x"] - bed["position"]["x"], stand["position"]["z"] - bed["position"]["z"])
        assert gap < 1.5


def test_a_bed_too_big_for_the_room_steps_down_a_size():
    # 6 ft wide inside: a king (6.6 ft) can't go against any wall, a queen (5.2 ft) can.
    narrow = {"id": 1, "name": "Primary Bedroom", "bounds": {"x0": 0.0, "x1": 2.0, "z0": 0.0, "z1": 3.4}}
    out, notes = _build([{"type": "bed", "size": "king"}], narrow, [])
    assert out["pieces"][0]["type"] == "bed"
    assert notes == ["A king bed doesn't fit in Primary Bedroom, so it has a queen"]


def test_exact_position_is_kept():
    out, _ = _build([{"type": "piano", "x": 7, "z": 6, "facing": "left"}])
    piano = out["pieces"][0]
    assert piano["position"]["x"] == pytest.approx(7 * 0.3048, abs=0.01)
    assert piano["position"]["z"] == pytest.approx(6 * 0.3048, abs=0.01)
    assert piano["yaw"] == 90.0  # front toward -x


def test_what_does_not_fit_is_noted():
    closet = {"id": 1, "name": "Closet", "bounds": {"x0": 0.0, "x1": 1.2, "z0": 0.0, "z1": 1.2}}
    out, notes = _build([{"type": "piano"}], closet, [])
    assert out is None or not out["pieces"]
    assert notes == ["No room for the piano in Closet"]


def test_a_photo_model_replaces_the_drawn_piece():
    models = [{"id": 7, "name": "Grandma's armchair", "url": "/plant_models/7/model-a.glb", "aspect": 0.9,
               "height_ft": 3.5}]
    out, _ = _build([{"type": "armchair", "name": "grandmas armchairs"}, {"type": "sofa"}], models=models)
    assert [m["model_id"] for m in out["models"]] == [7]
    assert out["models"][0]["scale"] == pytest.approx(3.5 * 0.3048, abs=0.01)
    assert [p["type"] for p in out["pieces"]] == ["sofa"]


def test_auto_furnishes_every_room_of_the_example_house():
    geometry = build_geometry_from_rooms(
        rooms_ft=EXAMPLE_STRUCTURE["rooms"], layout=EXAMPLE_STRUCTURE["layout"], furniture={"auto": True},
    )
    furniture = geometry["furniture"]
    by_room = {}
    for p in furniture["pieces"]:
        by_room.setdefault(p["room"], []).append(p["type"])
    names = {r["id"]: r["name"] for r in geometry["rooms"]}
    furnished = {names[i]: types for i, types in by_room.items()}
    assert "sofa" in furnished["Living Room"]
    assert "dining table" in furnished["Dining Room"]
    assert "counter" in furnished["Kitchen"]
    assert "bed" in furnished["Primary Bedroom"] and "bed" in furnished["Bedroom 2"]
    assert {"toilet", "vanity"} <= set(furnished["Hall Bathroom"])
    # Every piece's mesh is sent once.
    assert {p["mesh"] for p in furniture["pieces"]} == set(furniture["meshes"])
    for mesh in furniture["meshes"].values():
        for group in mesh["groups"]:
            assert len(group["positions"]) % 9 == 0


def test_a_listed_room_keeps_exactly_its_items_and_others_stay_empty_without_auto():
    geometry = build_geometry_from_rooms(
        rooms_ft=EXAMPLE_STRUCTURE["rooms"], layout=EXAMPLE_STRUCTURE["layout"],
        furniture={"rooms": {"Living Room": [{"type": "piano"}]}},
    )
    assert [p["type"] for p in geometry["furniture"]["pieces"]] == ["piano"]
    plain = build_geometry_from_rooms(rooms_ft=EXAMPLE_STRUCTURE["rooms"], layout=EXAMPLE_STRUCTURE["layout"])
    assert plain["furniture"] is None


def test_every_piece_builds_a_mesh():
    for name, piece in vf.PIECES.items():
        W, D, H = (vf._m(v) for v in (piece.width, piece.depth, piece.height))
        mesh = vf.piece_mesh(piece.builder, round(W, 2), round(D, 2), round(H, 2),
                             vf._colors({"type": name}, piece), ())
        assert mesh.triangles > 0, name
        ys = [p[1] for pts in mesh.groups.values() for p in pts]
        assert min(ys) >= -1e-6, name  # nothing below the floor

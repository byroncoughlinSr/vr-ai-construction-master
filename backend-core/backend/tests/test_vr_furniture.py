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


def _build(items, room=ROOM, openings=(DOOR, WINDOW), models=None, auto=None, styles=None):
    spec = {"rooms": {room["name"]: items}}
    if auto is not None:
        spec["auto"] = auto
    out, notes = vf.build_furniture(vf.furniture_spec(spec), [room], list(openings), models, styles)
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


def test_an_exact_piece_turned_sideways_stays_inside_the_room():
    # A 9 x 6.5 ft sectional facing right lies 9 ft along z: kept off the front wall by its width.
    out, _ = _build([{"type": "sectional", "x": 0, "z": 0, "facing": "right"}])
    _, x0, x1, z0, z1 = _boxes(out)[0]
    assert x0 >= -0.01 and z0 >= -0.01
    assert z1 - z0 == pytest.approx(9 * 0.3048, abs=0.05)


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


def test_a_turned_photo_model_is_turned_in_the_house():
    model = {"id": 7, "name": "Island", "url": "/plant_models/7/model-a.glb", "aspect": 2.0, "height_ft": 3.0}
    item = [{"type": "kitchen island", "name": "island", "seats": 2}]
    plain = _build(item, room=KITCHEN, openings=[], models=[model])[0]
    turned = _build(item, room=KITCHEN, openings=[], models=[{**model, "turn": 180}])[0]
    assert turned["models"][0]["yaw"] == (plain["models"][0]["yaw"] + 180) % 360
    assert _boxes(turned) == _boxes(plain)  # it stands in the same place, stools and all


def test_a_photo_model_takes_its_real_size_turned_too():
    # 3.1 ft tall, 9.7 ft wide and 6 ft deep as photographed; turned 90° it is 6 ft wide.
    model = {"id": 3, "name": "Sectional sofa", "url": "/plant_models/3/model-a.glb", "aspect": 3.13,
             "height_ft": 3.1, "turn": 90, "footprint": (3.13, 1.94)}
    out, _ = _build([{"type": "sectional", "name": "sectional sofa", "x": 0, "z": 0, "facing": "back"}],
                    models=[model])
    _, x0, x1, z0, z1 = _boxes(out)[0]
    assert x1 - x0 == pytest.approx(6.0 * 0.3048, abs=0.05)
    assert z1 - z0 == pytest.approx(9.7 * 0.3048, abs=0.05)
    assert x0 >= -0.01 and z0 >= -0.01


def test_a_photo_model_matches_a_longer_name_too():
    desk = {"id": 4, "name": "Office desk", "url": "/plant_models/4/model-a.glb", "aspect": 1, "height_ft": 2.5}
    plain = {"id": 5, "name": "Desk", "url": "/plant_models/5/model-a.glb", "aspect": 1, "height_ft": 2.5}
    out, _ = _build([{"type": "desk", "name": "my office desk"}], models=[plain, desk])
    assert [m["model_id"] for m in out["models"]] == [4]


def test_the_refine_prompt_shows_what_auto_rooms_hold():
    rooms = [{"name": "Office", "dimensions": {"length": 11.5, "width": 17.5, "height": 9}},
             {"name": "Kitchen", "dimensions": {"length": 9.5, "width": 16, "height": 9}}]
    spec = {"auto": True, "rooms": {"Kitchen": [{"type": "counter"}]}}
    shown = vf.shown_furniture(spec, rooms)
    assert "auto" not in shown  # the AI read "every room listed" as auto: false
    assert shown["rooms"]["Kitchen"] == [{"type": "counter"}]
    assert {i["type"] for i in shown["rooms"]["Office"]} >= {"desk"}
    assert vf.shown_furniture({"rooms": {}}, rooms) == {"rooms": {}}


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


# A 9 x 15 ft kitchen whose whole left side is open to the family room.
KITCHEN = {"id": 2, "name": "Kitchen", "bounds": {"x0": 0.0, "x1": 2.7432, "z0": 0.0, "z1": 4.572}}
OPEN_LEFT = {"axis": "z", "line": 0.0, "lo": 0.0, "hi": 4.572, "bottom": 0.0, "top": 2.74, "kind": "open"}


def _island_and_stools(out):
    island = next(b for b in _boxes(out) if b[0] == "kitchen island")
    stools = [b for b in _boxes(out) if b[0] == "bar stool"]
    return island, stools


def test_an_island_backs_onto_the_open_side_it_is_put_on():
    out, _ = _build([{"type": "kitchen island", "place": "left", "seats": 3}], room=KITCHEN, openings=[OPEN_LEFT])
    island, stools = _island_and_stools(out)
    assert island[1] < vf.WALL_T + 0.05  # its back at the open edge, not 2 ft in from it
    assert len(stools) == 3 and all(s[1] >= island[2] - 0.3 for s in stools)  # seats on the kitchen side


def test_an_island_in_the_middle_faces_where_it_is_told():
    for facing, east in (("right", True), ("left", False)):
        out, _ = _build([{"type": "kitchen island", "facing": facing, "seats": 2}], room=KITCHEN, openings=[])
        island, stools = _island_and_stools(out)
        mid = (island[1] + island[2]) / 2
        assert stools and all(((s[1] + s[2]) / 2 > mid) == east for s in stools)


def test_an_island_facing_the_open_side_puts_its_stools_in_the_next_room():
    out, _ = _build([{"type": "kitchen island", "place": "left", "facing": "left", "seats": 3}],
                    room=KITCHEN, openings=[OPEN_LEFT])
    island, stools = _island_and_stools(out)
    assert island[1] >= 0.0  # the island stays in the kitchen
    assert len(stools) == 3 and all(s[1] < 0.0 for s in stools)  # its stools reach into the family room


def test_an_island_only_turns_outward_through_an_opening():
    out, _ = _build([{"type": "kitchen island", "place": "left", "facing": "left", "seats": 3}],
                    room=KITCHEN, openings=[])
    island, stools = _island_and_stools(out)
    assert all(s[1] >= 0.0 for s in stools)  # a solid wall: the stools stay in the room


# --- A stove across a corner, counters between pieces -------------------------------

def _by_type(out, kind):
    return [p for p in out["pieces"] if p["type"] == kind]


@pytest.mark.parametrize("raw, corner", [
    ({"type": "stove", "place": "front right corner", "name": "diagonal stove"}, "front-right"),
    ({"type": "range", "corner": "diagonal"}, "any"),
    ({"type": "oven", "place": "corner"}, "any"),
])
def test_a_stove_in_a_corner_is_read_and_survives_cleaning_again(raw, corner):
    spec = vf.furniture_spec({"rooms": {"Kitchen": [raw]}})
    assert spec["rooms"]["Kitchen"][0]["corner"] == corner
    assert vf.furniture_spec(spec) == spec


@pytest.mark.parametrize("raw", [
    {"type": "counter", "between": ["stove", "fridge"]},
    {"type": "countertop", "between": "the range and the refrigerator"},
    {"type": "counter", "from": "stove", "to": "refrigerator"},
])
def test_a_counter_between_two_pieces_is_read(raw):
    item = vf.furniture_spec({"rooms": {"Kitchen": [raw]}})["rooms"]["Kitchen"][0]
    assert item["between"] == ["stove", "refrigerator"]


def test_a_corner_stove_with_counters_running_to_the_fridge():
    # Kitchen 9 x 15 ft, open to the next room on the left.
    out, notes = _build([
        {"type": "stove", "corner": "front-right"},
        {"type": "counter", "between": ["stove", "refrigerator"]},
        {"type": "refrigerator", "place": "back"},  # no room there: the far end of the stove's wall
    ], room=KITCHEN, openings=[OPEN_LEFT, {**WINDOW, "line": 4.572, "lo": 0.2, "hi": 2.6}])
    assert notes == []
    (stove,), (counter,), (fridge,) = (_by_type(out, k) for k in ("stove", "counter", "refrigerator"))
    assert "corner" in stove["mesh"] and "range" not in counter["mesh"] and "sink" in counter["mesh"]
    sx = [c[0] for c in stove["outline"]]
    sz = [c[1] for c in stove["outline"]]
    assert max(sx) == pytest.approx(2.7432 - 0.12, abs=0.01) and min(sz) == pytest.approx(0.12, abs=0.01)
    # The fridge on the right wall at the back, the counter filling the wall from the stove to it, flush.
    cz = sorted(c[1] for c in counter["outline"])
    fz = sorted(c[1] for c in fridge["outline"])
    assert min(c[0] for c in fridge["outline"]) > 1.5
    assert cz[0] == pytest.approx(max(sz), abs=0.01) and cz[-1] == pytest.approx(fz[0], abs=0.01)


BYRON = {"id": 1, "name": "Byron's kitchen", "cabinet": "#ece4d4", "door": "raised", "uppers": "glass",
         "handle": "#3b2e27", "crown": True, "top": "#1b1b1d", "fleck": "#8f8a80", "backsplash": "mosaic",
         "backsplash_color": "#4a5058", "stove_model_id": 9, "fridge_model_id": None}
STOVE_MODEL = {"id": 9, "name": "Stove and microwave", "url": "/plant_models/9/model-a.glb", "aspect": 0.43,
               "height_ft": 5.8, "turn": 0, "footprint": (0.43, 0.40)}


def test_a_kitchen_style_is_read_and_survives_cleaning_again():
    spec = vf.furniture_spec({"rooms": {"Kitchen": [{"type": "counter", "style": " Byron's  kitchen "},
                                                      {"type": "sofa", "style": "Byron's kitchen"}]}})
    assert spec["rooms"]["Kitchen"] == [{"type": "counter", "style": "Byron's kitchen"}, {"type": "sofa"}]
    assert vf.furniture_spec(spec) == spec


def test_a_kitchen_style_draws_the_whole_kitchen_and_puts_its_stove_in_the_corner():
    out, notes = _build([
        {"type": "stove", "name": "stove", "corner": "front-right", "style": "byron kitchen"},  # as the AI names it
        {"type": "counter", "between": ["stove", "refrigerator"]},
        {"type": "refrigerator", "place": "back"},
        {"type": "kitchen island", "place": "center", "seats": 0},
    ], room=KITCHEN, openings=[OPEN_LEFT, {**WINDOW, "line": 4.572, "lo": 0.2, "hi": 2.6}], models=[STOVE_MODEL],
        styles=[BYRON])
    assert notes == []
    (corner,), (counter,), (island,) = (_by_type(out, k) for k in ("stove", "counter", "kitchen island"))
    # Every kitchen piece in the style: its cabinet colour, raised doors, glass uppers, granite, mosaic.
    for piece in (corner, counter, island):
        assert "ece4d4" in piece["mesh"] and "1b1b1d" in piece["mesh"] and "door_raised" in piece["mesh"]
    assert "-glass" in counter["mesh"] and "splash_mosaic" in counter["mesh"] and "-crown" in counter["mesh"]
    # The stove is the style's photo model, standing on the corner's diagonal facing out of it.
    (stove,) = [m for m in out["models"] if m["type"] == "stove"]
    assert stove["model_id"] == 9 and stove["scale"] == pytest.approx(5.8 * 0.3048, abs=0.01)
    assert stove["yaw"] == pytest.approx(45.0)
    assert "-model" in corner["mesh"] and "range_w" in corner["mesh"]
    cx = sum(c[0] for c in corner["outline"]) / 4
    cz = sum(c[1] for c in corner["outline"]) / 4
    assert stove["position"]["x"] < cx and stove["position"]["z"] > cz  # out of the front-right corner
    # The drawn part is only the cabinet round it: no range or hood of its own.
    mesh = out["meshes"][corner["mesh"]]
    assert all(g["color"] != vf._rgb("#3b3b3b") for g in mesh["groups"])


def test_a_style_the_request_names_is_put_on_the_kitchen_when_the_ai_leaves_it_out():
    raw = {"rooms": {"Kitchen": [{"type": "stove", "corner": "front-right"}, {"type": "counter"}, {"type": "rug"}],
                     "Office": [{"type": "desk"}]}}
    spec = vf.with_named_style(raw, "Make the kitchen in Byron's kitchen style", ["Byron's kitchen", "Beach"])
    assert [i.get("style") for i in spec["rooms"]["Kitchen"]] == ["Byron's kitchen", "Byron's kitchen", None]
    assert "style" not in spec["rooms"]["Office"][0]
    # Not named: left as the AI sent it; one the AI gave is kept.
    assert "style" not in vf.with_named_style(raw, "a white kitchen", ["Byron's kitchen"])["rooms"]["Kitchen"][0]
    # An "auto" nobody asked for is dropped; "furnish the house" keeps it.
    assert "auto" not in vf.with_named_style({**raw, "auto": False}, "Byron's kitchen style", ["Byron's kitchen"])
    assert vf.with_named_style({**raw, "auto": True}, "furnish the house", [])["auto"] is True
    given = {"rooms": {"Kitchen": [{"type": "counter", "style": "Beach"}]}}
    assert vf.with_named_style(given, "byrons kitchen", ["Byron's kitchen", "Beach"])["rooms"]["Kitchen"][0]["style"] == "Beach"


def test_a_style_mesh_has_its_doors_backsplash_and_crown():
    style = (("door", "raised"), ("glass", True), ("handle", "#3b2e27"), ("crown", True), ("fleck", "#8f8a80"),
             ("splash", "mosaic"), ("splash_color", "#4a5058"))
    plain = vf.piece_mesh("counter", 3.0, 0.61, 0.91, (("main", "#ece4d4"), ("top", "#1b1b1d")),
                          (("sink", True), ("upper", True)))
    styled = vf.piece_mesh("counter", 3.0, 0.61, 0.91, (("main", "#ece4d4"), ("top", "#1b1b1d")),
                           (("sink", True), ("upper", True)) + style)
    assert vf.GLASS in styled.groups and "#3b2e27" in styled.groups and "#4a5058" in styled.groups
    assert vf.GLASS not in plain.groups
    top = max(p[1] for g in styled.groups.values() for p in g)
    assert top == pytest.approx(2.12 + 0.09, abs=0.001)  # the crown on the wall cabinets
    assert styled.triangles < 15000


def test_a_counter_width_sets_the_gap_to_the_fridge_and_cabinets_fill_the_wall_past_it():
    # Kitchen 9 x 15 ft: 4 ft of counter from the corner stove, the fridge, then more cabinets.
    out, notes = _build([
        {"type": "stove", "corner": "front-right"},
        {"type": "counter", "between": ["stove", "refrigerator"], "width": 4},
        {"type": "refrigerator", "place": "back"},
        {"type": "counter"},  # no wall named: on along the run's wall, not the longer back wall
    ], room=KITCHEN, openings=[OPEN_LEFT])
    assert notes == []
    (stove,), (fridge,) = _by_type(out, "stove"), _by_type(out, "refrigerator")
    first, past = sorted(_by_type(out, "counter"), key=lambda p: min(c[1] for c in p["outline"]))
    z = lambda p: (min(c[1] for c in p["outline"]), max(c[1] for c in p["outline"]))  # noqa: E731
    assert z(first)[0] == pytest.approx(z(stove)[1], abs=0.01)
    assert z(first)[1] - z(first)[0] == pytest.approx(4 * 0.3048, abs=0.01)
    assert z(fridge)[0] == pytest.approx(z(first)[1], abs=0.01)  # on the right wall, 4 ft on
    assert min(c[0] for c in fridge["outline"]) > 1.5
    assert z(past)[0] >= z(fridge)[1] - 0.01 and z(past)[1] - z(past)[0] > 0.9
    assert "sink" in first["mesh"] and "sink" not in past["mesh"]


def test_the_corner_stove_mesh_fills_the_corner_and_faces_out_of_it():
    L = vf._corner_size()
    m = vf.piece_mesh("stove", L, L, 0.914, (("main", vf.STEEL),), (("corner", True), ("cabinet", "#ffffff")))
    pts = [p for g in m.groups.values() for p in g]
    assert min(p[0] for p in pts) == pytest.approx(-L / 2, abs=0.01)
    assert max(p[2] for p in pts) == pytest.approx(L / 2, abs=0.01)
    burners = m.groups["#3b3b3b"]
    # Burners toward the room (+x, +z in the piece), not in the corner (-x, -z).
    assert sum(p[0] + p[2] for p in burners) / len(burners) > 0

"""Tests for the floor-plan layout in vr_geometry_service: doorways, openings, reachability."""

import pytest

from app.services import vr_geometry_service as geo


def room(name, length=12, width=12, connects_to=None):
    r = {"name": name, "dimensions": {"length": length, "width": width, "height": 9}}
    if connects_to is not None:
        r["connects_to"] = connects_to
    return r


def house():
    # Grid, 3 wide:   Entry | Living | Kitchen
    #                 Bed 1 | Hall   | Bath
    return [
        room("Entry Foyer", 8, 12, ["Living Room"]),
        room("Living Room", 16, 12, ["Kitchen", "Hallway"]),
        room("Kitchen", 12, 12),
        room("Bedroom 1", 8, 12, ["Hallway"]),
        room("Hallway", 16, 12, ["Bathroom"]),
        room("Bathroom", 12, 12),
    ]


def interior_pairs(geometry):
    return {tuple(sorted(d["rooms"])) for d in geometry["doors"] if d["door_type"] == "interior"}


def test_requested_connections_become_doors():
    g = geo.build_geometry_from_rooms(house())
    assert interior_pairs(g) == {(1, 2), (2, 3), (2, 5), (4, 5), (5, 6)}
    rooms = {r["name"]: r for r in g["rooms"]}
    assert sorted(rooms["Hallway"]["connects_to"]) == [2, 4, 6]


def test_front_door_on_entry_street_wall_and_spawn_in_front():
    g = geo.build_geometry_from_rooms(house())
    front = [d for d in g["doors"] if d["door_type"] == "exterior"]
    assert len(front) == 1
    entry = g["rooms"][0]["bounds"]
    assert front[0]["position"]["z"] == pytest.approx(entry["z0"])
    assert front[0]["rotation"] == 0
    assert g["spawn_position"]["x"] == pytest.approx(front[0]["position"]["x"])


def test_non_adjacent_request_is_skipped():
    rooms = house()
    rooms[0]["connects_to"] = ["Living Room", "Bathroom"]  # Entry and Bathroom don't touch
    g = geo.build_geometry_from_rooms(rooms)
    assert (1, 6) not in interior_pairs(g)


def test_every_room_reachable_without_connects_to():
    rooms = [room(f"Room {i}") for i in range(7)]
    g = geo.build_geometry_from_rooms(rooms)
    pairs = interior_pairs(g)
    seen, stack = {1}, [1]
    while stack:
        cur = stack.pop()
        for a, b in pairs:
            nxt = b if a == cur else a if b == cur else None
            if nxt and nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    assert seen == set(range(1, 8))
    assert len(pairs) == 6  # a spanning tree, not a door on every wall


def test_unmatched_connects_to_prefers_circulation_room():
    rooms = house()
    rooms[3]["connects_to"] = []  # Bedroom 1 touches Entry (front) and Hallway (east)
    g = geo.build_geometry_from_rooms(rooms)
    bedroom_doors = {p for p in interior_pairs(g) if 4 in p}
    assert bedroom_doors in ({(4, 5)}, {(1, 4)})


def test_no_door_to_removes_an_automatically_added_door():
    rooms = house()
    rooms[1]["connects_to"] = ["Hallway"]  # Kitchen is no longer requested from anywhere
    assert (2, 3) in interior_pairs(geo.build_geometry_from_rooms(rooms))  # added for reachability
    rooms[1]["no_door_to"] = ["Kitchen"]
    g = geo.build_geometry_from_rooms(rooms)
    pairs = interior_pairs(g)
    assert (2, 3) not in pairs
    assert (3, 6) in pairs  # reached through the bathroom instead
    assert g["notes"] == []


def test_no_door_to_beats_connects_to():
    rooms = house()
    rooms[2]["no_door_to"] = "Living Room"  # a lone name; Living Room still lists Kitchen
    assert (2, 3) not in interior_pairs(geo.build_geometry_from_rooms(rooms))


def test_no_door_to_keeps_the_only_way_in_and_says_so():
    rooms = house()
    rooms[1]["connects_to"] = ["Hallway"]
    rooms[2]["no_door_to"] = ["Living Room", "Bathroom"]  # both of the kitchen's neighbours
    g = geo.build_geometry_from_rooms(rooms)
    assert any(3 in p for p in interior_pairs(g))
    assert any("Kitchen" in n and "only way" in n for n in g["notes"])


def _side_x_or_z(room_out, opening):
    """Which side of a built room an opening (door/window) sits on."""
    b, p = room_out["bounds"], opening["position"]
    if opening["rotation"] == 0:
        return "front" if abs(p["z"] - b["z0"]) < 1e-3 else "back" if abs(p["z"] - b["z1"]) < 1e-3 else None
    return "left" if abs(p["x"] - b["x0"]) < 1e-3 else "right" if abs(p["x"] - b["x1"]) < 1e-3 else None


def test_solid_wall_moves_the_doorway_off_it():
    rooms = house()
    rooms[2]["solid_walls"] = ["left"]  # Kitchen's wall to the Living Room
    g = geo.build_geometry_from_rooms(rooms)
    pairs = interior_pairs(g)
    assert (2, 3) not in pairs
    assert (3, 6) in pairs  # through the bathroom instead
    assert g["rooms"][2]["solid_walls"] == ["left"]
    assert g["notes"] == []


def test_solid_walls_get_no_windows_or_outside_doors():
    rooms = house()
    rooms[2]["solid_walls"] = ["front", "right wall"]  # both of the kitchen's outside walls
    rooms[2]["outside_doors"] = [{"side": "right", "style": "sliding_glass"}]
    g = geo.build_geometry_from_rooms(rooms)
    assert not [w for w in g["windows"] if w["room"] == 3]
    assert not [d for d in g["doors"] if d["door_type"] == "patio"]
    assert any("kept solid" in n for n in g["notes"])


def test_front_door_avoids_a_solid_wall():
    rooms = house()
    rooms[0]["solid_walls"] = "front"
    g = geo.build_geometry_from_rooms(rooms)
    front = next(d for d in g["doors"] if d["door_type"] == "exterior")
    assert _side_x_or_z(g["rooms"][0], front) == "left"
    assert g["notes"] == []


def test_window_can_be_removed_or_put_on_a_side():
    rooms = house()
    rooms[1]["window"] = False  # Living Room
    rooms[2]["window"] = {"side": "right"}  # Kitchen
    g = geo.build_geometry_from_rooms(rooms)
    assert not [w for w in g["windows"] if w["room"] == 2]
    kitchen_windows = [w for w in g["windows"] if w["room"] == 3]
    assert [_side_x_or_z(g["rooms"][2], w) for w in kitchen_windows] == ["right"]


def test_kitchen_keeps_its_last_clean_wall_for_counters():
    rooms = house()
    # Doorways on the left (Living Room) and back (Bathroom), a sliding door on the
    # right: only the front wall is left clean, so it gets no window.
    rooms[2]["connects_to"] = ["Bathroom"]
    rooms[2]["outside_doors"] = [{"side": "right", "style": "sliding_glass"}]
    g = geo.build_geometry_from_rooms(rooms)
    assert not [w for w in g["windows"] if w["room"] == 3]
    rooms[2]["name"] = "Den"  # any other room does get one
    rooms[1]["connects_to"] = ["Den", "Hallway"]
    g = geo.build_geometry_from_rooms(rooms)
    assert [_side_x_or_z(g["rooms"][2], w) for w in g["windows"] if w["room"] == 3] == ["front"]


def test_open_to_removes_the_wall_between_rooms():
    rooms = house()
    rooms[1]["connects_to"] = ["Hallway"]
    rooms[1]["open_to"] = ["Kitchen"]
    g = geo.build_geometry_from_rooms(rooms)
    assert not [p for p in interior_pairs(g) if 3 in p]  # joined without a door
    assert [o["rooms"] for o in g["open_walls"]] == [[2, 3]]
    assert g["rooms"][1]["open_to"] == [3] and g["rooms"][2]["open_to"] == [2]
    x = g["rooms"][2]["bounds"]["x0"]  # the shared wall
    z0, z1 = g["rooms"][2]["bounds"]["z0"], g["rooms"][2]["bounds"]["z1"]
    for room_out in (g["rooms"][1], g["rooms"][2]):
        for w in room_out["walls"]:
            on_line = abs(w["start"]["x"] - x) < 1e-3 and abs(w["end"]["x"] - x) < 1e-3
            lo, hi = sorted((w["start"]["z"], w["end"]["z"]))
            assert not (on_line and w["start"]["y"] == 0 and hi > z0 + 0.2 and lo < z1 - 0.2)


def test_open_to_a_room_that_does_not_touch_is_reported():
    rooms = house()
    rooms[0]["open_to"] = ["Bathroom"]
    g = geo.build_geometry_from_rooms(rooms)
    assert g["open_walls"] == []
    assert any("don't share a wall" in n for n in g["notes"])


def test_walls_have_a_hole_at_each_door_on_both_sides():
    g = geo.build_geometry_from_rooms(house())
    door = next(d for d in g["doors"] if sorted(d["rooms"]) == [1, 2])
    x, z = door["position"]["x"], door["position"]["z"]
    for room_out in (g["rooms"][0], g["rooms"][1]):
        for w in room_out["walls"]:
            if w["start"]["y"] > 0:  # header above the door
                continue
            if abs(w["start"]["x"] - x) < 1e-3 and abs(w["end"]["x"] - x) < 1e-3:
                lo, hi = sorted((w["start"]["z"], w["end"]["z"]))
                assert not (lo < z < hi), f"{room_out['name']} wall blocks the doorway"


def test_door_header_fills_wall_above_opening():
    g = geo.build_geometry_from_rooms(house())
    headers = [w for r in g["rooms"] for w in r["walls"] if w["start"]["y"] == pytest.approx(geo.DOOR_H)]
    assert headers
    for h in headers:
        assert h["start"]["y"] + h["height"] == pytest.approx(9 * geo.FT_TO_M, abs=1e-3)


def test_windows_only_on_exterior_walls_and_not_in_hallway():
    g = geo.build_geometry_from_rooms(house())
    hallway_id = next(r["id"] for r in g["rooms"] if r["name"] == "Hallway")
    assert all(w["room"] != hallway_id for w in g["windows"])
    bath = next(w for w in g["windows"] if g["rooms"][w["room"] - 1]["name"] == "Bathroom")
    assert bath["width"] == geo.SMALL_WINDOW_W
    for w in g["windows"]:
        p = w["position"]
        for r in g["rooms"]:
            b = r["bounds"]
            strictly_inside = b["x0"] + 1e-3 < p["x"] < b["x1"] - 1e-3 and b["z0"] + 1e-3 < p["z"] < b["z1"] - 1e-3
            assert not strictly_inside
        # Not on a wall two rooms share.
        touching = [
            r for r in g["rooms"]
            if r["bounds"]["x0"] - 1e-3 <= p["x"] <= r["bounds"]["x1"] + 1e-3
            and r["bounds"]["z0"] - 1e-3 <= p["z"] <= r["bounds"]["z1"] + 1e-3
        ]
        assert len(touching) == 1


def test_empty_house():
    g = geo.build_geometry_from_rooms([])
    assert g["rooms"] == [] and g["doors"] == [] and g["windows"] == []


# --- Nested-split layout -------------------------------------------------------

def ranch_layout():
    # 48 x 32 ft: front zone | full-length hallway | back zone.
    return {
        "length": 48, "width": 32, "entry": "Entry Foyer", "split": "z",
        "parts": [
            {"size": 14, "split": "x", "parts": [
                {"size": 10, "room": "Entry Foyer"},
                {"size": 22, "room": "Living Room"},
                {"size": 16, "room": "Kitchen"},
            ]},
            {"size": 4, "room": "Hallway"},
            {"size": 14, "split": "x", "parts": [
                {"size": 14, "room": "Primary Bedroom"},
                {"size": 8, "room": "Bathroom"},
                {"size": 12, "room": "Bedroom 2"},
                {"size": 14, "room": "Bedroom 3"},
            ]},
        ],
    }


def ranch_rooms():
    return [
        room("Entry Foyer", connects_to=["Living Room"]),
        room("Living Room", connects_to=["Kitchen", "Hallway"]),
        room("Kitchen"),
        room("Hallway", connects_to=["Primary Bedroom", "Bathroom", "Bedroom 2", "Bedroom 3"]),
        room("Primary Bedroom"),
        room("Bathroom"),
        room("Bedroom 2"),
        room("Bedroom 3"),
    ]


def by_name(g):
    return {r["name"]: r for r in g["rooms"]}


def test_split_layout_tiles_the_footprint_exactly():
    g = geo.build_geometry_from_rooms(ranch_rooms(), layout=ranch_layout())
    assert g["metadata"]["layout"] == "split"
    area = sum(
        (r["bounds"]["x1"] - r["bounds"]["x0"]) * (r["bounds"]["z1"] - r["bounds"]["z0"])
        for r in g["rooms"]
    )
    assert area == pytest.approx(48 * 32 * geo.FT_TO_M ** 2, rel=1e-3)
    hall = by_name(g)["Hallway"]["bounds"]
    assert hall["x0"] == pytest.approx(0) and hall["x1"] == pytest.approx(48 * geo.FT_TO_M, abs=1e-3)
    assert hall["z1"] - hall["z0"] == pytest.approx(4 * geo.FT_TO_M, abs=1e-3)


def test_split_layout_uses_tree_sizes_and_room_heights():
    rooms = ranch_rooms()
    rooms[1]["dimensions"]["height"] = 10
    g = geo.build_geometry_from_rooms(rooms, layout=ranch_layout())
    living = by_name(g)["Living Room"]
    assert living["dimensions"]["length"] == pytest.approx(22 * geo.FT_TO_M, abs=1e-3)
    assert living["dimensions"]["width"] == pytest.approx(14 * geo.FT_TO_M, abs=1e-3)
    assert living["dimensions"]["height"] == pytest.approx(10 * geo.FT_TO_M, abs=1e-3)


def test_split_layout_doors_follow_connects_to():
    g = geo.build_geometry_from_rooms(ranch_rooms(), layout=ranch_layout())
    ids = {r["name"]: r["id"] for r in g["rooms"]}
    expected = {
        tuple(sorted((ids[a], ids[b]))) for a, b in [
            ("Entry Foyer", "Living Room"), ("Living Room", "Kitchen"), ("Living Room", "Hallway"),
            ("Hallway", "Primary Bedroom"), ("Hallway", "Bathroom"),
            ("Hallway", "Bedroom 2"), ("Hallway", "Bedroom 3"),
        ]
    }
    assert interior_pairs(g) == expected


def test_split_layout_entry_is_room_one_with_front_door_and_spawn_outside():
    g = geo.build_geometry_from_rooms(ranch_rooms(), layout=ranch_layout())
    assert g["rooms"][0]["name"] == "Entry Foyer"
    front = next(d for d in g["doors"] if d["door_type"] == "exterior")
    assert front["position"]["z"] == pytest.approx(0)
    assert g["spawn_position"]["z"] == pytest.approx(-3.0)
    assert g["spawn_position"]["x"] == pytest.approx(front["position"]["x"])


def test_entry_on_side_gets_side_door_and_spawn_outside_that_side():
    layout = {"length": 30, "width": 30, "entry": "Mudroom", "split": "x", "parts": [
        {"size": 20, "split": "z", "parts": [
            {"size": 15, "room": "Living Room"}, {"size": 15, "room": "Bedroom"}]},
        {"size": 10, "split": "z", "parts": [
            {"size": 15, "room": "Kitchen"}, {"size": 15, "room": "Mudroom"}]},
    ]}
    g = geo.build_geometry_from_rooms([], layout=layout)
    assert g["rooms"][0]["name"] == "Mudroom"
    front = next(d for d in g["doors"] if d["door_type"] == "exterior")
    assert front["rotation"] == 90 and front["position"]["x"] == pytest.approx(30 * geo.FT_TO_M, abs=1e-3)
    assert g["spawn_position"]["x"] == pytest.approx(front["position"]["x"] + 3.0)


def test_part_sizes_are_rescaled_to_fill_parent():
    layout = {"length": 40, "width": 12, "split": "x", "parts": [
        {"size": 1, "room": "Living Room"}, {"size": 1, "room": "Kitchen"}]}
    g = geo.build_geometry_from_rooms([], layout=layout)
    for r in g["rooms"]:
        assert r["dimensions"]["length"] == pytest.approx(20 * geo.FT_TO_M, abs=1e-3)


def test_tiny_parts_get_minimum_size():
    layout = {"length": 30, "width": 12, "split": "x", "parts": [
        {"size": 29, "room": "Living Room"}, {"size": 0.5, "room": "Closet"}]}
    g = geo.build_geometry_from_rooms([], layout=layout)
    assert by_name(g)["Closet"]["dimensions"]["length"] == pytest.approx(geo.MIN_PART, abs=1e-3)
    total = sum(r["dimensions"]["length"] for r in g["rooms"])
    assert total == pytest.approx(30 * geo.FT_TO_M, abs=1e-3)


@pytest.mark.parametrize("layout", [
    {"length": 0, "width": 30, "split": "x", "parts": [{"room": "A"}]},
    {"width": 30, "split": "x", "parts": [{"room": "A"}]},
    {"length": 30, "width": 30, "split": "diagonal", "parts": [{"room": "A"}]},
    {"length": 30, "width": 30, "split": "x", "parts": []},
    {"length": 30, "width": 30, "split": "x", "parts": [{"room": "A"}, {"room": "a"}]},
    {"length": 3, "width": 30, "split": "x", "parts": [{"room": "A"}, {"room": "B"}, {"room": "C"}]},
    {"length": 30, "width": 30, "split": "x", "parts": [{"open": True}, {"open": True}]},
    "not a layout",
])
def test_bad_layout_falls_back_to_grid(layout):
    g = geo.build_geometry_from_rooms(house(), layout=layout)
    assert g["metadata"]["layout"] == "grid"
    assert len(g["rooms"]) == 6


def test_rooms_missing_from_layout_are_dropped():
    rooms = ranch_rooms() + [room("Sunroom")]
    g = geo.build_geometry_from_rooms(rooms, layout=ranch_layout())
    assert "Sunroom" not in by_name(g)
    assert len(g["rooms"]) == 8


def l_shape_layout():
    # Street side at the top of this sketch:
    #   Living Room | (open)
    #   Kitchen     | Bedroom
    return {"length": 40, "width": 30, "entry": "Living Room", "split": "z", "parts": [
        {"size": 15, "split": "x", "parts": [
            {"size": 20, "room": "Living Room"}, {"size": 20, "open": True}]},
        {"size": 15, "split": "x", "parts": [
            {"size": 20, "room": "Kitchen"}, {"size": 20, "room": "Bedroom"}]},
    ]}


def test_open_part_leaves_a_notch_in_the_house():
    g = geo.build_geometry_from_rooms([], layout=l_shape_layout())
    assert g["metadata"]["layout"] == "split"
    assert sorted(by_name(g)) == ["Bedroom", "Kitchen", "Living Room"]
    ft = geo.FT_TO_M
    assert g["open_areas"] == [{"bounds": pytest.approx(
        {"x0": 20 * ft, "x1": 40 * ft, "z0": 0.0, "z1": 15 * ft}, abs=1e-3)}]
    area = sum(
        (r["bounds"]["x1"] - r["bounds"]["x0"]) * (r["bounds"]["z1"] - r["bounds"]["z0"])
        for r in g["rooms"]
    )
    assert area == pytest.approx(3 * 20 * 15 * ft ** 2, rel=1e-3)


def test_walls_facing_an_open_part_are_exterior():
    g = geo.build_geometry_from_rooms([], layout=l_shape_layout())
    rooms = by_name(g)
    rects = [r["bounds"] for r in g["rooms"]]
    shared = geo.find_shared_walls(rects)
    # Living Room's east side and Bedroom's front side face the yard.
    living_east = geo._room_sides(rooms["Living Room"]["bounds"])[1]
    bedroom_front = geo._room_sides(rooms["Bedroom"]["bounds"])[0]
    assert geo.exterior_intervals(living_east, shared) == [pytest.approx(living_east[2:])]
    assert geo.exterior_intervals(bedroom_front, shared) == [pytest.approx(bedroom_front[2:])]
    # The bedroom gets its window on that wall: it is the longest outside stretch it has.
    window = next(w for w in g["windows"] if w["room"] == rooms["Bedroom"]["id"])
    assert window["position"]["z"] == pytest.approx(15 * geo.FT_TO_M, abs=1e-3)


def test_open_parts_are_not_rooms_in_the_tree():
    rooms = geo.layout_rects_from_tree(l_shape_layout())
    assert [n for n, _ in rooms] == ["Living Room", "Kitchen", "Bedroom"]
    assert len(geo.layout_open_rects(l_shape_layout())) == 1


def test_rectangular_house_has_no_open_areas():
    g = geo.build_geometry_from_rooms(ranch_rooms(), layout=ranch_layout())
    assert g["open_areas"] == []


def test_spawn_stays_out_of_the_room_across_a_courtyard():
    # Front door facing +x at x = 0, another room 4 m away across an open area.
    rects = [{"x0": 4.0, "x1": 8.0, "z0": -2.0, "z1": 2.0}]
    assert geo._spawn_distance(0.0, 0.0, 1, 0, rects) == pytest.approx(2.0)
    # Nothing across: the usual distance.
    assert geo._spawn_distance(0.0, 0.0, -1, 0, rects) == pytest.approx(geo.SPAWN_DISTANCE)
    assert geo._spawn_distance(0.0, 5.0, 1, 0, rects) == pytest.approx(geo.SPAWN_DISTANCE)


def bay_house(bay):
    # Living Room (entry) | Kitchen, both 20 x 14 ft, street side in front.
    layout = {"length": 40, "width": 14, "entry": "Living Room", "split": "x", "parts": [
        {"size": 20, "room": "Living Room"}, {"size": 20, "room": "Kitchen"}]}
    rooms = [
        {"name": "Living Room", "dimensions": {"height": 9}, "connects_to": ["Kitchen"], "bay_window": bay},
        {"name": "Kitchen", "dimensions": {"height": 9}},
    ]
    return geo.build_geometry_from_rooms(rooms, layout=layout)


def test_angled_bay_window_has_three_glazed_faces():
    g = bay_house({"side": "back", "width": 8, "depth": 2.5})
    living = by_name(g)["Living Room"]
    bay = living["bay_window"]
    assert bay["style"] == "angled" and bay["side"] == "back"
    assert bay["width"] == pytest.approx(8 * geo.FT_TO_M, abs=1e-3)
    assert bay["depth"] == pytest.approx(2.5 * geo.FT_TO_M, abs=1e-3)
    back = 14 * geo.FT_TO_M
    assert [p["z"] for p in bay["outline"]] == pytest.approx([back, back + bay["depth"], back + bay["depth"], back])
    glass = [w for w in g["windows"] if w["room"] == living["id"]]
    assert all(w["bay"] for w in glass)  # replaces the room's ordinary window
    assert sorted(w["rotation"] for w in glass) == [-45, 0, 45]
    # Its own floor and ceiling slabs reach past the back wall.
    assert bay["floor"]["vertices"][2]["z"] > back + bay["depth"]
    assert bay["ceiling"]["vertices"][0]["y"] == pytest.approx(living["dimensions"]["height"])


def test_bay_window_opens_up_the_room_wall():
    g = bay_house({"side": "back", "style": "box"})
    living = by_name(g)["Living Room"]
    outline = living["bay_window"]["outline"]
    lo, hi = outline[0]["x"], outline[-1]["x"]
    back = living["bounds"]["z1"]
    on_back_wall = [
        w for w in living["walls"]
        if w["start"]["z"] == pytest.approx(back) and w["end"]["z"] == pytest.approx(back)
    ]
    for w in on_back_wall:
        a, b = sorted((w["start"]["x"], w["end"]["x"]))
        assert b <= lo + 1e-3 or a >= hi - 1e-3, "a wall piece still crosses the bay opening"
    # Box bay: side faces run straight out, front parallel to the wall.
    assert outline[1]["x"] == pytest.approx(lo) and outline[2]["x"] == pytest.approx(hi)


def test_bay_window_keeps_clear_of_the_front_door():
    g = bay_house({"side": "front", "width": 16})
    door = next(d for d in g["doors"] if d["door_type"] == "exterior")
    outline = by_name(g)["Living Room"]["bay_window"]["outline"]
    lo, hi = outline[0]["x"], outline[-1]["x"]
    door_lo, door_hi = door["position"]["x"] - geo.DOOR_W / 2, door["position"]["x"] + geo.DOOR_W / 2
    assert door_hi <= lo or door_lo >= hi
    assert hi - lo < 16 * geo.FT_TO_M  # shrank to fit beside the door


def test_bay_window_on_an_inside_wall_is_skipped():
    g = bay_house({"side": "right"})  # the Living Room's right side is the Kitchen
    living = by_name(g)["Living Room"]
    assert living["bay_window"] is None
    assert any(w["room"] == living["id"] and not w.get("bay") for w in g["windows"])


def test_bay_window_stops_short_of_a_room_across_a_courtyard():
    layout = {"length": 30, "width": 30, "entry": "Den", "split": "z", "parts": [
        {"size": 12, "room": "Den"},
        {"size": 6, "open": True},
        {"size": 12, "room": "Studio"},
    ]}
    rooms = [{"name": "Den", "bay_window": {"side": "back", "depth": 6}}, {"name": "Studio"}]
    g = geo.build_geometry_from_rooms(rooms, layout=layout)
    depth = by_name(g)["Den"]["bay_window"]["depth"]
    assert depth < 3 * geo.FT_TO_M  # at most half the 6 ft courtyard


@pytest.mark.parametrize("raw, expected", [
    (True, ("front", "angled")),
    ({"side": "Rear", "style": "BOX"}, ("back", "box")),
    ({"side": "diagonal"}, None),
    ("yes", None),
    (None, None),
])
def test_bay_spec_parsing(raw, expected):
    spec = geo.bay_spec({"bay_window": raw})
    assert (spec and (spec["side"], spec["style"])) == expected


def test_deep_angled_bay_steepens_its_sides_instead_of_turning_into_a_box():
    g = bay_house({"side": "back", "width": 8, "depth": 5})
    bay = by_name(g)["Living Room"]["bay_window"]
    assert bay["style"] == "angled"
    lo, front_lo, front_hi, hi = (p["x"] for p in bay["outline"])
    assert front_hi - front_lo == pytest.approx(geo.BAY_MIN_W / 2, abs=1e-3)
    inset = front_lo - lo
    assert inset < bay["depth"]  # steeper than 45°
    living = by_name(g)["Living Room"]["id"]
    rotations = sorted(abs(w["rotation"]) for w in g["windows"] if w["room"] == living)
    assert rotations[0] == 0 and 45 < rotations[1] < 90


# Doors to the yard ("outside_doors")

def door_house(kitchen_doors, kitchen_extra=None):
    # Living Room (entry) | Kitchen, both 20 x 14 ft, street side in front.
    layout = {"length": 40, "width": 14, "entry": "Living Room", "split": "x", "parts": [
        {"size": 20, "room": "Living Room"}, {"size": 20, "room": "Kitchen"}]}
    rooms = [
        {"name": "Living Room", "dimensions": {"height": 9}, "connects_to": ["Kitchen"]},
        {"name": "Kitchen", "dimensions": {"height": 9}, "outside_doors": kitchen_doors, **(kitchen_extra or {})},
    ]
    return geo.build_geometry_from_rooms(rooms, layout=layout)


def test_sliding_glass_door_to_the_back_yard():
    g = door_house([{"side": "back", "style": "sliding glass", "width": 6}])
    kitchen = by_name(g)["Kitchen"]
    patio = [d for d in g["doors"] if d["door_type"] == "patio"]
    assert len(patio) == 1
    door = patio[0]
    assert door["style"] == "sliding_glass" and door["side"] == "back"
    assert door["rooms"] == [kitchen["id"]]
    assert door["width"] == pytest.approx(6 * geo.FT_TO_M, abs=1e-3)
    assert door["position"]["z"] == pytest.approx(kitchen["bounds"]["z1"])
    assert door["rotation"] == 0
    # The front door is still the only "exterior" door, and nothing was skipped.
    assert [d["door_type"] for d in g["doors"]].count("exterior") == 1
    assert g["notes"] == []


def test_outside_door_cuts_a_hole_in_the_wall():
    g = door_house([{"side": "back", "style": "sliding_glass", "width": 6}])
    kitchen = by_name(g)["Kitchen"]
    door = next(d for d in g["doors"] if d["door_type"] == "patio")
    lo = door["position"]["x"] - door["width"] / 2
    hi = door["position"]["x"] + door["width"] / 2
    back = kitchen["bounds"]["z1"]
    for w in kitchen["walls"]:
        if w["start"]["z"] == pytest.approx(back) and w["end"]["z"] == pytest.approx(back):
            a, b = sorted((w["start"]["x"], w["end"]["x"]))
            crosses = a < hi - 1e-3 and b > lo + 1e-3
            assert not crosses or w["start"]["y"] >= geo.DOOR_H - 1e-3, "wall left standing in the doorway"


def test_window_keeps_clear_of_an_outside_door():
    g = door_house([{"side": "back", "style": "french"}])
    door = next(d for d in g["doors"] if d["door_type"] == "patio")
    kitchen = by_name(g)["Kitchen"]
    for w in g["windows"]:
        if w["room"] == kitchen["id"] and w["position"]["z"] == pytest.approx(door["position"]["z"]):
            gap = abs(w["position"]["x"] - door["position"]["x"])
            assert gap >= (w["width"] + door["width"]) / 2


def test_bay_window_keeps_clear_of_an_outside_door():
    g = door_house(
        [{"side": "back", "style": "sliding_glass", "width": 8}],
        {"bay_window": {"side": "back", "width": 6, "style": "box"}},
    )
    door = next(d for d in g["doors"] if d["door_type"] == "patio")
    bay = by_name(g)["Kitchen"]["bay_window"]
    if bay is not None:
        lo, hi = bay["outline"][0]["x"], bay["outline"][-1]["x"]
        d_lo = door["position"]["x"] - door["width"] / 2
        d_hi = door["position"]["x"] + door["width"] / 2
        assert d_hi <= min(lo, hi) or d_lo >= max(lo, hi)


def test_outside_door_on_an_inside_wall_is_skipped_with_a_note():
    g = door_house([{"side": "left", "style": "sliding_glass"}])  # the Kitchen's left is the Living Room
    assert not [d for d in g["doors"] if d["door_type"] == "patio"]
    assert g["notes"] == ["Kitchen has no left outside wall for a sliding glass door"]


def test_outside_door_shrinks_to_fit_its_wall():
    g = door_house([{"side": "right", "style": "sliding_glass", "width": 40}])  # 14 ft wall
    door = next(d for d in g["doors"] if d["door_type"] == "patio")
    assert door["width"] <= 14 * geo.FT_TO_M - 2 * geo.EDGE_MARGIN + 1e-3
    assert door["rotation"] == 90


def test_skipped_bay_window_is_noted():
    g = bay_house({"side": "right"})
    assert g["notes"] == ["Living Room has no room for a right bay window"]


@pytest.mark.parametrize("raw, expected", [
    ({"side": "rear", "style": "Sliding Glass Door"}, [("back", "sliding_glass", 6.0)]),
    ([{"side": "backyard", "style": "double french doors", "width": 6}], [("back", "french", 6.0)]),
    ("left", [("left", "hinged", 3.0)]),
    ([{"side": "up"}], []),
    (None, []),
    ([{"side": "back", "width": 1}], [("back", "hinged", 3.0)]),  # never narrower than a door
])
def test_outside_door_spec_parsing(raw, expected):
    specs = geo.outside_door_specs({"outside_doors": raw})
    got = [(s["side"], s["style"], round(s["width"] / geo.FT_TO_M, 1)) for s in specs]
    assert got == expected

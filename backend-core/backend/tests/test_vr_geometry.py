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

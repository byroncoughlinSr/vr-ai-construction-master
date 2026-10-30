"""Rectangle floor plans (vr_geometry_service) and the floor-plan checker (layout_check)."""

import pytest

from app.services import vr_geometry_service as geo
from app.services.layout_check import layout_problems

FT = geo.FT_TO_M


def rect(room, x, z, length, width):
    return {"room": room, "x": x, "z": z, "length": length, "width": width}


def by_name(g):
    return {r["name"]: r for r in g["rooms"]}


def l_shape():
    # Street side at the top of this sketch:
    #   Living Room | (yard)
    #   Kitchen     | Bedroom
    return {"entry": "Living Room", "rects": [
        rect("Living Room", 0, 0, 20, 15),
        rect("Kitchen", 0, 15, 20, 15),
        rect("Bedroom", 20, 15, 20, 15),
    ]}


def test_rect_layout_puts_rooms_where_it_says():
    g = geo.build_geometry_from_rooms([], layout=l_shape())
    assert g["metadata"]["layout"] == "rects"
    bedroom = by_name(g)["Bedroom"]["bounds"]
    assert bedroom == pytest.approx({"x0": 20 * FT, "x1": 40 * FT, "z0": 15 * FT, "z1": 30 * FT}, abs=1e-3)
    assert g["rooms"][0]["name"] == "Living Room"  # the entry is room 1


def test_rect_layout_leaves_the_uncovered_corner_outdoors():
    g = geo.build_geometry_from_rooms([], layout=l_shape())
    assert g["open_areas"] == [{"bounds": pytest.approx(
        {"x0": 20 * FT, "x1": 40 * FT, "z0": 0.0, "z1": 15 * FT}, abs=1e-3)}]


def test_rect_layout_builds_the_same_house_as_the_tree():
    tree = {"length": 40, "width": 30, "entry": "Living Room", "split": "z", "parts": [
        {"size": 15, "split": "x", "parts": [{"size": 20, "room": "Living Room"}, {"size": 20, "open": True}]},
        {"size": 15, "split": "x", "parts": [{"size": 20, "room": "Kitchen"}, {"size": 20, "room": "Bedroom"}]},
    ]}
    a = geo.build_geometry_from_rooms([], layout=tree)
    b = geo.build_geometry_from_rooms([], layout=l_shape())
    assert [r["bounds"] for r in a["rooms"]] == pytest.approx([r["bounds"] for r in b["rooms"]])
    assert len(a["doors"]) == len(b["doors"]) and len(a["windows"]) == len(b["windows"])


def test_nearly_touching_edges_are_snapped_together():
    layout = {"entry": "A", "rects": [rect("A", 0, 0, 10, 12), rect("B", 10.2, 0, 10, 12)]}
    entries = geo.rect_entries(layout)
    assert entries[1]["x0"] == entries[0]["x1"] == 10
    assert geo.find_shared_walls([r for _, r in geo.layout_rects_from_tree(layout)])


def test_plan_is_shifted_to_start_at_the_street():
    layout = {"rects": [rect("A", 5, 3, 10, 12)]}
    assert geo.rect_entries(layout)[0] == {"room": "A", "x0": 0, "x1": 10, "z0": 0, "z1": 12}


@pytest.mark.parametrize("layout", [
    {"rects": []},
    {"rects": [rect("A", 0, 0, 0, 10)]},
    {"rects": [{"room": "A", "x": 0, "z": 0, "length": "big", "width": 10}]},
    {"rects": [rect("A", 0, 0, 10, 10), rect("a", 10, 0, 10, 10)]},
    {"rects": [rect("A", 0, 0, 10, 10), rect("B", 5, 5, 10, 10)]},
])
def test_unbuildable_rect_layout_falls_back_to_grid(layout):
    g = geo.build_geometry_from_rooms([{"name": "A"}, {"name": "B"}], layout=layout)
    assert g["metadata"]["layout"] == "grid"


def test_tree_converts_to_rects_whose_neighbours_still_meet():
    tree = {"length": 40, "width": 45, "split": "z", "parts": [
        {"size": 5.5, "room": "Entry"}, {"size": 13.5, "room": "Living"}, {"size": 26, "room": "Garage"}]}
    rects = geo.layout_as_rects(tree)["rects"]
    for a, b in zip(rects, rects[1:]):
        assert a["z"] + a["width"] == pytest.approx(b["z"])
    assert sum(r["width"] for r in rects) == pytest.approx(45)


def test_a_doorway_fits_at_the_end_of_a_4_5_ft_hallway():
    layout = {"entry": "Hallway", "rects": [rect("Hallway", 0, 0, 4.5, 20), rect("Laundry", 0, 20, 6, 7)]}
    rooms = [{"name": "Hallway", "connects_to": ["Laundry"]}, {"name": "Laundry"}]
    g = geo.build_geometry_from_rooms(rooms, layout=layout)
    assert any(d["door_type"] == "interior" for d in g["doors"])
    assert layout_problems({"layout": layout, "rooms": rooms}) == []


def test_a_3_ft_toilet_room_fits_in_a_split():
    tree = {"length": 7.5, "width": 6, "split": "x", "parts": [
        {"size": 3, "room": "Toilet Room"}, {"size": 4.5, "room": "Shower"}]}
    toilet = dict(geo.layout_rects_from_tree(tree))["Toilet Room"]
    assert toilet["x1"] - toilet["x0"] == pytest.approx(3 * FT, abs=1e-3)


# --- layout_check -------------------------------------------------------------

def test_a_good_plan_has_no_problems():
    rooms = [{"name": "Living Room", "connects_to": ["Kitchen"]}, {"name": "Kitchen"}, {"name": "Bedroom"}]
    assert layout_problems({"layout": l_shape(), "rooms": rooms}) == []


def test_overlapping_rooms_are_reported_with_the_overlap():
    layout = {"rects": [rect("Office", 0, 0, 10, 12.5), rect("Hallway", 0, 11.5, 30, 4.5)]}
    assert layout_problems({"layout": layout, "rooms": []}) == ["Office and Hallway overlap by 10.0 x 1.0 ft"]


def test_a_sliver_between_rooms_is_reported():
    layout = {"rects": [rect("A", 0, 0, 10, 12), rect("B", 11, 0, 10, 12)]}
    problems = layout_problems({"layout": layout, "rooms": []})
    assert len(problems) == 1 and problems[0].startswith("A 1.0 x 12.0 ft gap is left between rooms")


def test_doorway_between_rooms_that_dont_touch_is_reported():
    rooms = [{"name": "Living Room", "connects_to": ["Bedroom"]}, {"name": "Kitchen"}, {"name": "Bedroom"}]
    problems = layout_problems({"layout": l_shape(), "rooms": rooms})
    assert problems == ["Living Room and Bedroom don't touch, so there can't be a doorway between them"]


def test_room_left_out_of_the_layout_is_reported():
    rooms = [{"name": "Living Room"}, {"name": "Kitchen"}, {"name": "Bedroom"}, {"name": "Office"}]
    problems = layout_problems({"layout": l_shape(), "rooms": rooms})
    assert problems == ["In the room list but not in the layout (left out of the house): Office"]


def test_tree_whose_parts_dont_add_up_and_squash_the_rooms():
    # The shape of the first plan Groq drew for the 14-room house: strips adding up
    # to 59.5 ft in a 45 ft deep footprint.
    tree = {"length": 40, "width": 45, "entry": "Entry Foyer", "split": "z", "parts": [
        {"size": 5.5, "room": "Entry Foyer"}, {"size": 13.5, "room": "Living Room"},
        {"size": 40.5, "room": "Garage"}]}
    rooms = [{"name": "Entry Foyer", "dimensions": {"length": 5.5, "width": 16}},
             {"name": "Living Room"}, {"name": "Garage"}]
    problems = layout_problems({"layout": tree, "rooms": rooms})
    assert problems[0].startswith("The parts holding Entry Foyer, Living Room, Garage add up to 59.5 ft front to back")
    assert "Entry Foyer is 4.2 x 40 ft in the layout but 5.5 x 16 ft in the room list" in problems


def test_unbuildable_layout_is_one_problem():
    problems = layout_problems({"layout": {"rects": [rect("A", 0, 0, -1, 4)]}, "rooms": []})
    assert problems == ["The layout can't be built: A's rectangle must have a positive length and width"]


def test_layout_problems_show_with_the_house():
    rooms = [{"name": "Living Room"}, {"name": "Kitchen"}, {"name": "Bedroom"}, {"name": "Office"}]
    layout = {**l_shape(), "notes": ["Kitchen made 15 ft deep to line up with the bedroom"]}
    g = geo.build_geometry_from_rooms(rooms, layout=layout)
    assert g["notes"][:2] == [
        "Kitchen made 15 ft deep to line up with the bedroom",
        "In the room list but not in the layout (left out of the house): Office",
    ]


def snout_garage():
    # The garage sticks out toward the street beside the entry:
    #   (yard)  | Garage
    #   Entry   | Garage
    return {"entry": "Entry", "rects": [rect("Garage", 10, 0, 24, 29), rect("Entry", 0, 10, 10, 19)]}


def test_a_garage_may_stick_out_in_front_of_the_entry():
    rooms = [{"name": "Entry", "connects_to": ["Garage"]}, {"name": "Garage"}]
    g = geo.build_geometry_from_rooms(rooms, layout=snout_garage())
    assert g["metadata"]["layout"] == "rects"
    front = next(d for d in g["doors"] if d["door_type"] == "exterior")
    assert front["position"]["z"] == pytest.approx(10 * FT, abs=1e-3)  # the entry's street-side wall
    assert front["position"]["x"] < 10 * FT
    assert layout_problems({"layout": snout_garage(), "rooms": rooms}) == []


def test_a_room_in_front_of_the_entry_is_reported():
    layout = {"entry": "Entry", "rects": [rect("Porch Room", 0, 0, 10, 8), rect("Entry", 0, 8, 10, 10)]}
    assert layout_problems({"layout": layout, "rooms": []}) == [
        "Porch Room is in front of the entry (Entry), between its front door and the street: "
        "move it beside the entry or make another room the entry"]

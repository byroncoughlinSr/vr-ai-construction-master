"""The outside of the house: cleaning the AI's description and building it (no network calls)."""

import math

import pytest

from app.services.example_floor_plans import EXAMPLE_STRUCTURE
from app.services.vr_exterior import (
    MAX_ITEMS,
    MAX_TILES,
    NAMED_COLORS,
    ROOF_MATERIALS,
    exterior_spec,
    roof_sections,
)
from app.services.vr_geometry_service import (
    DOOR_H,
    DOOR_W,
    FT_TO_M,
    WALL_T,
    build_geometry_from_rooms,
)

L_LAYOUT = {
    "length": 40, "width": 30, "entry": "Living", "split": "z",
    "parts": [
        {"size": 15, "split": "x", "parts": [{"size": 20, "room": "Living"}, {"size": 20, "open": True}]},
        {"size": 15, "split": "x", "parts": [{"size": 20, "room": "Kitchen"}, {"size": 20, "room": "Bedroom"}]},
    ],
}
L_ROOMS = [{"name": n, "dimensions": {"height": 9}} for n in ("Living", "Kitchen", "Bedroom")]


def _example(exterior):
    return build_geometry_from_rooms(
        EXAMPLE_STRUCTURE["rooms"], layout=EXAMPLE_STRUCTURE["layout"], exterior=exterior,
    )


def _parts(geometry, kind=None):
    return [p for p in geometry["exterior"]["parts"] if kind is None or p["kind"] == kind]


# --- Cleaning -------------------------------------------------------------------

def test_spec_understands_loose_words():
    spec = exterior_spec({
        "roof": {"style": "Hip", "material": "spanish clay tiles", "pitch": 40},
        "walls": {"material": "Stucco", "color": "warm beige"},
        "landscape": [{"type": "palm tree", "x": "4", "z": -6}, {"type": "bushes", "x": 1, "z": -2}],
    })
    assert spec["roof"] == {
        "style": "hip", "material": "clay_tile", "color": ROOF_MATERIALS["clay_tile"],
        "pitch": 12.0, "overhang": 1.5,
    }
    assert spec["walls"] == {"material": "stucco", "color": NAMED_COLORS["beige"]}
    assert [i["type"] for i in spec["landscape"]] == ["palm", "shrub"]
    assert spec["landscape"][0]["x"] == 4.0


def test_spec_keeps_hex_colors_and_drops_junk():
    spec = exterior_spec({
        "roof": {"color": "#ABC"},
        "landscape": [
            {"type": "unicorn", "x": 1, "z": 1},
            {"type": "tree"},  # nowhere
            {"type": "fence", "from": {"x": 0, "z": 0}, "to": {"x": 0, "z": 0}},  # zero length
            {"type": "tree", "x": 1e9, "z": 0},  # absurdly far
            {"type": "path", "from": [0, -20], "to": [0, 0], "width": 4},
        ],
    })
    assert spec["roof"]["color"] == "#aabbcc"
    assert spec["landscape"] == [{"type": "path", "from": {"x": 0.0, "z": -20.0}, "to": {"x": 0.0, "z": 0.0}, "width": 4.0}]


@pytest.mark.parametrize("raw", [None, {}, "tile roof", {"roof": None}, {"landscape": [{"type": "tree"}]}])
def test_spec_with_nothing_usable_is_none(raw):
    assert exterior_spec(raw) is None


def test_spec_caps_the_number_of_items():
    items = [{"type": "shrub", "x": i, "z": -3} for i in range(MAX_ITEMS + 20)]
    assert len(exterior_spec({"landscape": items})["landscape"]) == MAX_ITEMS


# --- Building ----------------------------------------------------------------------

def test_no_exterior_builds_the_house_as_before():
    assert _example(None)["exterior"] is None


@pytest.mark.parametrize("style,meshes", [("hip", 1), ("gable", 2), ("shed", 2), ("flat", 0)])
def test_each_roof_style_builds(style, meshes):
    exterior = _example({"roof": {"style": style}})["exterior"]
    assert len(exterior["roof"]) == meshes
    for mesh in exterior["roof"]:
        assert len(mesh["positions"]) % 9 == 0
        assert len(mesh["normals"]) == len(mesh["positions"])
        assert mesh["indices"] == list(range(len(mesh["positions"]) // 3))
        for k in range(0, len(mesh["normals"]), 3):
            assert math.isclose(math.hypot(*mesh["normals"][k:k + 3]), 1.0, abs_tol=1e-3)
    if style == "flat":
        assert len(_parts(_example({"roof": {"style": style}}), "roof")) == 1


def test_hip_roof_covers_the_house_with_its_overhang():
    geometry = _example({"roof": {"style": "hip", "pitch": 6, "overhang": 2}})
    pos = geometry["exterior"]["roof"][0]["positions"]
    xs, ys, zs = pos[0::3], pos[1::3], pos[2::3]
    reach = WALL_T + 2 * FT_TO_M
    assert min(xs) == pytest.approx(0 - reach, abs=1e-3)
    assert max(xs) == pytest.approx(50 * FT_TO_M + reach, abs=1e-3)
    assert min(zs) == pytest.approx(0 - reach, abs=1e-3)
    assert max(zs) == pytest.approx(36 * FT_TO_M + reach, abs=1e-3)
    # The eave sits on the tallest room (the 10 ft living room); the ridge is half
    # the roof's span above it at a 6/12 pitch.
    eave = 10 * FT_TO_M
    span = 36 * FT_TO_M + 2 * reach
    assert max(ys) == pytest.approx(eave - (reach - WALL_T) * 0.5 + span / 2 * 0.5, abs=1e-3)


def test_rectangular_house_gets_one_roof_and_an_l_shape_two():
    geometry = _example({"roof": {}})
    rects = [r["bounds"] for r in geometry["rooms"]]
    assert len(roof_sections(rects, [3.0] * len(rects))) == 1
    l_geometry = build_geometry_from_rooms(L_ROOMS, layout=L_LAYOUT)
    l_rects = [r["bounds"] for r in l_geometry["rooms"]]
    assert len(roof_sections(l_rects, [2.7] * 3)) == 2


def test_wall_finish_is_only_on_outside_walls_and_leaves_the_front_door_open():
    geometry = build_geometry_from_rooms(L_ROOMS, layout=L_LAYOUT, exterior={"walls": {"color": "beige"}})
    skins = _parts(geometry, "wall")
    assert skins
    # Kitchen and bedroom share the wall at x = 20 ft; nothing is painted on it.
    shared_x = 20 * FT_TO_M
    for p in skins:
        if p["size"]["x"] > 0.5 and abs(abs(p["yaw"]) - 90) < 1:
            assert abs(p["center"]["x"] - shared_x) > 0.05
    door = next(d for d in geometry["doors"] if d["door_type"] == "exterior")["position"]
    for p in skins:
        c, s = p["center"], p["size"]
        along_x = abs(p["yaw"]) < 1 or abs(abs(p["yaw"]) - 180) < 1
        near_door = (
            abs(c["z"] - door["z"]) < 0.3 and abs(c["x"] - door["x"]) < s["x"] / 2 - 0.01
            if along_x else
            abs(c["x"] - door["x"]) < 0.3 and abs(c["z"] - door["z"]) < s["x"] / 2 - 0.01
        )
        if near_door:
            assert c["y"] - s["y"] / 2 >= DOOR_H - 1e-3, "a finish piece covers the front door"
    assert DOOR_W > 0


def test_lower_rooms_finish_reaches_the_roof():
    geometry = _example({"roof": {}, "walls": {"color": "beige"}})
    tops = {round(p["center"]["y"] + p["size"]["y"] / 2, 3) for p in _parts(geometry, "wall")}
    assert max(tops) == pytest.approx(10 * FT_TO_M, abs=1e-3)
    assert round(9 * FT_TO_M, 3) not in tops


def test_landscaping_builds_plants_paths_and_a_yard_big_enough():
    geometry = _example({"landscape": [
        {"type": "tree", "x": 60, "z": 20},
        {"type": "path", "from": {"x": 4, "z": -28}, "to": {"x": 4, "z": 0}, "width": 4, "material": "pavers"},
        {"type": "patio", "x": 25, "z": 300, "width": 200, "depth": 200, "material": "tile"},
        {"type": "flower_bed", "x": 25, "z": -3, "width": 40, "depth": 10, "color": "red"},
    ]})
    exterior = geometry["exterior"]
    assert exterior["roof"] == []
    ground = next(p for p in exterior["parts"] if p["kind"] == "ground")
    assert ground["walkable"] is True
    # The far patio is inside the yard.
    assert exterior["ground_bounds"]["z1"] >= 400 * FT_TO_M
    # Big tiled areas stay under the tile budget.
    assert len(_parts(geometry, "landscape")) < 2 * (MAX_TILES + 1) + 10
    tree = next(p for p in exterior["plants"] if not p.get("baked"))
    assert tree["mesh"] in exterior["plant_meshes"]
    assert tree["position"]["x"] == pytest.approx(60 * FT_TO_M, abs=0.01)
    # The flower bed is one mesh, in the color asked for.
    bed = next(p for p in exterior["plants"] if p.get("baked"))
    assert bed["color"] == {"r": 0.651, "g": 0.227, "b": 0.196}
    assert len(exterior["plant_meshes"][bed["mesh"]]["groups"]) >= 2


def test_plants_placed_in_a_room_are_moved_out_into_the_yard():
    # A palm on the entry's front wall line (z = 0) and a shrub in the middle of the living room.
    geometry = _example({"landscape": [{"type": "palm", "x": 4, "z": 0}, {"type": "shrub", "x": 12, "z": 4}]})
    rects = [r["bounds"] for r in geometry["rooms"]]
    palm, bush = geometry["exterior"]["plants"]
    for plant in (palm, bush):
        x, z = plant["position"]["x"], plant["position"]["z"]
        assert not any(r["x0"] - WALL_T < x < r["x1"] + WALL_T and r["z0"] - WALL_T < z < r["z1"] + WALL_T for r in rects)
    assert palm["position"]["z"] < 0  # out the front, the nearest way

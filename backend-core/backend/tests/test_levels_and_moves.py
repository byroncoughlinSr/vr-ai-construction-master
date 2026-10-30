"""Houses of several storeys with stairs, floor finishes, and furniture that can be
changed piece by piece: switched features, turned freely, grabbed and moved (no network)."""

import pytest

from app.services import vr_furniture as vf
from app.services.layout_check import layout_problems
from app.services.vr_floors import floor_finish
from app.services.vr_geometry_service import FT_TO_M, build_geometry_from_rooms, layout_levels, subtract_rects

TWO_STOREYS = {
    "layout": {"entry": "Living Room", "rects": [
        {"room": "Living Room", "x": 0, "z": 0, "length": 16, "width": 14},
        {"room": "Kitchen", "x": 16, "z": 0, "length": 12, "width": 14},
        {"room": "Stairs", "x": 0, "z": 14, "length": 14, "width": 4},
        {"room": "Dining Room", "x": 14, "z": 14, "length": 14, "width": 10},
        {"room": "Den", "x": 0, "z": 18, "length": 14, "width": 6},
        {"room": "Landing", "level": 1, "x": 0, "z": 14, "length": 14, "width": 4},
        {"room": "Bedroom 1", "level": 1, "x": 0, "z": 0, "length": 14, "width": 14},
        {"room": "Bedroom 2", "level": 1, "x": 14, "z": 0, "length": 14, "width": 14},
        {"room": "Bathroom", "level": 1, "x": 14, "z": 14, "length": 14, "width": 10},
        {"room": "Closet", "level": 1, "x": 0, "z": 18, "length": 14, "width": 6},
    ]},
    "rooms": [{"name": n, "dimensions": {"height": h}, "connects_to": c, "floor_material": f} for n, h, c, f in [
        ("Living Room", 9, ["Kitchen", "Stairs"], "white oak hardwood"), ("Kitchen", 9, ["Dining Room"], "gray tile"),
        ("Stairs", 9, ["Living Room"], "oak"), ("Dining Room", 9, ["Kitchen"], "oak"), ("Den", 9, ["Stairs"], "carpet"),
        ("Landing", 8, ["Bedroom 1", "Bathroom"], "carpet"), ("Bedroom 1", 8, [], "carpet"),
        ("Bedroom 2", 8, ["Bathroom"], "carpet"), ("Bathroom", 8, [], "marble"), ("Closet", 8, ["Landing"], "carpet"),
    ]],
}


def _build(**kw):
    return build_geometry_from_rooms(rooms_ft=TWO_STOREYS["rooms"], layout=TWO_STOREYS["layout"], **kw)


def test_a_layout_splits_into_levels_that_share_the_house_corner():
    levels = layout_levels(TWO_STOREYS["layout"])
    assert sorted(levels) == [0, 1]
    assert levels[0]["entry"] == "Living Room" and "entry" not in levels[1]
    assert levels[0]["origin"] == levels[1]["origin"] == [0.0, 0.0]
    assert layout_levels({"rects": [{"room": "A", "x": 0, "z": 0, "length": 9, "width": 9}]}) == {
        0: {"rects": [{"room": "A", "x": 0, "z": 0, "length": 9, "width": 9}]}}


def test_two_storeys_stack_with_stairs_between_them():
    g = _build(exterior={"roof": {"style": "gable"}, "walls": {"material": "siding", "color": "#dddddd"}})
    rooms = {r["name"]: r for r in g["rooms"]}
    up = 9 * FT_TO_M
    assert [lv["y"] for lv in g["levels"]] == [0.0, pytest.approx(up, abs=1e-3)]
    assert rooms["Bedroom 1"]["position"]["y"] == pytest.approx(up, abs=1e-3)
    assert rooms["Bedroom 1"]["floor"]["vertices"][0]["y"] == pytest.approx(up, abs=1e-3)
    assert all(w["start"]["y"] >= up - 1e-3 for w in rooms["Bedroom 1"]["walls"])
    # Room ids run on across the storeys; doorways only join rooms on one level.
    assert sorted(r["id"] for r in g["rooms"]) == list(range(1, 11))
    level = {r["id"]: r["level"] for r in g["rooms"]}
    assert all(len({level[i] for i in d["rooms"]}) == 1 for d in g["doors"])
    assert all(d["door_type"] != "exterior" or level[d["rooms"][0]] == 0 for d in g["doors"])
    # Downstairs ceilings are gone where the floor above covers them.
    assert rooms["Living Room"]["ceilings"] == [] and rooms["Living Room"]["ceiling"] is None
    # The stairs climb the storey in the Stairs room, the landing's floor cut over them and railed.
    (flight,) = g["stairs"]
    assert flight["room"] == rooms["Stairs"]["id"] and flight["rise"] == pytest.approx(up, abs=1e-3)
    b = rooms["Stairs"]["bounds"]
    assert b["x0"] <= flight["x0"] < flight["x1"] <= b["x1"] and b["z0"] <= flight["z0"] < flight["z1"] <= b["z1"]
    assert len(rooms["Landing"]["floors"]) > 1
    kinds = {(p["type"], p["room"]) for p in g["furniture"]["pieces"]}
    assert ("stairs", rooms["Stairs"]["id"]) in kinds and ("railing", rooms["Landing"]["id"]) in kinds
    # Upstairs is reached from the landing; the roof is over the top storey only.
    assert rooms["Landing"]["connects_to"]
    roof_y = [p for m in g["exterior"]["roof"] for p in m["positions"][1::3]]
    assert min(roof_y) > up + 2.0  # none at the top of the ground floor (its overhang dips below the eave)


def test_floor_problems_are_judged_floor_by_floor():
    assert layout_problems(TWO_STOREYS) == []
    bad = {**TWO_STOREYS, "layout": {**TWO_STOREYS["layout"], "rects": TWO_STOREYS["layout"]["rects"] + [
        {"room": "Office", "level": 1, "x": 2, "z": 2, "length": 6, "width": 6}]}}
    assert any(p.startswith("Floor 2: Bedroom 1 and Office overlap") for p in layout_problems(bad))


def test_without_stairs_the_upper_floor_says_so():
    rects = [r for r in TWO_STOREYS["layout"]["rects"] if r["room"] != "Stairs"]
    rects.append({"room": "Hall", "x": 0, "z": 14, "length": 14, "width": 4})
    g = build_geometry_from_rooms(rooms_ft=TWO_STOREYS["rooms"], layout={"entry": "Living Room", "rects": rects})
    assert any("no stairs up" in n for n in g["notes"])


def test_subtracting_rectangles():
    pieces = subtract_rects({"x0": 0, "x1": 4, "z0": 0, "z1": 4}, [{"x0": 1, "x1": 2, "z0": 1, "z1": 2}])
    assert sum((p["x1"] - p["x0"]) * (p["z1"] - p["z0"]) for p in pieces) == pytest.approx(15)


@pytest.mark.parametrize("words, kind, color", [
    ("white oak hardwood", "planks", None), ("gray porcelain tile", "tiles", "gray"), ("beige carpet", "plain", None),
    ("polished concrete", "plain", "#9e9e9a"), ("", "plain", "#a89a88"),
])
def test_floor_materials_in_words(words, kind, color):
    finish = floor_finish(words)
    assert finish["kind"] == kind
    if color == "gray":
        assert finish["color"] != "#d9d4cc"
    elif color:
        assert finish["color"] == color
    assert floor_finish("24 inch tile")["size"] == pytest.approx(0.61, abs=0.01)


def test_every_floor_gets_its_finish_at_its_storey():
    g = _build()
    rooms = {r["id"]: r for r in g["rooms"]}
    pieces = g["finishes"]["pieces"]
    assert {p["room"] for p in pieces} == set(rooms)
    for p in pieces:
        assert p["position"]["y"] == pytest.approx(rooms[p["room"]]["position"]["y"] + 0.027, abs=1e-3)


# --- Furniture changed piece by piece -------------------------------------------------

KITCHEN = {"id": 2, "name": "Kitchen", "bounds": {"x0": 0.0, "x1": 2.7432, "z0": 0.0, "z1": 4.572}}
LIVING = {"id": 3, "name": "Living Room", "bounds": {"x0": 2.7432, "x1": 7.0, "z0": 0.0, "z1": 4.572}}


def _furnish(items, room=KITCHEN, auto=None):
    spec = {"rooms": {room["name"]: items}}
    if auto is not None:
        spec["auto"] = auto
    return vf.build_furniture(vf.furniture_spec(spec), [room], [])


def test_a_counter_can_lose_its_sink_and_wall_cabinets_and_an_island_take_the_sink():
    spec = vf.furniture_spec({"rooms": {"Kitchen": [
        {"type": "counter", "sink": "no", "uppers": False}, {"type": "kitchen island", "sink": True, "seats": 2}]}})
    assert spec["rooms"]["Kitchen"][0] == {"type": "counter", "sink": False, "uppers": False}
    assert vf.furniture_spec(spec) == spec
    out, _ = _furnish(spec["rooms"]["Kitchen"])
    (counter,) = [p for p in out["pieces"] if p["type"] == "counter"]
    (island,) = [p for p in out["pieces"] if p["type"] == "kitchen island"]
    assert "sink" not in counter["mesh"] and "upper" not in counter["mesh"] and "-sink" in island["mesh"]


def test_a_piece_at_an_exact_spot_can_be_turned_any_way():
    out, _ = _furnish([{"type": "armchair", "x": 4, "z": 7, "rotation": 30}])
    (chair,) = out["pieces"]
    assert chair["yaw"] == 30.0
    assert chair["ref"] == {"room": "Kitchen", "item": 0, "width": pytest.approx(2.8, abs=0.3),
                            "depth": pytest.approx(2.9, abs=0.3)}


def test_a_grabbed_piece_is_saved_where_it_was_left():
    spec = {"rooms": {"Kitchen": [{"type": "refrigerator", "place": "back"}, {"type": "counter"}]}}
    sizes = {"Kitchen": (2.74, 4.57), "Living Room": (4.26, 4.57)}
    moved = vf.move_piece(spec, {"room": "Kitchen", "item": 0, "width": 3.0, "depth": 2.6}, "Kitchen", 4.5, 3.0, 90, sizes)
    assert moved["rooms"]["Kitchen"][0] == {"type": "refrigerator", "width": 3.0, "depth": 2.6, "x": 4.5, "z": 3.0,
                                            "rotation": 90.0}
    assert spec["rooms"]["Kitchen"][0]["place"] == "back"  # the original is left alone
    # Into another room; a room furnished automatically has its list written out first.
    out = vf.move_piece({"auto": True, "rooms": {"Kitchen": [{"type": "bar stool", "count": 3}]}},
                        {"room": "Kitchen", "item": 0}, "Living Room", 2, 2, 0, sizes)
    assert out["rooms"]["Kitchen"] == [{"type": "bar stool", "count": 2}]
    assert out["rooms"]["Living Room"][-1] == {"type": "bar stool", "x": 2, "z": 2, "rotation": 0}
    assert any(i["type"] == "sofa" for i in out["rooms"]["Living Room"])
    with pytest.raises(vf.MoveError):
        vf.move_piece(spec, {"room": "Kitchen", "item": 9}, "Kitchen", 1, 1, 0, sizes)
    # Cleaned again, it is placed there.
    built, _ = _furnish(vf.furniture_spec(moved)["rooms"]["Kitchen"])
    fridge = next(p for p in built["pieces"] if p["type"] == "refrigerator")
    assert fridge["yaw"] == 90.0
    assert sum(c[0] for c in fridge["outline"]) / 4 == pytest.approx(4.5 * FT_TO_M, abs=0.02)

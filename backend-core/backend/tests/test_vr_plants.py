"""Procedural plants: naming the species, building meshes, placing them (no network calls)."""

import pytest

from app.services.example_floor_plans import EXAMPLE_STRUCTURE
from app.services.vr_exterior import NAMED_COLORS, exterior_spec
from app.services.vr_geometry_service import FT_TO_M, build_geometry_from_rooms
from app.services.vr_plants import SPECIES, VARIANTS, find_species, name_key, plant_mesh, resolve


def _exterior(landscape, plant_models=None):
    geometry = build_geometry_from_rooms(
        rooms_ft=EXAMPLE_STRUCTURE["rooms"], layout=EXAMPLE_STRUCTURE["layout"],
        exterior={"landscape": landscape}, plant_models=plant_models,
    )
    return geometry["exterior"]


@pytest.mark.parametrize("text, species", [
    ("coral rose", "rose"),
    ("two Coral Knock Out Roses", "rose"),
    ("Japanese maple", "japanese maple"),
    ("a maple", "maple"),
    ("blue hydrangeas", "hydrangea"),
    ("Italian cypress", "cypress"),
    ("black-eyed Susans", "black eyed susan"),
    ("ornamental grasses", "ornamental grass"),
    ("something unheard of", None),
])
def test_species_from_what_people_call_plants(text, species):
    assert find_species(text) == species


def test_name_key_ignores_case_and_plurals():
    assert name_key("Coral Roses") == name_key("coral rose") == "coral rose"
    assert name_key("Hibiscus") == "hibiscus"


def test_color_words_tint_the_flowers():
    species, leaf, flower = resolve({"type": "shrub", "plant": "coral rose"}, NAMED_COLORS)
    assert (species, leaf, flower) == ("rose", SPECIES["rose"].leaf, "#f88379")
    # An explicit flower color wins; "color" is the leaves'.
    _, leaf, flower = resolve({"type": "shrub", "plant": "rose", "flower_color": "#ffffff", "color": "#112233"}, NAMED_COLORS)
    assert (leaf, flower) == ("#112233", "#ffffff")
    # A plant without a name falls back to its type.
    assert resolve({"type": "palm"}, NAMED_COLORS)[0] == "palm"


def test_spec_keeps_plant_names_and_reads_plants_given_as_types():
    spec = exterior_spec({"landscape": [
        {"type": "shrub", "plant": "Coral rose", "x": 1, "z": -3, "flower_color": "coral", "model_id": "7"},
        {"type": "hydrangea", "x": 5, "z": -3},
        {"type": "flower_bed", "plant": "tulips", "x": 0, "z": -5, "width": 10, "depth": 3},
    ]})
    rose, hydrangea, bed = spec["landscape"]
    assert rose == {"type": "shrub", "x": 1.0, "z": -3.0, "plant": "Coral rose", "flower_color": "#f88379", "model_id": 7}
    assert hydrangea["type"] == "shrub" and hydrangea["plant"] == "hydrangea"
    assert bed["plant"] == "tulips"


@pytest.mark.parametrize("species", sorted(SPECIES))
def test_every_species_builds_into_the_unit_box(species):
    sp = SPECIES[species]
    for variant in range(VARIANTS):
        mesh = plant_mesh(species, variant, sp.leaf, sp.flower)
        assert 20 <= mesh.triangles <= 2500
        points = [p for pts in mesh.groups.values() for p in pts]
        assert min(p[1] for p in points) == pytest.approx(0, abs=1e-6)
        assert max(p[1] for p in points) == pytest.approx(1, abs=1e-6)
        assert max(max(abs(p[0]), abs(p[2])) for p in points) <= 0.5 + 1e-6
        # Several shades, not one flat color.
        assert len(mesh.groups) >= 2


def test_meshes_are_repeatable_and_variants_differ():
    a = plant_mesh("rose", 0, "#3f6b2e", "#f88379").out()
    assert plant_mesh("rose", 0, "#3f6b2e", "#f88379").out() == a
    assert plant_mesh("rose", 1, "#3f6b2e", "#f88379").out() != a


def test_same_plants_share_a_mesh_and_flowers_show_their_color():
    exterior = _exterior([
        {"type": "shrub", "plant": "coral rose", "x": 3, "z": -4},
        {"type": "shrub", "plant": "coral rose", "x": 3, "z": -4.0},
        {"type": "tree", "plant": "Japanese maple", "x": -10, "z": -15, "height": 14},
    ])
    rose1, rose2, maple = exterior["plants"]
    assert rose1["mesh"] == rose2["mesh"] and rose1["mesh"].startswith("rose-")
    assert len(exterior["plant_meshes"]) == 2
    coral = {"r": 0.973, "g": 0.514, "b": 0.475}
    assert rose1["color"] == coral  # the plan shows a rose by its flowers
    assert maple["scale"]["y"] == pytest.approx(14 * FT_TO_M, abs=0.01)
    assert maple["position"]["y"] == pytest.approx(-0.10)
    groups = exterior["plant_meshes"][maple["mesh"]]["groups"]
    assert all(len(g["positions"]) % 9 == 0 for g in groups)  # whole triangles


def test_hedges_and_flower_beds_are_single_meshes():
    exterior = _exterior([
        {"type": "hedge", "from": {"x": -5, "z": -25}, "to": {"x": 40, "z": -25}, "height": 4},
        {"type": "flower_bed", "plant": "tulips", "x": 20, "z": -3, "width": 16, "depth": 4},
    ])
    hedge, bed = exterior["plants"]
    assert hedge["baked"] and bed["baked"]
    points = exterior["plant_meshes"][hedge["mesh"]]["groups"][0]["positions"]
    ys = points[1::3]
    assert max(ys) == pytest.approx(-0.10 + 4 * FT_TO_M, abs=0.01)
    xs = [x for g in exterior["plant_meshes"][hedge["mesh"]]["groups"] for x in g["positions"][0::3]]
    assert min(xs) < -5 * FT_TO_M + 0.3 and max(xs) > 40 * FT_TO_M - 0.3
    # The bed keeps its soil box; tulips are red by default.
    assert any(p["kind"] == "landscape" and p["size"]["y"] == pytest.approx(0.15) for p in exterior["parts"])
    assert bed["color"] == {"r": 0.839, "g": 0.157, "b": 0.227}


def test_a_plant_with_a_photo_model_uses_it():
    models = [{"id": 4, "name": "Coral rose", "url": "/plant_models/4/model-a.glb", "aspect": 0.8, "height_ft": None}]
    exterior = _exterior([
        {"type": "shrub", "plant": "coral roses", "x": 3, "z": -4},
        {"type": "shrub", "plant": "boxwood", "x": 8, "z": -4, "model_id": 99},  # no such model
        {"type": "shrub", "x": 12, "z": -4, "model_id": 4, "width": 4},
    ], plant_models=models)
    assert [p["mesh"].split("-")[0] for p in exterior["plants"]] == ["boxwood"]
    by_name, by_id = exterior["models"]
    assert by_name["url"] == "/plant_models/4/model-a.glb"
    assert by_name["scale"] == pytest.approx(SPECIES["rose"].height * FT_TO_M, abs=0.01)
    assert by_id["scale"] == pytest.approx(4 * FT_TO_M / 0.8, abs=0.01)
    assert by_id["width"] == pytest.approx(4 * FT_TO_M, abs=0.01)

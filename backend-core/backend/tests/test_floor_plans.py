"""Versioned floor plans: saving, editing, refining, linking images (no network calls)."""

import copy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import ai_planning
from app.database import Base, get_db
from app.main import app
from app.models import AIGeneration, FloorPlan, Project
from app.services import floor_plan_service
from app.services.example_floor_plans import EXAMPLE_NAME, EXAMPLE_STRUCTURE, seed_example

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database(monkeypatch):
    app.dependency_overrides[get_db] = override_get_db
    # _save_project opens its own sessions.
    monkeypatch.setattr(ai_planning, "SessionLocal", TestingSessionLocal)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def example_id():
    with TestingSessionLocal() as db:
        return seed_example(db).id


def _plan_result(structure, source="groq"):
    return {"success": True, "plan": {"project_structure": structure}, "source": source}


def test_example_is_built_from_its_floor_plan(example_id):
    geometry = client.get(f"/api/v1/projects/{example_id}/generate-vr").json()["geometry"]
    assert geometry["project_name"] == EXAMPLE_NAME
    assert geometry["floor_plan"]["version"] == 1
    assert geometry["metadata"]["layout"] == "split"
    assert len(geometry["rooms"]) == 9
    # Nine requested doorways, all on shared walls, plus the front door.
    assert len(geometry["doors"]) == 10
    assert geometry["rooms"][0]["name"] == "Entry Foyer"


def test_seeding_twice_keeps_one_example(example_id):
    with TestingSessionLocal() as db:
        assert seed_example(db).id == example_id
        assert db.query(Project).count() == 1


def test_edit_adds_a_version_and_renames_the_house(example_id):
    structure = copy.deepcopy(EXAMPLE_STRUCTURE)
    structure["layout"]["parts"][0]["size"] = 30  # wider public wing
    structure["rooms"][0]["name"] = "Front Hall"
    structure["layout"]["parts"][0]["parts"][0]["parts"][0]["room"] = "Front Hall"
    structure["layout"]["entry"] = "Front Hall"

    response = client.put(
        f"/api/v1/projects/{example_id}/floor-plan",
        json={"name": "Maple Hollow II", "layout": structure["layout"], "rooms": structure["rooms"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["floor_plan"]["version"] == 2
    assert body["floor_plan"]["change_type"] == "edited"
    assert body["geometry"]["project_name"] == "Maple Hollow II"
    assert "Front Hall" in [r["name"] for r in body["geometry"]["rooms"]]

    assert client.get(f"/api/v1/projects/{example_id}").json()["name"] == "Maple Hollow II"
    versions = client.get(f"/api/v1/projects/{example_id}/floor-plans").json()["floor_plans"]
    assert [v["version"] for v in versions] == [2, 1]


def test_unbuildable_edit_is_rejected(example_id):
    response = client.put(
        f"/api/v1/projects/{example_id}/floor-plan",
        json={"layout": {"length": 0, "width": 10, "room": "Box"}, "rooms": [{"name": "Box"}]},
    )
    assert response.status_code == 422
    assert client.get(f"/api/v1/projects/{example_id}/floor-plan").json()["version"] == 1


def test_refine_saves_the_ai_revision(example_id, monkeypatch):
    revised = copy.deepcopy(EXAMPLE_STRUCTURE)
    revised["layout"]["parts"][0]["parts"][1]["parts"][1]["size"] = 18  # bigger kitchen
    seen = {}

    async def refine(structure, instruction, site=None):
        seen["rooms"] = [r["name"] for r in structure["rooms"]]
        seen["instruction"] = instruction
        return _plan_result(revised)

    monkeypatch.setattr(ai_planning.planning_service, "refine_floor_plan", refine)
    response = client.post(
        f"/api/v1/projects/{example_id}/floor-plan/refine",
        json={"instruction": "make the kitchen bigger"},
    )
    assert response.status_code == 200
    plan = response.json()["floor_plan"]
    assert plan["version"] == 2
    assert plan["change_type"] == "refined"
    assert plan["change_note"] == "make the kitchen bigger"
    assert plan["source"] == "groq"
    assert plan["name"] == EXAMPLE_NAME
    assert seen == {"rooms": [r["name"] for r in EXAMPLE_STRUCTURE["rooms"]],
                    "instruction": "make the kitchen bigger"}


def test_refine_rejects_an_empty_revision(example_id, monkeypatch):
    async def refine(structure, instruction, site=None):
        return _plan_result({})

    monkeypatch.setattr(ai_planning.planning_service, "refine_floor_plan", refine)
    response = client.post(
        f"/api/v1/projects/{example_id}/floor-plan/refine", json={"instruction": "remove everything"}
    )
    assert response.status_code == 422
    assert client.get(f"/api/v1/projects/{example_id}/floor-plan").json()["version"] == 1


def test_accepted_image_is_linked_to_the_floor_plan(example_id):
    response = client.put(
        f"/api/v1/projects/{example_id}/floor-plan/image",
        json={"generation_id": "abc-123", "image_url": "/generated_images/generated_abc-123_0.png"},
    )
    assert response.status_code == 200
    geometry = client.get(f"/api/v1/projects/{example_id}/generate-vr").json()["geometry"]
    assert geometry["floor_plan"]["image_url"] == "/generated_images/generated_abc-123_0.png"
    with TestingSessionLocal() as db:
        image = db.query(AIGeneration).filter(AIGeneration.generation_type == "image").one()
        assert image.source == "stable_diffusion"


def test_image_link_must_be_a_generated_image(example_id):
    response = client.put(
        f"/api/v1/projects/{example_id}/floor-plan/image",
        json={"generation_id": "x", "image_url": "http://elsewhere/evil.png"},
    )
    assert response.status_code == 422


def test_voice_flow_house_is_saved_as_a_project(monkeypatch):
    async def generate_complete_project(project_description, **kwargs):
        return {
            "success": True,
            "project_name": "Sunny Ridge Bungalow",
            "plan": {"project_structure": copy.deepcopy(EXAMPLE_STRUCTURE), "phases": [], "material_list": []},
            "source": "groq",
        }

    monkeypatch.setattr(ai_planning.planning_service, "generate_complete_project", generate_complete_project)
    response = client.post(
        "/api/v1/planning/generate-vr-from-prompt", json={"prompt": "a three bedroom cottage"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["project_name"] == "Sunny Ridge Bungalow"
    assert body["geometry"]["project_name"] == "Sunny Ridge Bungalow"
    assert body["geometry"]["floor_plan"]["version"] == 1
    project_id = body["project_id"]

    with TestingSessionLocal() as db:
        plan = db.query(FloorPlan).filter(FloorPlan.project_id == project_id).one()
        assert plan.change_type == "generated"
        assert plan.change_note == "a three bedroom cottage"
        generation = db.query(AIGeneration).filter(AIGeneration.project_id == project_id).one()
        # Used to stay at the column default "ollama" whatever planner ran.
        assert generation.source == "groq"


def test_project_without_floor_plan_uses_its_stored_plan():
    with TestingSessionLocal() as db:
        project = Project(name="Old Project")
        db.add(project)
        db.flush()
        db.add(AIGeneration(
            project_id=project.id, generation_type="construction_plan",
            output_data={"project_structure": copy.deepcopy(EXAMPLE_STRUCTURE)},
        ))
        # A newer image row must not hide the plan.
        db.add(AIGeneration(project_id=project.id, generation_type="image", output_data={}))
        db.commit()
        project_id = project.id

    geometry = client.get(f"/api/v1/projects/{project_id}/generate-vr").json()["geometry"]
    assert geometry["floor_plan"] is None
    assert len(geometry["rooms"]) == 9
    assert client.get(f"/api/v1/projects/{project_id}/floor-plan").status_code == 404


TILE_ROOF = {
    "roof": {"style": "hip", "material": "clay tile", "color": "terracotta"},
    "walls": {"material": "stucco", "color": "beige"},
    "landscape": [{"type": "palm", "x": 4, "z": -6}],
}


def _refine(example_id, monkeypatch, plan: dict, instruction: str = "tile roof"):
    seen = {}

    async def refine(structure, instruction, site=None):
        seen["structure"], seen["site"] = structure, site
        return {"success": True, "plan": plan, "source": "groq"}

    monkeypatch.setattr(ai_planning.planning_service, "refine_floor_plan", refine)
    response = client.post(
        f"/api/v1/projects/{example_id}/floor-plan/refine", json={"instruction": instruction},
    )
    return response, seen


def test_exterior_change_updates_the_current_version_in_place(example_id, monkeypatch):
    response, seen = _refine(example_id, monkeypatch, {"scope": "exterior", "exterior": TILE_ROOF})
    assert response.status_code == 200
    body = response.json()
    assert body["updated_in_place"] is True
    assert body["floor_plan"]["version"] == 1
    assert body["floor_plan"]["change_type"] == "example"
    exterior = body["floor_plan"]["exterior"]
    assert exterior["roof"]["material"] == "clay_tile"
    assert exterior["walls"]["color"].startswith("#")
    assert body["geometry"]["exterior"]["roof"]
    # The AI is told where the house and its front door are.
    assert seen["site"]["footprint"] == {"length": 50.0, "width": 36.0}
    assert seen["site"]["front_door"]["faces"] == "-z (toward the street)"
    assert len(seen["site"]["front_door"]["beside_it"]) == 2
    assert len(seen["site"]["rooms"]) == len(EXAMPLE_STRUCTURE["rooms"])
    versions = client.get(f"/api/v1/projects/{example_id}/floor-plans").json()["floor_plans"]
    assert len(versions) == 1


def test_room_change_keeps_the_exterior(example_id, monkeypatch):
    _refine(example_id, monkeypatch, {"scope": "exterior", "exterior": TILE_ROOF})
    revised = copy.deepcopy(EXAMPLE_STRUCTURE)
    revised["layout"]["parts"][0]["parts"][1]["parts"][1]["size"] = 18
    response, seen = _refine(
        example_id, monkeypatch, {"scope": "floor_plan", "project_structure": revised}, "bigger kitchen",
    )
    assert seen["structure"]["exterior"]["roof"]["style"] == "hip"
    body = response.json()
    assert body["updated_in_place"] is False
    assert body["floor_plan"]["version"] == 2
    assert body["floor_plan"]["exterior"]["roof"]["style"] == "hip"


def test_change_to_both_saves_a_version_with_the_new_exterior(example_id, monkeypatch):
    response, _ = _refine(example_id, monkeypatch, {
        "scope": "both", "project_structure": copy.deepcopy(EXAMPLE_STRUCTURE), "exterior": TILE_ROOF,
    })
    body = response.json()
    assert body["floor_plan"]["version"] == 2
    assert body["floor_plan"]["exterior"]["landscape"][0]["type"] == "palm"


def test_exterior_change_without_an_exterior_is_rejected(example_id, monkeypatch):
    response, _ = _refine(example_id, monkeypatch, {"scope": "exterior"})
    assert response.status_code == 422
    assert client.get(f"/api/v1/projects/{example_id}/floor-plan").json()["exterior"] is None


def test_dashboard_edit_keeps_the_exterior(example_id, monkeypatch):
    _refine(example_id, monkeypatch, {"scope": "exterior", "exterior": TILE_ROOF})
    response = client.put(f"/api/v1/projects/{example_id}/floor-plan", json={
        "layout": EXAMPLE_STRUCTURE["layout"], "rooms": EXAMPLE_STRUCTURE["rooms"],
    })
    assert response.json()["floor_plan"]["exterior"]["roof"]["style"] == "hip"


def test_door_to_the_yard_is_a_room_change_and_is_shown_to_the_ai(example_id, monkeypatch):
    revised = copy.deepcopy(EXAMPLE_STRUCTURE)
    kitchen = next(r for r in revised["rooms"] if r["name"] == "Kitchen")
    kitchen["outside_doors"] = [{"side": "back", "style": "sliding_glass", "width": 6}]
    response, _ = _refine(
        example_id, monkeypatch, {"scope": "floor_plan", "project_structure": revised},
        "double glass sliding door from the kitchen to the backyard",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["updated_in_place"] is False
    assert body["floor_plan"]["version"] == 2
    patio = [d for d in body["geometry"]["doors"] if d["door_type"] == "patio"]
    assert [(d["style"], d["side"]) for d in patio] == [("sliding_glass", "back")]
    assert body["geometry"]["notes"] == []
    # The next change ("a deck outside the sliding door") is told where the door is.
    _, seen = _refine(example_id, monkeypatch, {"scope": "exterior", "exterior": TILE_ROOF})
    door = seen["site"]["outside_doors"][0]
    assert door["room"] == "Kitchen" and door["style"] == "sliding_glass" and door["side"] == "back"
    assert door["z"] == pytest.approx(36.0)


def test_site_summary_lists_doorways_added_for_reachability():
    from types import SimpleNamespace

    from app.services.floor_plan_service import site_summary

    layout = {"length": 24, "width": 12, "entry": "Den", "split": "x",
              "parts": [{"size": 12, "room": "Den"}, {"size": 12, "room": "Kitchen"}]}
    rooms = [{"name": "Den", "dimensions": {"height": 9}}, {"name": "Kitchen", "dimensions": {"height": 9}}]
    site = site_summary(SimpleNamespace(rooms=rooms, layout=layout))
    assert site["doorways"] == [["Den", "Kitchen"]]  # in no connects_to, added by the builder


def test_rename_rooms_renames_every_reference():
    from app.services.floor_plan_service import rename_rooms

    structure = {
        "layout": {"length": 24, "width": 12, "entry": "Den", "split": "x",
                   "parts": [{"size": 12, "room": "Den"}, {"size": 12, "room": "Kitchen"}]},
        "rooms": [{"name": "Den", "connects_to": ["kitchen"]},
                  {"name": "Kitchen", "open_to": "Den", "no_door_to": ["Den"]}],
    }
    out = rename_rooms(structure, {"den": "Family Room"})
    assert out["layout"]["entry"] == "Family Room"
    assert out["layout"]["parts"][0]["room"] == "Family Room"
    assert [r["name"] for r in out["rooms"]] == ["Family Room", "Kitchen"]
    assert out["rooms"][1]["open_to"] == "Family Room" and out["rooms"][1]["no_door_to"] == ["Family Room"]
    assert structure["rooms"][0]["name"] == "Den"  # a copy


def test_rename_rooms_renames_rectangles():
    from app.services.floor_plan_service import rename_rooms

    structure = {
        "layout": {"entry": "Den", "rects": [
            {"room": "Den", "x": 0, "z": 0, "length": 12, "width": 12},
            {"room": "Kitchen", "x": 12, "z": 0, "length": 12, "width": 12}]},
        "rooms": [{"name": "Den"}, {"name": "Kitchen"}],
    }
    out = rename_rooms(structure, {"Den": "Family Room"})
    assert out["layout"]["entry"] == "Family Room"
    assert [r["room"] for r in out["layout"]["rects"]] == ["Family Room", "Kitchen"]


def test_rename_in_only_the_layout_keeps_the_room_settings():
    from app.services.floor_plan_service import validate_structure

    structure = {
        "layout": {"length": 24, "width": 12, "split": "x",
                   "parts": [{"size": 12, "room": "Den"}, {"size": 12, "room": "Cook Space"}]},
        "rooms": [{"name": "Den"}, {"name": "Kitchen", "floor_material": "tile", "solid_walls": ["back"]}],
    }
    clean = validate_structure(structure)
    assert [r["name"] for r in clean["rooms"]] == ["Den", "Cook Space"]
    assert clean["rooms"][1]["floor_material"] == "tile"


def test_refine_applies_renames_the_ai_reports(example_id, monkeypatch):
    revised = copy.deepcopy(EXAMPLE_STRUCTURE)  # renamed nowhere: the backend does it

    async def refine(structure, instruction, site=None):
        return {"success": True, "source": "groq", "plan": {
            "scope": "floor_plan", "project_structure": revised, "renames": {"Kitchen": "Chef's Kitchen"}}}

    monkeypatch.setattr(ai_planning.planning_service, "refine_floor_plan", refine)
    response = client.post(
        f"/api/v1/projects/{example_id}/floor-plan/refine", json={"instruction": "call the kitchen chef's kitchen"}
    )
    assert response.status_code == 200
    names = [r["name"] for r in response.json()["geometry"]["rooms"]]
    assert "Chef's Kitchen" in names and "Kitchen" not in names


def test_site_summary_describes_each_wall():
    from types import SimpleNamespace

    from app.services.floor_plan_service import site_summary

    layout = {"length": 24, "width": 12, "entry": "Den", "split": "x",
              "parts": [{"size": 12, "room": "Den"}, {"size": 12, "room": "Kitchen"}]}
    rooms = [{"name": "Den"}, {"name": "Kitchen", "solid_walls": ["back"], "window": {"side": "right"}}]
    site = site_summary(SimpleNamespace(rooms=rooms, layout=layout))
    kitchen = next(r for r in site["rooms"] if r["name"] == "Kitchen")["walls"]
    assert kitchen["left"] == "Den: doorway to Den"
    assert kitchen["right"] == "outside: window"
    assert kitchen["back"] == "outside: none (solid)"


DINING = {"rooms": {"Dining Room": [{"type": "dining table", "seats": 6, "name": "oak farmhouse table"}]}}


def test_paint_change_updates_the_current_version_in_place(example_id, monkeypatch):
    response, _ = _refine(example_id, monkeypatch, {"scope": "paint", "paint": {
        "Primary Bedroom": {"wall_color": "sage green", "accent_wall": {"side": "back", "color": "navy"}},
        "Hallway": {"wall_color": "warm white"},
    }}, "paint the primary bedroom sage with a navy wall behind the bed")
    assert response.status_code == 200
    body = response.json()
    assert body["updated_in_place"] is True
    assert body["floor_plan"]["version"] == 1
    rooms = {r["name"]: r for r in body["floor_plan"]["rooms"]}
    assert rooms["Primary Bedroom"]["wall_color"] == "#a7b59a"
    assert rooms["Primary Bedroom"]["accent_wall"] == {"side": "back", "color": "#24344d"}
    painted = {r["name"] for r in body["geometry"]["rooms"] if r["paint"]}
    assert painted == {"Primary Bedroom", "Hallway"}
    assert len(body["geometry"]["paint"]["pieces"]) == 2

    # Taking the paint off one room keeps the other's.
    response, seen = _refine(example_id, monkeypatch, {"scope": "paint", "paint": {"Hallway": {"wall_color": None}}})
    assert any(r.get("wall_color") for r in seen["structure"]["rooms"])
    rooms = {r["name"]: r for r in response.json()["floor_plan"]["rooms"]}
    assert "wall_color" not in rooms["Hallway"] and rooms["Primary Bedroom"]["wall_color"] == "#a7b59a"


def test_paint_change_naming_no_room_is_rejected(example_id, monkeypatch):
    response, _ = _refine(example_id, monkeypatch, {"scope": "paint", "paint": {"Attic": {"wall_color": "red"}}})
    assert response.status_code == 422


def test_paint_beside_a_room_change_is_saved_in_the_new_version(example_id, monkeypatch):
    response, _ = _refine(example_id, monkeypatch, {
        "scope": "floor_plan", "project_structure": copy.deepcopy(EXAMPLE_STRUCTURE),
        "paint": {"Kitchen": {"wall_color": "pale yellow"}},
    }, "bigger kitchen painted pale yellow")
    body = response.json()
    assert body["floor_plan"]["version"] == 2
    assert {r["name"]: r for r in body["floor_plan"]["rooms"]}["Kitchen"]["wall_color"] == "#f3e7a9"


def test_furniture_change_updates_the_current_version_in_place(example_id, monkeypatch):
    response, seen = _refine(
        example_id, monkeypatch, {"scope": "furniture", "furniture": DINING},
        "a dining table with 6 chairs in the middle of the dining room",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["updated_in_place"] is True
    assert body["floor_plan"]["version"] == 1
    assert body["floor_plan"]["furniture"]["rooms"]["Dining Room"][0]["seats"] == 6
    types = [p["type"] for p in body["geometry"]["furniture"]["pieces"]]
    assert types.count("dining chair") == 6 and "dining table" in types
    assert seen["structure"]["furniture"] is None

    # A second change to another room keeps the dining room's.
    response, seen = _refine(example_id, monkeypatch, {
        "scope": "furniture", "furniture": {"rooms": {"Living Room": [{"type": "sofa"}]}},
    }, "a sofa in the living room")
    rooms = response.json()["floor_plan"]["furniture"]["rooms"]
    assert set(rooms) == {"Dining Room", "Living Room"}
    assert seen["structure"]["furniture"]["rooms"]["Dining Room"]


def test_furniture_change_without_furniture_is_rejected(example_id, monkeypatch):
    response, _ = _refine(example_id, monkeypatch, {"scope": "furniture"})
    assert response.status_code == 422


def test_room_change_keeps_the_furniture_and_follows_renames(example_id, monkeypatch):
    _refine(example_id, monkeypatch, {"scope": "furniture", "furniture": DINING})
    revised = floor_plan_service.rename_rooms(copy.deepcopy(EXAMPLE_STRUCTURE), {"Dining Room": "Formal Dining"})
    response, _ = _refine(example_id, monkeypatch, {
        "scope": "floor_plan", "project_structure": revised, "renames": {"Dining Room": "Formal Dining"},
        "furniture": {"rooms": {"Kitchen": [{"type": "kitchen island", "seats": 3}]}},
    }, "rename the dining room and add an island")
    body = response.json()
    assert body["updated_in_place"] is False
    assert body["floor_plan"]["version"] == 2
    assert set(body["floor_plan"]["furniture"]["rooms"]) == {"Formal Dining", "Kitchen"}


def test_dashboard_edit_keeps_the_furniture_of_rooms_it_keeps(example_id, monkeypatch):
    _refine(example_id, monkeypatch, {"scope": "furniture", "furniture": {"auto": True, **DINING}}, "furnish the house")
    rooms = [r for r in EXAMPLE_STRUCTURE["rooms"]]
    response = client.put(f"/api/v1/projects/{example_id}/floor-plan", json={
        "layout": EXAMPLE_STRUCTURE["layout"], "rooms": rooms,
    })
    furniture = response.json()["floor_plan"]["furniture"]
    assert furniture["auto"] is True and "Dining Room" in furniture["rooms"]


def test_a_furnished_house_from_the_planner_is_saved_with_its_furniture(monkeypatch):
    structure = {**copy.deepcopy(EXAMPLE_STRUCTURE), "furniture": {"auto": True}}

    async def generate_complete_project(project_description, **kwargs):
        return {"success": True, "plan": {"project_structure": structure, "phases": [], "material_list": []},
                "source": "groq", "project_name": "Furnished House"}

    monkeypatch.setattr(ai_planning.planning_service, "generate_complete_project", generate_complete_project)
    body = client.post("/api/v1/planning/generate-vr-from-prompt", json={"prompt": "a furnished cottage"}).json()
    assert body["geometry"]["furniture"]["pieces"]
    plan = client.get(f"/api/v1/projects/{body['project_id']}/floor-plan").json()
    assert plan["furniture"] == {"auto": True}


def test_furniture_put_down_in_the_headset_is_saved_in_place(example_id, monkeypatch):
    _refine(example_id, monkeypatch, {"scope": "furniture", "furniture": {"rooms": {
        "Living Room": [{"type": "sofa"}, {"type": "armchair"}]}}}, "a sofa and an armchair in the living room")
    geometry = client.get(f"/api/v1/projects/{example_id}/generate-vr").json()["geometry"]
    version = geometry["floor_plan"]["version"]
    chair = next(p for p in geometry["furniture"]["pieces"] if p["type"] == "armchair")
    living = next(r for r in geometry["rooms"] if r["name"] == "Living Room")["bounds"]
    x, z = living["x0"] + 1.0, living["z0"] + 1.2
    response = client.put(f"/api/v1/projects/{example_id}/furniture/move",
                          json={"ref": chair["ref"], "x": x, "z": z, "yaw": 45})
    assert response.status_code == 200, response.text
    assert response.json() == {"moved": True, "room": "Living Room", "version": version}
    items = client.get(f"/api/v1/projects/{example_id}/floor-plan").json()["furniture"]["rooms"]["Living Room"]
    assert items[1]["type"] == "armchair" and items[1]["rotation"] == 45.0
    assert items[1]["x"] == pytest.approx(1.0 / 0.3048, abs=0.1) and items[1]["z"] == pytest.approx(1.2 / 0.3048, abs=0.1)
    moved = next(p for p in client.get(f"/api/v1/projects/{example_id}/generate-vr").json()["geometry"]["furniture"]["pieces"]
                 if p["type"] == "armchair")
    assert moved["yaw"] == 45.0
    stale = client.put(f"/api/v1/projects/{example_id}/furniture/move",
                       json={"ref": {**chair["ref"], "item": 7}, "x": x, "z": z, "yaw": 0})
    assert stale.status_code == 409

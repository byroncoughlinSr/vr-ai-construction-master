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

    async def refine(structure, instruction):
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
    async def refine(structure, instruction):
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

"""Client CRM and the AI copilot (the AI call is replaced; no network calls)."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Client, ConstructionPhase, Project
from app.services import ai_assistant_service
from app.services.ai_assistant_service import AssistantError

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
def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def fake_ai(monkeypatch):
    """Replace the provider chain; records the prompts and answers ``answer``."""
    calls = []
    state = {"answer": {}}

    async def complete_json(planner, system, user, what, max_tokens=1200):
        calls.append({"system": system, "user": user, "what": what})
        if isinstance(state["answer"], Exception):
            raise state["answer"]
        return state["answer"], "groq"

    monkeypatch.setattr(ai_assistant_service, "complete_json", complete_json)
    return state, calls


def _create(**fields):
    response = client.post("/api/v1/crm/clients", json={"name": "Dana Park", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def test_new_client_gets_the_stages_win_probability():
    created = _create(email="dana@example.com", deal_value=600000)
    assert created["stage"] == "new_inquiry"
    assert created["win_probability"] == 10
    assert [a["summary"] for a in created["activities"]] == ["Client added"]

    proposal = _create(stage="cost_estimation", win_probability=70)
    assert proposal["win_probability"] == 70


def test_unknown_stage_is_rejected():
    assert client.post("/api/v1/crm/clients", json={"name": "X", "stage": "maybe"}).status_code == 422


def test_stage_change_is_logged_and_resets_the_probability():
    created = _create()
    updated = client.patch(f"/api/v1/crm/clients/{created['id']}", json={"stage": "vr_consultation"}).json()
    assert updated["win_probability"] == 25
    assert updated["activities"][0]["kind"] == "stage_change"
    assert updated["activities"][0]["summary"] == "New inquiry → VR consultation"

    kept = client.patch(f"/api/v1/crm/clients/{created['id']}", json={"stage": "cost_estimation", "win_probability": 65}).json()
    assert kept["win_probability"] == 65


def test_contact_activity_updates_last_contact_and_sentiment():
    created = _create()
    assert created["last_contact_at"] is None
    note = client.post(f"/api/v1/crm/clients/{created['id']}/activities", json={"kind": "note", "summary": "Thinking"}).json()
    assert note["last_contact_at"] is None

    call = client.post(f"/api/v1/crm/clients/{created['id']}/activities", json={
        "kind": "vr_demo", "summary": "Walked the house in VR", "sentiment": "enthusiastic",
        "action_items": ["Price a bigger pantry"],
    }).json()
    assert call["last_contact_at"] is not None
    assert call["sentiment"] == "enthusiastic"
    assert call["activities"][0]["action_items"] == ["Price a bigger pantry"]

    bad = client.post(f"/api/v1/crm/clients/{created['id']}/activities", json={"kind": "telepathy", "summary": "?"})
    assert bad.status_code == 422


def test_starting_a_project_carries_the_brief_over():
    created = _create(
        site_address="12 Oak Lane", target_budget=550000, preferred_style="Craftsman",
        requirements="Three bedrooms and a mudroom", target_square_feet=2200,
    )
    response = client.post(f"/api/v1/crm/clients/{created['id']}/project", json={})
    assert response.status_code == 201
    result = response.json()
    assert result["project_name"] == "Dana Park residence"
    assert result["client"]["project_id"] == result["project_id"]
    project = client.get(f"/api/v1/projects/{result['project_id']}").json()
    assert project["address"] == "12 Oak Lane" and project["budget"] == 550000
    assert "Craftsman" in project["description"] and "2,200 sq ft" in project["description"]

    overview = client.get(f"/api/v1/projects/{result['project_id']}/overview").json()
    assert overview["clients"] == [{"id": created["id"], "name": "Dana Park", "stage": "new_inquiry"}]


def test_deleting_the_project_keeps_the_client():
    created = _create()
    pid = client.post(f"/api/v1/crm/clients/{created['id']}/project", json={"name": "Park House"}).json()["project_id"]
    assert client.delete(f"/api/v1/projects/{pid}").status_code == 200
    assert client.get(f"/api/v1/crm/clients/{created['id']}").json()["project_id"] is None


def test_pipeline_figures():
    today = date.today()
    _create(deal_value=100000)  # 10 %
    _create(deal_value=200000, stage="cost_estimation")  # 55 %
    _create(deal_value=300000, stage="active_build")  # won
    _create(deal_value=50000, stage="closed_lost")
    due = _create(next_follow_up_at=(today - timedelta(days=1)).isoformat() + "T09:00:00", next_action="Call back")

    pipeline = client.get("/api/v1/crm/pipeline").json()
    assert pipeline["open_count"] == 3
    assert pipeline["open_value"] == 300000
    assert pipeline["weighted_value"] == pytest.approx(100000 * 0.10 + 200000 * 0.55)
    assert pipeline["won_value"] == 300000
    assert pipeline["win_rate"] == 50
    assert [f["id"] for f in pipeline["follow_ups_due"]] == [due["id"]]
    assert {s["id"]: s["count"] for s in pipeline["stages"]}["cost_estimation"] == 1


def test_search_finds_clients_by_address():
    _create(site_address="88 Birch Road")
    _create(name="Someone Else")
    found = client.get("/api/v1/crm/clients", params={"search": "birch"}).json()["clients"]
    assert [c["name"] for c in found] == ["Dana Park"]


def test_ai_insights_are_saved_on_the_client(fake_ai):
    state, calls = fake_ai
    state["answer"] = {
        "summary": "Young family building their first home.",
        "preferences": ["Big kitchen island", ""],
        "risks": ["Tight budget"],
        "next_best_action": "Send the estimate",
        "sentiment": "positive",
    }
    created = _create(requirements="Big kitchen island")
    response = client.post(f"/api/v1/crm/clients/{created['id']}/ai/insights")
    assert response.status_code == 200
    saved = response.json()["client"]
    assert saved["ai_summary"] == "Young family building their first home."
    assert saved["ai_insights"] == {"preferences": ["Big kitchen island"], "risks": ["Tight budget"],
                                    "next_best_action": "Send the estimate"}
    assert saved["sentiment"] == "positive"
    assert "Big kitchen island" in calls[0]["user"]


def test_ai_unavailable_is_a_503(fake_ai):
    state, _ = fake_ai
    state["answer"] = AssistantError("No AI provider could answer: none configured")
    created = _create()
    assert client.post(f"/api/v1/crm/clients/{created['id']}/ai/insights").status_code == 503
    assert client.post("/api/v1/assistant/chat", json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 503


def test_email_draft_is_grounded_in_the_project(fake_ai):
    state, calls = fake_ai
    state["answer"] = {"subject": "Your house in VR", "body": "Hi Dana, ..."}
    created = _create()
    client.post(f"/api/v1/crm/clients/{created['id']}/project", json={"name": "Park House"})
    response = client.post(f"/api/v1/crm/clients/{created['id']}/ai/draft", json={"purpose": "vr_invite", "sender": "Byron"})
    assert response.status_code == 200
    assert response.json()["subject"] == "Your house in VR"
    assert "Park House" in calls[0]["user"] and "SENDER: Byron" in calls[0]["user"]

    assert client.post(f"/api/v1/crm/clients/{created['id']}/ai/draft", json={"purpose": "spam"}).status_code == 503


def test_copilot_keeps_only_actions_that_point_at_real_things(fake_ai):
    state, calls = fake_ai
    with TestingSessionLocal() as db:
        project = Project(name="Lakeview", status="active")
        db.add(project)
        db.flush()
        phase = ConstructionPhase(project_id=project.id, name="Framing", phase_order=1, budgeted_cost=1000)
        db.add(phase)
        db.add(Client(name="Lee", stage="new_inquiry"))
        db.commit()
        pid, phase_id = project.id, phase.id
        lee_id = db.query(Client).first().id

    state["answer"] = {
        "reply": "Framing hasn't started yet.",
        "actions": [
            {"type": "create_task", "label": "Add task", "phase_id": phase_id, "name": "Order trusses", "priority": "urgent"},
            {"type": "create_task", "label": "Bad phase", "phase_id": 999, "name": "Ghost"},
            {"type": "refine_floor_plan", "instruction": "Bigger kitchen"},  # no floor plan yet
            {"type": "draft_email", "client_id": lee_id, "purpose": "follow_up"},
            {"type": "launch_rockets"},
        ],
    }
    response = client.post("/api/v1/assistant/chat", json={
        "project_id": pid, "messages": [{"role": "user", "content": "Where is framing?"}],
    })
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Framing hasn't started yet."
    assert body["actions"] == [
        {"type": "create_task", "label": "Add task", "phase_id": phase_id, "name": "Order trusses",
         "priority": "medium", "duration_days": 1.0},
        {"type": "draft_email", "label": "Draft email", "client_id": lee_id, "purpose": "follow_up"},
    ]
    assert '"name": "Lakeview"' in calls[0]["user"]
    assert "USER: Where is framing?" in calls[0]["user"]


def test_copilot_needs_the_users_message_last():
    response = client.post("/api/v1/assistant/chat", json={"messages": [{"role": "assistant", "content": "Hello"}]})
    assert response.status_code == 422


def test_budget_reading_states_what_the_figures_mean():
    reading = ai_assistant_service.budget_reading({
        "cpi": 0.67, "spi": 0.09, "cost_variance": -10000, "schedule_variance": -198000,
        "eac": 671642, "bac": 450000, "vac": -221642, "pending_change_orders": 6500,
    })
    assert reading[0].startswith("Cost: over budget. CPI 0.67")
    assert reading[1].startswith("Schedule: behind schedule. SPI 0.09")
    assert "$221,642 over" in reading[2] and "$6,500 more is awaiting approval" in reading[2]

    unknown = ai_assistant_service.budget_reading({
        "cpi": None, "spi": None, "cost_variance": 0, "schedule_variance": None,
        "eac": 1000, "bac": 1000, "vac": 0, "pending_change_orders": 0,
    })
    assert "no expenses logged" in unknown[0] and "not baselined" in unknown[1]

"""Project controls: schedule, earned value, change orders, compliance, crew
and equipment (no network calls)."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import ConstructionPhase, Project, Task

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
def project_id():
    """Two phases as the AI plan saves them: $10k over two 2-day + 1-day tasks
    after $30k over one 4-day task."""
    with TestingSessionLocal() as db:
        project = Project(name="Test House", status="planning", estimated_cost=40000)
        db.add(project)
        db.flush()
        site = ConstructionPhase(project_id=project.id, name="Site prep", phase_order=1, budgeted_cost=10000)
        frame = ConstructionPhase(project_id=project.id, name="Framing", phase_order=2, budgeted_cost=30000)
        db.add_all([site, frame])
        db.flush()
        db.add_all([
            Task(project_id=project.id, phase_id=site.id, name="Clear lot", task_order=1, planned_duration_days=2),
            Task(project_id=project.id, phase_id=site.id, name="Stake out", task_order=2, planned_duration_days=1),
            Task(project_id=project.id, phase_id=frame.id, name="Walls", task_order=1, planned_duration_days=4),
        ])
        db.commit()
        return project.id


def _schedule(pid):
    response = client.get(f"/api/v1/projects/{pid}/schedule")
    assert response.status_code == 200
    return response.json()


def _task(schedule, name):
    return next(t for p in schedule["phases"] for t in p["tasks"] if t["name"] == name)


def _set_status(pid, task_id, status):
    response = client.patch(f"/api/v1/projects/{pid}/tasks/{task_id}", json={"status": status})
    assert response.status_code == 200, response.text
    return response.json()


def test_progress_is_earned_with_the_50_50_rule(project_id):
    schedule = _schedule(project_id)
    clear = _task(schedule, "Clear lot")

    phase = _set_status(project_id, clear["id"], "in_progress")["phase"]
    # Half of a 2-day task out of 3 days of work.
    assert phase["progress"] == pytest.approx(33.3)
    assert phase["status"] == "in_progress"
    assert phase["actual_start"] == date.today().isoformat()

    result = _set_status(project_id, clear["id"], "completed")
    assert result["task"]["actual_end"] == date.today().isoformat()
    assert result["phase"]["progress"] == pytest.approx(66.7)

    _set_status(project_id, _task(schedule, "Stake out")["id"], "completed")
    schedule = _schedule(project_id)
    assert schedule["phases"][0]["status"] == "completed"
    # 3 of 7 days of work are done.
    assert schedule["progress"] == pytest.approx(100 * 3 / 7, abs=0.1)
    assert schedule["current_phase"]["name"] == "Framing"


def test_reopening_a_task_clears_its_finish(project_id):
    walls = _task(_schedule(project_id), "Walls")
    _set_status(project_id, walls["id"], "completed")
    result = _set_status(project_id, walls["id"], "in_progress")
    assert result["task"]["actual_end"] is None
    assert result["phase"]["status"] == "in_progress"
    assert result["phase"]["actual_end"] is None


def test_unknown_task_status_is_rejected(project_id):
    walls = _task(_schedule(project_id), "Walls")
    response = client.patch(f"/api/v1/projects/{project_id}/tasks/{walls['id']}", json={"status": "done-ish"})
    assert response.status_code == 422


def test_baseline_lays_phases_end_to_end(project_id):
    start = date(2026, 11, 2)
    response = client.post(f"/api/v1/projects/{project_id}/schedule/baseline", json={"start_date": start.isoformat()})
    assert response.status_code == 200
    schedule = response.json()
    site, frame = schedule["phases"]
    assert site["planned_start"] == "2026-11-02"
    assert site["tasks"][0]["planned_end"] == "2026-11-04"
    assert site["tasks"][1]["planned_start"] == "2026-11-04"
    assert site["planned_end"] == "2026-11-05"
    assert frame["planned_start"] == "2026-11-05"
    assert frame["planned_end"] == "2026-11-09"
    assert schedule["baselined"] is True
    assert schedule["planned_finish"] == "2026-11-09"


def test_task_past_its_planned_end_is_late(project_id):
    start = date.today() - timedelta(days=30)
    client.post(f"/api/v1/projects/{project_id}/schedule/baseline", json={"start_date": start.isoformat()})
    schedule = _schedule(project_id)
    assert _task(schedule, "Walls")["late"] is True
    assert schedule["tasks"]["late"] == 3
    attention = client.get(f"/api/v1/projects/{project_id}/overview").json()["attention"]
    assert any(item["title"] == "Late: Walls" for item in attention)


def test_tasks_can_be_added_and_deleted(project_id):
    site = _schedule(project_id)["phases"][0]
    response = client.post(
        f"/api/v1/projects/{project_id}/phases/{site['id']}/tasks",
        json={"name": "Silt fence", "priority": "high", "planned_duration_days": 1},
    )
    assert response.status_code == 201
    task = response.json()
    assert task["task_order"] == 3 and task["priority"] == "high"

    assert client.delete(f"/api/v1/projects/{project_id}/tasks/{task['id']}").status_code == 200
    assert len(_schedule(project_id)["phases"][0]["tasks"]) == 2


def test_earned_value(project_id):
    budget = client.get(f"/api/v1/projects/{project_id}/budget").json()
    assert budget["bac"] == 40000
    assert budget["earned_value"] == 0
    assert budget["cpi"] is None and budget["planned_value"] is None

    schedule = _schedule(project_id)
    _set_status(project_id, _task(schedule, "Clear lot")["id"], "completed")
    _set_status(project_id, _task(schedule, "Stake out")["id"], "completed")
    site_id = schedule["phases"][0]["id"]
    response = client.post(f"/api/v1/projects/{project_id}/expenses", json={
        "vendor": "Dirt Co", "amount": 8000, "category": "subcontract", "phase_id": site_id,
    })
    assert response.status_code == 201
    assert response.json()["phase_name"] == "Site prep"

    budget = client.get(f"/api/v1/projects/{project_id}/budget").json()
    assert budget["earned_value"] == 10000
    assert budget["actual_cost"] == 8000
    assert budget["cpi"] == 1.25
    assert budget["eac"] == 32000
    assert budget["by_phase"][0]["actual"] == 8000
    assert budget["by_category"] == [{"category": "subcontract", "actual": 8000}]


def test_planned_value_once_baselined(project_id):
    # Site prep (Nov 2-5) is over by Nov 7; Framing (Nov 5-9) is half way.
    client.post(f"/api/v1/projects/{project_id}/schedule/baseline", json={"start_date": "2026-11-02"})
    from app.services import project_controls_service as controls
    with TestingSessionLocal() as db:
        summary = controls.budget_summary(db.get(Project, project_id), date(2026, 11, 7))
    assert summary["planned_value"] == 10000 + 30000 * 0.5
    assert summary["spi"] == 0.0


def test_expense_on_another_projects_phase_is_rejected(project_id):
    response = client.post(f"/api/v1/projects/{project_id}/expenses", json={"vendor": "X", "amount": 5, "phase_id": 999})
    assert response.status_code == 422


def test_approved_change_orders_raise_the_contract_value(project_id):
    base = f"/api/v1/projects/{project_id}/change-orders"
    first = client.post(base, json={"title": "Bay window", "cost_impact": 5000}).json()
    second = client.post(base, json={"title": "Steam shower", "cost_impact": 2000}).json()
    assert (first["code"], second["code"]) == ("CO-001", "CO-002")

    budget = client.get(f"/api/v1/projects/{project_id}/budget").json()
    assert budget["pending_change_orders"] == 7000 and budget["bac"] == 40000

    approved = client.patch(f"{base}/{first['id']}", json={"status": "approved"}).json()
    assert approved["decided_at"] is not None
    budget = client.get(f"/api/v1/projects/{project_id}/budget").json()
    assert budget["bac"] == 45000
    assert budget["approved_change_orders"] == 5000 and budget["pending_change_orders"] == 2000

    assert client.patch(f"{base}/{second['id']}", json={"status": "maybe"}).status_code == 422


def test_permits_and_inspections(project_id):
    base = f"/api/v1/projects/{project_id}"
    permit = client.post(f"{base}/permits", json={
        "permit_number": "BLD-1", "permit_type": "Building", "status": "issued",
        "expiration_date": (date.today() + timedelta(days=10)).isoformat(),
    }).json()
    inspection = client.post(f"{base}/inspections", json={
        "inspection_type": "Framing", "permit_id": permit["id"],
        "scheduled_date": (date.today() + timedelta(days=2)).isoformat() + "T10:00:00",
    })
    assert inspection.status_code == 201
    inspection = inspection.json()
    assert inspection["permit_number"] == "BLD-1"

    compliance = client.get(f"{base}/compliance").json()
    assert compliance["summary"]["permits_active"] == 1
    assert compliance["summary"]["inspections_upcoming"] == 1
    kinds = {a["kind"] for a in client.get(f"{base}/overview").json()["attention"]}
    assert {"inspection_soon", "permit_expiring"} <= kinds

    failed = client.patch(f"{base}/inspections/{inspection['id']}", json={
        "status": "failed", "critical_findings": "Missing hold-downs",
    }).json()
    assert failed["actual_date"] is not None
    summary = client.get(f"{base}/compliance").json()["summary"]
    assert summary["inspections_failed"] == 1 and summary["pass_rate"] == 0
    attention = client.get(f"{base}/overview").json()["attention"]
    assert attention[0]["kind"] == "inspection_failed"


def test_inspection_cannot_use_another_projects_permit(project_id):
    with TestingSessionLocal() as db:
        other = Project(name="Other")
        db.add(other)
        db.commit()
        other_id = other.id
    permit = client.post(f"/api/v1/projects/{other_id}/permits", json={"permit_number": "P-9", "permit_type": "Zoning"}).json()
    response = client.post(f"/api/v1/projects/{project_id}/inspections", json={"inspection_type": "Final", "permit_id": permit["id"]})
    assert response.status_code == 404


def test_overview_without_anything_planned():
    with TestingSessionLocal() as db:
        project = Project(name="Empty")
        db.add(project)
        db.commit()
        pid = project.id
    overview = client.get(f"/api/v1/projects/{pid}/overview").json()
    assert overview["floor_plan"] is None
    assert overview["schedule"]["progress"] == 0
    assert overview["budget"]["bac"] == 0 and overview["budget"]["cpi"] is None
    assert overview["attention"] == []


def test_crew_and_equipment(project_id):
    member = client.post("/api/v1/resources/crew", json={
        "name": "Ana", "role": "Carpenter", "hourly_rate": 48, "project_id": project_id,
    })
    assert member.status_code == 201
    assert member.json()["project_name"] == "Test House"
    assert len(client.get(f"/api/v1/resources/crew?project_id={project_id}").json()["crew"]) == 1

    released = client.patch(f"/api/v1/resources/crew/{member.json()['id']}", json={"project_id": None}).json()
    assert released["project_id"] is None

    item = client.post("/api/v1/resources/equipment", json={
        "name": "Mini excavator", "equipment_type": "Excavator", "daily_rate": 350,
        "next_maintenance_date": "2026-12-01", "project_id": project_id, "status": "in_use",
    }).json()
    assert item["daily_rate"] == 350 and item["next_maintenance_date"] == "2026-12-01"
    assert client.patch(f"/api/v1/resources/equipment/{item['id']}", json={"status": "broken"}).status_code == 422
    assert client.post("/api/v1/resources/crew", json={"name": "B", "role": "X", "project_id": 999}).status_code == 404

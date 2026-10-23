"""Project controls: schedule, earned value, change orders, compliance, crew
and equipment. The construction plan lives in pm-mcp, so these run against a
real pm-mcp server (tests/pm_server.py); no other network calls."""

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import FloorPlan, Project
from app.services import pm_client
from app.services import project_controls_service as controls

from .pm_server import release_pm, unique, use_pm

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


@pytest.fixture(autouse=True)
def pm():
    yield use_pm()
    release_pm()


def _new_project(**fields) -> int:
    with TestingSessionLocal() as db:
        project = Project(name=unique(fields.pop("name", "Test House")), status="planning", **fields)
        db.add(project)
        db.commit()
        return project.id


def _post(url, body, status=201):
    response = client.post(url, json=body)
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture
def project_id():
    """Two phases as the AI plan saves them: $10k over two 2-day + 1-day tasks
    after $30k over one 4-day task."""
    pid = _new_project(estimated_cost=40000)
    base = f"/api/v1/projects/{pid}"
    site = _post(f"{base}/phases", {"name": "Site prep", "budgeted_cost": 10000})
    frame = _post(f"{base}/phases", {"name": "Framing", "budgeted_cost": 30000})
    _post(f"{base}/phases/{site['id']}/tasks", {"name": "Clear lot", "planned_duration_days": 2})
    _post(f"{base}/phases/{site['id']}/tasks", {"name": "Stake out", "planned_duration_days": 1})
    _post(f"{base}/phases/{frame['id']}/tasks", {"name": "Walls", "planned_duration_days": 4})
    return pid


def _schedule(pid):
    response = client.get(f"/api/v1/projects/{pid}/schedule")
    assert response.status_code == 200, response.text
    return response.json()


def _task(schedule, name):
    return next(t for p in schedule["phases"] for t in p["tasks"] if t["name"] == name)


def _set_status(pid, task_id, status, expect=200):
    response = client.patch(f"/api/v1/projects/{pid}/tasks/{task_id}", json={"status": status})
    assert response.status_code == expect, response.text
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


def test_tasks_are_chained_in_order(project_id, pm):
    """The plan is sequential: each task waits on the one before it, across phases."""
    with TestingSessionLocal() as db:
        plan = controls.load_plan(pm, db.get(Project, project_id))
    clear, stake, walls = plan.tasks()
    assert (clear["depends_on"], stake["depends_on"], walls["depends_on"]) == ([], [clear["id"]], [stake["id"]])


def test_baseline_lays_phases_end_to_end(project_id):
    start = date(2026, 11, 2)
    response = client.post(f"/api/v1/projects/{project_id}/schedule/baseline", json={"start_date": start.isoformat()})
    assert response.status_code == 200, response.text
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
    with TestingSessionLocal() as db:
        assert controls.as_date(db.get(Project, project_id).estimated_completion_date) == date(2026, 11, 9)


def test_a_phase_without_tasks_takes_a_week_when_baselined(project_id):
    _post(f"/api/v1/projects/{project_id}/phases", {"name": "Punch & clean"})
    schedule = client.post(f"/api/v1/projects/{project_id}/schedule/baseline", json={"start_date": "2026-11-02"}).json()
    last = schedule["phases"][-1]
    assert (last["planned_start"], last["planned_end"]) == ("2026-11-09", "2026-11-16")


def test_task_past_its_planned_end_is_late(project_id):
    start = date.today() - timedelta(days=30)
    client.post(f"/api/v1/projects/{project_id}/schedule/baseline", json={"start_date": start.isoformat()})
    schedule = _schedule(project_id)
    assert _task(schedule, "Walls")["late"] is True
    assert schedule["tasks"]["late"] == 3
    attention = client.get(f"/api/v1/projects/{project_id}/overview").json()["attention"]
    assert any(item["title"] == "Late: Walls" for item in attention)


def test_tasks_can_be_added_and_deleted(project_id, pm):
    site = _schedule(project_id)["phases"][0]
    task = _post(f"/api/v1/projects/{project_id}/phases/{site['id']}/tasks",
                 {"name": "Silt fence", "priority": "critical", "planned_duration_days": 1})
    assert task["task_order"] == 3 and task["priority"] == "critical"
    # Walls (next phase) now also waits on the new last task of Site prep.
    with TestingSessionLocal() as db:
        plan = controls.load_plan(pm, db.get(Project, project_id))
    assert task["id"] in plan.task(_task(_schedule(project_id), "Walls")["id"])[0]["depends_on"]

    assert client.delete(f"/api/v1/projects/{project_id}/tasks/{task['id']}").status_code == 200
    assert len(_schedule(project_id)["phases"][0]["tasks"]) == 2
    # Deleting a task in the middle keeps the chain.
    stake = _task(_schedule(project_id), "Stake out")
    assert client.delete(f"/api/v1/projects/{project_id}/tasks/{stake['id']}").status_code == 200
    with TestingSessionLocal() as db:
        plan = controls.load_plan(pm, db.get(Project, project_id))
    clear, walls = plan.tasks()
    assert clear["id"] in walls["depends_on"]


def test_other_projects_tasks_and_phases_are_not_found(project_id):
    other = _new_project(name="Other")
    walls = _task(_schedule(project_id), "Walls")
    assert client.patch(f"/api/v1/projects/{other}/tasks/{walls['id']}", json={"status": "completed"}).status_code == 404
    phase_id = _schedule(project_id)["phases"][0]["id"]
    assert client.post(f"/api/v1/projects/{other}/phases/{phase_id}/tasks", json={"name": "x"}).status_code == 404


def test_earned_value(project_id):
    budget = client.get(f"/api/v1/projects/{project_id}/budget").json()
    assert budget["bac"] == 40000
    assert budget["earned_value"] == 0
    assert budget["cpi"] is None and budget["planned_value"] is None

    schedule = _schedule(project_id)
    _set_status(project_id, _task(schedule, "Clear lot")["id"], "completed")
    _set_status(project_id, _task(schedule, "Stake out")["id"], "completed")
    site_id = schedule["phases"][0]["id"]
    expense = _post(f"/api/v1/projects/{project_id}/expenses", {
        "vendor": "Dirt Co", "amount": 8000, "category": "subcontract", "phase_id": site_id,
    })
    assert expense["phase_name"] == "Site prep"

    budget = client.get(f"/api/v1/projects/{project_id}/budget").json()
    assert budget["earned_value"] == 10000
    assert budget["actual_cost"] == 8000
    assert budget["cpi"] == 1.25
    assert budget["eac"] == 32000
    assert budget["by_phase"][0]["actual"] == 8000
    assert budget["by_category"] == [{"category": "subcontract", "actual": 8000}]

    listed = client.get(f"/api/v1/projects/{project_id}/expenses").json()["expenses"]
    assert [e["vendor"] for e in listed] == ["Dirt Co"]
    assert client.delete(f"/api/v1/projects/{project_id}/expenses/{expense['id']}").status_code == 200
    assert client.get(f"/api/v1/projects/{project_id}/budget").json()["actual_cost"] == 0


def test_phase_budget_can_be_changed(project_id):
    site = _schedule(project_id)["phases"][0]
    response = client.patch(f"/api/v1/projects/{project_id}/phases/{site['id']}", json={"budgeted_cost": 12500})
    assert response.status_code == 200, response.text
    assert response.json()["budgeted_cost"] == 12500
    assert client.get(f"/api/v1/projects/{project_id}/budget").json()["bac"] == 42500


def test_planned_value_once_baselined(project_id, pm):
    # Site prep (Nov 2-5) is over by Nov 7; Framing (Nov 5-9) is half way.
    client.post(f"/api/v1/projects/{project_id}/schedule/baseline", json={"start_date": "2026-11-02"})
    with TestingSessionLocal() as db:
        project = db.get(Project, project_id)
        summary = controls.budget_summary(controls.load_plan(pm, project), project, date(2026, 11, 7))
    assert summary["planned_value"] == 10000 + 30000 * 0.5
    assert summary["spi"] == 0.0


def test_expense_on_another_projects_phase_is_rejected(project_id):
    response = client.post(f"/api/v1/projects/{project_id}/expenses", json={"vendor": "X", "amount": 5, "phase_id": 999})
    assert response.status_code == 422


def test_approved_change_orders_raise_the_contract_value(project_id):
    base = f"/api/v1/projects/{project_id}/change-orders"
    first = _post(base, {"title": "Bay window", "cost_impact": 5000})
    second = _post(base, {"title": "Steam shower", "cost_impact": 2000})
    assert (first["code"], second["code"]) == ("CO-001", "CO-002")

    budget = client.get(f"/api/v1/projects/{project_id}/budget").json()
    assert budget["pending_change_orders"] == 7000 and budget["bac"] == 40000

    approved = client.patch(f"{base}/{first['id']}", json={"status": "approved"}).json()
    assert approved["decided_at"] is not None
    budget = client.get(f"/api/v1/projects/{project_id}/budget").json()
    assert budget["bac"] == 45000
    assert budget["approved_change_orders"] == 5000 and budget["pending_change_orders"] == 2000

    assert client.patch(f"{base}/{second['id']}", json={"status": "maybe"}).status_code == 422
    listed = client.get(base).json()["change_orders"]
    assert [c["code"] for c in listed] == ["CO-002", "CO-001"]


def test_permits_and_inspections(project_id):
    base = f"/api/v1/projects/{project_id}"
    permit = _post(f"{base}/permits", {
        "permit_number": "BLD-1", "permit_type": "Building", "status": "approved",
        "expiration_date": (date.today() + timedelta(days=10)).isoformat(),
    })
    assert permit["permit_type"] == "Building" and permit["status"] == "approved"
    inspection = _post(f"{base}/inspections", {
        "inspection_type": "Framing", "permit_id": permit["id"],
        "scheduled_date": (date.today() + timedelta(days=2)).isoformat() + "T10:00:00",
    })
    assert inspection["permit_number"] == "BLD-1" and inspection["status"] == "scheduled"

    compliance = client.get(f"{base}/compliance").json()
    assert compliance["summary"]["permits_active"] == 1
    assert compliance["summary"]["inspections_upcoming"] == 1
    assert "corrections_required" in compliance["statuses"]["permit"]
    kinds = {a["kind"] for a in client.get(f"{base}/overview").json()["attention"]}
    assert {"inspection_soon", "permit_expiring"} <= kinds

    failed = client.patch(f"{base}/inspections/{inspection['id']}", json={
        "status": "failed", "critical_findings": "Missing hold-downs",
    }).json()
    assert failed["actual_date"] is not None and failed["status"] == "failed"
    assert failed["attempts"][-1]["notes"] == "Missing hold-downs"
    summary = client.get(f"{base}/compliance").json()["summary"]
    assert summary["inspections_failed"] == 1 and summary["pass_rate"] == 0
    attention = client.get(f"{base}/overview").json()["attention"]
    assert attention[0]["kind"] == "inspection_failed"

    assert client.patch(f"{base}/permits/{permit['id']}", json={"status": "issued"}).status_code == 422
    assert client.delete(f"{base}/inspections/{inspection['id']}").status_code == 200
    assert client.delete(f"{base}/permits/{permit['id']}").status_code == 200
    assert client.get(f"{base}/compliance").json()["permits"] == []


def test_inspection_gates_its_task(project_id):
    """A task that requires an inspection can't be completed until the
    inspection passes; a failure adds a correction task it then waits on."""
    base = f"/api/v1/projects/{project_id}"
    frame = _schedule(project_id)["phases"][1]
    gate = _post(f"{base}/phases/{frame['id']}/tasks", {"name": "Framing inspection", "requires_inspection": True})
    assert gate["requires_inspection"] is True and gate["kind"] == "inspection"
    inspection = next(i for i in client.get(f"{base}/compliance").json()["inspections"] if i["task_id"] == gate["id"])

    # Walls must finish before the inspection task can start; then it is gated.
    _set_status(project_id, _task(_schedule(project_id), "Walls")["id"], "completed")
    refused = _set_status(project_id, gate["id"], "completed", expect=409)
    assert "inspection" in refused["detail"]

    failed = client.patch(f"{base}/inspections/{inspection['id']}", json={
        "status": "failed", "critical_findings": "Nailing pattern short at shear wall"}).json()
    correction = _task(_schedule(project_id), f"Correct deficiencies: {inspection['title']}")
    assert failed["correction_task"] == correction["id"] and correction["priority"] == "high"

    _set_status(project_id, correction["id"], "completed")
    passed = client.patch(f"{base}/inspections/{inspection['id']}", json={"status": "passed"}).json()
    assert passed["completed_task"] == gate["id"]
    assert _task(_schedule(project_id), "Framing inspection")["status"] == "completed"


def test_inspection_cannot_use_another_projects_permit(project_id):
    other_id = _new_project(name="Other")
    permit = _post(f"/api/v1/projects/{other_id}/permits", {"permit_number": "P-9", "permit_type": "Zoning"})
    assert permit["permit_type"] == "Zoning"  # unknown types keep their label
    response = client.post(f"/api/v1/projects/{project_id}/inspections",
                           json={"inspection_type": "Final", "permit_id": permit["id"]})
    assert response.status_code == 404


def test_overview_without_anything_planned():
    pid = _new_project(name="Empty")
    overview = client.get(f"/api/v1/projects/{pid}/overview").json()
    assert overview["floor_plan"] is None
    assert overview["pm_available"] is True
    assert overview["schedule"]["progress"] == 0
    assert overview["budget"]["bac"] == 0 and overview["budget"]["cpi"] is None
    assert overview["attention"] == []


def test_without_pm_mcp_the_overview_still_answers(project_id):
    down = pm_client.PMClient("http://127.0.0.1:9/mcp", timeout=1)
    pm_client._client = down
    try:
        overview = client.get(f"/api/v1/projects/{project_id}/overview")
        assert overview.status_code == 200
        assert overview.json()["pm_available"] is False
        assert overview.json()["attention"][0]["kind"] == "pm_unavailable"
        assert client.get(f"/api/v1/projects/{project_id}/schedule").status_code == 503
        assert client.get(f"/api/v1/projects/{project_id}/punch-list").status_code == 200
    finally:
        down.close()


def test_templates_can_be_laid_into_a_project():
    pid = _new_project(name="Kitchen")
    templates = client.get(f"/api/v1/projects/{pid}/construction-templates").json()["templates"]
    assert "residential_remodel" in {t["key"] for t in templates}
    result = _post(f"/api/v1/projects/{pid}/construction-plan",
                   {"template": "residential_remodel", "start_date": "2027-02-01"})
    assert result["tasks_created"] > 20 and result["records_created"] > 0
    assert result["phase_count"] == 8 and result["baselined"] is True
    compliance = client.get(f"/api/v1/projects/{pid}/compliance").json()
    assert compliance["permits"] and all(i["task_id"] for i in compliance["inspections"])
    assert client.post(f"/api/v1/projects/{pid}/construction-plan", json={"template": "nope"}).status_code == 404


def test_ai_plan_phases_go_to_pm_mcp(pm):
    pid = _new_project(name="AI house")
    with TestingSessionLocal() as db:
        project = db.get(Project, pid)
        controls.ensure_pm_project(db, pm, project)
        controls.import_ai_phases(pm, controls.load_plan(pm, project), [
            {"name": "Foundation", "estimated_cost": 20000,
             "tasks": [{"name": "Dig", "duration_days": 2}, {"name": "Pour", "duration_days": 3, "estimated_cost": 9000}]},
            {"name": "Framing", "estimated_cost": 30000, "tasks": [{"name": "Walls", "duration_days": 5}]},
        ])
    schedule = _schedule(pid)
    assert [p["name"] for p in schedule["phases"]] == ["Foundation", "Framing"]
    assert schedule["phases"][0]["budgeted_cost"] == 20000
    assert _task(schedule, "Pour")["budgeted_cost"] == 9000
    baselined = client.post(f"/api/v1/projects/{pid}/schedule/baseline", json={"start_date": "2027-01-04"}).json()
    assert baselined["planned_finish"] == "2027-01-14"  # 2 + 3 + 5 days end to end


def test_project_is_linked_in_pm_mcp(pm):
    # An id no other test uses: the pm-mcp server outlives each test's database.
    pid = _new_project(id=900_000 + int(uuid.uuid4().int % 99_999))
    assert client.get(f"/api/v1/projects/{pid}/schedule").status_code == 200
    with TestingSessionLocal() as db:
        project = db.get(Project, pid)
    links = pm.call("find_external", system=pm_client.SYSTEM, external_id=str(pid))
    assert [(l["entity_type"], l["entity_id"]) for l in links] == [("project", project.pm_project_id)]
    assert pm.call("export_project", project_id=project.pm_project_id)["project"]["details"]["vr_project_id"] == pid


def test_punch_items_are_copied_to_pm_mcp(project_id, pm):
    with TestingSessionLocal() as db:
        db.add(FloorPlan(project_id=project_id, version=1, name="Test House", change_type="generated",
                         layout={"length": 30, "width": 20}, rooms=[{"name": "Kitchen"}]))
        db.commit()
    phase = _schedule(project_id)["phases"][1]
    item = _post(f"/api/v1/projects/{project_id}/punch-items",
                 {"title": "Outlet cover missing", "room": "Kitchen", "trade": "electrical", "phase_id": phase["id"]})
    assert item["phase_name"] == "Framing"
    client.patch(f"/api/v1/projects/{project_id}/punch-items/{item['id']}", json={"status": "ready"})
    with TestingSessionLocal() as db:
        project = db.get(Project, project_id)
        records = controls.load_plan(pm, project).of_type("punch_item")
    assert [(r["title"], r["status"], r["data"]["location"], r["milestone_id"]) for r in records] == [
        ("Outlet cover missing", "ready_for_review", "Kitchen", phase["id"])]
    assert client.get(f"/api/v1/projects/{project_id}/punch-list").json()["phases"][1]["name"] == "Framing"

    client.delete(f"/api/v1/projects/{project_id}/punch-items/{item['id']}")
    with TestingSessionLocal() as db:
        assert controls.load_plan(pm, db.get(Project, project_id)).of_type("punch_item") == []


def test_deleting_a_project_archives_its_plan(project_id, pm):
    with TestingSessionLocal() as db:
        pm_id = db.get(Project, project_id).pm_project_id
    assert client.delete(f"/api/v1/projects/{project_id}").status_code == 200
    assert pm.call("export_project", project_id=pm_id)["project"]["status"] == "archived"


def test_crew_and_equipment(project_id):
    member = client.post("/api/v1/resources/crew", json={
        "name": "Ana", "role": "Carpenter", "hourly_rate": 48, "project_id": project_id,
    })
    assert member.status_code == 201
    assert member.json()["project_name"].startswith("Test House")
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

"""Punch list: items per project, the open → ready → closed workflow, the
summary, and what it adds to the overview's attention list. Punch items live
here; their phases are in pm-mcp, so these use the test pm-mcp server
(tests/pm_server.py); no other network calls."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import FloorPlan, Project

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


@pytest.fixture
def project_id():
    """A project with one phase and a floor plan of two rooms."""
    with TestingSessionLocal() as db:
        project = Project(name=unique("Test House"), status="active")
        db.add(project)
        db.flush()
        db.add(FloorPlan(
            project_id=project.id, version=1, name="Test House", change_type="generated",
            layout={"length": 30, "width": 20}, rooms=[{"name": "Kitchen"}, {"name": "Primary Bedroom"}],
        ))
        db.commit()
        pid = project.id
    response = client.post(f"/api/v1/projects/{pid}/phases", json={"name": "Finishes"})
    assert response.status_code == 201, response.text
    return pid


def _add(pid, **fields):
    response = client.post(f"/api/v1/projects/{pid}/punch-items", json={"title": "Touch up paint", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def _list(pid):
    response = client.get(f"/api/v1/projects/{pid}/punch-list")
    assert response.status_code == 200, response.text
    return response.json()


def test_items_are_numbered_per_project_and_list_offers_floor_plan_rooms(project_id):
    first = _add(project_id, room="Kitchen", trade="paint")
    second = _add(project_id, title="Cabinet door rubs", room="Kitchen", trade="cabinets")
    assert (first["code"], second["code"]) == ("PL-001", "PL-002")
    assert first["status"] == "open" and first["closed_at"] is None

    data = _list(project_id)
    assert data["rooms"] == ["Kitchen", "Primary Bedroom"]
    assert "electrical" in data["trades"]
    assert data["summary"]["open"] == 2
    assert data["summary"]["open_by_room"] == [{"room": "Kitchen", "open": 2}]


def test_closing_records_when_and_reopening_clears_it(project_id):
    item = _add(project_id)
    url = f"/api/v1/projects/{project_id}/punch-items/{item['id']}"

    ready = client.patch(url, json={"status": "ready"}).json()
    assert ready["status"] == "ready" and ready["closed_at"] is None

    closed = client.patch(url, json={"status": "closed"}).json()
    assert closed["closed_at"] is not None

    reopened = client.patch(url, json={"status": "open"}).json()
    assert reopened["closed_at"] is None

    summary = _list(project_id)["summary"]
    assert (summary["open"], summary["closed"], summary["percent_closed"]) == (1, 0, 0.0)


def test_list_puts_open_urgent_items_first_and_closed_last(project_id):
    low = _add(project_id, title="Low", priority="low")
    done = _add(project_id, title="Done", priority="critical", status="closed")
    soon = _add(project_id, title="High soon", priority="high", due_date=date.today().isoformat())
    later = _add(project_id, title="High later", priority="high", due_date=(date.today() + timedelta(days=9)).isoformat())
    crit = _add(project_id, title="Critical", priority="critical")

    order = [i["id"] for i in _list(project_id)["items"]]
    assert order == [crit["id"], soon["id"], later["id"], low["id"], done["id"]]


def test_rejects_unknown_values_and_other_projects_items(project_id):
    url = f"/api/v1/projects/{project_id}/punch-items"
    assert client.post(url, json={"title": "x", "trade": "astrology"}).status_code == 422
    assert client.post(url, json={"title": "x", "status": "done"}).status_code == 422
    assert client.post(url, json={"title": "x", "phase_id": 999}).status_code == 404

    with TestingSessionLocal() as db:
        other = Project(name=unique("Other"))
        db.add(other)
        db.commit()
        other_id = other.id
    item = _add(project_id)
    assert client.patch(f"/api/v1/projects/{other_id}/punch-items/{item['id']}", json={"status": "closed"}).status_code == 404
    assert client.delete(f"/api/v1/projects/{other_id}/punch-items/{item['id']}").status_code == 404

    assert client.delete(f"{url}/{item['id']}").json() == {"deleted": item["id"]}
    assert _list(project_id)["items"] == []


def test_overdue_and_ready_items_each_add_one_attention_line(project_id):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _add(project_id, title="Missing outlet cover", due_date=yesterday)
    _add(project_id, title="Grout haze", due_date=yesterday)
    _add(project_id, title="Closed late one", due_date=yesterday, status="closed")
    _add(project_id, title="Door stop", status="ready")

    overview = client.get(f"/api/v1/projects/{project_id}/overview").json()
    assert overview["punch_list"]["overdue"] == 2
    punch = {a["kind"]: a for a in overview["attention"] if a["kind"].startswith("punch_")}
    assert punch["punch_overdue"]["title"] == "2 punch items overdue"
    assert punch["punch_overdue"]["severity"] == "high"
    assert punch["punch_ready"]["title"] == "1 punch item ready for sign-off"
    assert punch["punch_ready"]["route"] == "/punch-list"


def test_items_go_with_their_project(project_id):
    _add(project_id)
    assert client.delete(f"/api/v1/projects/{project_id}").status_code in (200, 204)
    with TestingSessionLocal() as db:
        from app.models import PunchItem
        assert db.query(PunchItem).count() == 0

"""Saved kitchen styles: the API, and houses whose kitchens are drawn in one."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import PlantModel
from app.services import kitchen_style_service

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def _stove() -> int:
    db = TestingSessionLocal()
    m = PlantModel(kind="furniture", name="Stove and microwave", source="photo", status="ready", model_path="9/m.glb")
    db.add(m)
    db.commit()
    return m.id


def test_styles_are_made_cleaned_edited_and_deleted():
    stove = _stove()
    r = client.post("/api/v1/kitchen-styles", json={"name": " Byron's  kitchen ", "style": {
        "cabinet": "cream", "door": "Raised", "uppers": "glass", "top": "#1b1b1d", "fleck": "#8f8a80",
        "backsplash": "mosaic", "backsplash_color": "4a5058", "crown": True, "stove_model_id": stove, "bogus": 1}})
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["name"] == "Byron's kitchen" and s["door"] == "raised" and s["backsplash_color"] == "#4a5058"
    assert s["cabinet"].startswith("#") and s["stove_model_id"] == stove and "bogus" not in s
    assert s["handle"] == kitchen_style_service.DEFAULT_STYLE["handle"]  # what wasn't given keeps the default

    # Names are unique however they are written; a model must be furniture in the library.
    assert client.post("/api/v1/kitchen-styles", json={"name": "byrons kitchen"}).status_code == 422
    assert client.post("/api/v1/kitchen-styles", json={"name": "Other", "style": {"fridge_model_id": 999}}).status_code == 422

    r = client.put(f"/api/v1/kitchen-styles/{s['id']}", json={"style": {"door": "shaker", "fleck": None}})
    assert r.json()["door"] == "shaker" and r.json()["fleck"] is None and r.json()["uppers"] == "glass"
    listing = client.get("/api/v1/kitchen-styles").json()
    assert [x["name"] for x in listing["styles"]] == ["Byron's kitchen"] and "raised" in listing["choices"]["door"]

    assert client.delete(f"/api/v1/kitchen-styles/{s['id']}").status_code == 200
    assert client.get("/api/v1/kitchen-styles").json()["styles"] == []
    assert client.delete(f"/api/v1/kitchen-styles/{s['id']}").status_code == 404


def test_a_deleted_appliance_model_is_dropped_from_the_style_houses_use():
    stove = _stove()
    client.post("/api/v1/kitchen-styles", json={"name": "Byron's kitchen", "style": {"stove_model_id": stove}})
    db = TestingSessionLocal()
    assert kitchen_style_service.ready_styles(db)[0]["stove_model_id"] == stove
    db.delete(db.get(PlantModel, stove))
    db.commit()
    assert kitchen_style_service.ready_styles(db)[0]["stove_model_id"] is None

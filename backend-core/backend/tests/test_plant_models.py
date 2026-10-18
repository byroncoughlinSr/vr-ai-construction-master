"""3D plant models from photos: the library API, the job, normalising the model,
and houses that use it. The image-to-3D provider is faked (no network calls)."""

import asyncio
import io

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import ai_planning
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import PlantModel
from app.services import floor_plan_service, plant_model_service
from app.services.example_floor_plans import seed_example
from app.services.plant_model_service import (
    PlantModelError,
    Provider,
    ReplicateProvider,
    _find_model_url,
    normalize_glb,
)

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


class FakeProvider(Provider):
    """Returns a z-up box 0.5 × 0.4 wide and 2 tall, standing off the origin."""

    name = "fake"
    up_axis = "z"

    def __init__(self, fail: str | None = None):
        self.fail = fail
        self.images = []

    def problem(self):
        return None

    async def reconstruct(self, image, workdir):
        self.images.append(image)
        if self.fail:
            raise PlantModelError(self.fail)
        box = trimesh.creation.box(extents=[0.5, 0.4, 2.0])
        box.apply_translation([3.0, 1.0, 5.0])
        out = workdir / "raw.glb"
        out.write_bytes(trimesh.Scene(box).export(file_type="glb"))
        return out


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(ai_planning, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(plant_model_service, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(settings, "plant_models_dir", str(tmp_path / "plant_models"))
    monkeypatch.setattr(settings, "plant_model_up_axis", None)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def provider(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(plant_model_service, "get_provider", lambda: fake)
    return fake


@pytest.fixture
def started(monkeypatch):
    """Model ids whose job was started (run by hand with ``_run``)."""
    ids = []
    monkeypatch.setattr(plant_model_service, "start", ids.append)
    return ids


def _photo(fmt="PNG", size=(1600, 1200), mode="RGB") -> bytes:
    out = io.BytesIO()
    Image.new(mode, size, (200, 80, 90, 255) if mode == "RGBA" else (200, 80, 90)).save(out, format=fmt)
    return out.getvalue()


def _run(model_id):
    asyncio.run(plant_model_service.run_job(model_id))


def _add(name="Coral rose", **form):
    files = {"photo": ("rose.png", _photo(), "image/png")} if "photo" not in form else form.pop("photo")
    return client.post("/api/v1/plants/models", data={"name": name, **form}, files=files)


def test_a_photo_becomes_a_normalised_model(provider, started):
    response = _add(height_ft="4")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending" and body["source"] == "photo"
    assert body["image_url"] == f"/plant_models/{body['id']}/source.jpg"
    assert started == [body["id"]]

    _run(body["id"])
    model = client.get(f"/api/v1/plants/models/{body['id']}").json()
    assert model["status"] == "ready", model["error"]
    assert model["provider"] == "fake"
    assert model["model_url"].startswith(f"/plant_models/{body['id']}/model-")
    assert model["aspect"] == pytest.approx(0.25)  # 0.5 wide / 2 tall, once z is turned up
    # The photo was shrunk to a JPEG before it was sent.
    sent = Image.open(provider.images[0])
    assert sent.format == "JPEG" and max(sent.size) == 1024

    glb = trimesh.load(settings.plant_models_dir + model["model_url"][len("/plant_models"):], force="scene")
    lo, hi = glb.bounds
    assert hi[1] - lo[1] == pytest.approx(1.0)
    assert lo[1] == pytest.approx(0.0, abs=1e-6)
    assert np.allclose([(lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2], 0, atol=1e-6)


def test_a_description_is_drawn_first(provider, started, monkeypatch):
    drawn = []

    async def draw(description, out):
        drawn.append(description)
        out.write_bytes(_photo("JPEG", (512, 512)))
        return out

    monkeypatch.setattr(plant_model_service, "image_from_description", draw)
    body = _add("Coral rose", photo={}, description="coral Knock Out rose bush in bloom").json()
    assert body["source"] == "description" and body["image_url"] is None
    _run(body["id"])
    model = client.get(f"/api/v1/plants/models/{body['id']}").json()
    assert model["status"] == "ready"
    assert drawn == ["coral Knock Out rose bush in bloom"]
    assert model["image_url"] == f"/plant_models/{body['id']}/source.jpg"


def test_a_failure_is_kept_with_its_reason_and_can_be_retried(monkeypatch, started):
    fake = FakeProvider(fail="Replicate failed: out of credit")
    monkeypatch.setattr(plant_model_service, "get_provider", lambda: fake)
    model_id = _add().json()["id"]
    _run(model_id)
    model = client.get(f"/api/v1/plants/models/{model_id}").json()
    assert (model["status"], model["error"]) == ("failed", "Replicate failed: out of credit")
    assert model["model_url"] is None

    fake.fail = None
    assert client.post(f"/api/v1/plants/models/{model_id}/retry").status_code == 202
    _run(model_id)
    assert client.get(f"/api/v1/plants/models/{model_id}").json()["status"] == "ready"


@pytest.mark.parametrize("form, detail", [
    ({"photo": {}}, "add a photo"),
    ({"photo": {"photo": ("x.png", b"not an image", "image/png")}}, "not an image"),
    ({"height_ft": "900"}, "height"),
])
def test_bad_requests_are_refused(provider, started, form, detail):
    response = _add(**form)
    assert response.status_code == 422
    assert detail in response.json()["detail"]
    assert started == []


def test_nothing_is_started_without_a_provider(monkeypatch, started):
    monkeypatch.setattr(settings, "plant_model_provider", "replicate")
    monkeypatch.setattr(settings, "replicate_api_token", None)
    response = _add()
    assert response.status_code == 503
    assert "REPLICATE_API_TOKEN" in response.json()["detail"]
    listing = client.get("/api/v1/plants/models").json()
    assert listing["provider"] == "replicate" and listing["provider_ready"] is False


def test_a_job_cut_off_by_a_restart_shows_as_failed(provider, started):
    model_id = _add().json()["id"]  # started, but never run
    plant_model_service._active.discard(model_id)
    model = client.get("/api/v1/plants/models").json()["models"][0]
    assert model["status"] == "failed" and "restart" in model["error"]


def test_delete_removes_the_files(provider, started):
    model_id = _add().json()["id"]
    _run(model_id)
    folder = plant_model_service.model_folder(model_id)
    assert folder.exists()
    assert client.delete(f"/api/v1/plants/models/{model_id}").status_code == 200
    assert not folder.exists()
    assert client.get(f"/api/v1/plants/models/{model_id}").status_code == 404


def test_houses_that_name_the_plant_draw_the_model(provider, started, monkeypatch):
    model_id = _add("Coral rose").json()["id"]
    _run(model_id)
    with TestingSessionLocal() as db:
        project_id = seed_example(db).id
        plan = floor_plan_service.current_floor_plan(db, project_id)
        floor_plan_service.update_exterior(db, plan, {"landscape": [
            {"type": "shrub", "plant": "coral roses", "x": 4, "z": -6},
            {"type": "shrub", "plant": "boxwood", "x": 10, "z": -6},
        ]})
        db.commit()
    exterior = client.get(f"/api/v1/projects/{project_id}/generate-vr").json()["geometry"]["exterior"]
    assert [m["model_id"] for m in exterior["models"]] == [model_id]
    assert len(exterior["plants"]) == 1  # the boxwood is drawn

    # The refine prompt's SITE names the plants that have models.
    seen = {}

    async def refine(structure, instruction, site=None):
        seen.update(site)
        return {"success": True, "plan": {"scope": "exterior", "exterior": structure["exterior"]}, "source": "groq"}

    monkeypatch.setattr(ai_planning.planning_service, "refine_floor_plan", refine)
    client.post(f"/api/v1/projects/{project_id}/floor-plan/refine", json={"instruction": "more coral roses"})
    assert seen["plant_models"] == ["Coral rose"]


def test_normalize_turns_z_up_models_and_rejects_empty_ones(tmp_path):
    box = trimesh.creation.box(extents=[1.0, 1.0, 4.0])
    raw = tmp_path / "raw.glb"
    raw.write_bytes(trimesh.Scene(box).export(file_type="glb"))
    info = normalize_glb(raw, tmp_path / "y.glb", up_axis="y")
    assert info["aspect"] == pytest.approx(4.0)  # left as it was: lying down
    info = normalize_glb(raw, tmp_path / "z.glb", up_axis="z")
    assert info["aspect"] == pytest.approx(0.25) and info["triangles"] == 12
    (tmp_path / "bad.glb").write_bytes(b"nope")
    with pytest.raises(PlantModelError):
        normalize_glb(tmp_path / "bad.glb", tmp_path / "out.glb")


def test_replicate_output_and_input_shapes(monkeypatch):
    output = {"color_video": "https://x/v.mp4", "model_file": "https://x/out/model.glb?sig=1"}
    assert _find_model_url(output) == "https://x/out/model.glb?sig=1"
    assert _find_model_url(["https://x/a.png", "https://x/b.obj"]) == "https://x/b.obj"
    assert _find_model_url({"video": "https://x/v.mp4"}) is None
    monkeypatch.setattr(settings, "replicate_3d_model", "firtoz/trellis")
    monkeypatch.setattr(settings, "replicate_3d_input", '{"texture_size": 2048}')
    data = ReplicateProvider()._input("https://x/photo.jpg")
    assert data["images"] == ["https://x/photo.jpg"] and data["generate_model"] is True
    assert data["texture_size"] == 2048
    monkeypatch.setattr(settings, "replicate_3d_model", "someone/image-to-3d:abc123")
    monkeypatch.setattr(settings, "replicate_3d_input", None)
    assert ReplicateProvider()._input("u") == {"image": "u"}

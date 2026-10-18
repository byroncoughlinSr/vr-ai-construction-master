"""3D models of real plants, made from a photo (or a description).

The procedural plants in ``vr_plants`` look like *a* rose; this makes *that* rose:
someone uploads a photo of the plant they bought (or describes it, and Stable
Diffusion draws it), an image-to-3D model turns it into a textured ``.glb``, and
every plan that names the plant ("coral rose") draws the model instead.

Providers (``settings.plant_model_provider``):

- ``replicate``: a hosted image-to-3D model (``settings.replicate_3d_model``,
  TRELLIS by default). Needs ``REPLICATE_API_TOKEN``; the photo leaves the machine.
- ``triposr``: TripoSR (MIT) run as a subprocess from a local clone
  (``settings.triposr_dir``). No GPU is needed, but on a CPU it takes minutes and
  several GB of RAM, so it runs one model at a time.

Whatever comes back is normalised (``normalize_glb``) to stand 1 m tall with its
base centred on the origin, so the headset scales it by the plant's height.
Files: ``<plant_models_dir>/<id>/source.jpg`` and ``model-<n>.glb``, served under
``/plant_models``.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import math
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..background import run_in_background
from ..config import settings
from ..database import SessionLocal
from ..models.plant_model import PlantModel

logger = logging.getLogger(__name__)

MAX_PHOTO_BYTES = 15 * 1024 * 1024
PHOTO_MAX_SIDE = 1024
URL_PREFIX = "/plant_models"

# One model at a time: TripoSR on a CPU needs most of the machine's memory, and
# Replicate bills per run.
_lock = asyncio.Lock()
_active: set[int] = set()


class PlantModelError(Exception):
    """A model could not be made; the message says why, for the dashboard."""


# --- Files ----------------------------------------------------------------------

def models_root() -> Path:
    return Path(settings.plant_models_dir)


def model_folder(model_id: int) -> Path:
    return models_root() / str(model_id)


def file_url(relative: str | None) -> str | None:
    return f"{URL_PREFIX}/{relative}" if relative else None


def prepare_photo(data: bytes) -> bytes:
    """The photo as a JPEG at most ``PHOTO_MAX_SIDE`` px on a side (transparent
    parts on white). Raises PlantModelError when it is not an image."""
    from PIL import Image, ImageOps

    if not data:
        raise PlantModelError("the photo is empty")
    if len(data) > MAX_PHOTO_BYTES:
        raise PlantModelError(f"the photo is over {MAX_PHOTO_BYTES // (1024 * 1024)} MB")
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)
    except Exception as e:
        raise PlantModelError(f"that is not an image the server can read ({e})")
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1])
        image = background
    else:
        image = image.convert("RGB")
    image.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=90)
    return out.getvalue()


def normalize_glb(raw: Path, out: Path, up_axis: str = "y") -> dict:
    """Stand the model up (y up), centre its base on the origin, make it 1 m tall,
    and write it as ``out``. Returns ``{"aspect": width / height, "triangles": n}``."""
    import numpy as np
    import trimesh

    try:
        scene = trimesh.load(str(raw), force="scene")
    except Exception as e:
        raise PlantModelError(f"the 3D model could not be read ({e})")
    if not scene.geometry:
        raise PlantModelError("the 3D model is empty")
    if up_axis == "z":
        scene.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
    lo, hi = scene.bounds
    size = hi - lo
    if size[1] <= 1e-6:
        raise PlantModelError("the 3D model is flat")
    move = trimesh.transformations.translation_matrix([-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2])
    scale = np.eye(4)
    scale[:3, :3] *= 1.0 / size[1]
    scene.apply_transform(scale @ move)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(scene.export(file_type="glb"))
    triangles = sum(len(g.faces) for g in scene.geometry.values() if hasattr(g, "faces"))
    return {"aspect": round(float(max(size[0], size[2]) / size[1]), 3), "triangles": int(triangles)}


# --- Providers --------------------------------------------------------------------

class Provider:
    name = "none"
    up_axis = "y"  # which way is up in what it returns

    def problem(self) -> str | None:
        """Why it cannot run, or None when it is ready."""
        return "3D plant models are turned off (PLANT_MODEL_PROVIDER=none)"

    async def reconstruct(self, image: Path, workdir: Path) -> Path:
        """Turn ``image`` into a 3D model file in ``workdir``; returns its path."""
        raise PlantModelError(self.problem() or "not available")


class ReplicateProvider(Provider):
    """A hosted image-to-3D model on Replicate (https://replicate.com)."""

    name = "replicate"
    API = "https://api.replicate.com/v1"
    POLL_SECONDS = 3.0

    def problem(self) -> str | None:
        if not settings.replicate_api_token:
            return "set REPLICATE_API_TOKEN in the backend's .env to make 3D models on Replicate"
        return None

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {settings.replicate_api_token}"}

    def _input(self, image_url: str) -> dict:
        model = settings.replicate_3d_model.lower()
        if "trellis" in model:
            data: dict[str, Any] = {
                "images": [image_url], "generate_model": True, "texture_size": 1024, "mesh_simplify": 0.95,
            }
        else:
            data = {"image": image_url}
        if settings.replicate_3d_input:
            try:
                data.update(json.loads(settings.replicate_3d_input))
            except ValueError:
                logger.warning("⚠️  REPLICATE_3D_INPUT is not a JSON object; ignored")
        return data

    async def _version(self, client) -> str:
        model = settings.replicate_3d_model
        if ":" in model:
            return model.split(":", 1)[1]
        r = await client.get(f"{self.API}/models/{model}", headers=self._headers())
        if r.status_code != 200:
            raise PlantModelError(f"Replicate has no model '{model}' ({r.status_code})")
        version = (r.json().get("latest_version") or {}).get("id")
        if not version:
            raise PlantModelError(f"Replicate model '{model}' has no published version")
        return version

    async def _upload(self, client, image: Path) -> str:
        r = await client.post(
            f"{self.API}/files", headers=self._headers(),
            files={"content": (image.name, image.read_bytes(), "image/jpeg")},
        )
        if r.status_code in (200, 201):
            url = (r.json().get("urls") or {}).get("get")
            if url:
                return url
        logger.warning(f"⚠️  Replicate file upload failed ({r.status_code}); sending the photo inline")
        return "data:image/jpeg;base64," + base64.b64encode(image.read_bytes()).decode()

    async def reconstruct(self, image: Path, workdir: Path) -> Path:
        import httpx

        if self.problem():
            raise PlantModelError(self.problem())
        deadline = time.monotonic() + settings.plant_model_timeout_seconds
        async with httpx.AsyncClient(timeout=60.0) as client:
            version = await self._version(client)
            image_url = await self._upload(client, image)
            r = await client.post(
                f"{self.API}/predictions", headers=self._headers(),
                json={"version": version, "input": self._input(image_url)},
            )
            if r.status_code not in (200, 201):
                raise PlantModelError(f"Replicate refused the job ({r.status_code}): {r.text[:300]}")
            prediction = r.json()
            logger.info(f"🌱 Replicate prediction {prediction.get('id')} started ({settings.replicate_3d_model})")
            while prediction.get("status") not in ("succeeded", "failed", "canceled"):
                if time.monotonic() > deadline:
                    raise PlantModelError("Replicate took too long")
                await asyncio.sleep(self.POLL_SECONDS)
                r = await client.get(prediction["urls"]["get"], headers=self._headers())
                if r.status_code == 200:
                    prediction = r.json()
            if prediction["status"] != "succeeded":
                raise PlantModelError(f"Replicate {prediction['status']}: {prediction.get('error') or 'no reason given'}")
            url = _find_model_url(prediction.get("output"))
            if not url:
                raise PlantModelError("Replicate returned no 3D model file")
            r = await client.get(url, follow_redirects=True, timeout=120.0)
            if r.status_code != 200:
                raise PlantModelError(f"could not download the model from Replicate ({r.status_code})")
        raw = workdir / ("raw" + Path(url.split("?")[0]).suffix.lower())
        raw.write_bytes(r.content)
        return raw


def _find_model_url(output: Any) -> str | None:
    """The first .glb (else .obj/.ply) link anywhere in a prediction's output."""
    found: list[str] = []

    def walk(value: Any):
        if isinstance(value, str) and value.startswith("http"):
            found.append(value)
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                walk(v)

    walk(output)
    for ext in (".glb", ".gltf", ".obj"):
        for url in found:
            if url.split("?")[0].lower().endswith(ext):
                return url
    return None


class TripoSRProvider(Provider):
    """TripoSR (https://github.com/VAST-AI-Research/TripoSR) run from a local clone."""

    name = "triposr"
    up_axis = "z"  # its meshes come out z-up (its demo app turns them for display)

    def _dir(self) -> Path | None:
        return Path(settings.triposr_dir).expanduser() if settings.triposr_dir else None

    def problem(self) -> str | None:
        folder = self._dir()
        if not folder:
            return "set TRIPOSR_DIR to a clone of github.com/VAST-AI-Research/TripoSR to make 3D models locally"
        if not (folder / "run.py").is_file():
            return f"TRIPOSR_DIR ({folder}) has no run.py"
        return None

    async def _run(self, image: Path, out: Path, bake: bool) -> tuple[int, str]:
        cmd = [
            settings.triposr_python or sys.executable, "run.py", str(image.resolve()),
            "--output-dir", str(out.resolve()), "--mc-resolution", str(settings.triposr_mc_resolution),
            "--model-save-format", "glb",
        ]
        if bake:
            cmd += ["--bake-texture", "--texture-resolution", "1024"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(self._dir()), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        try:
            output, _ = await asyncio.wait_for(proc.communicate(), timeout=settings.plant_model_timeout_seconds)
        except asyncio.TimeoutError:
            proc.kill()
            raise PlantModelError("TripoSR took too long")
        return proc.returncode, output.decode(errors="replace")[-800:]

    async def reconstruct(self, image: Path, workdir: Path) -> Path:
        if self.problem():
            raise PlantModelError(self.problem())
        out = workdir / "triposr"
        bake = settings.triposr_bake_texture
        code, log = await self._run(image, out, bake)
        if code != 0 and bake:
            # Texture baking needs an OpenGL context, which a headless server may not have.
            logger.warning(f"⚠️  TripoSR texture baking failed, retrying with vertex colors: {log[-200:]}")
            shutil.rmtree(out, ignore_errors=True)
            code, log = await self._run(image, out, False)
        if code != 0:
            raise PlantModelError(f"TripoSR failed: {log[-300:]}")
        return _triposr_result(out / "0")


def _triposr_result(folder: Path) -> Path:
    """TripoSR's mesh as one file: a baked texture is written beside an .obj."""
    glb = folder / "mesh.glb"
    if glb.is_file():
        return glb
    obj, texture = folder / "mesh.obj", folder / "texture.png"
    if not obj.is_file():
        raise PlantModelError("TripoSR wrote no mesh")
    if not texture.is_file():
        return obj
    import trimesh
    from PIL import Image

    mesh = trimesh.load(str(obj), force="mesh", process=False)
    uv = getattr(mesh.visual, "uv", None)
    if uv is not None:
        mesh.visual = trimesh.visual.TextureVisuals(uv=uv, image=Image.open(texture))
    combined = folder / "mesh-textured.glb"
    combined.write_bytes(trimesh.Scene(mesh).export(file_type="glb"))
    return combined


PROVIDERS = {"replicate": ReplicateProvider, "triposr": TripoSRProvider}


def get_provider() -> Provider:
    return PROVIDERS.get((settings.plant_model_provider or "none").strip().lower(), Provider)()


def provider_status() -> dict:
    provider = get_provider()
    problem = provider.problem()
    return {"provider": provider.name, "provider_ready": problem is None, "provider_problem": problem}


# --- Pictures from descriptions -------------------------------------------------------

async def image_from_description(description: str, out: Path) -> Path:
    """Draw the plant with Stable Diffusion, whole and on plain white, for the 3D model."""
    from . import get_image_service

    prompt = (
        f"{description}, a single whole plant, full plant visible from the ground up, side view, "
        "isolated on a plain white background, product photo, sharp focus, natural colors"
    )
    result = await get_image_service().generate_image(
        prompt=prompt,
        negative_prompt="cropped, multiple plants, cut off, text, watermark, people, hands, blurry, dark background",
        width=512, height=512, num_inference_steps=30, guidance_scale=7.5,
        generation_id=f"plant-{uuid.uuid4().hex[:8]}",
    )
    if not result.get("success") or not result.get("images"):
        raise PlantModelError(f"could not draw the plant: {result.get('error', 'no image')}")
    out.write_bytes(prepare_photo(Path(result["images"][0]["path"]).read_bytes()))
    return out


# --- The library ------------------------------------------------------------------

def serialize(model: PlantModel) -> dict:
    return {
        "id": model.id,
        "name": model.name,
        "description": model.description,
        "source": model.source,
        "provider": model.provider,
        "status": model.status,
        "error": model.error,
        "height_ft": model.height_ft,
        "aspect": model.aspect,
        "triangles": model.triangles,
        "image_url": file_url(model.image_path),
        "model_url": file_url(model.model_path) if model.status == "ready" else None,
        "created_at": model.created_at.isoformat() if model.created_at else None,
    }


def list_models(db: Session) -> list[PlantModel]:
    models = db.query(PlantModel).order_by(PlantModel.name, PlantModel.id).all()
    # A job this process is not running was cut off by a restart.
    stale = [m for m in models if m.status in ("pending", "generating") and m.id not in _active]
    for m in stale:
        m.status, m.error = "failed", "interrupted by a server restart; try again"
    if stale:
        db.commit()
    return models


def ready_models(db: Session) -> list[dict]:
    """The finished models, as ``vr_exterior.build_exterior`` takes them."""
    return [
        {"id": m.id, "name": m.name, "url": file_url(m.model_path), "aspect": m.aspect, "height_ft": m.height_ft}
        for m in db.query(PlantModel).filter(PlantModel.status == "ready").order_by(PlantModel.id.desc()).all()
        if m.model_path
    ]


def create(
    db: Session, name: str, photo: bytes | None = None, description: str | None = None,
    height_ft: float | None = None,
) -> PlantModel:
    """Add a plant to the library (committed); ``start`` then makes its model."""
    name = " ".join(str(name or "").split())[:120]
    description = " ".join(str(description or "").split())[:500] or None
    if not name:
        raise PlantModelError("give the plant a name, e.g. 'Coral rose'")
    if not photo and not description:
        raise PlantModelError("add a photo of the plant or describe it")
    jpeg = prepare_photo(photo) if photo else None
    if height_ft is not None and not (0.1 <= height_ft <= 150):
        raise PlantModelError("the height should be between 0.1 and 150 ft")
    model = PlantModel(
        name=name, description=description, source="photo" if jpeg else "description",
        status="pending", height_ft=height_ft,
    )
    db.add(model)
    db.flush()
    if jpeg:
        folder = model_folder(model.id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "source.jpg").write_bytes(jpeg)
        model.image_path = f"{model.id}/source.jpg"
    db.commit()
    db.refresh(model)
    logger.info(f"🌱 Plant model {model.id} '{model.name}' added (from {model.source})")
    return model


def delete(db: Session, model: PlantModel) -> None:
    folder = model_folder(model.id)
    db.delete(model)
    db.commit()
    shutil.rmtree(folder, ignore_errors=True)


def is_running(model_id: int) -> bool:
    return model_id in _active


def start(model_id: int) -> None:
    """Make the model in the background."""
    _active.add(model_id)
    run_in_background(run_job(model_id), name=f"plant-model-{model_id}")


async def run_job(model_id: int) -> None:
    _active.add(model_id)
    try:
        async with _lock:
            await _make(model_id)
    finally:
        _active.discard(model_id)


def _update(model_id: int, **fields) -> PlantModel | None:
    with SessionLocal() as db:
        model = db.get(PlantModel, model_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        db.commit()
        db.refresh(model)
        db.expunge(model)
        return model


async def _make(model_id: int) -> None:
    provider = get_provider()
    model = _update(model_id, status="generating", error=None, provider=provider.name)
    if model is None:
        return  # deleted while waiting its turn
    folder = model_folder(model_id)
    folder.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        if provider.problem():
            raise PlantModelError(provider.problem())
        if model.image_path:
            image = models_root() / model.image_path
        else:
            image = await image_from_description(model.description or model.name, folder / "source.jpg")
            _update(model_id, image_path=f"{model_id}/source.jpg")
        with tempfile.TemporaryDirectory(prefix=f"plant-{model_id}-") as tmp:
            raw = await provider.reconstruct(image, Path(tmp))
            up = (settings.plant_model_up_axis or provider.up_axis).strip().lower()
            name = f"model-{uuid.uuid4().hex[:8]}.glb"
            info = await asyncio.to_thread(normalize_glb, raw, folder / name, up)
        old = model.model_path
        if _update(model_id, status="ready", model_path=f"{model_id}/{name}", **info) is None:
            shutil.rmtree(folder, ignore_errors=True)
            return
        if old and old != f"{model_id}/{name}":
            (models_root() / old).unlink(missing_ok=True)
        logger.info(
            f"🌳 Plant model {model_id} '{model.name}' ready from {provider.name} in "
            f"{time.monotonic() - started:.0f}s ({info['triangles']} triangles)"
        )
    except Exception as e:
        message = str(e) if isinstance(e, PlantModelError) else f"{type(e).__name__}: {e}"
        logger.error(f"❌ Plant model {model_id} failed: {message}", exc_info=not isinstance(e, PlantModelError))
        _update(model_id, status="failed", error=message[:500])

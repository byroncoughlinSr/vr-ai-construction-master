"""The library of 3D plant models made from photos (plant_model_service.py).

A plant added here ("Coral rose" + a photo) gets a model in the background; any
house whose landscaping names it is then drawn with that model.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import PlantModel
from ...services import plant_model_service
from ...services.plant_model_service import PlantModelError

logger = logging.getLogger(__name__)
router = APIRouter()


def _get(db: Session, model_id: int) -> PlantModel:
    model = db.get(PlantModel, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="No such plant model")
    return model


def _require_provider():
    status = plant_model_service.provider_status()
    if not status["provider_ready"]:
        raise HTTPException(status_code=503, detail=status["provider_problem"])


@router.get("/models")
def list_plant_models(db: Session = Depends(get_db)):
    """Every plant in the library, and whether models can be made right now."""
    models = plant_model_service.list_models(db)
    return {"models": [plant_model_service.serialize(m) for m in models], **plant_model_service.provider_status()}


@router.post("/models", status_code=202)
async def create_plant_model(
    name: str = Form(..., description="What plans call it, e.g. 'Coral rose'"),
    description: Optional[str] = Form(None, description="Used to draw it when there is no photo"),
    height_ft: Optional[float] = Form(None, description="Its usual height"),
    photo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """Add a plant from a photo (or a description) and start making its 3D model."""
    _require_provider()
    data = await photo.read(plant_model_service.MAX_PHOTO_BYTES + 1) if photo else None
    try:
        model = plant_model_service.create(db, name, photo=data or None, description=description, height_ft=height_ft)
    except PlantModelError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    plant_model_service.start(model.id)
    return JSONResponse(status_code=202, content=plant_model_service.serialize(model))


@router.get("/models/{model_id}")
def get_plant_model(model_id: int, db: Session = Depends(get_db)):
    plant_model_service.list_models(db)  # marks a job cut off by a restart
    return plant_model_service.serialize(_get(db, model_id))


@router.post("/models/{model_id}/retry", status_code=202)
def retry_plant_model(model_id: int, db: Session = Depends(get_db)):
    """Make the model again (after a failure, or for a better one)."""
    model = _get(db, model_id)
    if plant_model_service.is_running(model.id):
        raise HTTPException(status_code=409, detail="This model is already being made")
    _require_provider()
    model.status, model.error = "pending", None
    db.commit()
    plant_model_service.start(model.id)
    return JSONResponse(status_code=202, content=plant_model_service.serialize(model))


@router.delete("/models/{model_id}")
def delete_plant_model(model_id: int, db: Session = Depends(get_db)):
    """Remove a plant; houses that named it go back to the drawn plant."""
    plant_model_service.delete(db, _get(db, model_id))
    return {"deleted": model_id}
